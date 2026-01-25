from dagster import (
    op, job, Config,asset,
    In, Nothing,
    sensor, RunRequest, RunConfig,
    SensorEvaluationContext, asset_sensor, EventLogEntry,
    SkipReason,
    AssetKey,
    static_partitioned_config, dynamic_partitioned_config, DynamicPartitionsDefinition,
    define_asset_job, AssetSelection,graph_asset,
    get_dagster_logger
)

from dagster_aws.s3.sensor import get_s3_keys
from typing import List, Dict
from pydantic import Field
import pydash

#from pydash.collections import find
#from pydash.predicates import is_match
from ec.graph.manageGraph import ManageBlazegraph
from ..assets import gleanerio_tenants, tenant_partitions_def, sources_partitions_def
from .gleaner_summon_assets import RELEASE_PATH, SUMMARY_PATH
from ..resources.graph import get_graph_resource_for_tenant

import os

PROJECT=os.environ.get('PROJECT')
class TenantConfig(Config):
    source_name: str
    name: str
    source_list: List[str]
    TENANT_GRAPH_NAMESPACE: str
    TENANT_GRAPH_SUMMARY_NAMESPACE: str
    SUMMARY_PATH: str =  Field(
         description="GLEANERIO_GRAPH_SUMMARY_PATH.", default='graphs/summary')
    RELEASE_PATH : str =  Field(
         description="GLEANERIO_GRAPH_RELEASE_PATH.", default='graphs/latest')


class TenantOpConfig(Config):
    source_name: str

def find_tenants_with_source(context, source_name, tenats_all):
    get_dagster_logger().info(f" find tenant  {source_name} with {tenats_all}")
    tenants =[]
    # tenants = pydash.collections.find(tenats_all,
    #            lambda t: p    ydash.predicates.is_match(t["sources"], source_name) or pydash.predicates.is_match(t["sources"], 'all')
    #                                   )
    #tenants = pydash.collections.find(tenats_all,  lambda t: pydash.predicates.is_match(t["sources"], "all") )
    for tenant in tenats_all:
        get_dagster_logger().info(f"  {tenant['community']} sources {tenant['sources']}")
        if source_name in tenant["sources"]:
            get_dagster_logger().info(f" found source  {source_name} in {tenant['community']}")
            tenants.append(tenant)
        if 'all' in tenant["sources"]:
            get_dagster_logger().info(f" found source  all in {tenant['community']}")
            tenants.append(tenant)
    context.log.info(f" source {source_name}  in {tenants}")
    return tenants
@asset(
    group_name="tenant_load",key_prefix=f"{PROJECT}_ingest",
op_tags={"ingest": "graph"},
    deps=[AssetKey([f"{PROJECT}_ingest","tenant_names"]), AssetKey([f"{PROJECT}_ingest","tenant_all"])],
    required_resource_keys={"gleanerio",}
    ,partitions_def=sources_partitions_def
)
#def upload_release(context, config:TennantOpConfig  ):
def upload_release(context ):
    #context.log.info(config.source_name)
    tenants_all = context.repository_def.load_asset_value(AssetKey([f"{PROJECT}_ingest","tenant_all"]))['tenant']
    source_name = context.asset_partition_key_for_output()

    context.log.info(f"source_name {source_name}")
    gleaner_resource = context.resources.gleanerio
    s3_resource = context.resources.gleanerio.gs3.s3
    gleaner_s3 = context.resources.gleanerio.gs3
    default_triplestore = context.resources.gleanerio.triplestore
    tenants = find_tenants_with_source(context, source_name, tenants_all)
    for tenant in tenants:
        try:
            # Get the appropriate graph resource for this tenant's store type
            triplestore = get_graph_resource_for_tenant(tenant, default_triplestore)
            namespace = tenant['graph']['main_namespace']
            endpoint = triplestore.GraphEndpoint(namespace)
            store_type = tenant.get('graph', {}).get('store', {}).get('type', 'blazegraph')
            triplestore.post_to_graph(source_name, path=RELEASE_PATH, extension="nq", graphendpoint=endpoint)
            context.log.info(f"load release for {source_name} to tenant {tenant['community']} ({store_type}) {endpoint}")
        except Exception as ex:
            context.log.error(f"load to tenant {source_name} failed to {endpoint} {ex}")
            raise Exception(f"load to tenant {source_name} failed to {endpoint} {ex}")
    return

