from types import SimpleNamespace
from unittest import mock

import pytest
from dagster_k8s.pipes import build_pod_body

from workflows.ingest.ingest.resources import gleanerio_k8s
from workflows.ingest.ingest.resources.gleanerio import GleanerioResource
from workflows.ingest.ingest.resources.gleanerio_k8s import (
    LAUNCH_ID_LABEL,
    MAIN_CONTAINER,
    SIDECAR_CONTAINER,
    PodLaunch,
    build_pod,
    label_value,
    run_pod,
)


def _launch(**overrides):
    values = dict(
        image="nsfearthcube/gleaner:test",
        args=["--cfgURL", "http://minio:9000/test/cfg.yaml", "-source", "src", "--rude"],
        working_dir="/gleaner/",
        env={"MINIO_ADDRESS": "minio", "MINIO_ACCESS_KEY": "ak", "MINIO_SECRET_KEY": "sk"},
        secret_env={},
        s3_url="http://minio:9000",
        log_target="test/scheduler/logs/src_gleaner_runlogs_2026_01_01",
        labels={"gleanerio/source": "src"},
    )
    values.update(overrides)
    return PodLaunch(**values)


def _pod(exit_code, name="dagster-run-gleanerio-run-123"):
    terminated = SimpleNamespace(exit_code=exit_code)
    status = SimpleNamespace(name=MAIN_CONTAINER, state=SimpleNamespace(terminated=terminated))
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name),
        status=SimpleNamespace(container_statuses=[status]),
    )


def _env(container):
    return {e.name: e for e in container.env}


@pytest.mark.parametrize(
    "value,expected",
    [("eco", "eco"), ("my source/v2", "my-source-v2"), ("_x_", "x"), ("a" * 80, "a" * 63), ("", "none")],
)
def test_label_value(value, expected):
    assert label_value(value) == expected


def test_build_pod_is_a_valid_pipes_pod():
    meta, spec = build_pod(_launch(), "abc123")
    pod = build_pod_body(
        pod_name="p", image=None, command=None, env_vars={}, base_pod_meta=meta, base_pod_spec=spec
    )

    assert pod.metadata.labels[LAUNCH_ID_LABEL] == "abc123"
    assert pod.spec.restart_policy == "Never"

    main = pod.spec.containers[0]
    assert main.name == MAIN_CONTAINER
    assert main.args[:2] == ["--cfgURL", "http://minio:9000/test/cfg.yaml"]
    assert main.command is None  # keeps the image entrypoint
    assert main.working_dir == "/gleaner/"
    assert [(m.name, m.mount_path) for m in main.volume_mounts] == [("logs", "/gleaner/logs")]

    sidecar = pod.spec.init_containers[0]
    assert sidecar.name == SIDECAR_CONTAINER
    assert sidecar.restart_policy == "Always"
    assert [(m.name, m.mount_path) for m in sidecar.volume_mounts] == [("logs", "/logs")]
    sidecar_env = _env(sidecar)
    assert sidecar_env["LOG_TARGET"].value == "test/scheduler/logs/src_gleaner_runlogs_2026_01_01"
    assert sidecar_env["MINIO_ACCESS_KEY"].value == "ak"
    assert "MINIO_ADDRESS" not in sidecar_env


def test_build_pod_uses_secret_refs_for_credentials():
    secret_env = {
        "MINIO_ACCESS_KEY": ("s3-creds", "accessKey"),
        "MINIO_SECRET_KEY": ("s3-creds", "secretKey"),
    }
    meta, spec = build_pod(_launch(secret_env=secret_env, service_account="gleanerio"), "id")
    pod = build_pod_body(
        pod_name="p", image=None, command=None, env_vars={}, base_pod_meta=meta, base_pod_spec=spec
    )

    assert pod.spec.service_account_name == "gleanerio"
    for container in (pod.spec.containers[0], pod.spec.init_containers[0]):
        env = _env(container)
        assert env["MINIO_SECRET_KEY"].value is None
        assert env["MINIO_SECRET_KEY"].value_from.secret_key_ref.name == "s3-creds"
        assert env["MINIO_SECRET_KEY"].value_from.secret_key_ref.key == "secretKey"


def _patched_k8s(pods, run_side_effect=None):
    core_api = mock.MagicMock()
    core_api.list_namespaced_pod.return_value = SimpleNamespace(items=pods)
    core_api.read_namespaced_pod_log.return_value = "gleaner output"
    pipes = mock.MagicMock()
    pipes.return_value.run.side_effect = run_side_effect
    return core_api, [
        mock.patch("dagster_k8s.PipesK8sClient", pipes),
        mock.patch(
            "dagster_k8s.client.DagsterKubernetesClient.production_client",
            return_value=SimpleNamespace(core_api=core_api),
        ),
        mock.patch("dagster_k8s.utils.detect_current_namespace", return_value="geocodes"),
    ]


