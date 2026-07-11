import os

from dagster import schedule, RunRequest, DefaultScheduleStatus, get_dagster_logger

from .assets import sources_partitions_def
from .jobs import pysummon_source_job

PROJECT = os.environ.get('PROJECT')
sched = os.environ.get("PYSUMMON_SCHEDULE",
                       os.environ.get("GLEANERIO_DEFAULT_SCHEDULE", "@weekly"))
sched_timezone = os.environ.get("GLEANERIO_DEFAULT_SCHEDULE_TIMEZONE", "America/Los_Angeles")


@schedule(job=pysummon_source_job, cron_schedule=sched,
          execution_timezone=sched_timezone,
          default_status=DefaultScheduleStatus.RUNNING)
def pysummon_schedule(context):
    """Weekly fan-out: one pysummon run per active source partition.

    Runs in parallel with the gleaner pipeline's schedule during the
    comparison window; pause either one from the Dagster UI."""
    partition_keys = sources_partitions_def.get_partition_keys(
        dynamic_partitions_store=context.instance)
    get_dagster_logger().info(str(partition_keys))
    return [
        RunRequest(partition_key=pk, run_key=f"{PROJECT}_pysummon_{pk}")
        for pk in partition_keys
    ]
