# a test asset to see that all the resource configurations load.
# basically runs the first step, of gleaner on geocodes demo datasets
import orjson

import dagster
from dagster import get_dagster_logger, asset,multi_asset, AssetOut, In, Nothing, Config,DynamicPartitionsDefinition, sensor
import yaml

sources_partitions_def = DynamicPartitionsDefinition(name="sources_names_active")
#from ..resources.gleanerio import GleanerioResource

### PRESENT HACK. Using the orgs
# really needs to read a future tenant file, and then add
# new partions with a sensor
# need to add a sensor to add paritions when one is added
# https://docs.dagster.io/concepts/partitions-schedules-sensors/partitioning-assets#dynamically-partitioned-assets

# for right now, using a list of orgs as the sources.
# future read the gleaner config file.
# future future, store sources in (s3/googlesheets) and read them.


@asset( group_name="configs", name="org_names",required_resource_keys={"gs3"})
def gleanerio_orgs(context ):
    s3_resource = context.resources.gs3
    source="orgs_list_from_a_s3_bucket"
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
    #return orjson.dumps(orgs,  option=orjson.OPT_INDENT_2)
    # this is used for partitioning, so let it pickle (aka be a python list)
    return orgs
@asset(group_name="configs",name="tennant_names",required_resource_keys={"gs3"})
def gleanerio_tennants(context ):
    gleaner_resource =  context.resources.gs3
    s3_resource = context.resources.gs3
    # tennant_path =  f'{s3_resource.GLEANERIO_CONFIG_PATH}{s3_resource.GLEANERIO_TENNANT_FILENAME}'
    # get_dagster_logger().info(f"tennant_path {tennant_path} ")
    #
    # tennant = s3_resource.getFile(path=tennant_path)
    tennant = s3_resource.getTennatFile()
    get_dagster_logger().info(f"tennant {tennant} ")
    tennant_obj = yaml.safe_load(tennant)
    tennants = list(map(lambda t: t["community"], tennant_obj["tennant"] ))
    context.add_output_metadata(
            metadata={
                "source": tennants,  # Metadata can be any key-value pair
                "run": "gleaner",
                # The `MetadataValue` class has useful static methods to build Metadata
            }
        )
    #return orjson.dumps(orgs,  option=orjson.OPT_INDENT_2)
    # this is used for partitioning, so let it pickle (aka be a python list)
    return tennants
@multi_asset(group_name="configs",outs=
             {
                 "sources_all": AssetOut(),
                 "sources_names_active": AssetOut(),
             }
    ,required_resource_keys={"gs3"})
def gleanerio_sources(context ):

    s3_resource = context.resources.gs3
    # tennant_path =  f'{s3_resource.GLEANERIO_CONFIG_PATH}{s3_resource.GLEANERIO_TENNANT_FILENAME}'
    # get_dagster_logger().info(f"tennant_path {tennant_path} ")
    #
    # tennant = s3_resource.getFile(path=tennant_path)
    source = s3_resource.getSourcesFile()
    get_dagster_logger().info(f"sources {source} ")
    sources_obj = yaml.safe_load(source)
    sources_all_value = list(filter(lambda t: t["name"], sources_obj["sources"]))
    sources_active_value = filter(lambda t: t["active"], sources_all_value )
    sources_active_value = list(map(lambda t: t["name"], sources_active_value))
    # context.add_output_metadata(
    #         metadata={
    #             "source": sources_value,  # Metadata can be any key-value pair
    #             "run": "gleaner",
    #             # The `MetadataValue` class has useful static methods to build Metadata
    #         }
    #     )
    #return orjson.dumps(orgs,  option=orjson.OPT_INDENT_2)
    # this is used for partitioning, so let it pickle (aka be a python list)
    return sources_all_value, sources_active_value
# @asset(required_resource_keys={"gs3"})
# def gleanerio_orgs(context ):
#     s3_resource = context.resources.gs3
#     source="geocodes_demo_datasets"
#     files = s3_resource.listPath(path='orgs')
#     orgs = list(map(lambda o: o["Key"].removeprefix("orgs/").removesuffix(".nq") , files))
#     # rather than do this with an @asset_sensor, just do it here.
#     sources = orgs
#     new_sources = [
#         source
#         for source in sources
#         if not sources_partitions_def.has_partition_key(
#             source, dynamic_partitions_store=context.instance
#         )
#     ]
#     sources_partitions_def.build_add_request(new_sources)
#     # return SensorResult(
#     #     run_requests=[
#     #         RunRequest(partition_key=source) for source in new_sources
#     #     ],
#     #     dynamic_partitions_requests=[
#     #         sources_partitions_def.build_add_request(new_sources)
#     #     ],
#     # )
#     dagster.get_dagster_logger().info(str(orgs))
#     context.add_output_metadata(
#             metadata={
#                 "source": source,  # Metadata can be any key-value pair
#                 "new_sources":new_sources,
#                 "run": "gleaner",
#                 # The `MetadataValue` class has useful static methods to build Metadata
#             }
#         )
#     #return orjson.dumps(orgs,  option=orjson.OPT_INDENT_2)
#     # this is used for partitioning, so let it pickle (aka be a python list)
#     return orgs
