"""Run a gleaner/nabu container as a Kubernetes pod, using dagster-k8s pipes.

This replaces the docker swarm service that GleanerioResource creates through the
Portainer API. The pod has:

* the gleaner or nabu container, with its logs/ directory on a shared emptyDir
* a native sidecar (an init container with restartPolicy: Always, k8s >= 1.29)
  that copies that directory to s3 every `sync_interval` seconds, and once more
  when kubernetes stops it after the main container exits.
* headless Chrome, only when the source needs it (`headless: true`). Chrome's
  DevTools endpoint rejects a Host header that is not an IP or localhost, so it
  cannot be reached through a Service name; running it in the pod and pointing
  Gleaner at localhost is the k8s equivalent of the shared headless_gleanerio
  network the swarm stack used.

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
CHROME_CONTAINER = "headless"
LOGS_VOLUME = "logs"
SHM_VOLUME = "shm"
LAUNCH_ID_LABEL = "gleanerio/launch-id"

# Chrome's DevTools endpoint answers 500 to any Host header that is not an IP
# or localhost: "Host header is specified and is not an IP address or
# localhost." An in-cluster Service name (http://<release>-headless:9222) is a
# hostname, so Gleaner cannot drive a Chrome that lives behind a Service. Running
# Chrome as a container in the same pod and pointing Gleaner at localhost avoids
# the Service name entirely, and is the k8s equivalent of the shared
# headless_gleanerio Docker network the swarm stack used.
CHROME_ENDPOINT_HOST = "localhost"
CHROME_PORT = 9222
CHROME_ENDPOINT = f"http://{CHROME_ENDPOINT_HOST}:{CHROME_PORT}"

# Shared emptyDir file that the main container touches when its work is done.
# The Chrome supervisor polls for it (on the logs emptyDir shared by both) so it
# can stop Chrome and let the pod reach a terminal phase. It deliberately does
# NOT rely on a shared PID namespace: shareProcessNamespace breaks Chrome's
# renderer sandbox (infinite "broker_posix.cc: Received unexpected number of
# handles"), which is what made every headless harvest hang with SitemapSummoned: 0.
DONE_FILE = "gleaner.done"

# Launch Chrome and keep the *pod* from outliving the work it serves.
#
# A headless source runs Chrome as a container in the same pod so Gleaner can
# drive it over localhost (see the module docstring). Chrome is long-running, so
# with the pod-level restartPolicy: Never the pod would never reach a terminal
# phase while Chrome is alive -- and dagster-k8s's PipesK8sClient.run() blocks
# until the pod terminates. The step would hang forever with a healthy index
# waiting on a pod that cannot finish.
#
# The main container writes DONE_FILE into the shared logs emptyDir when its
# work finishes; this supervisor polls for the file (mounting the same volume)
# and, on seeing it, shuts Chrome down so the pod reaches Succeeded/Failed.
#
# The drops (--no-sandbox --use-gl=angle --use-angle=swiftshader) and the default
# address 0.0.0.0:9222 mirror the Debian/chromedp headless-shell default entry
# that the standalone geocodes-headless Service uses. The binary path comes from
# the debian/chromedp image layout.
CHROME_SUPERVISOR = """
[ -n "$DONE_FILE" ] || DONE_FILE=gleaner.done
STOP_ALL() { pkill -f '/headless-shell/headless-shell' 2>/dev/null || true; exit 0; }
trap STOP_ALL TERM INT
/headless-shell/headless-shell \\
  --no-sandbox --use-gl=angle --use-angle=swiftshader \\
  --remote-debugging-address=0.0.0.0 --remote-debugging-port=9222 &
CHROME_PID=$!

# Wait for the main container's completion marker on the shared logs volume.
# DONE_DIR is injected by build_pod as an env var pointing at this container's
# mount of the logs emptyDir (the /logs path the supervisor mounts to).
while kill -0 "$CHROME_PID" 2>/dev/null; do
  if [ -f "$DONE_DIR/$DONE_FILE" ]; then
    break
  fi
  sleep 1
