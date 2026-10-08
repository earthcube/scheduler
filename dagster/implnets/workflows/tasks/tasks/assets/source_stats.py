import json
import os
from typing import List, Any
import pandas as pd
from io import StringIO
from dagster import (asset, get_dagster_logger, define_asset_job, AutoMaterializePolicy,
                     asset_check, AssetCheckExecutionContext, AssetCheckResult)
from ec.datastore import s3
from pydash import pick
from ..utils import strtobool
PROJECT=os.environ.get('PROJECT')
GLEANER_MINIO_ADDRESS = os.environ.get('GLEANERIO_MINIO_ADDRESS')
GLEANER_MINIO_PORT = os.environ.get('GLEANERIO_MINIO_PORT')
GLEANER_MINIO_USE_SSL = bool(strtobool(os.environ.get('GLEANERIO_MINIO_USE_SSL', 'true')))
GLEANER_MINIO_SECRET_KEY = os.environ.get('GLEANERIO_MINIO_SECRET_KEY')
GLEANER_MINIO_ACCESS_KEY = os.environ.get('GLEANERIO_MINIO_ACCESS_KEY')
GLEANER_MINIO_BUCKET = os.environ.get('GLEANERIO_MINIO_BUCKET')
# set for the earhtcube utiltiies
MINIO_OPTIONS={"secure":GLEANER_MINIO_USE_SSL

              ,"access_key": GLEANER_MINIO_ACCESS_KEY
              ,"secret_key": GLEANER_MINIO_SECRET_KEY
               }
REPORT_PATH = "reports/"
TASKS_PATH="tasks/"
ORG_PATH = "orgs/"
STAT_FILE_NAME = "load_report_release.json"
def _pythonMinioUrl(url):

    if (url.endswith(".amazonaws.com")):
        PYTHON_MINIO_URL = "s3.amazonaws.com"
    else:
        PYTHON_MINIO_URL = url
    return PYTHON_MINIO_URL

def getName(name):
    return name.replace("orgs/","").replace(".nq","")
@asset(group_name="load",key_prefix=f"{PROJECT}_task",
       auto_materialize_policy=AutoMaterializePolicy.eager())
def source_list() -> List[Any]:
    s3Minio = s3.MinioDatastore(_pythonMinioUrl(GLEANER_MINIO_ADDRESS), MINIO_OPTIONS)
    orglist = s3Minio.listPath(GLEANER_MINIO_BUCKET, ORG_PATH,recursive=False)
    sources = map( lambda f: { "name": getName(f.object_name)}, orglist )
    sources=list(sources)
    source_json = json.dumps(sources)
    os.makedirs("data", exist_ok=True)

    s3Minio.putReportFile(GLEANER_MINIO_BUCKET, "all", f"source_list.json", source_json )
    # with open("data/source_list.json", "w") as f:
    #     json.dump(list(sources), f)
    return sources
#@asset(deps=[source_list])

# set a prefix so we can have some named stats file

#@asset( group_name="load",key_prefix="task",)
@asset(group_name="load",key_prefix=f"{PROJECT}_task",)
def loadstatsHistory(context,source_list) -> str:
    prefix="history"
    logger = get_dagster_logger()
    s3Minio = s3.MinioDatastore(_pythonMinioUrl(GLEANER_MINIO_ADDRESS),MINIO_OPTIONS)
 #   sourcelist = list(s3Minio.listPath(GLEANER_MINIO_BUCKET, ORG_PATH,recursive=False))

    # with open("data/source_list.json","r" ) as f:
    #     sourcelist = json.load(f)
    sourcelist=source_list
    stats = []
    for source in sourcelist:
        try:
           # stat = s3Minio.getReportFile(GLEANER_MINIO_BUCKET,source.get("name"), STAT_FILE_NAME )
           repo = source.get("name")
           dirs = s3Minio.listPath( GLEANER_MINIO_BUCKET,f"{REPORT_PATH}{repo}/",recursive=False )
           for d in dirs:
               latestpath = f"{REPORT_PATH}{repo}/latest/"
               if (d.object_name.casefold() == latestpath.casefold()) or (d.is_dir == False):
                   continue
               path = f"{d.object_name}{STAT_FILE_NAME}"
               s3ObjectInfo = {"bucket_name": GLEANER_MINIO_BUCKET, "object_name": path}
               try:
                   resp = s3Minio.getFileFromStore(s3ObjectInfo)
                   stat = json.loads(resp)
                   stat = pick(stat, 'source', 'sitemap', 'date', 'sitemap_count', 'summoned_count',
                               'missing_sitemap_summon_count',
                               'release_urn_count', 'missing_summon_release_count')
                   stats.append(stat)
               except Exception as ex:
                   logger.info(f"no missing graph report {source.get('name')}  {ex}")
        except Exception as ex:
            logger.info(f"Failed to get { source.get('name')}  {ex}")
    df = pd.DataFrame(stats)
    # source_list happens to create this, but nothing here guarantees the two
    # ran in the same process
    os.makedirs("data", exist_ok=True)
    df.to_csv(f"data/all_stats.csv")
    df_csv = df.to_csv()
    s3Minio.putReportFile(GLEANER_MINIO_BUCKET, "all", f"all_stats.csv", df_csv)
    context.log.info(f"all_stats.csv uploaded using putReportFile s3://{GLEANER_MINIO_BUCKET} all ")
    #return df_csv
    return df_csv


# reports/{repo}/{date}/{filename}, per MinioDatastore.putReportFile
STAT_HISTORY_OBJECT = f"{REPORT_PATH}all/latest/all_stats.csv"


def _csv_data_row_count(csv_text) -> int:
    """Data rows in a csv, header and index column excluded.

    pandas writes an empty frame as "\n", which naive line counting scores as a
    row, so parse it rather than splitting.
    """
    if not csv_text or not csv_text.strip():
        return 0
    try:
        return len(pd.read_csv(StringIO(csv_text)))
    except pd.errors.EmptyDataError:
        return 0


def _object_size(gleaner_s3, object_name):
    """Size of an object, or None if it cannot be determined."""
    try:
        head = gleaner_s3.s3.get_client().head_object(
            Bucket=gleaner_s3.GLEANERIO_MINIO_BUCKET, Key=object_name
        )
        return head.get("ContentLength")
    except Exception as ex:
        get_dagster_logger().info(f"Could not size {object_name}: {ex}")
        return None


def _non_zero_length_check_result(gleaner_s3, object_name):
    size = _object_size(gleaner_s3, object_name)
    metadata = {
        "bucket_name": gleaner_s3.GLEANERIO_MINIO_BUCKET,
        "object_name": object_name,
    }
    if size is not None:
        metadata["size_bytes"] = size
    return AssetCheckResult(
        passed=size is not None and size > 0,
        metadata=metadata,
    )


# Two checks rather than one, because they fail for different reasons and want
# different fixes: the harvest produced no rows, versus the harvest produced
# rows and the write to s3 did not land.
@asset_check(asset=loadstatsHistory, name="non_zero_rows")
def loadstatsHistory_non_zero_rows(
    context: AssetCheckExecutionContext, loadstatsHistory
) -> AssetCheckResult:
    rows = _csv_data_row_count(loadstatsHistory)
    return AssetCheckResult(passed=rows > 0, metadata={"data_rows": rows})


@asset_check(asset=loadstatsHistory, name="non_zero_length",
             required_resource_keys={"s3"})
def loadstatsHistory_non_zero_length(
    context: AssetCheckExecutionContext,
) -> AssetCheckResult:
    return _non_zero_length_check_result(context.resources.s3, STAT_HISTORY_OBJECT)
