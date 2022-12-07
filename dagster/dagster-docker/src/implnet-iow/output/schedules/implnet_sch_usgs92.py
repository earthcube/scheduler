from dagster import schedule

from jobs.implnet_jobs_usgs92 import implnet_job_usgs92

@schedule(cron_schedule="0 22 * * 0", job=implnet_job_usgs92, execution_timezone="US/Central")
def implnet_sch_usgs92(_context):
    run_config = {}
    return run_config