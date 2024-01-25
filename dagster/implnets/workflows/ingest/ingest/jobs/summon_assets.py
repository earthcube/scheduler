from dagster import (
    asset, Config, Output,
    define_asset_job, AssetSelection,
get_dagster_logger,
)

from ..assets.gleaner_summon_assets import *
from ..assets.gleaner_sources import sources_partitions_def

summon_asset_job = define_asset_job(
    name="summon_and_release_job",
    selection=AssetSelection.assets(gleanerio_run, release_nabu_run, load_report_s3,
                                    release_summarize, identifier_stats, bucket_urls),
    partitions_def=sources_partitions_def,
)
