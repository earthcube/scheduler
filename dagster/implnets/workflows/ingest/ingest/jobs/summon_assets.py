from dagster import (
    asset, Config, Output,AssetKey,
    define_asset_job, AssetSelection,
get_dagster_logger,
)

# from dagster.implnets.templates.v1.implnet_ops_SOURCEVAL import post_to_graph
from ..assets.gleaner_summon_assets import *
from ..assets.tenant import *
from ..assets.gleaner_sources import sources_partitions_def, gleanerio_sources
import os
PROJECT=os.environ.get('PROJECT')


# load_report_release is back in: it was disabled because it queried
# GLEANERIO_GRAPH_NAMESPACE, a namespace nothing here creates or loads. It now
# reads the release it already depends on, so there is no graph to wait for.
summon_asset_job = define_asset_job(
    name=f"{PROJECT}_summon_and_release_job",
    selection=AssetSelection.assets(validate_sitemap_url, gleanerio_run, release_nabu_run, load_report_s3,
                                    load_report_release,
                                    release_summarize, spatial_release_quads, identifier_stats, bucket_urls,
                                    graph_stats_report #, upload_release
                                    ),
    partitions_def=sources_partitions_def,
   #tags={"dagster/concurrency_key": 'ingest'},
tags={"ingest": 'docker'},
)
# so can use command line to limit: https://docs.dagster.io/guides/limiting-concurrency-in-data-pipelines#limiting-opasset-concurrency-across-runs
# value is ingest
sources_asset_job = define_asset_job(
    name=f"{PROJECT}_sources_config_updated_job",
    selection=AssetSelection.assets(AssetKey([f"{PROJECT}_ingest","sources_names_active"])).required_multi_asset_neighbors(),
    partitions_def=sources_partitions_def,
    tags={"dagster/priority": "11"}
)
