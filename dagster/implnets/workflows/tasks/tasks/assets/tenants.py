import json
from typing import Any
from io import StringIO
import yaml
import os
import pandas as pd
import pydash
from pydash import pick
from dagster import (asset,
                     AssetIn,
                     get_dagster_logger,
                     Output,
                     DynamicPartitionsDefinition,
                     define_asset_job,
                     AssetSelection,
                     sensor, SensorResult, DefaultSensorStatus,
                     RunRequest,
                     asset_sensor, AssetKey, AutoMaterializePolicy,
                     )
from ec.datastore import s3
from ..utils import strtobool
from ..resources.gleanerS3 import _pythonMinioAddress
from ec.reporting.report import generateReportStats
from .release_stats import release_record_count

PROJECT=os.environ.get('PROJECT')
GLEANER_MINIO_ADDRESS = os.environ.get('GLEANERIO_MINIO_ADDRESS')
GLEANER_MINIO_PORT = os.environ.get('GLEANERIO_MINIO_PORT')
GLEANER_MINIO_USE_SSL = bool(strtobool(os.environ.get('GLEANERIO_MINIO_USE_SSL', 'true')))
GLEANER_MINIO_SECRET_KEY = os.environ.get('GLEANERIO_MINIO_SECRET_KEY')
GLEANER_MINIO_ACCESS_KEY = os.environ.get('GLEANERIO_MINIO_ACCESS_KEY')
GLEANER_MINIO_BUCKET = os.environ.get('GLEANERIO_MINIO_BUCKET')
GLEANERIO_GRAPH_URL = os.environ.get('GLEANERIO_GRAPH_URL')
GLEANERIO_GRAPH_SUMMARY_NAMESPACE = os.environ.get('GLEANERIO_GRAPH_SUMMARY_NAMESPACE')

MINIO_OPTIONS={"secure":GLEANER_MINIO_USE_SSL

              ,"access_key": GLEANER_MINIO_ACCESS_KEY
              ,"secret_key": GLEANER_MINIO_SECRET_KEY
               }


@asset(group_name="community",key_prefix=f"{PROJECT}_task",
       required_resource_keys={"triplestore"},
       auto_materialize_policy=AutoMaterializePolicy.eager())
def task_tenant_sources(context) ->Any:
    s3_resource = context.resources.triplestore.s3
    t=s3_resource.getTennatInfo()
    tenants = t['tenant']
    listTenants = map (lambda a: {a['community']}, tenants)
    get_dagster_logger().info(str(t))

    return t
        #     metadata={
        #         "tennants": str(listTenants),  # Metadata can be any key-value pair
        #         "run": "gleaner",
        #         # The `MetadataValue` class has useful static methods to build Metadata
        #     }
        # )
@asset(group_name="community",key_prefix=f"{PROJECT}_task",
       required_resource_keys={"triplestore"},
       auto_materialize_policy=AutoMaterializePolicy.eager())
def task_sources_config(context) -> Any:
    """The sources: list from gleanerconfig.yaml.

    tenant.yaml names which sources are in a community; this is where the rest
    of a source lives -- propername, domain, url, logo, active -- which the
    community report used to take from the published sources sheet.
    """
    sources = context.resources.triplestore.s3.getSourcesInfo().get('sources', [])
    get_dagster_logger().info(f"{len(sources)} sources in gleanerconfig")
    return sources


@asset(group_name="community",key_prefix=f"{PROJECT}_task",
       #name='task_tenant_names',
       required_resource_keys={"triplestore"},
       auto_materialize_policy=AutoMaterializePolicy.eager() )
def task_tenant_names(context, task_tenant_sources) -> Output[Any]:

    tenants = task_tenant_sources['tenant']
    listTenants = map (lambda a: a['community'], tenants)
    get_dagster_logger().info(str(listTenants))
    communities = list(listTenants)
    return Output(
            communities,
            metadata={
                "tenants": str(listTenants),  # Metadata can be any key-value pair
                "run": "gleaner",
                # The `MetadataValue` class has useful static methods to build Metadata
            }
        )


