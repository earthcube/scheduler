from dagster import schedule

from gleaner.jobs.implnet_jobs_invemarvessel import implnet_job_invemarvessel

@schedule(cron_schedule="0 16 * * *", job=implnet_job_invemarvessel, execution_timezone="US/Central")
def implnet_sch_invemarvessel(_context):
    run_config = {}
    return run_config