def _run(pods, run_side_effect=None, **launch):
    core_api, patches = _patched_k8s(pods, run_side_effect)
    with patches[0] as pipes, patches[1], patches[2]:
        result = run_pod(mock.MagicMock(), _launch(**launch))
    return result, core_api, pipes


def test_run_pod_success_reads_logs_and_deletes_pod():
    (exit_code, logs), core_api, pipes = _run([_pod(0)])

    assert (exit_code, logs) == (0, "gleaner output")
    kwargs = pipes.return_value.run.call_args.kwargs
    assert kwargs["namespace"] == "geocodes"
    assert kwargs["delete_pod_on_completion"] is False
    assert kwargs["enable_multi_container_logs"] is True
    core_api.read_namespaced_pod_log.assert_called_once_with(
        "dagster-run-gleanerio-run-123", "geocodes", container=MAIN_CONTAINER
    )
    core_api.delete_namespaced_pod.assert_called_once_with("dagster-run-gleanerio-run-123", "geocodes")


def test_run_pod_returns_non_zero_exit_code_when_pipes_raises():
    (exit_code, logs), core_api, _ = _run([_pod(2)], run_side_effect=Exception("container failed"))

    assert (exit_code, logs) == (2, "gleaner output")
    core_api.delete_namespaced_pod.assert_called_once()


def test_run_pod_keeps_pod_when_debugging():
    _, core_api, _ = _run([_pod(0)], keep_pod=True)

    core_api.delete_namespaced_pod.assert_not_called()


def test_run_pod_raises_when_pod_was_never_created():
    with pytest.raises(Exception, match="was not found"):
        _run([], run_side_effect=Exception("forbidden"))


def test_run_pod_raises_and_cleans_up_without_exit_code():
    pod = _pod(0)
    pod.status.container_statuses[0].state.terminated = None
    core_api, patches = _patched_k8s([pod], Exception("timed out"))
    with patches[0], patches[1], patches[2]:
        with pytest.raises(Exception, match="has no exit code"):
            run_pod(mock.MagicMock(), _launch())
    core_api.delete_namespaced_pod.assert_called_once()


def _resource(**overrides):
    gs3 = SimpleNamespace(
        GLEANERIO_MINIO_ADDRESS="minio",
        GLEANERIO_MINIO_PORT="9000",
        GLEANERIO_MINIO_BUCKET="test",
        s3=SimpleNamespace(use_ssl=False, aws_access_key_id="ak", aws_secret_access_key="sk"),
    )
    values = dict(
        DEBUG_CONTAINER=False,
        GLEANERIO_LOG_PREFIX="scheduler/logs/",
        GLEANERIO_K8S_S3_SECRET="",
        GLEANERIO_K8S_NAMESPACE="",
        GLEANERIO_K8S_SERVICE_ACCOUNT="",
        GLEANERIO_K8S_LOG_SIDECAR_IMAGE="docker.io/rclone/rclone:1",
        GLEANERIO_K8S_POD_TIMEOUT=86400,
        GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT=300,
        gs3=gs3,
        s3loader=mock.MagicMock(),
        _container_env=lambda: {"MINIO_ACCESS_KEY": "ak", "MINIO_SECRET_KEY": "sk"},
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _execute_k8s(resource, exit_code=0):
    with mock.patch.object(gleanerio_k8s, "run_pod", return_value=(exit_code, "out")) as run:
        exit_code = GleanerioResource._execute_k8s(
            resource, mock.MagicMock(), "img", ["a"], "/nabu/", "sch_eco_src_release",
            "release", "src", "2026_01_01_00_00_00",
        )
        return exit_code, run.call_args.args[1]


def test_execute_k8s_builds_launch_and_uploads_stdout():
    resource = _resource(GLEANERIO_K8S_S3_SECRET="s3-creds")
    exit_code, launch = _execute_k8s(resource)

    assert exit_code == 0
    assert launch.s3_url == "http://minio:9000"
    assert launch.log_target == "test/scheduler/logs/src_release_runlogs_2026_01_01_00_00_00"
    assert launch.sync_interval == 300
    assert launch.secret_env["MINIO_SECRET_KEY"] == ("s3-creds", "secretKey")
    resource.s3loader.assert_called_once_with(
        b"out", "sch_eco_src_release", date_string="2026_01_01_00_00_00"
    )


def test_execute_k8s_raises_on_non_zero_exit_after_uploading_logs():
    resource = _resource()
    with pytest.raises(Exception, match="exit code 3"):
        _execute_k8s(resource, exit_code=3)
    resource.s3loader.assert_called_once()
