########### NOTES ON THIS ####
# the resources need to be correct for the code to run,
# * fields need to be defined. they cannot be

#    BlaszegraphResource(),

#    need have definitions.

#    BlazegraphResource(
#             GLEANERIO_GRAPH_URL=EnvVar('GLEANERIO_GRAPH_URL'),
#             GLEANERIO_GRAPH_NAMESPACE=EnvVar('GLEANERIO_GRAPH_NAMESPACE'),
#         )
#### QUIRKS ###
# if a type is changed in a configuraiton, you need to change all the configs, and not just one.
# so when

import os

from dagster import Definitions, load_assets_from_modules, EnvVar,RunFailureSensorContext,get_dagster_logger
from dagster_aws.s3.resources import S3Resource
from dagster_aws.s3.ops import S3Coordinate
from dagster import (
    AssetSelection,
    Definitions,
    define_asset_job,
)
from dagster_slack import SlackResource, make_slack_on_run_failure_sensor

from .resources.graph import BlazegraphResource, GraphResource, GraphdbResource
from .resources.gleanerio import GleanerioResource
from .resources.gleanerS3 import gleanerS3Resource
from .assets import (
    gleanerio_run,
                     release_nabu_run
)

from .jobs.summon_assets import summon_asset_job
from .jobs import (
    summon_asset_job, sources_asset_job,
                   sources_partitions_def
                ,tenant_asset_job,
                   tenant_namespaces_job,
                   release_asset_job,
                   tenant_rebuild_namespaces_job
)

jobs = [
summon_asset_job, sources_asset_job,
                tenant_asset_job,
                   tenant_namespaces_job,
                   release_asset_job,
                   tenant_rebuild_namespaces_job
]
from pydantic import Field

from . import assets
from .utils import PythonMinioAddress


all_assets = load_assets_from_modules([assets])

#harvest_job = define_asset_job(name="harvest_job", selection="harvest_and_release")

from .sensors import (
    release_file_sensor,
release_file_sensor_v2,
    sources_sensor,
    tenant_names_sensor,
    sources_s3_sensor,
    tenant_s3_sensor,
#tenant_names_sensor_v2
)
def slack_message_fn(context: RunFailureSensorContext) -> str:
    return (
        f"Partition for Source *[{context.partition_key}]* failed! "
        f"Error: {context.failure_event.message}"
        f"Date: {context.failure_event.date}"
    )
slack_on_run_failure = make_slack_on_run_failure_sensor(
     os.getenv("SLACK_CHANNEL"),
    EnvVar("SLACK_TOKEN"),  # hide in interface
    webserver_base_url=f'https://{os.getenv("SCHED_HOSTNAME")}.{os.getenv("HOST")}',
    text_fn=slack_message_fn
)
all_sensors = [
    slack_on_run_failure,
  #             release_file_sensor,
release_file_sensor_v2,
               sources_sensor, # original code. Now use a schedule
               tenant_names_sensor,
                sources_s3_sensor,
                tenant_s3_sensor,
#tenant_names_sensor_v2
               ]

from .sensors.gleaner_summon import sources_schedule

all_schedules = [sources_schedule]

def _awsEndpointAddress(url, port=None, use_ssl=True):
    if use_ssl:
        protocol = "https"
    else:
        protocol = "http"
    if port is not None:
        return  f"{protocol}://{url}:{port}"
    else:
        return  f"{protocol}://{url}"

