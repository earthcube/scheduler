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

from dagster import Definitions, load_assets_from_modules, EnvVar
from dagster_aws.s3.resources import S3Resource
from dagster_aws.s3.ops import S3Coordinate
from dagster import (
    AssetSelection,
    Definitions,
    define_asset_job,
)
from dagster_slack import SlackResource, make_slack_on_run_failure_sensor

from .resources.graph import BlazegraphResource, GraphResource
from .resources.gleanerio import GleanerioResource
from .resources.gleanerS3 import gleanerS3Resource
from .assets import gleanerio_run, nabu_release_run, sources_partitions_def
from pydantic import Field

from . import assets

all_assets = load_assets_from_modules([assets])

from .sensors import release_file_sensor
slack_on_run_failure = make_slack_on_run_failure_sensor(
     os.getenv("SLACK_CHANNEL"),
    os.getenv("SLACK_TOKEN")
)
all_sensors = [slack_on_run_failure, release_file_sensor]

def _pythonMinioAddress(url, port=None):
    if (url.endswith(".amazonaws.com")):
        PYTHON_MINIO_URL = "s3.amazonaws.com"
    else:
        PYTHON_MINIO_URL = url
    if port is not None:
        PYTHON_MINIO_URL = f"{PYTHON_MINIO_URL}:{port}"
    return PYTHON_MINIO_URL
def _awsEndpointAddress(url, port=None, use_ssl=True):
    if use_ssl:
        protocol = "https"
    else:
        protocol = "http"
    if port is not None:
        return  f"{protocol}://{url}:{port}"
    else:
        return  f"{protocol}://{url}"


minio=gleanerS3Resource(
    # GLEANER_MINIO_BUCKET =EnvVar('GLEANER_MINIO_BUCKET'),
    # GLEANER_MINIO_ADDRESS=EnvVar('GLEANER_MINIO_ADDRESS'),
    # GLEANER_MINIO_PORT=EnvVar('GLEANER_MINIO_PORT'),
    GLEANERIO_MINIO_BUCKET=EnvVar('GLEANERIO_MINIO_BUCKET'),
    GLEANERIO_MINIO_ADDRESS=EnvVar('GLEANERIO_MINIO_ADDRESS'),
    GLEANERIO_MINIO_PORT=EnvVar('GLEANERIO_MINIO_PORT'),
    GLEANERIO_MINIO_ACCESS_KEY=EnvVar('GLEANERIO_MINIO_ACCESS_KEY'),
    GLEANERIO_MINIO_SECRET_KEY=EnvVar('GLEANERIO_MINIO_SECRET_KEY'),
    endpoint_url =_awsEndpointAddress(EnvVar('GLEANERIO_MINIO_ADDRESS').get_value(), port=EnvVar('GLEANERIO_MINIO_PORT').get_value()),
    aws_access_key_id=EnvVar('GLEANERIO_MINIO_ACCESS_KEY'),
    aws_secret_access_key=EnvVar('GLEANERIO_MINIO_SECRET_KEY')
)
triplestore=BlazegraphResource(
            GLEANERIO_GRAPH_URL=EnvVar('GLEANERIO_GRAPH_URL'),
            GLEANERIO_GRAPH_NAMESPACE=EnvVar('GLEANERIO_GRAPH_NAMESPACE'),
        )
triplestore_summary=BlazegraphResource(
            GLEANERIO_GRAPH_URL=EnvVar('GLEANERIO_GRAPH_URL'),
            GLEANERIO_GRAPH_NAMESPACE=EnvVar('GLEANERIO_GRAPH_SUMMARY_NAMESPACE'),
        )

