# Config assets for the pysummon project. Same S3 config files as the
# pipeline project (gleanerconfig.yaml, tenant.yaml, pipelineconfig.yaml),
# but its own asset prefix and dynamic partitions so both code locations
# coexist in one Dagster instance.
import os

import yaml
from dagster import (
    get_dagster_logger, multi_asset, asset, AssetOut,
    DynamicPartitionsDefinition, AutoMaterializePolicy,
)
from pipeline.steps import load_pipeline_config

from ..summon import validate_sitemap

PROJECT = os.environ.get('PROJECT')
PREFIX = f"{PROJECT}_pysummon"

sources_partitions_def = DynamicPartitionsDefinition(name=f"{PROJECT}pysummon_sources_active")


def check_for_valid_sitemap(sources_active):
    validated_sources = []
    for source in sources_active:
        if source['sourcetype'] == "sitegraph":
            source['sm_url_is_valid'] = True
        else:
            try:
                source['sm_url_is_valid'] = validate_sitemap(source['url'])
            except Exception as e:
                get_dagster_logger().error(
                    f"sitemap ERROR for {source['name']} {source['url']}: {e}")
                source['sm_url_is_valid'] = False
        validated_sources.append(source)
    return validated_sources


@multi_asset(
    outs={
        "sources_all": AssetOut(key_prefix=PREFIX, group_name="configs",
                                auto_materialize_policy=AutoMaterializePolicy.eager()),
        "sources_names_active": AssetOut(key_prefix=PREFIX, group_name="configs",
                                         auto_materialize_policy=AutoMaterializePolicy.eager()),
        "sources_names_invalid_sitemap": AssetOut(key_prefix=PREFIX, group_name="configs",
                                                  auto_materialize_policy=AutoMaterializePolicy.eager()),
    },
    required_resource_keys={"gs3"})
def pysummon_sources(context):
    s3_resource = context.resources.gs3
    config = yaml.safe_load(s3_resource.getSourcesFile())
    sources_all_value = list(filter(lambda t: t["name"], config["sources"]))
    active = filter(lambda t: t["active"], sources_all_value)
    validated = check_for_valid_sitemap(active)
    active_names = [s["name"] for s in validated if s["sm_url_is_valid"]]
    invalid_names = [s["name"] for s in validated if not s["sm_url_is_valid"]]
    # the summoner section (threads etc.) rides along with sources_all
    context.add_output_metadata(metadata={"sources": active_names},
                                output_name="sources_names_active")
    return ({"sources": sources_all_value, "summoner": config.get("summoner", {})},
            active_names, invalid_names)


@multi_asset(
    outs={
        "tenant_all": AssetOut(key_prefix=PREFIX, group_name="configs",
                               auto_materialize_policy=AutoMaterializePolicy.eager()),
        "tenant_names": AssetOut(key_prefix=PREFIX, group_name="configs",
                                 auto_materialize_policy=AutoMaterializePolicy.eager()),
    },
    required_resource_keys={"gs3"})
def pysummon_tenants(context):
    tenant_obj = yaml.safe_load(context.resources.gs3.getTennatFile())
    tenants = [t["community"] for t in tenant_obj["tenant"]]
    context.add_output_metadata(metadata={"tenants": tenants}, output_name="tenant_names")
    return tenant_obj, tenants


@asset(key_prefix=PREFIX, group_name="configs",
       auto_materialize_policy=AutoMaterializePolicy.eager(),
       required_resource_keys={"gs3"})
def pipeline_step_config(context):
    """Per-source pipeline step settings (pipelineconfig.yaml, shared with
    the pipeline project)."""
    config = load_pipeline_config(context.resources.gs3)
    context.add_output_metadata(metadata={
        "defaults": str(config.get("defaults", "built-in")),
        "overridden_sources": list((config.get("sources") or {}).keys()),
    })
    return config
