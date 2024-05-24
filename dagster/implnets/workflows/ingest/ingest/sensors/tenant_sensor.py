from dagster import (
op, job, Config,
sensor, RunRequest, RunConfig,SensorResult,
SensorEvaluationContext,asset_sensor, EventLogEntry,
SkipReason,
AssetKey,
static_partitioned_config,DynamicPartitionsDefinition
)
from ..jobs.tennant_load import tenant_create_job
from ..assets import tenant_partitions_def
#from ..assets.tenant import build_community

## Thinking. Doing this the wrong way.
##   for each source, we dynamically generate a set of tenants to load, rather than for each tenant we reload
##  So, at the end of a source load, we trigger a load tenants.
##   this figures out what tenants to load, and call those ops.

## So the asset key is not tenant names, it is still source_names_active.

# now we do need to build tenants when a new tenant is added.
# this should just handle the cretion of namespaces, and adding the UI's

@asset_sensor( asset_key=AssetKey("tenant_names"), job=tenant_create_job
   # , minimum_interval_seconds=600
               )
def tenant_names_sensor(context,  asset_event: EventLogEntry):
    assert asset_event.dagster_event and asset_event.dagster_event.asset_key

# well this is a pain. but it works. Cannot just pass it like you do in ops
    # otherwise it's just an AssetDefinition.
    tenants = context.repository_def.load_asset_value(AssetKey("tenant_names"))
    new_tenants = [
        tenant
        for tenant in tenants
        if not tenant_partitions_def.has_partition_key(
            tenant, dynamic_partitions_store=context.instance
        )
    ]

    return SensorResult(
        run_requests=[
            RunRequest(partition_key=tenant
                   #    , job_name=f"{source}_load"
            , run_key=f"{tenant}_tenant"
                       ) for tenant in new_tenants
        ],
        dynamic_partitions_requests=[
            tenant_partitions_def.build_add_request(new_tenants)
        ],
    )
