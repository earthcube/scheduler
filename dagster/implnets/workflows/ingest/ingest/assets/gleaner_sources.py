# a test asset to see that all the resource configurations load.
# basically runs the first step, of gleaner on geocodes demo datasets
import orjson

import dagster
from dagster import get_dagster_logger, asset, In, Nothing, Config,DynamicPartitionsDefinition

sources_partitions_def = DynamicPartitionsDefinition(name="gleanerio_orgs")
from ..resources.gleanerio import GleanerioResource

# for right now, using a list of orgs as the sources.
# future read the gleaner config file.
# future future, store soruces and read them.
@asset(required_resource_keys={"gs3"})
def gleanerio_orgs(context ):
    s3_resource = context.resources.gs3
    source="geocodes_demo_datasets"
    files = s3_resource.listPath(path='orgs')
    orgs = list(map(lambda o: o["Key"].removeprefix("orgs/").removesuffix(".nq") , files))
    dagster.get_dagster_logger().info(str(orgs))
    context.add_output_metadata(
            metadata={
                "source": source,  # Metadata can be any key-value pair
                "run": "gleaner",
                # The `MetadataValue` class has useful static methods to build Metadata
            }
        )
    return orjson.dumps(orgs,  option=orjson.OPT_INDENT_2)
