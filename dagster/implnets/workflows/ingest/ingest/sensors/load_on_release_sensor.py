from dagster import (
op, job, Config,
sensor, RunRequest, RunConfig,
SensorEvaluationContext,asset_sensor, EventLogEntry,
SkipReason
)
from dagster_aws.s3.sensor import get_s3_keys
from typing import List, Dict
from pydantic import Field

from ..resources.gleanerio import GleanerioResource
from ..resources.gleanerS3 import gleanerS3Resource
from ..resources.graph import BlazegraphResource

class TennantConfig(Config):
    name: str
    source_list: List[str]
    TENNANT_GRAPH_NAMESPACE: str
    TENNANT_GRAPH_SUMMARY_NAMESPACE: str
    SUMMARY_PATH: str =  Field(
         description="GLEANERIO_GRAPH_SUMMARY_PATH.", default='graphs/summary')
    RELEASE_PATH : str =  Field(
         description="GLEANERIO_GRAPH_RELEASE_PATH.", default='graphs/latest')

@op(required_resource_keys={"gs3","triplestore",})
def upload_release(context, config:TennantConfig  ):
    context.log.info(config.name)

@op(required_resource_keys={"gs3","triplestore"})
def upload_summary(context, config:TennantConfig):
    context.log.info(config.name)
# Put the config for a tennant at the job level so we only have to define it once
default_config = RunConfig(
    ops={"upload_release": TennantConfig(
        name="name",
source_list=[],
TENNANT_GRAPH_NAMESPACE="",
TENNANT_GRAPH_SUMMARY_NAMESPACE=""
    ),
        "upload_summary": TennantConfig(
            name="name",
            source_list=[],
            TENNANT_GRAPH_NAMESPACE="",
            TENNANT_GRAPH_SUMMARY_NAMESPACE=""
        )
    }
)
@job(config=default_config)
def build_community():
    upload_release()
    upload_summary()
@sensor(

    job=build_community,
    #minimum_interval_seconds=60
)
def release_file_sensor(context,config: TennantConfig, gleanerio:GleanerioResource, gs3:gleanerS3Resource, triplestore: BlazegraphResource ):
    since_key = context.cursor or None
    new_s3_keys = get_s3_keys(gs3.GLEANERIO_MINIO_BUCKET, prefix=config.RELEASE_PATH, since_key=since_key)
    if not new_s3_keys:
        return SkipReason(f"No new s3 files found for bucket {gs3.GLEANERIO_MINIO_BUCKET}.")
    last_key = new_s3_keys[-1]
    run_requests = [RunRequest(run_key=s3_key, run_config={}) for s3_key in new_s3_keys]
    context.update_cursor(last_key)
    return run_requests
