# Release phase: enhanced JSON-LD -> N-Quads named graphs + per-source
# DataCatalog (shared conversion logic from pipeline.rdf_utils).
import os
from typing import Any

import orjson
from dagster import asset, AssetKey, AssetIn, Output, get_dagster_logger
from pipeline.rdf_utils import graph_uri, to_nquads, datacatalog_doc

from .sources import sources_partitions_def, PREFIX
from .summon_assets import get_source
from .enhance import enhanced_jsonld
from ..paths import ENHANCED_PATH, RELEASE_PATH

PROJECT = os.environ.get('PROJECT')


@asset(group_name="release", key_prefix=PREFIX,
       op_tags={"ingest": "report"},
       partitions_def=sources_partitions_def,
       required_resource_keys={"gs3"})
def source_datacatalog(context) -> Output[Any]:
    source_name = context.asset_partition_key_for_output()
    source, _ = get_source(context, source_name)
    doc = datacatalog_doc(source)
    return Output(doc, metadata={"source": source_name, "catalog_id": doc["@id"]})


@asset(group_name="release", key_prefix=PREFIX,
       op_tags={"ingest": "report"},
       deps=[enhanced_jsonld],
       ins={"source_datacatalog": AssetIn(AssetKey([PREFIX, "source_datacatalog"]))},
       partitions_def=sources_partitions_def,
       required_resource_keys={"gs3"})
def release_nquads(context, source_datacatalog) -> Output[Any]:
    gs3 = context.resources.gs3
    source = context.asset_partition_key_for_output()

    objects = gs3.listPath(path=f"{ENHANCED_PATH}/{source}/")
    client = gs3.s3.get_client()

    parts = []
    converted = 0
    errors = 0
    quad_count = 0
    for obj in objects:
        key = obj["Key"]
        sha = key.rsplit("/", 1)[-1].removesuffix(".jsonld")
        try:
            result = client.get_object(Bucket=gs3.GLEANERIO_MINIO_BUCKET, Key=key)
            doc = orjson.loads(result["Body"].read())
            nq = to_nquads(doc, graph_uri(source, sha))
        except Exception as e:
            get_dagster_logger().warning(f"conversion failed for {key}: {e}")
            errors += 1
            continue
        if nq:
            parts.append(nq)
            quad_count += nq.count("\n")
            converted += 1

    try:
        catalog_nq = to_nquads(source_datacatalog, graph_uri(source, "datacatalog"))
        parts.append(catalog_nq)
        quad_count += catalog_nq.count("\n")
    except Exception as e:
        get_dagster_logger().warning(f"DataCatalog conversion failed for {source}: {e}")

    if objects and converted == 0:
        raise Exception(f"release: all {len(objects)} documents for {source} failed")

    release_key = f"{RELEASE_PATH}/{source}_release.nq"
    gs3.putFile(release_key, "".join(parts), content_type="application/n-quads")
    return Output(release_key, metadata={
        "source": source,
        "release": release_key,
        "documents_converted": converted,
        "errors": errors,
        "quad_count": quad_count,
    })
