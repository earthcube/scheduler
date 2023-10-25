
from dagster import get_dagster_logger, asset, In, Nothing, Config

from ..resources.gleanerio import GleanerioResource
@asset()
def gleanerio_demo(gleanerio: GleanerioResource, ):
    source="geocodes_demo_data"
    gleaner = gleanerio.execute(gleanerio, "gleaner", source )


