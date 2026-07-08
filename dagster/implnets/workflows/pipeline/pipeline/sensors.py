import os

from dagster import (
    sensor, asset_sensor, multi_asset_sensor, SensorResult, RunRequest,
    EventLogEntry, AssetKey, MultiAssetSensorEvaluationContext,
    DefaultSensorStatus, SkipReason,
)

from .assets import sources_partitions_def, PREFIX
from .jobs import pipeline_source_job, sources_config_job, qlever_rebuild_job

PROJECT = os.environ.get('PROJECT')


@asset_sensor(default_status=DefaultSensorStatus.RUNNING,
              asset_key=AssetKey([PREFIX, "sources_names_active"]),
              job=pipeline_source_job)
def pipeline_sources_sensor(context, asset_event: EventLogEntry):
    """Sync dynamic partitions with the active source list; kick a pipeline
    run for newly added sources."""
    assert asset_event.dagster_event and asset_event.dagster_event.asset_key
    sources = context.repository_def.load_asset_value(
        AssetKey([PREFIX, "sources_names_active"]))
    new_sources = [
        source for source in sources
        if not sources_partitions_def.has_partition_key(
            source, dynamic_partitions_store=context.instance)
    ]
    removed_sources = [
        source for source in sources_partitions_def.get_partition_keys(
            dynamic_partitions_store=context.instance)
        if source not in sources
    ]
    for s in removed_sources:
        context.instance.delete_dynamic_partition(sources_partitions_def.name, s)
    context.log.info(f"new sources {new_sources}; removed {removed_sources}")
    return SensorResult(
        run_requests=[
            RunRequest(partition_key=source, run_key=f"{source}_pipeline")
            for source in new_sources
        ],
        dynamic_partitions_requests=[
            sources_partitions_def.build_add_request(new_sources)
        ],
    )


@sensor(job=sources_config_job, default_status=DefaultSensorStatus.RUNNING,
        minimum_interval_seconds=300, required_resource_keys={"gs3"})
def config_files_sensor(context):
    """Re-materialize the config assets when gleanerconfig.yaml, tenant.yaml,
    or pipelineconfig.yaml change in S3 (ETag comparison)."""
    gs3 = context.resources.gs3
    client = gs3.s3.get_client()
    etags = []
    from .steps import PIPELINE_CONFIG_FILENAME
    for filename in (gs3.GLEANERIO_SOURCES_FILENAME, gs3.GLEANERIO_TENANT_FILENAME,
                     PIPELINE_CONFIG_FILENAME):
        try:
            head = client.head_object(
                Bucket=gs3.GLEANERIO_MINIO_BUCKET,
                Key=f"{gs3.GLEANERIO_CONFIG_PATH}{filename}")
            etags.append(f"{filename}:{head['ETag']}")
        except Exception:
            etags.append(f"{filename}:absent")
    cursor = ";".join(etags)
    if context.cursor == cursor:
        return SkipReason("config files unchanged")
    context.update_cursor(cursor)
    return RunRequest(run_key=cursor)


@multi_asset_sensor(
    monitored_assets=[AssetKey([PREFIX, "release_nquads"])],
    job=qlever_rebuild_job,
    default_status=DefaultSensorStatus.RUNNING,
    minimum_interval_seconds=600,
)
def qlever_rebuild_sensor(context: MultiAssetSensorEvaluationContext):
    """Kick one Qlever index rebuild after release files land.

    Debounced by minimum_interval_seconds: a weekly fan-out that finishes
    many sources in one window triggers a single rebuild, not one per source.
    """
    records = context.latest_materialization_records_by_key()
    if any(records.values()):
        context.advance_all_cursors()
        return SensorResult(run_requests=[RunRequest(run_key=None)])
    return SkipReason("no new release files")
