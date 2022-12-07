from dagster import schedule

from jobs.implnet_jobs_cuahsi113 import implnet_job_cuahsi113

@schedule(cron_schedule="0 20 * * 0", job=implnet_job_cuahsi113, execution_timezone="US/Central")
def implnet_sch_cuahsi113(_context):
    run_config = {}
    return run_config