community_partitions_def = DynamicPartitionsDefinition(name="tenantsPartition")
tenant_task_job = define_asset_job(
    "tenant_job", AssetSelection.keys(AssetKey([f"{PROJECT}_task","loadstatsCommunity"])), partitions_def=community_partitions_def
)
#@sensor(job=tenant_job)
@asset_sensor(asset_key=AssetKey([f"{PROJECT}_task","task_tenant_names"]),
               default_status=DefaultSensorStatus.RUNNING,
     job=tenant_task_job)
def community_sensor(context):
    tenants = context.repository_def.load_asset_value(AssetKey([f"{PROJECT}_task","task_tenant_names"]))
    new_community = [
        community
        for community in tenants
        if not context.instance.has_dynamic_partition(
            community_partitions_def.name, community
        )
    ]

    return SensorResult(
        run_requests=[
            RunRequest(partition_key=community) for community in new_community
        ],
        dynamic_partitions_requests=[
            community_partitions_def.build_add_request(new_community)
        ],
    )
REPORT_PATH = "reports/"
COMMUNITY_PATH = "reports/community/"
TASKS_PATH="tasks/"
ORG_PATH = "orgs/"
STAT_FILE_NAME = "load_report_graph.json"

def _pythonMinioUrl(url):

    if (url.endswith(".amazonaws.com")):
        PYTHON_MINIO_URL = "s3.amazonaws.com"
    else:
        PYTHON_MINIO_URL = url
    return PYTHON_MINIO_URL

def getName(name):
    return name.replace("orgs/","").replace(".nq","")
# @asset(group_name="community")
# def source_list(task_tenant_sources) -> Output(str):
#     s3Minio = s3.MinioDatastore(_pythonMinioUrl(GLEANER_MINIO_ADDRESS), MINIO_OPTIONS)
#     orglist = s3Minio.listPath(GLEANER_MINIO_BUCKET, ORG_PATH,recursive=False)
#     sources = map( lambda f: { "name": getName(f.object_name)}, orglist )
#     source_json = json.dumps(list(sources))
#     os.makedirs("data", exist_ok=True)
#
#     s3Minio.putReportFile(GLEANER_MINIO_BUCKET, "all", f"source_list.json", source_json )
#     with open("data/source_list.json", "w") as f:
#         json.dump(list(sources), f)
#     return source_json
#@asset(deps=[source_list])

# set a prefix so we can have some named stats file

def _sources_by_name(sources_config):
    """{name: source dict} from a parsed gleanerconfig.yaml sources list."""
    return {s['name']: s for s in sources_config if s.get('name')}


def _expand_tenant_sources(tenant_sources, sources_by_name, logger=None):
    """A tenant's sources: list resolved to concrete source names.

    'all' means every active source in gleanerconfig, matching what the ingest
    workflow does with it (assets/tenant.py). Both tenant.yaml and
    tenant_prod.yaml declare a geocodesall community exactly that way, so this
    is load bearing. A name with no gleanerconfig entry is dropped with a
    warning -- the two files are edited independently and do drift, and one
    stale name should not take a whole community's report down with it.
    """
    log = logger or get_dagster_logger()
    tenant_sources = tenant_sources or []

    if any(str(name).casefold() == "all" for name in tenant_sources):
        return [name for name, source in sources_by_name.items() if source.get('active')]

    names = []
    for name in tenant_sources:
        if name in sources_by_name:
            if name not in names:
                names.append(name)
        else:
            log.warning(f"tenant source {name} is not in gleanerconfig, skipping")
    return names


#@asset( group_name="load")
@asset(partitions_def=community_partitions_def,
       group_name="community",
       key_prefix=f"{PROJECT}_task",
       required_resource_keys={"triplestore"},
       ins={
           "task_tenant_sources": AssetIn(
               key=AssetKey([f"{PROJECT}_task", "task_tenant_sources"])),
           "task_sources_config": AssetIn(
               key=AssetKey([f"{PROJECT}_task", "task_sources_config"])),
           "source_release_counts": AssetIn(
               key=AssetKey([f"{PROJECT}_task", "source_release_counts"])),
       })
