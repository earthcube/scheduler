from dagster import schedule

from jobs.implnet_jobs_usgs77 import implnet_job_usgs77

@schedule(cron_schedule="0 7 * * 0", job=implnet_job_usgs77, execution_timezone="US/Central")
def implnet_sch_usgs77(_context):
    run_config = {}
    return run_config
