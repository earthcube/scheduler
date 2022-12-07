from dagster import schedule

from jobs.implnet_jobs_cuahsi181 import implnet_job_cuahsi181

@schedule(cron_schedule="0 19 * * 0", job=implnet_job_cuahsi181, execution_timezone="US/Central")
def implnet_sch_cuahsi181(_context):
    run_config = {}
    return run_config