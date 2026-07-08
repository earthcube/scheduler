# Phase 2 — correct and enhance harvested JSON-LD.
#
# Reads  summoned/{source}/  (raw Gleaner output)
# Writes enhanced/{source}/{sha}.jsonld
#
# Which steps run is configured PER SOURCE in pipelineconfig.yaml (see
# pipeline/steps.py). A source configured with steps: [] is copied through
# unmodified — downstream phases always read enhanced/, never summoned/.
import os
from typing import Any

import orjson
from dagster import asset, AssetKey, AssetIn, Output, get_dagster_logger

from .sources import sources_partitions_def, PREFIX
from .phase1_harvest import harvest_source, SUMMONED_PATH
from ..steps import source_settings, resolve_steps, apply_steps

PROJECT = os.environ.get('PROJECT')

ENHANCED_PATH = "enhanced"


@asset(group_name="phase2_enhance", key_prefix=PREFIX,
       op_tags={"ingest": "report"},
       deps=[harvest_source],
       ins={"pipeline_step_config": AssetIn(AssetKey([PREFIX, "pipeline_step_config"]))},
       partitions_def=sources_partitions_def,
       required_resource_keys={"gs3"})
def enhanced_jsonld(context, pipeline_step_config) -> Output[Any]:
    """Corrected + skolemized JSON-LD for one source.

    Per document:
      1. parse the summoned JSON-LD
      2. run the source's configured steps (default: fix_context, skolemize)
      3. write to enhanced/{source}/{sha}.jsonld with provenance in the
         object's S3 user metadata

    Documents that fail to parse are skipped and counted; the asset fails only
    when every document is unreadable (a systematically broken source).
    """
    gs3 = context.resources.gs3
    source = context.asset_partition_key_for_output()

    settings = source_settings(pipeline_step_config, source)
    steps = resolve_steps(settings, source)
    context.log.info(f"source {source}: steps {[n for n, _ in steps]}")

    prefix = f"{SUMMONED_PATH}/{source}/"
    objects = gs3.listPath(path=prefix)
    client = gs3.s3.get_client()

    processed = 0
    errors = 0
    total_meta = {}
    for obj in objects:
        key = obj["Key"]
        sha = key.rsplit("/", 1)[-1].removesuffix(".jsonld")
        try:
            result = client.get_object(Bucket=gs3.GLEANERIO_MINIO_BUCKET, Key=key)
            source_meta = result.get("Metadata", {}) or {}
            raw = result["Body"].read()
            doc = orjson.loads(raw)
        except Exception as e:
            get_dagster_logger().warning(f"skipping unreadable object {key}: {e}")
            errors += 1
            continue

        try:
            doc, meta = apply_steps(doc, source, steps)
        except Exception as e:
            get_dagster_logger().warning(f"enhancement failed for {key}: {e}")
            errors += 1
            continue
        for k, v in meta.items():
            if isinstance(v, int):
                total_meta[k] = total_meta.get(k, 0) + v

        out_key = f"{ENHANCED_PATH}/{source}/{sha}.jsonld"
        provenance = {
            "summoned-key": key,
            "steps": ",".join(n for n, _ in steps) or "none",
        }
        if source_meta.get("url"):
            provenance["harvested-from"] = source_meta["url"]
        gs3.putFile(out_key, orjson.dumps(doc),
                    content_type="application/ld+json", metadata=provenance)
        processed += 1

    if objects and processed == 0:
        raise Exception(
            f"phase2: all {len(objects)} documents for {source} failed to process")

    return Output(f"{ENHANCED_PATH}/{source}/", metadata={
        "source": source,
        "steps": str([n for n, _ in steps]),
        "documents": processed,
        "errors": errors,
        **total_meta,
    })