def loadstatsCommunity(context, task_tenant_sources, task_sources_config,
                       source_release_counts) -> Output[str]:
    """Harvest history and the source cards report, for one community.

    Both come from the config the pipeline already runs on: tenant.yaml for
    which sources are in the community, gleanerconfig.yaml for what each source
    is, and the releases for how many records it has.
    """
    logger = get_dagster_logger()
    s3_config = context.resources.triplestore.s3
    s3Minio = s3.MinioDatastore(_pythonMinioUrl(s3_config.GLEANERIO_MINIO_ADDRESS), MINIO_OPTIONS)
    community_code = context.partition_key

    tenant = pydash.find(task_tenant_sources["tenant"],
                         lambda t: t['community'] == community_code)
    if tenant is None:
        raise Exception(f"community {community_code} is not in the tenant file")

    sources_by_name = _sources_by_name(task_sources_config)
    names = _expand_tenant_sources(tenant.get("sources"), sources_by_name, context.log)
    context.log.info(f"community {community_code} resolves to {len(names)} sources: {names}")

    # ---- harvest history -> all_stats.csv
    stats = []
    for source in names:
        try:
            dirs = s3Minio.listPath(s3_config.GLEANERIO_MINIO_BUCKET,
                                    path=f"{REPORT_PATH}{source}/", recursive=False)
            for d in dirs:
                latestpath = f"{REPORT_PATH}{source}/latest/"
                if (d.object_name.casefold() == latestpath.casefold()) or (d.is_dir == False):
                    continue
                path = f"{d.object_name}{STAT_FILE_NAME}"
                s3ObjectInfo = {"bucket_name": s3_config.GLEANERIO_MINIO_BUCKET, "object_name": path}
                try:
                    resp = s3Minio.getFileFromStore(s3ObjectInfo)
                    stat = json.loads(resp)
                    stat = pick(stat, 'source', 'sitemap', 'date', 'sitemap_count', 'summoned_count',
                                'missing_sitemap_summon_count',
                                'graph_urn_count', 'missing_summon_graph_count')
                    stats.append(stat)
                except Exception as ex:
                    context.log.info(f"Failed to get report {path} for tenant {community_code}  {ex}")
        except Exception as ex:
            context.log.info(f"Failed to list reports for source {source} in tenant {community_code}  {ex}")

    df = pd.DataFrame(stats)
    df_csv = df.to_csv()

    s3Minio.putReportFile(s3_config.GLEANERIO_MINIO_BUCKET, f"tenant/{community_code}",
                          f"all_stats.csv", df_csv)
    context.log.info(
        f"all_stats.csv uploaded using ec.datastore.putReportFile "
        f"{s3_config.GLEANERIO_MINIO_BUCKET} tenant/{community_code} ")

    # ---- source cards -> report_stats.json
    # counts come from the shared source_release_counts asset. A source added to
    # tenant.yaml since that last ran is counted here rather than reported as 0.
    counts = dict(source_release_counts or {})
    for name in names:
        if name not in counts:
            context.log.info(f"{name} is not in source_release_counts, counting it now")
            counts[name] = release_record_count(s3_config, name, context.log)

    sources = [sources_by_name[name] for name in names]
    report = generateReportStats(sources, counts, community_code)

    if sources:
        s3Minio.putReportFile(s3_config.GLEANERIO_MINIO_BUCKET, f"tenant/{community_code}",
                              f"report_stats.json", report)
        context.log.info(
            f"report_stats.json uploaded using ec.datastore.putReportFile "
            f"{s3_config.GLEANERIO_MINIO_BUCKET} tenant/{community_code} ")
    else:
        # an empty report would overwrite a good one with []
        context.log.warning(
            f"community {community_code} resolved to no sources, "
            f"leaving the existing report_stats.json alone")

    return Output(
        df_csv,
        metadata={
            "community": community_code,
            "sources": len(names),
            "records": sum(counts.get(name, 0) for name in names),
            "sources_without_a_release": [n for n in names if not counts.get(n)],
        },
    )
