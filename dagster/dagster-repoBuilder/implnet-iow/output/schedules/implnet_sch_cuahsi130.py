from dagster import schedule

from jobs.implnet_jobs_cuahsi130 import implnet_job_cuahsi130

@schedule(cron_schedule="0 14 * * 0", job=implnet_job_cuahsi130, execution_timezone="US/Central")
def implnet_sch_cuahsi130(_context):
    run_config = {}
    return run_config
