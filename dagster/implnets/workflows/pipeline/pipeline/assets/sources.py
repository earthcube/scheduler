# Config assets: source list, tenant list, and per-source pipeline settings.
# Adapted from ingest/assets/gleaner_sources.py; asset key prefix is
# {PROJECT}_pipeline so the package can coexist with ingest in one instance.
import os

import yaml
from dagster import (
    get_dagster_logger, multi_asset, asset, AssetOut,
    DynamicPartitionsDefinition, AutoMaterializePolicy,
)
from ec.sitemap import Sitemap

PROJECT = os.environ.get('PROJECT')
PREFIX = f"{PROJECT}_pipeline"

sources_partitions_def = DynamicPartitionsDefinition(name=f"{PROJECT}pipeline_sources_active")

from ..steps import load_pipeline_config


def check_for_valid_sitemap(sources_active):
    """Validate the sitemap URL of every active source; annotates in place."""
    validated_sources = []
    for source in sources_active:
        if source['sourcetype'] == "sitegraph":
            source['sm_url_is_valid'] = True
            validated_sources.append(source)
        else:
            try:
                sm = Sitemap(source['url'], no_progress_bar=True)
                source['sm_url_is_valid'] = sm.validUrl()
                validated_sources.append(source)
            except Exception as e:
                get_dagster_logger().error(
                    f"sitemap url ERROR for {source['name']} {source['url']} exception {e}")
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
def pipeline_sources(context):
    s3_resource = context.resources.gs3
    source = s3_resource.getSourcesFile()
    sources_obj = yaml.safe_load(source)
    sources_all_value = list(filter(lambda t: t["name"], sources_obj["sources"]))
    sources_active_value = filter(lambda t: t["active"], sources_all_value)
    source_sm_validated = list(check_for_valid_sitemap(sources_active_value))
    sources_active_names = list(map(
        lambda t: t["name"], filter(lambda t: t["sm_url_is_valid"], source_sm_validated)))
    sources_invalid_sm = list(map(
        lambda t: t["name"], filter(lambda t: not t["sm_url_is_valid"], source_sm_validated)))

    context.add_output_metadata(
        metadata={"sources": sources_active_names},
        output_name="sources_names_active")
    return sources_all_value, sources_active_names, sources_invalid_sm


@multi_asset(
    outs={
        "tenant_all": AssetOut(key_prefix=PREFIX, group_name="configs",
                               auto_materialize_policy=AutoMaterializePolicy.eager()),
        "tenant_names": AssetOut(key_prefix=PREFIX, group_name="configs",
                                 auto_materialize_policy=AutoMaterializePolicy.eager()),
    },
    required_resource_keys={"gs3"})
def pipeline_tenants(context):
    s3_resource = context.resources.gs3
    tenant = s3_resource.getTennatFile()
    tenant_obj = yaml.safe_load(tenant)
    tenants = list(map(lambda t: t["community"], tenant_obj["tenant"]))
    context.add_output_metadata(metadata={"tenants": tenants}, output_name="tenant_names")
    return tenant_obj, tenants


@asset(key_prefix=PREFIX, group_name="configs",
       auto_materialize_policy=AutoMaterializePolicy.eager(),
       required_resource_keys={"gs3"})
def pipeline_step_config(context):
    """Per-source pipeline step configuration (pipelineconfig.yaml in S3).

    Controls which enhancement steps run for which source — some sources need
    additional steps, others need none. See pipeline/steps.py for the format
    and the step registry.
    """
    config = load_pipeline_config(context.resources.gs3)
    context.add_output_metadata(metadata={
        "defaults": str(config.get("defaults", "built-in")),
        "overridden_sources": list((config.get("sources") or {}).keys()),
    })
    return config
