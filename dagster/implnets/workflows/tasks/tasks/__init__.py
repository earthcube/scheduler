import os
from dagster import (Definitions, load_assets_from_modules,
                     load_asset_checks_from_modules, EnvVar, RunFailureSensorContext)
from dagster_aws.s3 import  S3Resource
#from dagster_slack import SlackResource, make_slack_on_run_failure_sensor
from . import assets
from .sch import weekly_sch
from .sch.s3_sensor import tenant_s3_sensor
from .assets.tenants import community_sensor

from .resources.graph import BlazegraphResource, GraphResource
from .resources.gleanerS3 import gleanerS3Resource

from dagster_slack import SlackResource, make_slack_on_run_failure_sensor
def slack_message_fn(context: RunFailureSensorContext) -> str:
    return (
        f"Partition for Source *[{context.partition_key}]*  failed!"
        f"Error: {context.failure_event.message}"
    )

slack_on_run_failure = make_slack_on_run_failure_sensor(
     os.getenv("SLACK_CHANNEL"),
    os.getenv("SLACK_TOKEN"),
    webserver_base_url=f'https://{os.getenv("SCHED_HOSTNAME")}.{os.getenv("HOST")}/',
    text_fn=slack_message_fn,
)
def _awsEndpointAddress(url, port=None, use_ssl=True):
    if use_ssl:
        protocol = "https"
    else:
        protocol = "http"
    if port is not None:
        return  f"{protocol}://{url}:{port}"
    else:
        return  f"{protocol}://{url}"


def _env_bool(name, default=False):
    """Parse a boolean env var.

    Not a bare os.environ.get, which returns a string and makes bool("false")
    True -- that would force https on a plain-HTTP S3 endpoint.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")

all_assets = load_assets_from_modules([assets])
all_asset_checks = load_asset_checks_from_modules([assets])
# as noted: https://docs.dagster.io/concepts/assets/software-defined-assets#from-assets-in-a-sub-module
# tried to use load_assets_from_modules([assets] , key_prefix=["tasks"])
# this meant that the prefix had to included in the code... so, just add it individually
weekly_data_schedule=[ weekly_sch.loadstats_schedule, weekly_sch.all_graph_stats_schedule]
s3 = S3Resource(
    endpoint_url=_awsEndpointAddress(EnvVar('GLEANERIO_MINIO_ADDRESS').get_value(),
                                     port=EnvVar('GLEANERIO_MINIO_PORT').get_value(),
                                     use_ssl=_env_bool('GLEANERIO_MINIO_USE_SSL')),
    # See the same field in workflows/ingest/ingest/__init__.py: without this the
    # resource keeps its default of True and downstream code reads the wrong value.
    use_ssl=_env_bool('GLEANERIO_MINIO_USE_SSL'),
    aws_access_key_id=EnvVar('GLEANERIO_MINIO_ACCESS_KEY'),
    aws_secret_access_key=EnvVar('GLEANERIO_MINIO_SECRET_KEY')
)
minio=gleanerS3Resource(
    s3=s3,
    # GLEANER_MINIO_BUCKET =EnvVar('GLEANER_MINIO_BUCKET'),
    # GLEANER_MINIO_ADDRESS=EnvVar('GLEANER_MINIO_ADDRESS'),
    # GLEANER_MINIO_PORT=EnvVar('GLEANER_MINIO_PORT'),

    GLEANERIO_MINIO_BUCKET=os.environ.get('GLEANERIO_MINIO_BUCKET'),
    GLEANERIO_MINIO_ADDRESS=os.environ.get('GLEANERIO_MINIO_ADDRESS'),
    GLEANERIO_MINIO_PORT=os.environ.get('GLEANERIO_MINIO_PORT'),
    GLEANERIO_MINIO_USE_SSL=_env_bool('GLEANERIO_MINIO_USE_SSL'),
    GLEANERIO_MINIO_ACCESS_KEY=EnvVar('GLEANERIO_MINIO_ACCESS_KEY'),
    GLEANERIO_MINIO_SECRET_KEY=EnvVar('GLEANERIO_MINIO_SECRET_KEY'),
    GLEANERIO_CONFIG_PATH=os.environ.get('GLEANERIO_CONFIG_PATH'),
    GLEANERIO_TENANT_FILENAME=os.environ.get('GLEANERIO_TENANT_FILENAME'),
    GLEANERIO_SOURCES_FILENAME=os.environ.get('GLEANERIO_SOURCES_FILENAME', 'gleanerconfig.yaml')

)
triplestore=BlazegraphResource(
            GLEANERIO_GRAPH_URL=os.environ.get('GLEANERIO_GRAPH_URL'),
            GLEANERIO_GRAPH_NAMESPACE=os.environ.get('GLEANERIO_GRAPH_NAMESPACE'),
            GLEANERIO_GRAPH_SUMMARY_NAMESPACE=os.environ.get('GLEANERIO_GRAPH_SUMMARY_NAMESPACE'),
            GLEANERIO_GRAPH_SUMMARIZE=os.environ.get('GLEANERIO_GRAPH_SUMMARIZE'),
              s3=minio,
        )


resources = {
    "local": {

        "s3":minio,
        "triplestore": triplestore,
 #       "slack": SlackResource(token=EnvVar("SLACK_TOKEN")),
    },
    "production": {

        "s3":minio,
        "triplestore":triplestore,
 #       "slack":SlackResource(token=EnvVar("SLACK_TOKEN")),
    },
}

deployment_name = os.environ.get("DAGSTER_DEPLOYMENT", "local")


def _make_io_manager():
    """See the same function in workflows/ingest/ingest/__init__.py.

    Asset values that cross pods must not live on a container filesystem.
    tasks/assets/tenants.py also calls load_asset_value, so this module needs
    the same manager or that call fails the same way.
    """
    if os.environ.get("GLEANERIO_IO_MANAGER", "").strip().lower() in ("1", "true", "s3", "yes", "on"):
        from dagster_aws.s3 import S3PickleIOManager

        return S3PickleIOManager(
            s3_resource=s3,
            s3_bucket=os.environ.get("GLEANERIO_MINIO_BUCKET"),
            s3_prefix=os.environ.get("GLEANERIO_IO_MANAGER_PREFIX", "dagster/io"),
        )
    return None


_io_manager = _make_io_manager()
resources_for_deployment = dict(resources[deployment_name])
if _io_manager is not None:
    resources_for_deployment["io_manager"] = _io_manager


defs = Definitions(
    assets=all_assets,
    asset_checks=all_asset_checks,
    schedules=weekly_data_schedule,
     resources=resources_for_deployment,
    sensors=[community_sensor, tenant_s3_sensor, slack_on_run_failure]
)
