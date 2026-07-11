import os

from dagster import (
    sensor, asset_sensor, multi_asset_sensor, SensorResult, RunRequest,
    EventLogEntry, AssetKey, MultiAssetSensorEvaluationContext,
    DefaultSensorStatus, SkipReason,
)
from pipeline.steps import PIPELINE_CONFIG_FILENAME

from .assets import sources_partitions_def, PREFIX
from .jobs import pysummon_source_job, pysummon_config_job, pysummon_publish_job

PROJECT = os.environ.get('PROJECT')


@asset_sensor(default_status=DefaultSensorStatus.RUNNING,
              asset_key=AssetKey([PREFIX, "sources_names_active"]),
              job=pysummon_source_job,
              name="pysummon_sources_sensor")
def pysummon_sources_sensor(context, asset_event: EventLogEntry):
    """Sync pysummon's dynamic partitions with the active source list."""
    assert asset_event.dagster_event and asset_event.dagster_event.asset_key
    sources = context.repository_def.load_asset_value(
        AssetKey([PREFIX, "sources_names_active"]))
    new_sources = [
        s for s in sources
        if not sources_partitions_def.has_partition_key(
            s, dynamic_partitions_store=context.instance)
    ]
    removed = [
        s for s in sources_partitions_def.get_partition_keys(
            dynamic_partitions_store=context.instance)
        if s not in sources
    ]
    for s in removed:
        context.instance.delete_dynamic_partition(sources_partitions_def.name, s)
    context.log.info(f"new sources {new_sources}; removed {removed}")
    return SensorResult(
        run_requests=[RunRequest(partition_key=s, run_key=f"{s}_pysummon")
                      for s in new_sources],
        dynamic_partitions_requests=[sources_partitions_def.build_add_request(new_sources)],
    )


@sensor(job=pysummon_config_job, default_status=DefaultSensorStatus.RUNNING,
        minimum_interval_seconds=300, required_resource_keys={"gs3"},
        name="pysummon_config_files_sensor")
def pysummon_config_files_sensor(context):
    """Re-materialize config assets when the shared S3 config files change."""
    gs3 = context.resources.gs3
    client = gs3.s3.get_client()
    etags = []
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
    job=pysummon_publish_job,
    default_status=DefaultSensorStatus.RUNNING,
    minimum_interval_seconds=600,
    name="pysummon_publish_sensor",
)
def pysummon_publish_sensor(context: MultiAssetSensorEvaluationContext):
    """Regenerate community load files after release files land (debounced:
    one publish run per window, not one per source)."""
    records = context.latest_materialization_records_by_key()
    if any(records.values()):
        context.advance_all_cursors()
        return SensorResult(run_requests=[RunRequest(run_key=None)])
    return SkipReason("no new release files")
