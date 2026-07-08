# Phase 2.1 — per-source community reports.
#
# Reads  enhanced/{source}/
# Writes reports/{source}/keyword_counts.csv, author_names.csv, places.csv,
#        publisher_counts.csv, summary.json
#
# Computed straight from the enhanced JSON-LD (no triplestore needed), so
# reports are available right after phase 2 and can inform a community before
# anything is loaded into the graph. Disable per source with reports: false
# in pipelineconfig.yaml.
import json
import os
from typing import Any

import orjson
from dagster import asset, AssetKey, AssetIn, Output, get_dagster_logger

from .sources import sources_partitions_def, PREFIX
from .phase2_enhance import enhanced_jsonld, ENHANCED_PATH
from ..reporting import aggregate, counter_to_csv
from ..steps import source_settings

PROJECT = os.environ.get('PROJECT')

REPORTS_PATH = "reports"


@asset(group_name="phase2_reports", key_prefix=PREFIX,
       op_tags={"ingest": "report"},
       deps=[enhanced_jsonld],
       ins={"pipeline_step_config": AssetIn(AssetKey([PREFIX, "pipeline_step_config"]))},
       partitions_def=sources_partitions_def,
       required_resource_keys={"gs3"})
def source_report(context, pipeline_step_config) -> Output[Any]:
    """Keyword counts, author names, places, publishers, and dataset counts
    for one source's enhanced documents."""
    gs3 = context.resources.gs3
    source = context.asset_partition_key_for_output()

    settings = source_settings(pipeline_step_config, source)
    if not settings.get("reports", True):
        context.log.info(f"reports disabled for {source} in pipelineconfig.yaml")
        return Output(None, metadata={"source": source, "skipped": True})

    prefix = f"{ENHANCED_PATH}/{source}/"
    objects = gs3.listPath(path=prefix)
    client = gs3.s3.get_client()

    def doc_stream():
        for obj in objects:
            try:
                result = client.get_object(Bucket=gs3.GLEANERIO_MINIO_BUCKET, Key=obj["Key"])
                yield orjson.loads(result["Body"].read())
            except Exception as e:
                get_dagster_logger().warning(f"skipping unreadable {obj['Key']}: {e}")

    stats = aggregate(doc_stream())

    gs3.putReportFile(source, "keyword_counts.csv",
                      counter_to_csv(stats["keywords"], ["keyword", "count"]))
    gs3.putReportFile(source, "author_names.csv",
                      counter_to_csv(stats["authors"], ["author", "count"]))
    gs3.putReportFile(source, "places.csv",
                      counter_to_csv(stats["places"], ["place", "count"]))
    gs3.putReportFile(source, "publisher_counts.csv",
                      counter_to_csv(stats["publishers"], ["publisher", "count"]))

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
    gs3.putReportFile(source, "summary.json", json.dumps(summary, indent=2),
                      content_type="application/json")

    return Output(f"{REPORTS_PATH}/{source}/", metadata=summary)