#@asset(required_resource_keys={"gleanerio",},ins={"start": In(Nothing)})
@asset(group_name="tenant_load",key_prefix=f"{PROJECT}_ingest",
op_tags={"ingest": "graph"},
       deps=[AssetKey([f"{PROJECT}_ingest","tenant_names"]), AssetKey([f"{PROJECT}_ingest","tenant_all"])],
       required_resource_keys={"gleanerio",}
    ,partitions_def=sources_partitions_def
       )
#def upload_summary(context, config:TennantOpConfig):
def upload_summary(context):
    #context.log.info(config.source_name)
    source_name = context.asset_partition_key_for_output()
    context.log.info(f"source_name {source_name} ")
    tenants_all = context.repository_def.load_asset_value(AssetKey([f"{PROJECT}_ingest","tenant_all"]))['tenant']

    gleaner_resource = context.resources.gleanerio
    s3_resource = context.resources.gleanerio.gs3.s3
    gleaner_s3 = context.resources.gleanerio.gs3
    default_triplestore = context.resources.gleanerio.triplestore
    tenants = find_tenants_with_source(context,source_name, tenants_all)
    for tenant in tenants:
        try:
            # Get the appropriate graph resource for this tenant's store type
            triplestore = get_graph_resource_for_tenant(tenant, default_triplestore)
            namespace = tenant['graph'].get('summary_namespace', tenant['graph']['main_namespace'] + '_summary')
            endpoint = triplestore.GraphEndpoint(namespace)
            store_type = tenant.get('graph', {}).get('store', {}).get('type', 'blazegraph')
            triplestore.post_to_graph(source_name, path=SUMMARY_PATH, extension="ttl", graphendpoint=endpoint, suffix="release_summary")
            context.log.info(f"load summary for {source_name} to tenant {tenant['community']} ({store_type}) {endpoint}")
        except Exception as ex:
            context.log.error(f"load to tenant failed {source_name} {endpoint} {ex}")
            raise Exception(f"load to tenant failed {source_name} {endpoint} {ex}")
    return
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
@asset(group_name="tenant_create",key_prefix=f"{PROJECT}_ingest",
       deps=[AssetKey([f"{PROJECT}_ingest","tenant_all"])],
op_tags={"ingest": "graph"},
       required_resource_keys={"gleanerio",},partitions_def=tenant_partitions_def)
