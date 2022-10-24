from dagster import schedule

from jobs.implnet_jobs_cchdo import implnet_job_cchdo

@schedule(cron_schedule="0 8 * * 0", job=implnet_job_cchdo, execution_timezone="US/Central")
def implnet_sch_cchdo(_context):
    run_config = {}
    return run_config
