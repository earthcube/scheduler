# a test asset to see that all the resource configurations load.
# basically runs the first step, of gleaner on geocodes demo datasets
from typing import Any

from dagster import (
    get_dagster_logger,graph, asset,graph_asset, op, In, Nothing, Config, StaticPartitionsDefinition, Output,
static_partitioned_config,dynamic_partitioned_config, schedule, job, RunRequest,
define_asset_job, AssetSelection
)
from ..resources.gleanerio import GleanerioResource
from .gleaner_sources import sources_partitions_def, gleanerio_orgs
class HarvestOpConfig(Config):
    source_name: str
# sources_partitions_def = StaticPartitionsDefinition(
#     ["geocodes_demo_datasets", "iris"]
# )
from ..resources.gleanerio import GleanerioResource
@asset(partitions_def=sources_partitions_def, required_resource_keys={"gleanerio"})
#@asset( required_resource_keys={"gleanerio"})
def gleanerio_run(context ) -> Output[Any]:
    gleaner_resource =  context.resources.gleanerio
    source= context.asset_partition_key_for_output()
    gleaner = gleaner_resource.execute(context, "gleaner", source )

    metadata={
                "source": source,  # Metadata can be any key-value pair
                "run": "gleaner",
                # The `MetadataValue` class has useful static methods to build Metadata
            }

    return Output(gleaner, metadata=metadata)
@asset(partitions_def=sources_partitions_def, required_resource_keys={"gleanerio"})
#@asset(required_resource_keys={"gleanerio"})
def nabu_release_run(context, gleanerio_run ) -> Output[Any]:
    gleaner_resource = context.resources.gleanerio
    source= context.asset_partition_key_for_output()
    nabu=gleaner_resource.execute(context, "release", source )
    metadata={
                "source": source,  # Metadata can be any key-value pair
                "run": "release",
                # The `MetadataValue` class has useful static methods to build Metadata
            }

    return Output(nabu, metadata=metadata)

summon_asset_job = define_asset_job(
    name="summon_and_release_job",
    selection=AssetSelection.assets(gleanerio_run, nabu_release_run),
    partitions_def=sources_partitions_def,
)

# need to add a sensor to add paritions when one is added
# https://docs.dagster.io/concepts/partitions-schedules-sensors/partitioning-assets#dynamically-partitioned-assets


# #########
# CRUFT
#  worked to see if this could be a graph with an assent, and really a defiend asset job works better

# ## partitioning
# ####
# class HarvestOpConfig(Config):
#     source_name: str
# @dynamic_partitioned_config(partition_fn=gleanerio_orgs)
# def harvest_config(partition_key: str):
#     return {
#         "ops":
#             {"harvest_and_release":
#                  {"config": {"source_name": partition_key},
#                   "ops": {
#                       "gleanerio_run":
#                            {"config": {"source_name": partition_key}
#                             },
#                       "nabu_release_run":
#                            {"config": {"source_name": partition_key}
#                             }
#                   }
#                   }
#              }
#     }
#
# # ops:
# #   harvest_and_release:
# #     ops:
# #       gleanerio_run:
# #         config:
# #           source_name: ""
# #       nabu_release_run:
# #         config:
# #           source_name: ""
#
# @graph_asset(partitions_def=sources_partitions_def)
# #@graph_asset( )
# def harvest_and_release() :
#     #source = context.asset_partition_key_for_output()
#     #containers = getImage()
#     #harvest = gleanerio_run(start=containers)
#     harvest = gleanerio_run()
#     release = nabu_release_run(harvest)
#     return release
#
# #@asset
# # def harvest_op(context, config: HarvestOpConfig):
# #     context.log.info(config.source_name)
# #     harvest = gleanerio_run()
# #     release = nabu_release_run(harvest)
# #     return release
#
# # @job(config=harvest_config)
# # def harvest_job( ):
# #     harvest_op()
#     #harvest_and_release()
# # @schedule(cron_schedule="0 0 * * *", job=harvest_job)
# # def geocodes_schedule():
# #     return RunRequest(partition_key="iris")
