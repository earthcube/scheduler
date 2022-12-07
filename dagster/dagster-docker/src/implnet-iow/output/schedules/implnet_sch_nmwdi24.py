from dagster import schedule

from jobs.implnet_jobs_nmwdi24 import implnet_job_nmwdi24

@schedule(cron_schedule="0 0 * * 0", job=implnet_job_nmwdi24, execution_timezone="US/Central")
def implnet_sch_nmwdi24(_context):
    run_config = {}
    return run_config