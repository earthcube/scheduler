from dagster import schedule

from jobs.implnet_jobs_refgage0 import implnet_job_refgage0

@schedule(cron_schedule="0 9 * * 2", job=implnet_job_refgage0, execution_timezone="US/Central")
def implnet_sch_refgage0(_context):
    run_config = {}
    return run_config
