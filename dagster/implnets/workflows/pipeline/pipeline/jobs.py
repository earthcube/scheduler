import os

from dagster import define_asset_job, AssetSelection, AssetKey

from .assets import (
    validate_sitemap_url, harvest_source, identifier_manifest,
    enhanced_jsonld, source_report, source_datacatalog, release_nquads,
    sources_partitions_def, PREFIX,
)

PROJECT = os.environ.get('PROJECT')

# The weekly per-source run: phase 1 (harvest + manifest) -> phase 2
# (enhance) -> phase 2.1 (reports) -> phase 3 (release). Phase 4 (qlever
# rebuild) is unpartitioned and triggered separately (or manually) once the
# fan-out finishes.
pipeline_source_job = define_asset_job(
    name=f"{PROJECT}_pipeline_source_job",
    selection=AssetSelection.assets(
        validate_sitemap_url, harvest_source, identifier_manifest,
        enhanced_jsonld, source_report, source_datacatalog, release_nquads,
    ),
    partitions_def=sources_partitions_def,
    tags={"ingest": "docker"},
)

sources_config_job = define_asset_job(
    name=f"{PROJECT}_pipeline_sources_config_job",
    selection=AssetSelection.assets(
        AssetKey([PREFIX, "sources_names_active"])).required_multi_asset_neighbors(),
    tags={"dagster/priority": "11"},
)

qlever_rebuild_job = define_asset_job(
    name=f"{PROJECT}_pipeline_qlever_rebuild_job",
    selection=AssetSelection.assets(AssetKey([PREFIX, "qlever_index_rebuild"])),
    tags={"tenant_load": "graph"},
)
