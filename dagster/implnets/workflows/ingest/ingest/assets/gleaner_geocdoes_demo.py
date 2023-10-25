# a test asset to see that all the resource configurations load.
# basically runs the first step, of gleaner on geocodes demo datasets

from dagster import get_dagster_logger, asset, In, Nothing, Config

from ..resources.gleanerio import GleanerioResource
@asset(required_resource_keys={"gleanerio"})
def gleanerio_demo(context ):
    gleaner_resource = foo = context.resources.gleanerio
    source="geocodes_demo_datasets"
    gleaner = gleaner_resource.execute(context, "gleaner", source )


