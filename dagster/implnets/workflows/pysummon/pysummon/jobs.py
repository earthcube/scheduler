import os

from dagster import define_asset_job, AssetSelection, AssetKey

from .assets import (
    validate_sitemap_url, summon_source, identifier_manifest,
    enhanced_jsonld, source_report, source_datacatalog, release_nquads,
    sparql_update_load,
    sources_partitions_def, PREFIX,
)

PROJECT = os.environ.get('PROJECT')

# per-source weekly run: summon -> manifest -> enhance -> reports -> release
# (sparql_update_load included; it self-skips when no endpoint configured)
pysummon_source_job = define_asset_job(
    name=f"{PROJECT}_pysummon_source_job",
    selection=AssetSelection.assets(
        validate_sitemap_url, summon_source, identifier_manifest,
        enhanced_jsonld, source_report, source_datacatalog, release_nquads,
        sparql_update_load,
    ),
    partitions_def=sources_partitions_def,
    tags={"ingest": "summon"},
)

pysummon_config_job = define_asset_job(
    name=f"{PROJECT}_pysummon_sources_config_job",
    selection=AssetSelection.assets(
        AssetKey([PREFIX, "sources_names_active"])).required_multi_asset_neighbors(),
    tags={"dagster/priority": "11"},
)

pysummon_publish_job = define_asset_job(
    name=f"{PROJECT}_pysummon_publish_job",
    selection=AssetSelection.assets(AssetKey([PREFIX, "community_load_files"])),
)
