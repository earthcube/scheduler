from dagster import (
    op, job, Config,
    sensor, RunRequest, RunConfig,
    SensorEvaluationContext, asset_sensor, EventLogEntry,
    SkipReason,
    AssetKey,
    static_partitioned_config, dynamic_partitioned_config, DynamicPartitionsDefinition,
    define_asset_job, AssetSelection, graph_asset,
    BackfillPolicy
)
from ..assets import task_tenant_sources, task_sources_config, source_release_counts
import os
PROJECT=os.environ.get('PROJECT')
from dagster_aws.s3.sensor import get_s3_keys
from typing import List, Dict
from pydantic import Field


# The three roots of the community chain, all of which read s3 directly and so
# have no upstream asset whose materialization an eager policy could react to.
# The s3 sensor fires this job, task_tenant_names then goes eager, and
# community_sensor takes it from there into the loadstatsCommunity partitions --
# which now need the sources config and the release counts to be there already.
tenant_asset_job = define_asset_job(
    name=f"{PROJECT}_task_tenant_config_updated_job",
    selection=AssetSelection.assets(task_tenant_sources)
    | AssetSelection.assets(task_sources_config)
    | AssetSelection.assets(source_release_counts),
)
