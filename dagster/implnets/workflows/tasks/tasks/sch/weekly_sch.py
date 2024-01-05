import distutils
import os

from dagster import schedule, RunRequest,  ScheduleEvaluationContext, define_asset_job, AssetSelection
from ec.datastore import s3
from ec.reporting.report import generateReportStats

GLEANER_MINIO_ADDRESS = str(os.environ.get('GLEANERIO_MINIO_ADDRESS'))
GLEANER_MINIO_PORT = str(os.environ.get('GLEANERIO_MINIO_PORT'))
GLEANER_MINIO_USE_SSL = bool(distutils.util.strtobool(os.environ.get('GLEANERIO_MINIO_USE_SSL')))
GLEANER_MINIO_SECRET_KEY = str(os.environ.get('GLEANERIO_MINIO_SECRET_KEY'))
GLEANER_MINIO_ACCESS_KEY = str(os.environ.get('GLEANERIO_MINIO_ACCESS_KEY'))
GLEANER_MINIO_BUCKET = str(os.environ.get('GLEANERIO_MINIO_BUCKET'))
# set for the earhtcube utiltiies
MINIO_OPTIONS = {"secure": GLEANER_MINIO_USE_SSL, "access_key": GLEANER_MINIO_ACCESS_KEY,
                 "secret_key": GLEANER_MINIO_SECRET_KEY}
GLEANERIO_SUMMARIZE_GRAPH=(os.getenv('GLEANERIO_GRAPH_SUMMARIZE', 'False').lower() == 'true')
GLEANER_GRAPH_URL = str(os.environ.get('GLEANERIO_GRAPH_URL'))
GLEANER_GRAPH_NAMESPACE = str(os.environ.get('GLEANERIO_GRAPH_NAMESPACE'))
GLEANERIO_SUMMARY_GRAPH_NAMESPACE = os.environ.get('GLEANERIO_GRAPH_SUMMARY_NAMESPACE', f"{GLEANER_GRAPH_NAMESPACE}_summary" )
GLEANERIO_CSV_CONFIG_URL = str(os.environ.get('GLEANERIO_CSV_CONFIG_URL'))

load_analytics_job = define_asset_job("load_analytics_job", selection=AssetSelection.groups("load"))
graph_analytics_job = define_asset_job("graph_analytics_job", selection=AssetSelection.groups("graph"))
report_stats_job = define_asset_job("report_stats_job", selection=AssetSelection.groups("stats"))

def _pythonMinioAddress(url, port = None):

    if (url.endswith(".amazonaws.com")):
        PYTHON_MINIO_URL = "s3.amazonaws.com"
    else:
        PYTHON_MINIO_URL = url
    if port is not None:
        PYTHON_MINIO_URL = f"{PYTHON_MINIO_URL}:{port}"
    return PYTHON_MINIO_URL

def _graphEndpoint():
    url = f"{GLEANER_GRAPH_URL}/namespace/{GLEANER_GRAPH_NAMESPACE}/sparql"
    return url

def _graphSummaryEndpoint():
    url = f"{GLEANER_GRAPH_URL}/namespace/{GLEANERIO_SUMMARY_GRAPH_NAMESPACE}/sparql"
    return url

@schedule(job=load_analytics_job, cron_schedule="@weekly")
def loadstats_schedule(context:  ScheduleEvaluationContext):

    return RunRequest(
        run_key=None,
        run_config={}

    )

@schedule(job=graph_analytics_job, cron_schedule="@weekly")
def all_graph_stats_schedule(context:  ScheduleEvaluationContext):

    return RunRequest(
        run_key=None,
        run_config={}

    )

@schedule(job=report_stats_job, cron_schedule="@weekly")
def all_report_stats_schedule(context:  ScheduleEvaluationContext):
    s3Minio = s3.MinioDatastore(_pythonMinioAddress(GLEANER_MINIO_ADDRESS, GLEANER_MINIO_PORT), MINIO_OPTIONS)
    bucket = GLEANER_MINIO_BUCKET
    summary_namespace = _graphSummaryEndpoint()
    source_url = GLEANERIO_CSV_CONFIG_URL

    if (GLEANERIO_SUMMARIZE_GRAPH):
        report = generateReportStats(source_url, bucket, s3Minio, summary_namespace, "all")
        s3Minio.putReportFile(bucket, "all", f"report_all_stats.json", report)

    return RunRequest(
        run_key=None,
        run_config={}

    )