s3=S3Resource(
    endpoint_url =_awsEndpointAddress(
        EnvVar('GLEANERIO_MINIO_ADDRESS').get_value(),
        port=EnvVar('GLEANERIO_MINIO_PORT').get_value(),
        use_ssl=EnvVar('GLEANERIO_MINIO_USE_SSL').get_value()
        ),
    aws_access_key_id=EnvVar('GLEANERIO_MINIO_ACCESS_KEY'), # hide in interface
    aws_secret_access_key=EnvVar('GLEANERIO_MINIO_SECRET_KEY') # hide in interface
)
gleaners3=gleanerS3Resource(

    GLEANERIO_MINIO_BUCKET=os.environ.get('GLEANERIO_MINIO_BUCKET'),
    GLEANERIO_MINIO_ADDRESS=os.environ.get('GLEANERIO_MINIO_ADDRESS'),
    GLEANERIO_MINIO_PORT=os.environ.get('GLEANERIO_MINIO_PORT'),
    GLEANERIO_MINIO_USE_SSL=os.environ.get('GLEANERIO_MINIO_USE_SSL', "True"),
    GLEANERIO_MINIO_ACCESS_KEY=EnvVar('GLEANERIO_MINIO_ACCESS_KEY'), # hide in interface
    GLEANERIO_MINIO_SECRET_KEY=EnvVar('GLEANERIO_MINIO_SECRET_KEY'), # hide in interface
    GLEANERIO_CONFIG_PATH=os.environ.get('GLEANERIO_CONFIG_PATH'),
    GLEANERIO_SOURCES_FILENAME=os.environ.get('GLEANERIO_SOURCES_FILENAME'),
    GLEANERIO_TENANT_FILENAME=os.environ.get('GLEANERIO_TENANT_FILENAME'),
    # this is S3. It is the s3 resource
    s3=s3

)
triplestore=BlazegraphResource(
            GLEANERIO_GRAPH_URL=os.environ.get('GLEANERIO_GRAPH_URL'),
            GLEANERIO_GRAPH_NAMESPACE=os.environ.get('GLEANERIO_GRAPH_NAMESPACE'),
            GLEANERIO_GRAPH_USERNAME=EnvVar('GLEANERIO_GRAPH_USERNAME'),
            GLEANERIO_GRAPH_PASSWORD=EnvVar('GLEANERIO_GRAPH_PASSWORD'),
       gs3=gleaners3,
        )
triplestore_summary=BlazegraphResource(
            GLEANERIO_GRAPH_URL=os.environ.get('GLEANERIO_GRAPH_URL'),
            GLEANERIO_GRAPH_NAMESPACE=os.environ.get('GLEANERIO_GRAPH_SUMMARY_NAMESPACE'),
            GLEANERIO_GRAPH_USERNAME=EnvVar('GLEANERIO_GRAPH_USERNAME'),
            GLEANERIO_GRAPH_PASSWORD=EnvVar('GLEANERIO_GRAPH_PASSWORD'),
       gs3=gleaners3,
        )
Gdbtriplestore=GraphdbResource(
            GLEANERIO_GRAPH_URL=os.environ.get('GLEANERIO_GRAPH_URL'),
            GLEANERIO_GRAPH_NAMESPACE=os.environ.get('GLEANERIO_GRAPH_NAMESPACE'),
            GLEANERIO_GRAPH_USERNAME=EnvVar('GLEANERIO_GRAPH_USERNAME'),
            GLEANERIO_GRAPH_PASSWORD=EnvVar('GLEANERIO_GRAPH_PASSWORD'),
       gs3=gleaners3,
        )
Gdbtriplestore_summary=GraphdbResource(
            GLEANERIO_GRAPH_URL=os.environ.get('GLEANERIO_GRAPH_URL'),
            GLEANERIO_GRAPH_NAMESPACE=os.environ.get('GLEANERIO_GRAPH_SUMMARY_NAMESPACE'),
GLEANERIO_GRAPH_USERNAME=EnvVar('GLEANERIO_GRAPH_USERNAME'),
GLEANERIO_GRAPH_PASSWORD=EnvVar('GLEANERIO_GRAPH_PASSWORD'),
       gs3=gleaners3,
        )

