# Enhance phase: shared step machinery from the pipeline package, run over
# pysummon's summoned prefix. Default chain here includes the identifier
# promotion and keyword splitting steps; pipelineconfig.yaml overrides win.
import os
from typing import Any

import orjson
from dagster import asset, AssetKey, AssetIn, Output, get_dagster_logger
from pipeline.steps import source_settings, resolve_steps, apply_steps

from .sources import sources_partitions_def, PREFIX
from .summon_assets import summon_source
from ..paths import SUMMONED_PATH, ENHANCED_PATH

PROJECT = os.environ.get('PROJECT')

PYSUMMON_DEFAULT_STEPS = ["fix_context", "promote_identifiers", "split_keywords", "skolemize"]


def pysummon_settings(config, source):
    """source_settings with pysummon's richer default chain when neither the
    defaults nor the source override specify steps."""
    settings = source_settings(config, source)
    defaults_steps = ((config or {}).get("defaults") or {}).get("steps")
    source_steps = (((config or {}).get("sources") or {}).get(source) or {}).get("steps")
    if defaults_steps is None and source_steps is None:
        settings["steps"] = PYSUMMON_DEFAULT_STEPS
    return settings


@asset(group_name="enhance", key_prefix=PREFIX,
       op_tags={"ingest": "report"},
       deps=[summon_source],
       ins={"pipeline_step_config": AssetIn(AssetKey([PREFIX, "pipeline_step_config"]))},
       partitions_def=sources_partitions_def,
       required_resource_keys={"gs3"})
def enhanced_jsonld(context, pipeline_step_config) -> Output[Any]:
    """Corrected + identified JSON-LD: promote known IDs (ORCID/ROR/DOI...),
    split packed keywords, skolemize remaining blank nodes."""
    gs3 = context.resources.gs3
    source = context.asset_partition_key_for_output()

    settings = pysummon_settings(pipeline_step_config, source)
    steps = resolve_steps(settings, source)
    context.log.info(f"source {source}: steps {[n for n, _ in steps]}")

    objects = gs3.listPath(path=f"{SUMMONED_PATH}/{source}/")
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
            doc = orjson.loads(result["Body"].read())
            doc, meta = apply_steps(doc, source, steps)
        except Exception as e:
            get_dagster_logger().warning(f"enhancement failed for {key}: {e}")
            errors += 1
            continue
        for k, v in meta.items():
            if isinstance(v, int):
                total_meta[k] = total_meta.get(k, 0) + v

        provenance = {"summoned-key": key,
                      "steps": ",".join(n for n, _ in steps) or "none"}
        if source_meta.get("url"):
            provenance["harvested-from"] = source_meta["url"]
        gs3.putFile(f"{ENHANCED_PATH}/{source}/{sha}.jsonld", orjson.dumps(doc),
                    content_type="application/ld+json", metadata=provenance)
        processed += 1

    if objects and processed == 0:
        raise Exception(f"enhance: all {len(objects)} documents for {source} failed")

    return Output(f"{ENHANCED_PATH}/{source}/", metadata={
        "source": source,
        "steps": str([n for n, _ in steps]),
        "documents": processed,
        "errors": errors,
        **total_meta,
    })
