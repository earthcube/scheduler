# Dagster Definitions for the phased geocodes ingest pipeline.
#
# Load with a python_module workspace entry:
#   load_from:
#     - python_module:
#         module_name: pipeline.definitions
#         location_name: pipeline
#
# Required env vars: PROJECT, GLEANERIO_MINIO_* (address/port/ssl/bucket/keys),
# GLEANERIO_DOCKER_URL, GLEANERIO_DOCKER_HEADLESS_NETWORK,
# GLEANERIO_GLEANER_IMAGE, GLEANERIO_LOG_PREFIX, QLEVER_CONTAINER_NAME.
# Optional: SLACK_TOKEN/SLACK_CHANNEL (failure notifications),
# GLEANERIO_DEFAULT_SCHEDULE (default @weekly).
import os

from dagster import Definitions, EnvVar, load_assets_from_modules, RunFailureSensorContext
from dagster_aws.s3.resources import S3Resource

from . import assets as assets_module
from .resources.gleanerio import GleanerioResource
from .resources.gleanerS3 import gleanerS3Resource
from .resources.qlever import QleverResource
from .jobs import pipeline_source_job, sources_config_job, qlever_rebuild_job
from .schedules import pipeline_schedule
from .sensors import pipeline_sources_sensor, config_files_sensor, qlever_rebuild_sensor


def _awsEndpointAddress(url, port=None, use_ssl=True):
    protocol = "https" if use_ssl else "http"
    if port is not None and port != "":
        return f"{protocol}://{url}:{port}"
    return f"{protocol}://{url}"


def _truthy(value):
    return str(value).lower() in ("1", "true", "yes", "on")


s3 = S3Resource(
    endpoint_url=_awsEndpointAddress(
        os.environ.get('GLEANERIO_MINIO_ADDRESS'),
        port=os.environ.get('GLEANERIO_MINIO_PORT'),
        use_ssl=_truthy(os.environ.get('GLEANERIO_MINIO_USE_SSL', "true")),
    ),
    aws_access_key_id=EnvVar('GLEANERIO_MINIO_ACCESS_KEY'),
    aws_secret_access_key=EnvVar('GLEANERIO_MINIO_SECRET_KEY'),
)

gleaners3 = gleanerS3Resource(
    GLEANERIO_MINIO_BUCKET=os.environ.get('GLEANERIO_MINIO_BUCKET'),
    GLEANERIO_MINIO_ADDRESS=os.environ.get('GLEANERIO_MINIO_ADDRESS'),
    GLEANERIO_MINIO_PORT=os.environ.get('GLEANERIO_MINIO_PORT'),
    GLEANERIO_MINIO_USE_SSL=_truthy(os.environ.get('GLEANERIO_MINIO_USE_SSL', "true")),
    GLEANERIO_MINIO_ACCESS_KEY=EnvVar('GLEANERIO_MINIO_ACCESS_KEY'),
    GLEANERIO_MINIO_SECRET_KEY=EnvVar('GLEANERIO_MINIO_SECRET_KEY'),
    GLEANERIO_CONFIG_PATH=os.environ.get(
        'GLEANERIO_CONFIG_PATH',
        os.environ.get('GLEANERIO_DAGSTER_CONFIG_PATH', "scheduler/configs/")),
    s3=s3,
)

gleanerio = GleanerioResource(
    DEBUG_CONTAINER=False,
    GLEANERIO_DOCKER_URL=os.environ.get('GLEANERIO_DOCKER_URL', 'unix:///var/run/docker.sock'),
    GLEANERIO_PORTAINER_APIKEY=os.environ.get('GLEANERIO_PORTAINER_APIKEY', 'not-used'),
    GLEANERIO_DOCKER_HEADLESS_NETWORK=os.environ.get(
        'GLEANERIO_DOCKER_HEADLESS_NETWORK', 'headless_gleanerio'),
    GLEANERIO_HEADLESS_ENDPOINT=os.environ.get(
        'GLEANERIO_HEADLESS_ENDPOINT', 'http://headless:9222'),
    GLEANERIO_GLEANER_IMAGE=os.environ.get(
        'GLEANERIO_GLEANER_IMAGE', 'nsfearthcube/gleaner:latest'),
    GLEANERIO_LOG_PREFIX=os.environ.get('GLEANERIO_LOG_PREFIX', 'scheduler/logs/'),
    GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT=int(
        os.environ.get('GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT', 600)),
    gs3=gleaners3,
)

qlever = QleverResource(
    QLEVER_CONTAINER_NAME=os.environ.get('QLEVER_CONTAINER_NAME', 'geocodes_qlever'),
    QLEVER_SPARQL_ENDPOINT=os.environ.get('QLEVER_SPARQL_ENDPOINT', 'http://qlever:7019'),
    QLEVER_DOCKER_URL=os.environ.get('GLEANERIO_DOCKER_URL', 'unix:///var/run/docker.sock'),
    QLEVER_HEALTH_TIMEOUT=int(os.environ.get('QLEVER_HEALTH_TIMEOUT', '600')),
)

resources = {
    "gleanerio": gleanerio,
    "s3": s3,
    "gs3": gleaners3,
    "qlever": qlever,
}

all_sensors = [pipeline_sources_sensor, config_files_sensor, qlever_rebuild_sensor]

# Slack failure notifications only when a token is configured; the simplified
# single-tenant deployment usually runs without Slack.
if os.environ.get("SLACK_TOKEN") and os.environ.get("SLACK_CHANNEL"):
    try:
        from dagster_slack import make_slack_on_run_failure_sensor

        def _slack_message_fn(context: RunFailureSensorContext) -> str:
            return (f"Partition for Source *[{context.partition_key}]* failed! "
                    f"Error: {context.failure_event.message}")

        all_sensors.append(make_slack_on_run_failure_sensor(
            os.getenv("SLACK_CHANNEL"),
            os.getenv("SLACK_TOKEN"),
            text_fn=_slack_message_fn,
        ))
    except ImportError:
        import logging
        logging.getLogger(__name__).warning(
            "SLACK_TOKEN set but dagster_slack not installed; "
            "failure notifications disabled")

defs = Definitions(
    assets=load_assets_from_modules([assets_module]),
    resources=resources,
    jobs=[pipeline_source_job, sources_config_job, qlever_rebuild_job],
    schedules=[pipeline_schedule],
    sensors=all_sensors,
)
