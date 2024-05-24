from dagster import (
    op, job, Config,
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

from ..assets import gleanerio_tenants, tenant_partitions_def, sources_partitions_def, upload_release,upload_summary
from ..assets.tenant import create_tenant_containers, create_graph_namespaces
from ..resources.gleanerio import GleanerioResource
from ..resources.gleanerS3 import gleanerS3Resource
from ..resources.graph import BlazegraphResource






release_asset_job = define_asset_job(
    name="tenant_release_job",
    selection=AssetSelection.assets(upload_release,upload_summary),
    partitions_def=sources_partitions_def,
)

tenant_create_job = define_asset_job(
    name="tenant_create_job",
    selection=AssetSelection.assets(create_tenant_containers, create_graph_namespaces),
    partitions_def=tenant_partitions_def,
)

# @job(partitions_def=tenant_partitions_def)
# def tenant_create_job(context):
#     source_name = context.asset_partition_key_for_output()
#     context.log.info(f"tennant_name {source_name}")
#     create_tenant_containers(create_graph_namespaces())


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
@dynamic_partitioned_config(partition_fn=gleanerio_tenants)
def tenant_config(partition_key: str):

    # default_config ={"ops": {
    #     "upload_release":
    #         {"config":
    #             {
    #                 TennantConfig(
    #                     source_name=partition_key,
    #                     name="name",
    #                     source_list=[],
    #                     TENNANT_GRAPH_NAMESPACE="",
    #                     TENNANT_GRAPH_SUMMARY_NAMESPACE=""
    #                 )
    #             }
    #             }
    #         },
    #     "upload_summary":
    #         {"config":
    #             {
    #                 TennantConfig(
    #                 source_name=partition_key,
    #                 name="name",
    #                 source_list=[],
    #                 TENNANT_GRAPH_NAMESPACE="",
    #                 TENNANT_GRAPH_SUMMARY_NAMESPACE=""
    #                 )
    #             }
    #         }
    #     }
    default_config = {"ops": {
        {"upload_release": {"config": {"source_name": partition_key}}},
        {"upload_summary": {"config": {"source_name": partition_key}}}
    }}
    return default_config
