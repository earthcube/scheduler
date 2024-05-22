from dagster import (
    SensorResult, RunRequest,
    EventLogEntry, AssetKey, asset_sensor
)
from ..assets import (
 sources_partitions_def
)
from ..jobs.summon_assets import summon_asset_job




@asset_sensor( asset_key=AssetKey("sources_names_active"), job=summon_asset_job
   # , minimum_interval_seconds=600
               )
def sources_sensor(context,  asset_event: EventLogEntry):
    assert asset_event.dagster_event and asset_event.dagster_event.asset_key

# well this is a pain. but it works. Cannot just pass it like you do in ops
    # otherwise it's just an AssetDefinition.
    sources = context.repository_def.load_asset_value(AssetKey("sources_names_active"))
    new_sources = [
        source
        for source in sources
        if not sources_partitions_def.has_partition_key(
            source, dynamic_partitions_store=context.instance
        )
    ]

    return SensorResult(
        run_requests=[
            RunRequest(partition_key=source
                   #    , job_name=f"{source}_load"
            , run_key=f"{source}_load"
                       ) for source in new_sources
        ],
        dynamic_partitions_requests=[
            sources_partitions_def.build_add_request(new_sources)
        ],
    )
