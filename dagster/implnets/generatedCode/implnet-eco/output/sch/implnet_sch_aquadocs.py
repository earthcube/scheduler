from dagster import schedule

from jobs.implnet_jobs_aquadocs import implnet_job_aquadocs

@schedule(cron_schedule="0 6 1 * *", job=implnet_job_aquadocs, execution_timezone="US/Central")
def implnet_sch_aquadocs(_context):
    run_config = {}
    return run_config
