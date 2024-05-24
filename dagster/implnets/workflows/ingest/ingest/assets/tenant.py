from dagster import (
    op, job, Config,asset,
In, Nothing,
    sensor, RunRequest, RunConfig,
    SensorEvaluationContext, asset_sensor, EventLogEntry,
    SkipReason,
    AssetKey,
    static_partitioned_config, dynamic_partitioned_config, DynamicPartitionsDefinition,
    define_asset_job, AssetSelection,graph_asset
)

from dagster_aws.s3.sensor import get_s3_keys
from typing import List, Dict
from pydantic import Field

from ..assets import gleanerio_tennants, tenant_partitions_def, sources_partitions_def

class TenantConfig(Config):
    source_name: str
    name: str
    source_list: List[str]
    TENNANT_GRAPH_NAMESPACE: str
    TENNANT_GRAPH_SUMMARY_NAMESPACE: str
    SUMMARY_PATH: str =  Field(
         description="GLEANERIO_GRAPH_SUMMARY_PATH.", default='graphs/summary')
    RELEASE_PATH : str =  Field(
         description="GLEANERIO_GRAPH_RELEASE_PATH.", default='graphs/latest')


class TenantOpConfig(Config):
    source_name: str
@asset(group_name="tenant_load",required_resource_keys={"gleanerio",},partitions_def=sources_partitions_def)
#def upload_release(context, config:TennantOpConfig  ):
def upload_release(context ):
    #context.log.info(config.source_name)
    source_name = context.asset_partition_key_for_output()
    context.log.info(f"tennant_name {source_name}")
    gleaner_resource = context.resources.gleanerio
    s3_resource = context.resources.gleanerio.gs3.s3
    gleaner_s3 = context.resources.gleanerio.gs3
    triplestore = context.resources.gleanerio.triplestore
    pass

#@asset(required_resource_keys={"gleanerio",},ins={"start": In(Nothing)})
@asset(group_name="tenant_load",required_resource_keys={"gleanerio",},partitions_def=sources_partitions_def)
#def upload_summary(context, config:TennantOpConfig):
def upload_summary(context):
    #context.log.info(config.source_name)
    source_name = context.asset_partition_key_for_output()
    context.log.info(f"tennant_name {source_name}")
    gleaner_resource = context.resources.gleanerio
    s3_resource = context.resources.gleanerio.gs3.s3
    gleaner_s3 = context.resources.gleanerio.gs3
    triplestore = context.resources.gleanerio.triplestore
    pass
#
# @asset(group_name="tenant_create",required_resource_keys={"gleanerio",},partitions_def=tenant_partitions_def)
# def create_graph_namespaces(context):
#     #context.log.info(config.source_name)
#     source_name = context.asset_partition_key_for_output()
#     context.log.info(f"tennant_name {source_name}")
#     gleaner_resource = context.resources.gleanerio
#     s3_resource = context.resources.gleanerio.gs3.s3
#     gleaner_s3 = context.resources.gleanerio.gs3
#     triplestore = context.resources.gleanerio.triplestore
#     pass
@asset(group_name="tenant_create",required_resource_keys={"gleanerio",},partitions_def=tenant_partitions_def)
def create_graph_namespaces(context):
    #context.log.info(config.source_name)
    source_name = context.asset_partition_key_for_output()
    context.log.info(f"tennant_name {source_name}")
    gleaner_resource = context.resources.gleanerio
    s3_resource = context.resources.gleanerio.gs3.s3
    gleaner_s3 = context.resources.gleanerio.gs3
    triplestore = context.resources.gleanerio.triplestore
    pass
@asset(group_name="tenant_create",required_resource_keys={"gleanerio",},partitions_def=tenant_partitions_def)
def create_tenant_containers(context):
    #context.log.info(config.source_name)
    source_name = context.asset_partition_key_for_output()
    context.log.info(f"tennant_name {source_name}")
    gleaner_resource = context.resources.gleanerio
    s3_resource = context.resources.gleanerio.gs3.s3
    gleaner_s3 = context.resources.gleanerio.gs3
    triplestore = context.resources.gleanerio.triplestore
    pass
#@static_partitioned_config(partition_keys=TENNANT_NAMES)

    #return {"ops": {"continent_op": {"config": {"continent_name": partition_key}}}}
#@job(config=tennant_config, partitions_def=tenant_partitions_def)
# @job( partitions_def=tenant_partitions_def)
# def build_community():
#     source_name = context.asset_partition_key_for_output()
#     context.log.info(f"tennant_name {source_name}")
#     upload_summary(upload_release())
