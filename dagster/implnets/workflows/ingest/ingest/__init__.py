from dagster import Definitions, load_assets_from_modules
from dagster_aws.s3.resources import S3Resource
from dagster_aws.s3.ops import S3Coordinate

from resources.triplestore import BlazegraphResource
from resources.gleanerio import GleanerioResource
from resources.docker import DockerResource

from . import assets

all_assets = load_assets_from_modules([assets])

defs = Definitions(
    assets=all_assets,
)

DAGSTER_GLEANER_CONFIG_PATH: str = Field(
    description="DAGSTER_GLEANER_CONFIG_PATH for Project.")
GLEANER_HEADLESS_NETWORK: str = Field(
    description="GLEANER_HEADLESS_NETWORK.")
GLEANERIO_GLEANER_CONFIG_PATH: str = Field(
    description="GLEANERIO_GLEANER_CONFIG_PATH.")
GLEANERIO_GLEANER_IMAGE: str = Field(
    description="GLEANERIO_GLEANER_IMAGE.")
GLEANERIO_NABU_IMAGE: str = Field(
    description="GLEANERIO_NABU_IMAGE.")
GLEANERIO_LOG_PREFIX: str = Field(
    description="GLEANERIO_LOG_PREFIX.")
GLEANERIO_GLEANER_DOCKER_CONFIG: str = Field(
    description="GLEANERIO_GLEANER_DOCKER_CONFIG.")
GLEANERIO_NABU_DOCKER_CONFIG: str = Field(
    description="GLEANERIO_NABU_DOCKER_CONFIG.")
resources = {
    "local": {
        "gleanerio": GleanerioResource(
            DAGSTER_GLEANER_CONFIG_PATH=EnvVar('DAGSTER_GLEANER_CONFIG_PATH'),
            GLEANER_HEADLESS_NETWORK=EnvVar('GLEANER_HEADLESS_NETWORK'),
            GLEANERIO_GLEANER_CONFIG_PATH=EnvVar('GLEANERIO_GLEANER_CONFIG_PATH'),
            GLEANERIO_NABU_DOCKER_CONFIG=EnvVar('GLEANERIO_NABU_DOCKER_CONFIG'),
            GLEANERIO_GLEANER_DOCKER_CONFIG=EnvVar('GLEANERIO_GLEANER_DOCKER_CONFIG'),
            GLEANERIO_NABU_CONFIG_PATH=EnvVar('GLEANERIO_NABU_CONFIG_PATH'),
            GLEANERIO_GLEANER_IMAGE=EnvVar('GLEANERIO_GLEANER_IMAGE'),
            GLEANERIO_NABU_IMAGE=EnvVar('GLEANERIO_NABU_IMAGE'),
            GLEANERIO_LOG_PREFIX=EnvVar('GLEANERIO_LOG_PREFIX'),

        ),
        "minio": S3Resource(),
        "triplestore": BlazegraphResource(
            GLEANER_GRAPH_URL=EnvVar('GLEANER_GRAPH_URL'),
            GLEANER_GRAPH_NAMESPACE=EnvVar('GLEANER_GRAPH_NAMESPACE'),
        ),
        "triplestore_summary": BlazegraphResource(
            GLEANER_GRAPH_URL=EnvVar('GLEANER_GRAPH_URL'),
            GLEANER_GRAPH_NAMESPACE=EnvVar('GLEANER_GRAPH_NAMESPACE'),
        ),
        "docker": DockerResource(
            DOCKER_URL=EnvVar('DOCKER_URL'),
            DOCKER_PORTAINER_APIKEY=EnvVar('DOCKER_PORTAINER_APIKEY'),
            DOCKER_CONTAINER_WAIT_TIMEOUT=EnvVar('DOCKER_CONTAINER_WAIT_TIMEOUT'),
        )
    },
    "production": {
        "gleanerio": GleanerioResource(
            account="abc1234.us-east-1",
            user=EnvVar("DEV_SNOWFLAKE_USER"),
            password=EnvVar("DEV_SNOWFLAKE_PASSWORD"),
            database="LOCAL",
            schema=EnvVar("DEV_SNOWFLAKE_SCHEMA"),
        ),
        "minio": S3Resource(),
        "triplestore": BlazegraphResource(),
        "docker": DockerResource()
    },
}

deployment_name = os.getenv("DAGSTER_DEPLOYMENT", "local")

defs = Definitions(
    assets=[items, comments, stories], resources=resources[deployment_name]
)
