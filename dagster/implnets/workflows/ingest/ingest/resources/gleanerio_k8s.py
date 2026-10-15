"""Run a gleaner/nabu container as a Kubernetes pod, using dagster-k8s pipes.

This replaces the docker swarm service that GleanerioResource creates through the
Portainer API. The pod has two containers:

* the gleaner or nabu container, with its logs/ directory on a shared emptyDir
* a native sidecar (an init container with restartPolicy: Always, k8s >= 1.29)
  that copies that directory to s3 every `sync_interval` seconds, and once more
  when kubernetes stops it after the main container exits.

The sidecar replaces the docker get_archive() calls, since kubernetes cannot copy
files out of a container once it has stopped.
"""

import re
import uuid
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence, Tuple

from dagster import get_dagster_logger

MAIN_CONTAINER = "gleanerio"
SIDECAR_CONTAINER = "log-sync"
LOGS_VOLUME = "logs"
LAUNCH_ID_LABEL = "gleanerio/launch-id"

# The sidecar needs `sh` and `rclone` (the minio/mc images are no longer publicly
# pullable). It uses `copy`, not `sync`, so nothing already in s3 is deleted, and
# exits 0 on SIGTERM after a final copy, so dagster-k8s does not report the sidecar
# shutdown as a container failure.
SIDECAR_SCRIPT = """
export RCLONE_CONFIG_S3_TYPE=s3 RCLONE_CONFIG_S3_PROVIDER=Minio
export RCLONE_CONFIG_S3_ENDPOINT="$S3_URL"
export RCLONE_CONFIG_S3_ACCESS_KEY_ID="$MINIO_ACCESS_KEY"
export RCLONE_CONFIG_S3_SECRET_ACCESS_KEY="$MINIO_SECRET_KEY"
sync_logs() { rclone copy --s3-no-check-bucket /logs "s3:$LOG_TARGET/" || true; }
trap 'sync_logs; exit 0' TERM INT
while true; do
  sleep "$SYNC_INTERVAL" &
  wait $!
  sync_logs
done
"""


@dataclass
class PodLaunch:
    """Everything needed to run one gleaner/nabu step as a pod."""

    image: str
    args: Sequence[str]
    working_dir: str
    env: Mapping[str, str]
    # env var name -> (secret name, key); takes precedence over `env`
    secret_env: Mapping[str, Tuple[str, str]]
    s3_url: str
    log_target: str  # bucket/prefix the sidecar copies logs/ into
    labels: Mapping[str, str] = field(default_factory=dict)
    namespace: Optional[str] = None
    service_account: Optional[str] = None
    sidecar_image: str = "docker.io/rclone/rclone:1"
    sync_interval: int = 600
    pod_timeout: float = 86400
    keep_pod: bool = False


