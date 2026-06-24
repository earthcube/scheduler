from typing import Any
import os

from dagster import (
    asset,
    Output,
    AssetKey,
    AssetDep,
    AllPartitionMapping,
    get_dagster_logger,
)

PROJECT = os.environ.get('PROJECT')


@asset(
    group_name="load",
    key_prefix=f"{PROJECT}_ingest",
    op_tags={"tenant_load": "graph"},
    deps=[
        AssetDep(
            AssetKey([f"{PROJECT}_ingest", "release_nabu_run"]),
            partition_mapping=AllPartitionMapping(),
        )
    ],
    required_resource_keys={"qlever"},
)
def qlever_index_rebuild(context) -> Output[Any]:
    """Rebuild the Qlever triplestore index from S3 release files.

    Restarts the Qlever container, which runs:
      qlever get-data  -- downloads *_release.nq from S3 (per Qleverfile GET_DATA_CMD)
      qlever index     -- builds binary index from downloaded N-Quads
      qlever start     -- starts the SPARQL server on the new index

    This asset is unpartitioned and depends on all partitions of release_nabu_run,
    so it shows as stale in the Dagster UI whenever any source is re-crawled.
    It can also be triggered manually after a partial re-crawl of one source.

    Note on Nabu release step: the release_nabu_run asset calls Nabu with the
    'release' command, which writes graphs/latest/{source}_release.nq to S3 AND
    attempts a SPARQL Update to the configured SPARQL endpoint. For Qlever
    deployments, configure Nabu without a SPARQL endpoint (or point SPARQL_ENDPOINT
    at a no-op URL) so the S3 write succeeds and the SPARQL upload is skipped.
    """
    qlever = context.resources.qlever

    elapsed = qlever.restart_and_rebuild(context)

    triple_count = -1
    try:
        triple_count = qlever.triple_count()
        context.log.info(f"Qlever index contains {triple_count:,} triples")
    except Exception as e:
        context.log.warning(f"Could not retrieve triple count after rebuild: {e}")

    return Output(
        True,
        metadata={
            "rebuild_time_seconds": int(elapsed),
            "triple_count": triple_count,
        },
    )
