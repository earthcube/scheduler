import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

LONG_RUNNING_RUN_ALERT_AGE = timedelta(hours=24)
LONG_RUNNING_RUN_ALERT_JOB_NAME = "long_running_runs_alert_job"
LONG_RUNNING_RUN_ALERT_SCHEDULE = "0 8 * * *"
LONG_RUNNING_RUN_ALERT_TIMEZONE = "America/Los_Angeles"
IN_PROGRESS_RUN_STATUS_VALUES = {"STARTING", "STARTED", "CANCELING"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_run_start_time(run_record) -> datetime:
    if run_record.start_time is not None:
        return datetime.fromtimestamp(run_record.start_time, tz=timezone.utc)
    return as_utc(run_record.create_timestamp)


def is_long_running_run(
    run_record,
    now: datetime | None = None,
    minimum_runtime: timedelta = LONG_RUNNING_RUN_ALERT_AGE,
) -> bool:
    dagster_run = run_record.dagster_run
    if dagster_run.job_name == LONG_RUNNING_RUN_ALERT_JOB_NAME:
        return False

    run_status = getattr(dagster_run.status, "value", str(dagster_run.status))
    if run_status not in IN_PROGRESS_RUN_STATUS_VALUES:
        return False

    current_time = now or utc_now()
    return current_time - get_run_start_time(run_record) >= minimum_runtime


def get_long_running_runs(
    run_records,
    now: datetime | None = None,
    minimum_runtime: timedelta = LONG_RUNNING_RUN_ALERT_AGE,
):
    current_time = now or utc_now()
    return sorted(
        [
            run_record
            for run_record in run_records
            if is_long_running_run(run_record, now=current_time, minimum_runtime=minimum_runtime)
        ],
        key=get_run_start_time,
    )


def get_webserver_base_url() -> str:
    sched_hostname = os.getenv("SCHED_HOSTNAME")
    host = os.getenv("HOST")
    if not sched_hostname or not host:
        return ""
    return f"https://{sched_hostname}.{host}/"


def get_run_url(webserver_base_url: str, run_id: str) -> str:
    if not webserver_base_url:
        return ""
    base_url = (
        webserver_base_url
        if webserver_base_url.endswith("/")
        else f"{webserver_base_url}/"
    )
    return urljoin(base_url, f"runs/{run_id}")


def format_runtime(elapsed: timedelta) -> str:
    total_hours = int(elapsed.total_seconds() // 3600)
    days, hours = divmod(total_hours, 24)
    if days and hours:
        return f"{days}d {hours}h"
    if days:
        return f"{days}d"
    return f"{hours}h"


def build_long_running_runs_message(
    run_records,
    webserver_base_url: str,
    now: datetime | None = None,
) -> str:
    current_time = now or utc_now()
    lines = [
        ":hourglass_flowing_sand: "
        f"{len(run_records)} Dagster run(s) have been running for more than 24 hours:"
    ]

    for run_record in run_records:
        dagster_run = run_record.dagster_run
        partition_key = dagster_run.tags.get("dagster/partition")
        partition_text = f" ({partition_key})" if partition_key else ""
        run_duration = format_runtime(current_time - get_run_start_time(run_record))
        run_url = get_run_url(webserver_base_url, dagster_run.run_id)
        run_link = f"<{run_url}|{dagster_run.run_id}>" if run_url else dagster_run.run_id
        lines.append(
            f"• `{dagster_run.job_name}`{partition_text} has been running for "
            f"{run_duration}: {run_link}"
        )

    return "\n".join(lines)