def label_value(value: str) -> str:
    """Kubernetes label values: <=63 chars of [A-Za-z0-9_.-], alphanumeric at both ends."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "-", str(value))[:63]
    return cleaned.strip("_.-") or "none"


def _env_list(env: Mapping[str, str], secret_env: Mapping[str, Tuple[str, str]]):
    plain = [{"name": k, "value": str(v)} for k, v in env.items() if k not in secret_env]
    secret = [
        {"name": k, "valueFrom": {"secretKeyRef": {"name": name, "key": key}}}
        for k, (name, key) in secret_env.items()
    ]
    return plain + secret


def build_pod(launch: PodLaunch, launch_id: str) -> Tuple[dict, dict]:
    """Return (pod metadata, pod spec) for PipesK8sClient.run."""
    logs_dir = launch.working_dir.rstrip("/") + "/logs"
    credentials = {
        k: v for k, v in launch.env.items() if k in ("MINIO_ACCESS_KEY", "MINIO_SECRET_KEY")
    }
    credential_secrets = {
        k: v for k, v in launch.secret_env.items() if k in ("MINIO_ACCESS_KEY", "MINIO_SECRET_KEY")
    }
    sidecar_env = {
        "S3_URL": launch.s3_url,
        "LOG_TARGET": launch.log_target,
        "SYNC_INTERVAL": str(launch.sync_interval),
        **credentials,
    }

    spec = {
        "restartPolicy": "Never",
        "terminationGracePeriodSeconds": 120,
        "initContainers": [
            {
                "name": SIDECAR_CONTAINER,
                "image": launch.sidecar_image,
                "restartPolicy": "Always",
                "command": ["/bin/sh", "-c", SIDECAR_SCRIPT],
                "env": _env_list(sidecar_env, credential_secrets),
                "volumeMounts": [{"name": LOGS_VOLUME, "mountPath": "/logs"}],
            }
        ],
        "containers": [
            {
                "name": MAIN_CONTAINER,
                "image": launch.image,
                # args, not command: keep the image entrypoint, as the swarm service did
                "args": list(launch.args),
                "workingDir": launch.working_dir,
                "env": _env_list(launch.env, launch.secret_env),
                "volumeMounts": [{"name": LOGS_VOLUME, "mountPath": logs_dir}],
            }
        ],
        "volumes": [{"name": LOGS_VOLUME, "emptyDir": {}}],
    }
    if launch.service_account:
        spec["serviceAccountName"] = launch.service_account

    meta = {"labels": {**launch.labels, LAUNCH_ID_LABEL: launch_id}}
    return meta, spec


def _find_pod(core_api, namespace: str, launch_id: str):
    pods = core_api.list_namespaced_pod(
        namespace, label_selector=f"{LAUNCH_ID_LABEL}={launch_id}"
    ).items
    return pods[0] if pods else None


def _exit_code(pod) -> Optional[int]:
    for status in (pod.status.container_statuses or []):
        if status.name == MAIN_CONTAINER and status.state and status.state.terminated:
            return status.state.terminated.exit_code
    return None


def run_pod(context, launch: PodLaunch) -> Tuple[int, str]:
    """Run the pod to completion. Returns (exit code, main container stdout/stderr).

    Raises if the pod could not be created or never produced an exit code. A
    non-zero exit code is returned, not raised, so the caller can upload logs first.
    """
    # imported here so the docker launcher keeps working without dagster-k8s installed
    from dagster_k8s import PipesK8sClient
    from dagster_k8s.client import DagsterKubernetesClient
    from dagster_k8s.utils import detect_current_namespace

    log = get_dagster_logger()
    launch_id = uuid.uuid4().hex
    meta, spec = build_pod(launch, launch_id)

    pipes = PipesK8sClient()
    namespace = launch.namespace or detect_current_namespace(None) or "default"

    error = None
    try:
        pipes.run(
            context=context,
            namespace=namespace,
            base_pod_meta=meta,
            base_pod_spec=spec,
            # more than one container, so logs have to be read per container
            enable_multi_container_logs=True,
            pod_wait_timeout=launch.pod_timeout,
            # we read the exit code and logs before deleting the pod ourselves
            delete_pod_on_completion=False,
        )
    except Exception as ex:  # dagster-k8s raises on non-zero exit, timeouts and pull errors
        error = ex
        log.warning(f"gleanerio pod {launch_id} did not complete cleanly: {ex}")

    core_api = DagsterKubernetesClient.production_client().core_api
    pod = _find_pod(core_api, namespace, launch_id)
    if pod is None:
        raise Exception(f"gleanerio pod {launch_id} was not found") from error

    pod_name = pod.metadata.name
    try:
        exit_code = _exit_code(pod)
        try:
            logs = core_api.read_namespaced_pod_log(pod_name, namespace, container=MAIN_CONTAINER)
        except Exception as ex:
            logs = f"could not read logs for {pod_name}: {ex}"
        if exit_code is None:
            raise Exception(f"gleanerio pod {pod_name} has no exit code") from error
        log.info(f"gleanerio pod {pod_name} exit code {exit_code}")
        return exit_code, logs
    finally:
        if launch.keep_pod:
            log.info(f"Pod {pod_name} NOT removed: DEBUG enabled")
        else:
            core_api.delete_namespaced_pod(pod_name, namespace)
            log.info(f"Pod removed: {pod_name}")