def create_graph_namespaces(context):
    """Create graph namespaces for a tenant.

    For Blazegraph: Creates namespaces using ManageBlazegraph
    For GraphDB: Logs info (repository creation typically done via admin API)
    For Qlever: Creates empty config files
    """
    from ..resources.graph import QleverResource

    tenant_name = context.asset_partition_key_for_output()
    context.log.info(f"tenant_name {tenant_name}")
    tenants = context.repository_def.load_asset_value(AssetKey([f"{PROJECT}_ingest","tenant_all"]))
    tenant = next((t for t in tenants["tenant"] if t['community'] == tenant_name), None)
    if tenant is None:
        raise Exception("Tenant with name {} does not exist".format(tenant_name))
    context.log.info(f"tenant {tenant}")

    main_namespace = tenant["graph"]["main_namespace"]
    summary_namespace = tenant["graph"].get("summary_namespace", main_namespace + "_summary")
    store_type = tenant.get('graph', {}).get('store', {}).get('type', 'blazegraph')

    gleaner_resource = context.resources.gleanerio
    default_triplestore = context.resources.gleanerio.triplestore
    triplestore = get_graph_resource_for_tenant(tenant, default_triplestore)

    try:
        if store_type == 'blazegraph':
            # Blazegraph: create namespaces
            bg = ManageBlazegraph(triplestore.GLEANERIO_GRAPH_URL, main_namespace)
            bg_summary = ManageBlazegraph(triplestore.GLEANERIO_GRAPH_URL, summary_namespace)
            msg = bg.createNamespace(quads=True)
            context.log.info(f"graph creation {tenant_name} {triplestore.GLEANERIO_GRAPH_URL} {msg}")
            msg = bg_summary.createNamespace(quads=False)
            context.log.info(f"graph creation {tenant_name} {triplestore.GLEANERIO_GRAPH_URL} {msg}")

        elif store_type == 'graphdb':
            # GraphDB: repository creation is typically done via admin API or manually
            context.log.info(f"GraphDB: namespace creation for {tenant_name} - ensure repository exists at {triplestore.GLEANERIO_GRAPH_URL}")

        elif store_type == 'qlever' and isinstance(triplestore, QleverResource):
            # Qlever: create empty config files
            triplestore.generate_full_config([], path='graphs/latest', extension="nq", suffix='release')
            context.log.info(f"Qlever: created empty config for tenant {tenant_name}")

        else:
            context.log.warning(f"Unknown store type '{store_type}' for tenant {tenant_name}")

    except Exception as ex:
        context.log.error(f"graph creation failed {tenant_name} {store_type} {ex}")
        raise Exception(f"graph creation failed {tenant_name} {store_type} {ex}")
    return

@asset(group_name="tenant_rebuild",key_prefix=f"{PROJECT}_ingest",
       deps=[AssetKey([f"{PROJECT}_ingest","tenant_all"]), AssetKey([f"{PROJECT}_ingest","sources_names_active"])],
op_tags={"ingest": "graph"},
       required_resource_keys={"gleanerio",'slack'},partitions_def=tenant_partitions_def)