resources = {
    "local": {
        "gleanerio": GleanerioResource(
#            DEBUG=os.environ.get('DEBUG'),
            DEBUG_CONTAINER=False,
            GLEANERIO_DOCKER_URL=EnvVar('GLEANERIO_DOCKER_URL'),
            GLEANERIO_PORTAINER_APIKEY=EnvVar('GLEANERIO_PORTAINER_APIKEY'),

            GLEANERIO_DOCKER_HEADLESS_NETWORK=EnvVar('GLEANERIO_DOCKER_HEADLESS_NETWORK'),
            GLEANERIO_HEADLESS_ENDPOINT=EnvVar('GLEANERIO_HEADLESS_ENDPOINT'),

            GLEANERIO_GLEANER_IMAGE=EnvVar('GLEANERIO_GLEANER_IMAGE'),
            GLEANERIO_NABU_IMAGE=EnvVar('GLEANERIO_NABU_IMAGE'),

            GLEANERIO_DAGSTER_CONFIG_PATH=EnvVar('GLEANERIO_DAGSTER_CONFIG_PATH'),


            GLEANERIO_DOCKER_NABU_CONFIG=EnvVar('GLEANERIO_DOCKER_NABU_CONFIG'),
            GLEANERIO_DOCKER_GLEANER_CONFIG=EnvVar('GLEANERIO_DOCKER_GLEANER_CONFIG'),

            GLEANERIO_NABU_CONFIG_PATH=EnvVar('GLEANERIO_NABU_CONFIG_PATH'),
            GLEANERIO_GLEANER_CONFIG_PATH=EnvVar('GLEANERIO_GLEANER_CONFIG_PATH'),

            GLEANERIO_LOG_PREFIX=EnvVar('GLEANERIO_LOG_PREFIX'),

            GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT=os.environ.get('GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT',600),
            GLEANERIO_GRAPH_NAMESPACE=EnvVar('GLEANERIO_GRAPH_NAMESPACE'),
            GLEANERIO_GRAPH_SUMMARY_NAMESPACE=EnvVar('GLEANERIO_GRAPH_SUMMARY_NAMESPACE'),
            s3=minio,
            # s3=gleanerS3Resource(
            #     GLEANERIO_MINIO_ADDRESS="oss.geocodes-aws-dev.earthcube.org",
            #         GLEANERIO_MINIO_PORT=443,
            #         GLEANERIO_MINIO_USE_SSL=True,
            #         GLEANERIO_MINIO_BUCKET="test",
            #         GLEANERIO_MINIO_ACCESS_KEY="worldsbestaccesskey",
            #         GLEANERIO_MINIO_SECRET_KEY="worldsbestsecretkey",
            #         ),
            triplestore=triplestore,
            # triplestore=BlazegraphResource(
            #     GLEANERIO_GRAPH_URL=EnvVar('GLEANERIO_GRAPH_URL'),
            #     GLEANERIO_GRAPH_NAMESPACE=EnvVar('GLEANERIO_GRAPH_NAMESPACE'),
            #     ),
            triplestore_summary=BlazegraphResource(
                GLEANERIO_GRAPH_URL=EnvVar('GLEANERIO_GRAPH_URL'),
                GLEANERIO_GRAPH_NAMESPACE=EnvVar('GLEANERIO_GRAPH_SUMMARY_NAMESPACE'),
            )
        ), # gleaner
        "s3":minio,
        "triplestore": triplestore,
        "slack": SlackResource(token=EnvVar("SLACK_TOKEN")),
    },
    "production": {
        "gleanerio": GleanerioResource(
            DEBUG_CONTAINER=False,

            GLEANERIO_DOCKER_URL=EnvVar('GLEANERIO_DOCKER_URL'),
            GLEANERIO_PORTAINER_APIKEY=EnvVar('GLEANERIO_PORTAINER_APIKEY'),

            GLEANERIO_DOCKER_HEADLESS_NETWORK=EnvVar('GLEANERIO_DOCKER_HEADLESS_NETWORK'),
            GLEANERIO_HEADLESS_ENDPOINT=EnvVar('GLEANERIO_HEADLESS_ENDPOINT'),

            GLEANERIO_GLEANER_IMAGE=EnvVar('GLEANERIO_GLEANER_IMAGE'),
            GLEANERIO_NABU_IMAGE=EnvVar('GLEANERIO_NABU_IMAGE'),

            GLEANERIO_DAGSTER_CONFIG_PATH=EnvVar('GLEANERIO_DAGSTER_CONFIG_PATH'),


            GLEANERIO_DOCKER_NABU_CONFIG=EnvVar('GLEANERIO_DOCKER_NABU_CONFIG'),
            GLEANERIO_DOCKER_GLEANER_CONFIG=EnvVar('GLEANERIO_DOCKER_GLEANER_CONFIG'),

            GLEANERIO_NABU_CONFIG_PATH=EnvVar('GLEANERIO_NABU_CONFIG_PATH'),
            GLEANERIO_GLEANER_CONFIG_PATH=EnvVar('GLEANERIO_GLEANER_CONFIG_PATH'),

            GLEANERIO_LOG_PREFIX=EnvVar('GLEANERIO_LOG_PREFIX'),

            GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT=os.environ.get('GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT',600),
GLEANERIO_GRAPH_NAMESPACE=EnvVar('GLEANERIO_GRAPH_NAMESPACE'),
GLEANERIO_GRAPH_SUMMARY_NAMESPACE=EnvVar('GLEANERIO_GRAPH_SUMMARY_NAMESPACE'),
            s3=gleanerS3Resource(
                GLEANERIO_MINIO_ADDRESS="oss.geocodes-aws-dev.earthcube.org",
                GLEANERIO_MINIO_PORT=443,
                GLEANERIO_MINIO_USE_SSL=True,
                GLEANERIO_MINIO_BUCKET="test",
                GLEANERIO_MINIO_ACCESS_KEY="worldsbestaccesskey",
                GLEANERIO_MINIO_SECRET_KEY="worldsbestsecretkey",
            ),
            triplestore=BlazegraphResource(
                GLEANERIO_GRAPH_URL=EnvVar('GLEANERIO_GRAPH_URL'),
                GLEANERIO_GRAPH_NAMESPACE=EnvVar('GLEANERIO_GRAPH_NAMESPACE'),
            ),
            triplestore_summary=BlazegraphResource(
                GLEANERIO_GRAPH_URL=EnvVar('GLEANERIO_GRAPH_URL'),
                GLEANERIO_GRAPH_NAMESPACE=EnvVar('GLEANERIO_GRAPH_SUMMARY_NAMESPACE'),
            )

        ), # gleaner
        "s3":minio,
        "triplestore":triplestore,
        "slack":SlackResource(token=EnvVar("SLACK_TOKEN")),
    },
}

deployment_name = os.environ.get("DAGSTER_DEPLOYMENT", "local")


# partitioned_asset_job = define_asset_job(
#     name="summon_and_release_job",
#     selection=AssetSelection.assets(gleanerio_run, nabu_release_run),
#     partitions_def=sources_partitions_def,
# )

defs = Definitions(
    assets=all_assets,
    resources=resources[deployment_name],
    sensors=all_sensors

)
