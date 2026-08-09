import os

from dagster import (
    DagsterRunStatus,
    DefaultScheduleStatus,
    RunRequest,
    RunsFilter,
    ScheduleEvaluationContext,
    job,
    op,
    schedule,
)
from ..long_running_run_alerts import (
    LONG_RUNNING_RUN_ALERT_AGE,
    LONG_RUNNING_RUN_ALERT_JOB_NAME,
    LONG_RUNNING_RUN_ALERT_SCHEDULE,
    LONG_RUNNING_RUN_ALERT_TIMEZONE,
    build_long_running_runs_message,
    get_long_running_runs,
    get_webserver_base_url,
    utc_now,
)


@op(required_resource_keys={"slack"})
def notify_on_long_running_runs(context):
    slack_channel = os.getenv("SLACK_CHANNEL")
    if not slack_channel:
        context.log.warning(
            "Skipping long-running run Slack alert because SLACK_CHANNEL is not configured."
        )
        return

    current_time = utc_now()
    run_records = context.instance.get_run_records(
        filters=RunsFilter(
            statuses=[
                DagsterRunStatus.STARTING,
                DagsterRunStatus.STARTED,
                DagsterRunStatus.CANCELING,
            ],
            created_before=current_time - LONG_RUNNING_RUN_ALERT_AGE,
        )
    )
    long_running_runs = get_long_running_runs(run_records, now=current_time)

    if not long_running_runs:
        context.log.info("No Dagster runs older than 24 hours are still in progress.")
        return

    context.resources.slack.get_client().chat_postMessage(
        channel=slack_channel,
        text=build_long_running_runs_message(
            long_running_runs,
            webserver_base_url=get_webserver_base_url(),
            now=current_time,
        ),
    )
    context.log.info(
        f"Sent long-running run Slack alert for {len(long_running_runs)} run(s)."
    )


@job(name=LONG_RUNNING_RUN_ALERT_JOB_NAME)
def long_running_runs_alert_job():
    notify_on_long_running_runs()


@schedule(
    job=long_running_runs_alert_job,
    cron_schedule=LONG_RUNNING_RUN_ALERT_SCHEDULE,
    execution_timezone=LONG_RUNNING_RUN_ALERT_TIMEZONE,
    default_status=DefaultScheduleStatus.RUNNING,
)
def long_running_runs_alert_schedule(context: ScheduleEvaluationContext):
    run_key = None
    if context.scheduled_execution_time:
        run_key = (
            "long-running-runs-alert-"
            f"{context.scheduled_execution_time.date().isoformat()}"
        )
    return RunRequest(run_key=run_key)
