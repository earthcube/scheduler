from dagster import Definitions, load_assets_from_modules, EnvVar
from dagster_aws.s3.resources import S3Resource
from dagster_aws.s3.ops import S3Coordinate

from resources.graph import BlazegraphResource
from resources.gleanerio import GleanerioResource

from pydantic import Field
from . import assets

all_assets = load_assets_from_modules([assets])


resources = {
    "local": {
        "gleanerio": GleanerioResource(
            DEBUG=EnvVar('DEBUG'),

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


        ),
        "minio": S3Resource(),
        "triplestore": BlazegraphResource(
            GLEANERIO_GRAPH_URL=EnvVar('GLEANERIO_GRAPH_URL'),
            GLEANERIO_GRAPH_NAMESPACE=EnvVar('GLEANERIO_GRAPH_NAMESPACE'),
        ),
        "triplestore_summary": BlazegraphResource(
            GLEANERIO_GRAPH_URL=EnvVar('GLEANERIO_GRAPH_URL'),
            GLEANERIO_GRAPH_NAMESPACE=EnvVar('GLEANERIO_GRAPH_SUMMARY_NAMESPACE'),
        ),

    },
    "production": {
        "gleanerio": GleanerioResource(
            DEBUG=EnvVar('DEBUG'),

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


        ),
        "minio": S3Resource(),
        "triplestore": BlazegraphResource(),

    },
}

deployment_name = EnvVar("DAGSTER_DEPLOYMENT", "local")

defs = Definitions(
    assets=all_assets, resources=resources[deployment_name]
)
