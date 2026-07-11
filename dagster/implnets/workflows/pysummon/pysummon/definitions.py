# Dagster Definitions for the pysummon project.
#
# Load alongside the pipeline project as a second code location:
#   load_from:
#     - python_module: {module_name: pipeline.definitions, location_name: pipeline}
#     - python_module: {module_name: pysummon.definitions, location_name: pysummon}
#
# Env: PROJECT, GLEANERIO_MINIO_* (shared with pipeline),
# PYSUMMON_DATA_PREFIX (default 'pysummon/'; "" to take over the legacy
# layout), PYSUMMON_HEADLESS_ENDPOINT (falls back to
# GLEANERIO_HEADLESS_ENDPOINT, default http://headless:9222),
# PYSUMMON_SCHEDULE (falls back to GLEANERIO_DEFAULT_SCHEDULE).
import os

from dagster import Definitions, EnvVar, load_assets_from_modules
from dagster_aws.s3.resources import S3Resource
from pipeline.resources.gleanerS3 import gleanerS3Resource

from . import assets as assets_module
from .resources.headless import HeadlessResource
from .jobs import pysummon_source_job, pysummon_config_job, pysummon_publish_job
from .schedules import pysummon_schedule
from .sensors import (
    pysummon_sources_sensor, pysummon_config_files_sensor, pysummon_publish_sensor,
)


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

headless = HeadlessResource(
    HEADLESS_ENDPOINT=os.environ.get(
        'PYSUMMON_HEADLESS_ENDPOINT',
        os.environ.get('GLEANERIO_HEADLESS_ENDPOINT', 'http://headless:9222')),
)

defs = Definitions(
    assets=load_assets_from_modules([assets_module]),
    resources={
        "s3": s3,
        "gs3": gleaners3,
        "headless": headless,
    },
    jobs=[pysummon_source_job, pysummon_config_job, pysummon_publish_job],
    schedules=[pysummon_schedule],
    sensors=[pysummon_sources_sensor, pysummon_config_files_sensor,
             pysummon_publish_sensor],
)
