import distutils
import json
import os

from dagster import asset, define_asset_job, get_dagster_logger
from ec.graph.sparql_query import queryWithSparql
from ec.reporting.report import generateGraphReportsRepo, reportTypes, generateReportStats
from ec.datastore import s3
from ec.logger import config_app

log = config_app()


GLEANERIO_MINIO_ADDRESS = str(os.environ.get('GLEANERIO_MINIO_ADDRESS'))
GLEANERIO_MINIO_PORT = str(os.environ.get('GLEANERIO_MINIO_PORT'))
GLEANERIO_MINIO_USE_SSL = bool(distutils.util.strtobool(os.environ.get('GLEANERIO_MINIO_USE_SSL', 'true')))
GLEANERIO_MINIO_SECRET_KEY = str(os.environ.get('GLEANERIO_MINIO_SECRET_KEY'))
GLEANERIO_MINIO_ACCESS_KEY = str(os.environ.get('GLEANERIO_MINIO_ACCESS_KEY'))
GLEANER_MINIO_BUCKET =str( os.environ.get('GLEANERIO_MINIO_BUCKET'))

# set for the earhtcube utiltiies
MINIO_OPTIONS={"secure":GLEANERIO_MINIO_USE_SSL

              ,"access_key": GLEANERIO_MINIO_ACCESS_KEY
              ,"secret_key": GLEANERIO_MINIO_SECRET_KEY
               }

GLEANERIO_HEADLESS_ENDPOINT = str(os.environ.get('GLEANERIO_HEADLESS_ENDPOINT', "http://headless:9222"))
# using GLEANER, even though this is a nabu property... same prefix seems easier
GLEANERIO_GRAPH_URL = str(os.environ.get('GLEANERIO_GRAPH_URL'))
GLEANERIO_GRAPH_NAMESPACE = str(os.environ.get('GLEANERIO_GRAPH_NAMESPACE'))
GLEANERIO_GLEANER_CONFIG_PATH= str(os.environ.get('GLEANERIO_GLEANER_CONFIG_PATH', "/gleaner/gleanerconfig.yaml"))
GLEANERIO_NABU_CONFIG_PATH= str(os.environ.get('GLEANERIO_NABU_CONFIG_PATH', "/nabu/nabuconfig.yaml"))
GLEANERIO_GLEANER_IMAGE =str( os.environ.get('GLEANERIO_GLEANER_IMAGE', 'nsfearthcube/gleaner:latest'))
GLEANERIO_NABU_IMAGE = str(os.environ.get('GLEANERIO_NABU_IMAGE', 'nsfearthcube/nabu:latest'))
GLEANERIO_LOG_PREFIX = str(os.environ.get('GLEANERIO_LOG_PREFIX', 'scheduler/logs/')) # path to logs in nabu/gleaner
GLEANERIO_GLEANER_ARCHIVE_OBJECT = str(os.environ.get('GLEANERIO_GLEANER_ARCHIVE_OBJECT', 'scheduler/configs/GleanerCfg.tgz'))
GLEANERIO_GLEANER_ARCHIVE_PATH = str(os.environ.get('GLEANERIO_GLEANER_ARCHIVE_PATH', '/gleaner/'))
GLEANERIO_NABU_ARCHIVE_OBJECT=str(os.environ.get('GLEANERIO_NABU_ARCHIVE_OBJECT', 'scheduler/configs/NabuCfg.tgz'))
GLEANERIO_NABU_ARCHIVE_PATH=str(os.environ.get('GLEANERIO_NABU_ARCHIVE_PATH', '/nabu/'))
GLEANERIO_GLEANER_DOCKER_CONFIG=str(os.environ.get('GLEANERIO_GLEANER_DOCKER_CONFIG', 'gleaner'))
GLEANER_GRAPH_URL = str(os.environ.get('GLEANERIO_GRAPH_URL'))
GLEANERIO_NABU_DOCKER_CONFIG=str(os.environ.get('GLEANERIO_NABU_DOCKER_CONFIG', 'nabu'))
#GLEANERIO_SUMMARY_GRAPH_ENDPOINT = os.environ.get('GLEANERIO_SUMMARY_GRAPH_ENDPOINT')
GLEANERIO_SUMMARY_GRAPH_NAMESPACE = os.environ.get('GLEANERIO_GRAPH_NAMESPACE',f"{GLEANERIO_GRAPH_NAMESPACE}_summary" )
GLEANERIO_SUMMARIZE_GRAPH=(os.getenv('GLEANERIO_GRAPH_SUMMARIZE', 'False').lower() == 'true')
GLEANERIO_CSV_CONFIG_URL = str(os.environ.get('GLEANERIO_CSV_CONFIG_URL'))

SUMMARY_PATH = 'graphs/summary'
RELEASE_PATH = 'graphs/latest'

def _graphSummaryEndpoint(community):
    if community == "all":
        url = f"{GLEANER_GRAPH_URL}/namespace/{GLEANERIO_SUMMARY_GRAPH_NAMESPACE}/sparql"
    else:
        url = f"{GLEANER_GRAPH_URL}/namespace/{community}_summary/sparql"
    return url
@asset(group_name="graph")
def sos_types( ):
    graphendpoint = f"{GLEANERIO_GRAPH_URL}/namespace/{GLEANERIO_GRAPH_NAMESPACE}/sparql"
    report = queryWithSparql("all_count_types", graphendpoint, parameters=None)
    report_csv =report.to_csv()
    # report_json = generateGraphReportsRepo("all",
    #                                        "", reportList=reportTypes["all"])
    s3Minio = s3.MinioDatastore( GLEANERIO_MINIO_ADDRESS, MINIO_OPTIONS)
    #data = f.getvalue()

    bucketname, objectname = s3Minio.putReportFile(GLEANER_MINIO_BUCKET,"all","sos_types.csv",report_csv)
    return bucketname, objectname, report_csv

@asset(group_name="graph")
def all_report_stats():
    s3Minio = s3.MinioDatastore( GLEANERIO_MINIO_ADDRESS, MINIO_OPTIONS)
    bucket = GLEANER_MINIO_BUCKET
    source_url = GLEANERIO_CSV_CONFIG_URL

    # TODO: remove the hardcoded community list
    community_list = ["all", "deepoceans", "ecoforecast", "geochemistry"]

    if (GLEANERIO_SUMMARIZE_GRAPH):
        for community in community_list:
            try:
                report = generateReportStats(source_url, bucket, s3Minio, _graphSummaryEndpoint(community), community)
                bucketname, objectname = s3Minio.putReportFile(bucket, "all", f"report_{community}_stats.json", report)
            except Exception as e:
                get_dagster_logger().info(f"Summary report errors: {str(e)}")

#all_urn_w_types_toplevel.sparql
# returns all grapurns with a type.
# def top_level_types():
#     graphendpoint = f"{GLEANERIO_GRAPH_URL}/namespace/{GLEANERIO_GRAPH_NAMESPACE}/sparql"
#     report = queryWithSparql("all_urn_w_types_toplevel", graphendpoint, parameters=None)
#     report_csv =report.to_csv()
#     # report_json = generateGraphReportsRepo("all",
#     #                                        "", reportList=reportTypes["all"])
#     s3Minio = s3.MinioDatastore( GLEANERIO_MINIO_ADDRESS, MINIO_OPTIONS)


