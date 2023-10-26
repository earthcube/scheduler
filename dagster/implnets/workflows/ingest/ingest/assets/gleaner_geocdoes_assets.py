# a test asset to see that all the resource configurations load.
# basically runs the first step, of gleaner on geocodes demo datasets
from typing import Any

from dagster import (
    get_dagster_logger,graph, asset,graph_asset, op, In, Nothing, Config, StaticPartitionsDefinition, Output
)
from ..resources.gleanerio import GleanerioResource

sources_partitions_def = StaticPartitionsDefinition(
    ["geocodes_demo_datasets", "iris"]
)
from ..resources.gleanerio import GleanerioResource
@asset(partitions_def=sources_partitions_def, required_resource_keys={"gleanerio"})
def gleanerio_run(context ) -> Output[Any]:
    gleaner_resource = foo = context.resources.gleanerio
    source= context.asset_partition_key_for_output()
    gleaner = gleaner_resource.execute(context, "gleaner", source )

    metadata={
                "source": source,  # Metadata can be any key-value pair
                "run": "gleaner",
                # The `MetadataValue` class has useful static methods to build Metadata
            }

    return Output(gleaner, metadata=metadata)
@asset(partitions_def=sources_partitions_def, required_resource_keys={"gleanerio"})
def nabu_release_run(context, gleanerio_run ) -> Output[Any]:
    gleaner_resource = foo = context.resources.gleanerio
    source= context.asset_partition_key_for_output()
    nabu=gleaner_resource.execute(context, "release", source )
    metadata={
                "source": source,  # Metadata can be any key-value pair
                "run": "release",
                # The `MetadataValue` class has useful static methods to build Metadata
            }

    return Output(nabu, metadata=metadata)
@graph_asset(partitions_def=sources_partitions_def)
def harvest_and_release() :
    #source = context.asset_partition_key_for_output()
    #containers = getImage()
    #harvest = gleanerio_run(start=containers)
    harvest = gleanerio_run()
    release = nabu_release_run(harvest)
    return release