done
STOP_ALL
"""

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
    # Headless Chrome, for sources that need JS rendering. Chrome runs in this
    # pod so GLEANER_HEADLESS_ENDPOINT can be localhost (see module docstring).
    # The image is pinned: versions after 105 break Gleaner with "devtool:
    # CreateURL: Using unsafe HTTP verb GET to invoke /json/new. This action
    # supports only PUT verb."
    #
    # Whether the source is a headless goldberg. Chrome is ALWAYS added to the
    # pod regardless of this flag: the dev_ec Gleaner build unconditional
    # DevTools handshake in getDomain() needs Chrome even for headless:false
    # sources. This flag is retained for callers who want to branch on the
    # source's own headless setting (e.g. diagnostics), but build_pod no longer
    # uses it to decide whether to include Chrome.
    headless: bool = True
    chrome_image: str = "docker.io/chromedp/headless-shell:105.0.5195.127"
    # Size of the Chrome /dev/shm volume. Chrome crashes on small /dev/shm, and
    # the container runtime defaults to 64Mi, so it is a tmpfs emptyDir.
    chrome_shm_size: str = "512Mi"


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

    # Chrome lives in this pod, so the endpoint has to be localhost rather than
    # whatever Service name the caller passed (see module docstring). This is
    # applied to the main container only: the sidecar does not scrape.
    #
    # Chrome is added UNCONDITIONALLY (not just for headless sources). The
    # `dev_ec` Gleaner build's getDomain() nevertheless always dials a DevTools
    # endpoint up front (acquire.go:131-169) with a NO-deadline chromedp
    # context, before the per-URL loop and regardless of the source's
    # `headless` flag. Without a reachable Chrome it logs "Is Headless
    # Container running?" and either returns or blocks forever. So even a
    # `headless: false` source needs the in-pod Chrome present.
    main_env = dict(launch.env)
    # Point Gleaner at the in-pod Chrome. This matches both the default
    # summoner.headless in the config and what the dev_ec handshake dials.
    main_env["GLEANER_HEADLESS_ENDPOINT"] = CHROME_ENDPOINT

    containers = []
    volumes = [{"name": LOGS_VOLUME, "emptyDir": {}}]
    containers.append(
        {
            "name": CHROME_CONTAINER,
            "image": launch.chrome_image,
            # Wrap the image's headless-shell entry with a supervisor that
            # stops Chrome when the gleaner/nabu container finishes, so the
            # pod (restartPolicy: Never) reaches a terminal phase and
            # PipesK8sClient.run() does not hang. See CHROME_SUPERVISOR.
            "command": ["/bin/sh", "-c", CHROME_SUPERVISOR],
            "env": [
                # Chrome mounts the shared logs emptyDir read-write so the
                # supervisor can see the main container's completion marker.
                {"name": "DONE_DIR", "value": "/logs"}
            ],
            "ports": [{"name": "devtools", "containerPort": CHROME_PORT}],
            # Chrome needs /dev/shm bigger than the runtime default. The
            # image's entrypoint already starts it on 9222.
            "volumeMounts": [
                {"name": SHM_VOLUME, "mountPath": "/dev/shm"},
                {"name": LOGS_VOLUME, "mountPath": "/logs"},
            ],
            "readinessProbe": {
                "tcpSocket": {"port": "devtools"},
                "periodSeconds": 5,
            },
        }
    )
    volumes.append(
        {
            "name": SHM_VOLUME,
            "emptyDir": {"medium": "Memory", "sizeLimit": launch.chrome_shm_size},
        }
    )

    # Always wrap the main command so it writes DONE_FILE into the shared logs
    # emptyDir when its work finishes. This lets the Chrome supervisor stop
    # Chrome (and thus end the pod) WITHOUT a shared PID namespace, which
    # Chrome cannot tolerate (see CHROME_SUPERVISOR). Required for every source
    # now that Chrome is always present. Detect the entrypoint binary from the
    # image so the harness still runs the real gleaner/nabu command.
    #
    # NOTE: this wrapper must NOT use `exec` on the entrypoint. The `touch`
    # after it would be dead code (exec replaces the shell), so the completion
    # marker would never appear and the Chrome supervisor would never stop
    # Chrome, leaving the pod stuck in Running after a successful gleaner.
    main_args = list(launch.args)
    image_lower = (launch.image or "").lower()
    entrypoint = "/nabu/nabu" if "nabu" in image_lower else "/gleaner/gleaner"
    script = (
        f"{entrypoint} \"$@\"; rc=$?; "
        f"touch {logs_dir}/{DONE_FILE}; exit $rc"
    )
    # /bin/sh -c SCRIPT -- <args...>: script runs with $0='--' and $@=args
    main_command = ["/bin/sh", "-c", script, "--"] + main_args

    containers.append(
        {
            "name": MAIN_CONTAINER,
            "image": launch.image,
            # Override the entrypoint with the shell wrapper (command+args) so
            # the supervisor can detect completion and stop Chrome.
            "command": main_command[:3],
            "args": main_command[3:],
            "workingDir": launch.working_dir,
            "env": _env_list(main_env, launch.secret_env),
            "volumeMounts": [{"name": LOGS_VOLUME, "mountPath": logs_dir}],
        }
    )

    spec = {
        "restartPolicy": "Never",
        # note: deliberately NOT setting shareProcessNamespace. It would let a
        # supervisor watch the gleaner pid, but it breaks Chrome's renderer
        # sandbox (infinite "broker_posix.cc: Received unexpected number of
        # handles"), which is what made headless harvests hang. Completion is
        # signalled through a shared emptyDir file instead.
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
        "containers": containers,
        "volumes": volumes,
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


def _load_k8s_config():
    """Load in-cluster config, falling back to a kubeconfig outside a cluster."""
    from kubernetes import config as kube_config

    try:
        kube_config.load_incluster_config()
    except kube_config.ConfigException:
        # running outside a cluster, e.g. a local test with KUBECONFIG set
        kube_config.load_kube_config()


def _auth_settings_with_bearer_token(token):
    """The auth settings dict, keyed the way the generated client looks it up.

    ApiClient.update_params_for_auth() resolves each name in auth_settings
    against Configuration.auth_settings():

        auth_setting = self.configuration.auth_settings().get(auth)

    and the generated API methods hardcode auth_settings=['BearerToken'].
    Configuration.auth_settings() only reports that name when api_key has a key
    of exactly that name:

        if 'BearerToken' in self.api_key:
            auth['BearerToken'] = {...}

    but the in-cluster loader stores the token as 'authorization':

        client_configuration.api_key['authorization'] = self.token

    So the lookup misses, nothing is attached, and the request goes out with only
    Accept and User-Agent. The API server then reports an anonymous user:
    "pods is forbidden: User \\"system:anonymous\\" ...".
    """
    return {
        "BearerToken": {
            "type": "api_key",
            "in": "header",
            "key": "authorization",
            "value": token,
        }
    }


def _install_auth_fix():
    """Make dagster_k8s's clients send the in-cluster token.

    PipesK8sClient.run() calls DagsterKubernetesClient.production_client(), which
    builds its api clients from PatchedApiClient(), and run() takes no client
    argument, so there is nowhere to inject an authenticated one. PatchedApiClient
    is a fork of ApiClient kept for a model-deserialization fix, and it inherits
    the mismatch described in _auth_settings_with_bearer_token, so pod creation
    fails 403 as system:anonymous.

    The override goes on the Configuration instance, not the client: that is what
    update_params_for_auth() consults. It is applied to Configuration itself so
    every client built afterwards - including the ones production_client()
    constructs on each call - picks it up.
    """
    from kubernetes.client import Configuration

    if getattr(Configuration, "_gleanerio_auth_fixed", False):
        return

    original = Configuration.auth_settings

    def auth_settings(self):
        token = (self.api_key or {}).get("authorization")
        if token:
            return _auth_settings_with_bearer_token(token)
        return original(self)

    Configuration.auth_settings = auth_settings
    Configuration._gleanerio_auth_fixed = True


def _authenticated_core_api():
    """A CoreV1Api for reading pods back after a run, with the token attached."""
    from kubernetes import client as kube_client

    _load_k8s_config()
    _install_auth_fix()
    return kube_client.CoreV1Api()


def run_pod(context, launch: PodLaunch) -> Tuple[int, str]:
    """Run the pod to completion. Returns (exit code, main container stdout/stderr).

    Raises if the pod could not be created or never produced an exit code. A
    non-zero exit code is returned, not raised, so the caller can upload logs first.
    """
    # imported here so the docker launcher keeps working without dagster-k8s installed
    from dagster_k8s import PipesK8sClient
    from dagster_k8s.utils import detect_current_namespace

    log = get_dagster_logger()
    launch_id = uuid.uuid4().hex
    meta, spec = build_pod(launch, launch_id)

    # PipesK8sClient.run() builds its own clients from PatchedApiClient, which
    # drops the in-cluster token. Patch that class before the client is used so
    # pod creation is authenticated.
    _load_k8s_config()
    _install_auth_fix()

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

    core_api = _authenticated_core_api()
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
