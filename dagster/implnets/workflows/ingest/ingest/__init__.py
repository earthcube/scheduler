import os

from dagster import Definitions, load_assets_from_modules, EnvVar
from dagster_aws.s3.resources import S3Resource
from dagster_aws.s3.ops import S3Coordinate

from .resources.graph import BlazegraphResource, GraphResource
from .resources.gleanerio import GleanerioResource
from .resources.gleanerS3 import gleanerS3Resource

from pydantic import Field
from . import assets

all_assets = load_assets_from_modules([assets])

minio=gleanerS3Resource(
    # GLEANER_MINIO_BUCKET =EnvVar('GLEANER_MINIO_BUCKET'),
    # GLEANER_MINIO_ADDRESS=EnvVar('GLEANER_MINIO_ADDRESS'),
    # GLEANER_MINIO_PORT=EnvVar('GLEANER_MINIO_PORT'),
    GLEANERIO_MINIO_BUCKET=EnvVar('GLEANERIO_MINIO_BUCKET'),
    GLEANERIO_MINIO_ADDRESS=EnvVar('GLEANERIO_MINIO_ADDRESS'),
    GLEANERIO_MINIO_PORT=EnvVar('GLEANERIO_MINIO_PORT'),
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
            DEBUG=False,
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

            GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT=EnvVar('GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT'),
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
        ) # gleaner


    },
    "production": {
        "gleanerio": GleanerioResource(
            DEBUG=False,

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

            GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT=EnvVar('GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT'),
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

        ),


    },
}

deployment_name = os.environ.get("DAGSTER_DEPLOYMENT", "local")

defs = Definitions(
    assets=all_assets, resources=resources[deployment_name]
)
