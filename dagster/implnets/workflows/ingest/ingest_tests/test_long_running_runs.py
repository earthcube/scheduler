from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from types import SimpleNamespace

MODULE_DIR = Path(__file__).resolve().parents[1] / "ingest"
sys.path.insert(0, str(MODULE_DIR))
import long_running_run_alerts

LONG_RUNNING_RUN_ALERT_JOB_NAME = long_running_run_alerts.LONG_RUNNING_RUN_ALERT_JOB_NAME
build_long_running_runs_message = long_running_run_alerts.build_long_running_runs_message
get_long_running_runs = long_running_run_alerts.get_long_running_runs
get_run_start_time = long_running_run_alerts.get_run_start_time


def _run_record(
    *,
    run_id="run-1",
    job_name="summon_asset_job",
    status="STARTED",
    started_at=None,
    created_at=None,
    tags=None,
):
    created_at = created_at or datetime(2026, 1, 1, tzinfo=timezone.utc)
    start_time = started_at.timestamp() if started_at is not None else None
    return SimpleNamespace(
        start_time=start_time,
        create_timestamp=created_at,
        dagster_run=SimpleNamespace(
            run_id=run_id,
            job_name=job_name,
            status=SimpleNamespace(value=status),
            tags=tags or {},
        ),
    )


def test_get_run_start_time_falls_back_to_create_timestamp():
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    run_record = _run_record(started_at=None, created_at=created_at)

    assert get_run_start_time(run_record) == created_at


def test_get_long_running_runs_filters_and_sorts_runs():
    now = datetime(2026, 1, 3, 12, 0, tzinfo=timezone.utc)
    oldest = _run_record(
        run_id="run-oldest",
        started_at=now - timedelta(days=3),
    )
    long_running = _run_record(
        run_id="run-long",
        started_at=now - timedelta(hours=30),
        tags={"dagster/partition": "source-a"},
    )
    too_new = _run_record(
        run_id="run-new",
        started_at=now - timedelta(hours=12),
    )
    completed = _run_record(
        run_id="run-success",
        status="SUCCESS",
        started_at=now - timedelta(days=2),
    )
    alert_job = _run_record(
        run_id="run-alert",
        job_name=LONG_RUNNING_RUN_ALERT_JOB_NAME,
        started_at=now - timedelta(days=2),
    )

    run_ids = [
        run.dagster_run.run_id
        for run in get_long_running_runs(
            [too_new, completed, oldest, alert_job, long_running],
            now=now,
        )
    ]

    assert run_ids == ["run-oldest", "run-long"]


def test_build_long_running_runs_message_includes_links_and_partition():
    now = datetime(2026, 1, 3, 12, 0, tzinfo=timezone.utc)
    run_record = _run_record(
        run_id="abc123",
        started_at=now - timedelta(hours=49),
        tags={"dagster/partition": "source-a"},
    )

    message = build_long_running_runs_message(
        [run_record],
        webserver_base_url="https://scheduler.example.org",
        now=now,
    )

    assert "1 Dagster run(s) have been running for more than 24 hours" in message
    assert "`summon_asset_job` (source-a) has been running for 2d 1h" in message
    assert "<https://scheduler.example.org/runs/abc123|abc123>" in message
