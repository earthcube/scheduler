# a test asset to see that all the resource configurations load.
# basically runs the first step, of gleaner on geocodes demo datasets
import dagster
from dagster import get_dagster_logger, asset, In, Nothing, Config,StaticPartitionsDefinition

sources_partitions_def = StaticPartitionsDefinition(
    ["geocodes_demo_datasets", "iris"]
)
from ..resources.gleanerio import GleanerioResource
@asset(partitions_def=sources_partitions_def,required_resource_keys={"s3"})
def gleanerio_sources(context ):
    s3_resource = foo = context.resources.s3
    source="geocodes_demo_datasets"
    sources= s3_resource.listPath(path='orgs')
    dagster.get_dagster_logger().info(str(sources))
    context.add_output_metadata(
            metadata={
                "source": source,  # Metadata can be any key-value pair
                "run": "gleaner",
                # The `MetadataValue` class has useful static methods to build Metadata
            }
        )

