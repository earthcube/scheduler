# Per-source community reports over pysummon's enhanced prefix (shared
# aggregation logic from pipeline.reporting).
import json
import os
from typing import Any

import orjson
from dagster import asset, AssetKey, AssetIn, Output, get_dagster_logger
from pipeline.reporting import aggregate, counter_to_csv
from pipeline.steps import source_settings

from .sources import sources_partitions_def, PREFIX
from .enhance import enhanced_jsonld
from ..paths import ENHANCED_PATH, REPORTS_PATH

PROJECT = os.environ.get('PROJECT')


@asset(group_name="reports", key_prefix=PREFIX,
       op_tags={"ingest": "report"},
       deps=[enhanced_jsonld],
       ins={"pipeline_step_config": AssetIn(AssetKey([PREFIX, "pipeline_step_config"]))},
       partitions_def=sources_partitions_def,
       required_resource_keys={"gs3"})
def source_report(context, pipeline_step_config) -> Output[Any]:
    gs3 = context.resources.gs3
    source = context.asset_partition_key_for_output()

    if not source_settings(pipeline_step_config, source).get("reports", True):
        context.log.info(f"reports disabled for {source}")
        return Output(None, metadata={"source": source, "skipped": True})

    objects = gs3.listPath(path=f"{ENHANCED_PATH}/{source}/")
    client = gs3.s3.get_client()

    def doc_stream():
        for obj in objects:
            try:
                result = client.get_object(Bucket=gs3.GLEANERIO_MINIO_BUCKET, Key=obj["Key"])
                yield orjson.loads(result["Body"].read())
            except Exception as e:
                get_dagster_logger().warning(f"skipping unreadable {obj['Key']}: {e}")

    stats = aggregate(doc_stream())

    def put(filename, text, content_type="text/csv"):
        gs3.putTextFile(f"{REPORTS_PATH}/{source}/{filename}", text,
                        content_type=content_type)

    put("keyword_counts.csv", counter_to_csv(stats["keywords"], ["keyword", "count"]))
    put("author_names.csv", counter_to_csv(stats["authors"], ["author", "count"]))
    put("places.csv", counter_to_csv(stats["places"], ["place", "count"]))
    put("publisher_counts.csv", counter_to_csv(stats["publishers"], ["publisher", "count"]))

    summary = {
        "source": source,
        "documents": stats["documents"],
        "datasets": stats["datasets"],
        "unique_keywords": len(stats["keywords"]),
        "unique_authors": len(stats["authors"]),
        "unique_places": len(stats["places"]),
        "unique_publishers": len(stats["publishers"]),
        "type_counts": dict(stats["types"].most_common()),
    }
    put("summary.json", json.dumps(summary, indent=2), content_type="application/json")
    return Output(f"{REPORTS_PATH}/{source}/", metadata=summary)
