import os

from dagster import (
    schedule, RunRequest, DefaultScheduleStatus, get_dagster_logger,
)

from .assets import sources_partitions_def
from .jobs import pipeline_source_job

PROJECT = os.environ.get('PROJECT')
sched = os.environ.get("GLEANERIO_DEFAULT_SCHEDULE", "@weekly")
sched_timezone = os.environ.get("GLEANERIO_DEFAULT_SCHEDULE_TIMEZONE", "America/Los_Angeles")


@schedule(job=pipeline_source_job, cron_schedule=sched,
          execution_timezone=sched_timezone,
          default_status=DefaultScheduleStatus.RUNNING)
def pipeline_schedule(context):
    """Weekly fan-out: one pipeline run per active source partition."""
    partition_keys = sources_partitions_def.get_partition_keys(
        dynamic_partitions_store=context.instance)
    get_dagster_logger().info(str(partition_keys))
    return [
        RunRequest(
            partition_key=partition_key,
            run_key=f"{PROJECT}_pipeline_{partition_key}",
        )
        for partition_key in partition_keys
    ]
