# Phase 4 — rebuild the Qlever index from the release files.
# Reuses the QleverResource pattern from the ingest package; depends on ALL
# partitions of release_nquads so it goes stale whenever any source changes.
import os
from typing import Any

from dagster import (
    asset, Output, AssetKey, AssetDep, AllPartitionMapping,
)

from .sources import PREFIX

PROJECT = os.environ.get('PROJECT')


@asset(group_name="phase4_index", key_prefix=PREFIX,
       op_tags={"tenant_load": "graph"},
       deps=[AssetDep(AssetKey([PREFIX, "release_nquads"]),
                      partition_mapping=AllPartitionMapping())],
       required_resource_keys={"qlever"})
def qlever_index_rebuild(context) -> Output[Any]:
    """Rebuild the Qlever triplestore index from S3 release files.

    Restarts the Qlever container, which runs (per its Qleverfile):
      qlever get-data  -- downloads *_release.nq from S3
      qlever index     -- rebuilds the binary index
      qlever start     -- serves SPARQL on the new index

    Trigger manually after a partial re-crawl of one source, or let the
    weekly schedule's final run kick it.
    """
    qlever = context.resources.qlever
    elapsed = qlever.restart_and_rebuild(context)

    triple_count = -1
    try:
        triple_count = qlever.triple_count()
        context.log.info(f"Qlever index contains {triple_count:,} triples")
    except Exception as e:
        context.log.warning(f"Could not retrieve triple count after rebuild: {e}")

    return Output(True, metadata={
        "rebuild_time_seconds": int(elapsed),
        "triple_count": triple_count,
    })
