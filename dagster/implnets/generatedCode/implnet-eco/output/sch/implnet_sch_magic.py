from dagster import schedule

from jobs.implnet_jobs_magic import implnet_job_magic

@schedule(cron_schedule="0 23 4 * *", job=implnet_job_magic, execution_timezone="US/Central")
def implnet_sch_magic(_context):
    run_config = {}
    return run_config