def rebuild_graph_namespaces(context):
    from ..resources.graph import QleverResource

    tenant_name = context.asset_partition_key_for_output()
    context.log.info(f"tenant_name {tenant_name}")
    tenants = context.repository_def.load_asset_value(AssetKey([f"{PROJECT}_ingest","tenant_all"]))
    source_names_active = context.repository_def.load_asset_value(AssetKey([f"{PROJECT}_ingest","sources_names_active"]))
    tenant = next((t for t in tenants["tenant"] if t['community'] == tenant_name ),None)
    if tenant is None:
        raise Exception("Tenant with name {} does not exist".format(tenant_name))
    context.log.info(f"tenant {tenant}")

    sources = tenant["sources"]
    gleaner_resource = context.resources.gleanerio
    s3_resource = context.resources.gleanerio.gs3.s3
    gleaner_s3 = context.resources.gleanerio.gs3
    default_triplestore = context.resources.gleanerio.triplestore
    slack = context.resources.slack
    slack_channel = os.getenv("SLACK_CHANNEL", "#production_discussion")

    # Get the appropriate graph resource for this tenant
    triplestore = get_graph_resource_for_tenant(tenant, default_triplestore)
    store_type = tenant.get('graph', {}).get('store', {}).get('type', 'blazegraph')

    main_namespace = tenant["graph"]["main_namespace"]
    summary_namespace = tenant["graph"].get("summary_namespace", main_namespace + "_summary")

    if 'all' in sources:
        sources = source_names_active

    try:
        # Handle rebuild differently based on store type
        if isinstance(triplestore, QleverResource):
            # For Qlever, generate complete config files
            context.log.info(f"Generating Qlever config for tenant {tenant_name}")
            triplestore.generate_full_config(sources, path=RELEASE_PATH, extension="nq", suffix='release')
            context.log.info(f"Generated Qlever release config for tenant {tenant_name} with {len(sources)} sources")

            # Generate summary config (different namespace)
            triplestore_summary = get_graph_resource_for_tenant(tenant, default_triplestore)
            triplestore_summary.GLEANERIO_GRAPH_NAMESPACE = summary_namespace
            triplestore_summary.generate_full_config(sources, path=SUMMARY_PATH, extension="ttl", suffix='release_summary')
            context.log.info(f"Generated Qlever summary config for tenant {tenant_name}")

        else:
            # For Blazegraph/GraphDB, recreate namespaces and reload data
            endpoint = triplestore.GraphEndpoint(main_namespace)
            summary_endpoint = triplestore.GraphEndpoint(summary_namespace)

            # Only Blazegraph supports namespace management via ManageBlazegraph
            if store_type == 'blazegraph':
                bg = ManageBlazegraph(triplestore.GLEANERIO_GRAPH_URL, main_namespace)
                bg_summary = ManageBlazegraph(triplestore.GLEANERIO_GRAPH_URL, summary_namespace)

                # Recreate main namespace
                msg = bg.deleteNamespace()
                context.log.info(f"graph deletion {tenant_name} {triplestore.GLEANERIO_GRAPH_URL} {msg}")
                msg = bg.createNamespace(quads=True)
                context.log.info(f"graph creation {tenant_name} {triplestore.GLEANERIO_GRAPH_URL} {msg}")

                # Recreate summary namespace
                msg = bg_summary.deleteNamespace()
                context.log.info(f"graph deletion {tenant_name} {triplestore.GLEANERIO_GRAPH_URL} {msg}")
                msg = bg_summary.createNamespace(quads=False)
                context.log.info(f"graph creation {tenant_name} {triplestore.GLEANERIO_GRAPH_URL} {msg}")
            else:
                # For GraphDB, we skip namespace recreation (would need different API)
                context.log.info(f"GraphDB: skipping namespace recreation for {tenant_name}")

            # Upload releases and summaries
            for source in sources:
                try:
                    triplestore.post_to_graph(source, path=RELEASE_PATH, extension="nq", graphendpoint=endpoint)
                    context.log.info(f"rebuild_graph_namespace: load release for {source} to tenant {tenant['community']} ({store_type}) {endpoint}")
                except Exception as e:
                    context.log.error(f"rebuild namespace: Failed to load release for {source} to tenant {tenant['community']} {endpoint}: {e}")
                    continue

                try:
                    triplestore.post_to_graph(source, path=SUMMARY_PATH, extension="ttl", graphendpoint=summary_endpoint, suffix="release_summary")
                    context.log.info(f"load summary for {source} to tenant {tenant['community']} {summary_endpoint}")
                except Exception as e:
                    context.log.error(f"rebuild namespace: Failed to load summary for {source} to tenant {tenant['community']} {summary_endpoint}: {e}")
                    continue

                context.log.info(f"rebuild namespace loaded source {source} for {tenant['community']}")

        context.log.info(f"rebuild namespace completed for {tenant['community']} ({store_type})")

    except Exception as ex:
        context.log.error(f"graph rebuild failed {tenant_name} {store_type} {ex}")
        raise Exception(f"graph rebuild failed {tenant_name} {store_type} {ex}")
    return

@asset(group_name="tenant_create",key_prefix=f"{PROJECT}_ingest",
       deps=[AssetKey([f"{PROJECT}_ingest","tenant_all"]), AssetKey([f"{PROJECT}_ingest","create_graph_namespaces"])],
       required_resource_keys={"gleanerio",},partitions_def=tenant_partitions_def)
def create_tenant_containers(context):
    #context.log.info(config.source_name)
    tenant_name = context.asset_partition_key_for_output()
    tenants = context.repository_def.load_asset_value(AssetKey([f"{PROJECT}_ingest","tenant_all"]))
    context.log.info(f"tennant_name {tenant_name}")
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