gleanerio=GleanerioResource(
#            DEBUG=os.environ.get('DEBUG'),
            DEBUG_CONTAINER=False,
            GLEANERIO_DOCKER_URL=EnvVar('GLEANERIO_DOCKER_URL'), # hide in interface
            GLEANERIO_PORTAINER_APIKEY=EnvVar('GLEANERIO_PORTAINER_APIKEY'), # hide in interface

            GLEANERIO_DOCKER_HEADLESS_NETWORK=os.environ.get('GLEANERIO_DOCKER_HEADLESS_NETWORK'),
            GLEANERIO_HEADLESS_ENDPOINT=os.environ.get('GLEANERIO_HEADLESS_ENDPOINT'),

            GLEANERIO_GLEANER_IMAGE=os.environ.get('GLEANERIO_GLEANER_IMAGE'),
            GLEANERIO_NABU_IMAGE=os.environ.get('GLEANERIO_NABU_IMAGE'),

             GLEANERIO_GLEANER_CONFIG_PATH=os.environ.get('GLEANERIO_GLEANER_CONFIG_PATH'),

            GLEANERIO_LOG_PREFIX=os.environ.get('GLEANERIO_LOG_PREFIX'),

            GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT=os.environ.get('GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT',600),
            GLEANERIO_GRAPH_NAMESPACE=os.environ.get('GLEANERIO_GRAPH_NAMESPACE'),
            GLEANERIO_GRAPH_SUMMARY_NAMESPACE=os.environ.get('GLEANERIO_GRAPH_SUMMARY_NAMESPACE'),
            gs3=gleaners3,
            triplestore=triplestore,
            triplestore_summary=triplestore_summary
        ) # gleaner

Gdbgleanerio=GleanerioResource(
#            DEBUG=os.environ.get('DEBUG'),
            DEBUG_CONTAINER=False,
            GLEANERIO_DOCKER_URL=EnvVar('GLEANERIO_DOCKER_URL'), # hide in interface
            GLEANERIO_PORTAINER_APIKEY=EnvVar('GLEANERIO_PORTAINER_APIKEY'), # hide in interface

            GLEANERIO_DOCKER_HEADLESS_NETWORK=os.environ.get('GLEANERIO_DOCKER_HEADLESS_NETWORK'),
            GLEANERIO_HEADLESS_ENDPOINT=os.environ.get('GLEANERIO_HEADLESS_ENDPOINT'),

            GLEANERIO_GLEANER_IMAGE=os.environ.get('GLEANERIO_GLEANER_IMAGE'),
            GLEANERIO_NABU_IMAGE=os.environ.get('GLEANERIO_NABU_IMAGE'),

             GLEANERIO_GLEANER_CONFIG_PATH=os.environ.get('GLEANERIO_GLEANER_CONFIG_PATH'),

            GLEANERIO_LOG_PREFIX=os.environ.get('GLEANERIO_LOG_PREFIX'),

            GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT=os.environ.get('GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT',600),
            GLEANERIO_GRAPH_NAMESPACE=os.environ.get('GLEANERIO_GRAPH_NAMESPACE'),
            GLEANERIO_GRAPH_SUMMARY_NAMESPACE=os.environ.get('GLEANERIO_GRAPH_SUMMARY_NAMESPACE'),
            gs3=gleaners3,
            triplestore=Gdbtriplestore,
            triplestore_summary=Gdbtriplestore_summary
        )

resources = {
    "local": {
        "gleanerio": gleanerio, # gleaner
        "s3":s3,
        "gs3":gleaners3,
        "triplestore": triplestore,
        "slack": SlackResource(token=EnvVar("SLACK_TOKEN")),
    },
    "localGdb": {
        "gleanerio": Gdbgleanerio,  # gleaner
        "s3": s3,
        "gs3": gleaners3,
        "triplestore": Gdbtriplestore,
        "slack": SlackResource(token=EnvVar("SLACK_TOKEN")),
    },
    "production": {
        "gleanerio": gleanerio, # gleaner
        # this nees to be s3 so s3 can find it.
        "s3":s3,
        "gs3":gleaners3,
        "triplestore":triplestore,
        "slack":SlackResource(token=EnvVar("SLACK_TOKEN")),
    },
    "productionGdb": {
        "gleanerio": Gdbgleanerio,  # gleaner
        "s3": s3,
        "gs3": gleaners3,
        "triplestore": Gdbtriplestore,
        "slack": SlackResource(token=EnvVar("SLACK_TOKEN")),
    },
}

deployment_name = os.environ.get("DAGSTER_DEPLOYMENT", "local")
get_dagster_logger().info(f"Deployment name: {deployment_name}")


defs = Definitions(
    assets=all_assets,
    resources=resources[deployment_name],
    sensors=all_sensors,
    jobs=jobs,
    schedules=all_schedules
#    jobs=[harvest_job]

)
