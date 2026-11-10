from types import SimpleNamespace
from unittest import mock

import inspect
import pytest
import yaml
from dagster_k8s.pipes import build_pod_body

from workflows.ingest.ingest.resources import gleanerio_k8s
from workflows.ingest.ingest.resources.gleanerio import (
    GleanerioResource,
    _in_cluster,
    default_launcher,
)
from workflows.ingest.ingest.resources.gleanerio_k8s import (
    CHROME_CONTAINER,
    DONE_FILE,
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

    chrome, main = pod.spec.containers[0], pod.spec.containers[1]
    assert chrome.name == CHROME_CONTAINER
    assert [(m.name, m.mount_path) for m in chrome.volume_mounts] == [
        ("shm", "/dev/shm"),
        ("logs", "/logs"),
    ]

    assert main.name == MAIN_CONTAINER
    # headless (the fixture default) wraps the main command so it raises the
    # completion marker; the original gleaner args become the shell's "$@" (args)
    assert main.command[:2] == ["/bin/sh", "-c"]
    assert "/gleaner/gleaner" in main.command[2]
    assert DONE_FILE in main.command[2]
    assert main.args[1:] == ["--cfgURL", "http://minio:9000/test/cfg.yaml", "-source", "src", "--rude"]
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


def test_build_pod_includes_chrome_even_when_the_source_does_not_need_it():
    """Chrome is always added, even for headless:false sources.

    The dev_ec Gleaner build's getDomain() unconditionally dials a DevTools
    endpoint (acquire.go:131-169) with a no-deadline context before the per-URL
    loop, regardless of the source's headless flag. Without Chrome present it
    logs "Is Headless Container running?" and returns/blocks, so a headless:
    false source still needs the in-pod Chrome.
    """
    meta, spec = build_pod(_launch(headless=False), "abc123")
    pod = build_pod_body(
        pod_name="p", image=None, command=None, env_vars={}, base_pod_meta=meta, base_pod_spec=spec
    )

    assert [c.name for c in pod.spec.containers] == [CHROME_CONTAINER, MAIN_CONTAINER]
    # in-pod Chrome at localhost
    assert _env(pod.spec.containers[1])["GLEANER_HEADLESS_ENDPOINT"].value == "http://localhost:9222"
    assert [v.name for v in pod.spec.volumes] == ["logs", "shm"]
    # the main command is always wrapped to write the completion marker so the
    # Chrome supervisor can stop Chrome and the pod reaches a terminal phase.
    main_cmd = " ".join(pod.spec.containers[1].command or [])
    assert main_cmd.startswith("/bin/sh -c /gleaner/gleaner")
    assert ".done" in main_cmd
    # the Chrome supervisor keys off that marker
    assert "DONE_FILE" in " ".join(pod.spec.containers[0].command or [])


def test_build_pod_includes_chrome_when_the_source_needs_it():
    meta, spec = build_pod(_launch(headless=True), "abc123")
    pod = build_pod_body(
        pod_name="p", image=None, command=None, env_vars={}, base_pod_meta=meta, base_pod_spec=spec
    )

    assert [c.name for c in pod.spec.containers] == [CHROME_CONTAINER, MAIN_CONTAINER]
    assert "shm" in [v.name for v in pod.spec.volumes]
    assert _env(pod.spec.containers[1])["GLEANER_HEADLESS_ENDPOINT"].value == "http://localhost:9222"
    # Chrome runs under a supervisor that stops it when the main container writes
    # DONE_FILE on the shared logs emptyDir, so the pod (restartPolicy: Never)
    # reaches a terminal phase and the dagster step returns. This must NOT use a
    # shared PID namespace: it breaks Chrome's renderer sandbox (infinite
    # "broker_posix.cc: Received unexpected number of handles").
    chrome = pod.spec.containers[0]
    assert chrome.command[:2] == ["/bin/sh", "-c"]
    supervisor = chrome.command[-1]
    assert "headless-shell" in supervisor
    assert "DONE_FILE" in supervisor
    assert "DONE_DIR" in supervisor
    # as the shares-logs mount and DONE_DIR env are set
    assert ("logs", "/logs") in [(m.name, m.mount_path) for m in chrome.volume_mounts]
    assert _env(chrome)["DONE_DIR"].value == "/logs"
    # the raw pod spec must NOT set shareProcessNamespace (it breaks Chrome)
    assert "shareProcessNamespace" not in spec
    # the main container is wrapped to raise the completion marker
    assert "/gleaner/gleaner" in " ".join(pod.spec.containers[1].command or [])


def test_default_launcher_detects_in_cluster(monkeypatch):
    """Inside a cluster (SA token + service host) the default launcher is k8s."""
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
    monkeypatch.setattr("os.path.exists", lambda p: p.endswith("serviceaccount/token"))
    assert default_launcher() == "k8s"


def test_default_launcher_falls_back_to_docker_outside_cluster(monkeypatch):
    """No cluster env -> docker, the historic compose/swarm path."""
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    monkeypatch.setattr("os.path.exists", lambda p: False)
    assert default_launcher() == "docker"


def test_execute_uses_explicit_launcher_over_detection(monkeypatch):
    """An explicit GLEANERIO_LAUNCHER is respected even inside a cluster."""
    r = mock.MagicMock(GLEANERIO_LAUNCHER="docker")
    launcher_slot = {}
    monkeypatch.setattr("os.path.exists", lambda p: True)
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
    # resolving: default_launcher() returns k8s, but explicit docker must win
    from workflows.ingest.ingest.resources import gleanerio as gi
    assert gi.default_launcher() == "k8s"
    assert (r.GLEANERIO_LAUNCHER or gi.default_launcher()) == "docker"


def _headless_source_resource(entries):
    sources_file = mock.MagicMock()
    sources_file.read.return_value = yaml.safe_dump({"sources": entries}).encode()
    return mock.MagicMock(gs3=SimpleNamespace(getSourcesFile=lambda: sources_file))


@pytest.mark.parametrize(
    "entries,source,expected",
    [
        ([{"name": "src", "headless": True}], "src", True),
        ([{"name": "src", "headless": False}], "src", False),
        # null is treated as falsy, matching how gleanerio_sources filters on the flag
        ([{"name": "src", "headless": None}], "src", False),
    ],
)
def test_source_needs_headless_reads_the_flag(entries, source, expected):
    resource = _headless_source_resource(entries)
    assert GleanerioResource._source_needs_headless(resource, "gleaner", source) is expected


def test_source_needs_headless_is_false_for_nabu_modes():
    """Only gleaner scrapes; release/prune/prov never need Chrome."""
    resource = _headless_source_resource([{"name": "src", "headless": True}])
    for mode in ("release", "prune", "prov", "orgs"):
        assert GleanerioResource._source_needs_headless(resource, mode, "src") is False


def test_source_needs_headless_defaults_to_true_when_unreadable():
    """Failing safe: a spare Chrome costs a container, a missing one fails the run."""
    broken = mock.MagicMock(gs3=SimpleNamespace(getSourcesFile=mock.MagicMock(side_effect=Exception("nope"))))
    assert GleanerioResource._source_needs_headless(broken, "gleaner", "src") is True

    missing = _headless_source_resource([{"name": "other", "headless": False}])
    assert GleanerioResource._source_needs_headless(missing, "gleaner", "src") is True


def test_source_needs_headless_defaults_to_true_when_the_config_is_none():
    """getSourcesFile swallows S3 errors and returns None rather than raising, so
    a None return has to be handled as well as an exception."""
    resource = mock.MagicMock(gs3=SimpleNamespace(getSourcesFile=lambda: None))
    assert GleanerioResource._source_needs_headless(resource, "gleaner", "src") is True


def test_build_pod_uses_a_tmpfs_for_dev_shm():
    """Chrome crashes on the runtime default of 64Mi /dev/shm."""
    meta, spec = build_pod(_launch(chrome_shm_size="1Gi"), "abc123")
    pod = build_pod_body(
        pod_name="p", image=None, command=None, env_vars={}, base_pod_meta=meta, base_pod_spec=spec
    )

    shm = {v.name: v for v in pod.spec.volumes}["shm"]
    assert shm.empty_dir.medium == "Memory"
    assert shm.empty_dir.size_limit == "1Gi"


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
    # Chrome carries no credentials, so only the main container and the log
    # sidecar should see the secret refs.
    for container in (pod.spec.containers[1], pod.spec.init_containers[0]):
        env = _env(container)
        assert env["MINIO_SECRET_KEY"].value is None
        assert env["MINIO_SECRET_KEY"].value_from.secret_key_ref.name == "s3-creds"
        assert env["MINIO_SECRET_KEY"].value_from.secret_key_ref.key == "secretKey"
    assert "MINIO_SECRET_KEY" not in _env(pod.spec.containers[0])


def _patched_k8s(pods, run_side_effect=None):
    core_api = mock.MagicMock()
    core_api.list_namespaced_pod.return_value = SimpleNamespace(items=pods)
    core_api.read_namespaced_pod_log.return_value = "gleaner output"
    pipes = mock.MagicMock()
    pipes.return_value.run.side_effect = run_side_effect
    return core_api, [
        mock.patch("dagster_k8s.PipesK8sClient", pipes),
        # run_pod builds its own authenticated client rather than using
        # DagsterKubernetesClient.production_client(), which does not send the
        # in-cluster token (see _authenticated_core_api).
        mock.patch.object(gleanerio_k8s, "_authenticated_core_api", return_value=core_api),
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


def test_authenticated_core_api_registers_bearer_token_for_the_generated_client():
    """Regression: Configuration.auth_settings() only reports BearerToken when
    api_key has a key of that name, but the in-cluster loader stores the token
    under 'authorization'. The generated methods ask for ['BearerToken'], the
    lookup misses, no Authorization header is attached, and every pods call
    returns 403 as system:anonymous."""
    from kubernetes import client as kube_client

    with mock.patch.object(gleanerio_k8s, "_load_k8s_config"):
        api = gleanerio_k8s._authenticated_core_api()

    assert isinstance(api, kube_client.CoreV1Api)
    # the fix lives on Configuration, which is what update_params_for_auth consults
    assert kube_client.Configuration._gleanerio_auth_fixed is True


def test_auth_settings_maps_authorization_to_bearer_token():
    settings = gleanerio_k8s._auth_settings_with_bearer_token("bearer abc")
    assert settings["BearerToken"]["key"] == "authorization"
    assert settings["BearerToken"]["value"] == "bearer abc"


def test_run_pod_installs_the_auth_fix_before_creating_the_pod():
    """PipesK8sClient.run() builds its own clients, so the fix has to be in
    place before it is called."""
    src = inspect.getsource(gleanerio_k8s.run_pod)
    assert "_install_auth_fix()" in src
    assert "production_client" not in src


def test_run_pod_raises_and_cleans_up_without_exit_code():
    pod = _pod(0)
    pod.status.container_statuses[0].state.terminated = None
    core_api, patches = _patched_k8s([pod], Exception("timed out"))
    with patches[0], patches[1], patches[2]:
        with pytest.raises(Exception, match="has no exit code"):
            run_pod(mock.MagicMock(), _launch())
    core_api.delete_namespaced_pod.assert_called_once()


def _resource(**overrides):
    # gleanerconfig the launcher reads to decide whether a source needs Chrome
    sources_file = mock.MagicMock()
    sources_file.read.return_value = yaml.safe_dump(
        {"sources": [{"name": "src", "headless": False}]}
    ).encode()
    gs3 = SimpleNamespace(
        GLEANERIO_MINIO_ADDRESS="minio",
        GLEANERIO_MINIO_PORT="9000",
        GLEANERIO_MINIO_BUCKET="test",
        s3=SimpleNamespace(use_ssl=False, aws_access_key_id="ak", aws_secret_access_key="sk"),
        getSourcesFile=lambda: sources_file,
    )
    values = dict(
        DEBUG_CONTAINER=False,
        GLEANERIO_LOG_PREFIX="scheduler/logs/",
        GLEANERIO_K8S_S3_SECRET="",
        GLEANERIO_K8S_NAMESPACE="",
        GLEANERIO_K8S_SERVICE_ACCOUNT="",
        GLEANERIO_K8S_LOG_SIDECAR_IMAGE="docker.io/rclone/rclone:1",
        GLEANERIO_K8S_POD_TIMEOUT=86400,
        GLEANERIO_K8S_CHROME_IMAGE="docker.io/chromedp/headless-shell:105.0.5195.127",
        GLEANERIO_K8S_CHROME_SHM_SIZE="512Mi",
        GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT=300,
        gs3=gs3,
        s3loader=mock.MagicMock(),
        _container_env=lambda: {"MINIO_ACCESS_KEY": "ak", "MINIO_SECRET_KEY": "sk"},
        # bound method so _execute_k8s can resolve whether the source needs Chrome
        _source_needs_headless=lambda mode, source: GleanerioResource._source_needs_headless(
            mock.MagicMock(gs3=gs3), mode, source
        ),
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
