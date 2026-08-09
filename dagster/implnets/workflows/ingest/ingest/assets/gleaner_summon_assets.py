# a test asset to see that all the resource configurations load.
# basically runs the first step, of gleaner on geocodes demo datasets
from typing import Any
import json
import pandas as pd
import csv
import gc
import shutil
import tempfile
from contextlib import contextmanager
from urllib.error import HTTPError
from pathlib import Path

from dagster import (
    asset,op, Config, Output,AssetKey,
    define_asset_job, AssetSelection,
get_dagster_logger,BackfillPolicy
)
from ec.datastore import s3 as utils_s3
from ec.sitemap import Sitemap
import pyoxigraph as ox
from .gleaner_sources import sources_partitions_def
from ..utils import PythonMinioAddress

from ec.gleanerio.gleaner import getGleaner, getSitemapSourcesFromGleaner, endpointUpdateNamespace
from ec.reporting.report import missingReport, generateIdentifierRepo, generateGraphReportsRelease, generateGraphReportsRepo, reportTypes
from ec.graph.release_graph import ReleaseGraph
from ec.summarize import summaryDF2ttl, get_summary4graph, get_summary4repoSubset
import os
PROJECT=os.environ.get('PROJECT')
from ec.graph.manageGraph import ManageBlazegraph
SUMMARY_PATH = 'graphs/summary'
RELEASE_PATH = 'graphs/latest'
SPATIAL_PATH = 'graphs/latest'
SPATIAL_GRAPH_NAMESPACE = "https://gleaner.io/enhancement/spatial/{source}"

SPATIAL_QUERY_FILES = (
    "spatial_construct_bbox.rq",
    "spatial_construct_multipoint.rq",
)

# Releases at or above this size are loaded into a temporary on disk store rather
# than an in memory one. Measured on r2r, the largest release at 462MB / 2.45M
# quads, on disk is worse on every axis than streaming into memory:
#
#   in memory, whole file read into bytes   2.50 GB rss   3.0s
#   in memory, streamed                     2.02 GB rss   3.8s
#   on disk, streamed                       2.53 GB rss   9.0s   + 918 MB disk
#
# RocksDB's write buffers during a bulk load cost more than the on disk
# representation saves, so the default sits above every current release and this
# is a safety valve for growth rather than something that fires today. Lower
# GLEANERIO_SPATIAL_ONDISK_THRESHOLD_BYTES if a worker is memory bound and would
# rather trade wall clock and disk for headroom.
SPATIAL_ONDISK_THRESHOLD_BYTES = int(
    os.environ.get("GLEANERIO_SPATIAL_ONDISK_THRESHOLD_BYTES", 2 * 1024 ** 3)
)

class HarvestOpConfig(Config):
    source_name: str
# sources_partitions_def = StaticPartitionsDefinition(
#     ["geocodes_demo_datasets", "iris"]
# )

def getSource(context, source_name):
    sources = context.repository_def.load_asset_value(AssetKey([f"{PROJECT}_ingest","sources_all"]))
    source = list(filter(lambda t: t["name"]==source_name, sources))
    return source[0]

@asset(
    group_name="load",
    key_prefix=f"{PROJECT}_ingest",
      deps=[AssetKey([f"{PROJECT}_ingest","sources_names_active"]) ],
       partitions_def=sources_partitions_def, required_resource_keys={"gleanerio"}
 #   , backfill_policy=BackfillPolicy.single_run()
       )
def validate_sitemap_url(context):
    source_name = context.asset_partition_key_for_output()
    source = getSource(context, source_name)

    if source['sourcetype'] == "sitemap": # ie, skip this for type sitegraph
        sm = Sitemap(source['url'], no_progress_bar=True)
        if sm.validUrl():
            return source['url']
        else:
            context.log.error(f"source: {source['name']} bad url: {source['url']}")
            raise HTTPError(url=source['url'],
                            code=404,
                            hdrs=None,
                            fp=None,
                            msg=f"Bad URL source: {source['name']} bad url: {source['url']}" )

@asset(group_name="load",
key_prefix=f"{PROJECT}_ingest",
op_tags={"ingest": "docker"},
      deps=[ validate_sitemap_url  ],
       partitions_def=sources_partitions_def, required_resource_keys={"gleanerio"}
 #   , backfill_policy=BackfillPolicy.single_run()
       )
#@asset( required_resource_keys={"gleanerio"})
def gleanerio_run(context ) -> Output[Any]:
    gleaner_resource =  context.resources.gleanerio
    source= context.asset_partition_key_for_output()
    gleaner = gleaner_resource.execute(context, "gleaner", source )

    metadata={
                "source": source,  # Metadata can be any key-value pair
                "run": "gleaner",
                # The `MetadataValue` class has useful static methods to build Metadata
            }

    return Output(gleaner, metadata=metadata)
@asset(group_name="load",
key_prefix=f"{PROJECT}_ingest",
op_tags={"ingest": "docker"},
       deps=[gleanerio_run],
       partitions_def=sources_partitions_def, required_resource_keys={"gleanerio"}
  #     ,backfill_policy=BackfillPolicy.single_run()
     )
#@asset(required_resource_keys={"gleanerio"})
def release_nabu_run(context) -> Output[Any]:
    gleaner_resource = context.resources.gleanerio
    source= context.asset_partition_key_for_output()
    nabu=gleaner_resource.execute(context, "release", source )
    # get the file, count the lines
    filename= f"{RELEASE_PATH}/{source}_release.nq"
    context.log.info(f"release_nabu_ filename: {filename}")
    file = gleaner_resource.gs3.getFile(filename).read().decode('utf-8')
    line_count = len(file.split('\n'))
    metadata={
                "source": source,  # Metadata can be any key-value pair
                "run": "release",
                 "bucket_name": gleaner_resource.gs3.GLEANERIO_MINIO_BUCKET,  # Metadata can be any key-value pair
                 "object_name": f"{RELEASE_PATH}{source}",
                 "line_count": line_count,
                # The `MetadataValue` class has useful static methods to build Metadata
            }

    return Output(nabu, metadata=metadata)
''' Return results of summoning the JSON-LD SOS from a source.
This includes the number of url in the sitemap, how many jsonLD were 'summoned'
There may be multiple json-ld per web page, so this needs to be monitored over time.
And how many made it into milled (this is how good the conversion at a single jsonld to RDF is.

'''

@asset(
key_prefix=f"{PROJECT}_ingest",
    group_name="load",
op_tags={"ingest": "report"},
       deps=[gleanerio_run], partitions_def=sources_partitions_def, required_resource_keys={"gleanerio"}
  #  , backfill_policy=BackfillPolicy.single_run()
)
def load_report_s3(context):
    gleaner_resource = context.resources.gleanerio
    s3_resource = context.resources.gleanerio.gs3.s3
    gleaner_s3 =  context.resources.gleanerio.gs3
    source_name = context.asset_partition_key_for_output()
    # source = getSitemapSourcesFromGleaner(gleaner_resource.GLEANERIO_GLEANER_CONFIG_PATH, sourcename=source_name)
    source = getSource(context, source_name)
    source_url = source.get('url')
    s3Minio = utils_s3.MinioDatastore(PythonMinioAddress(gleaner_s3.GLEANERIO_MINIO_ADDRESS,
                                                          gleaner_s3.GLEANERIO_MINIO_PORT),
                                       gleaner_s3.MinioOptions()
                                      )
    bucket = gleaner_s3.GLEANERIO_MINIO_BUCKET

    graphendpoint = None
    milled = False
    summon = True
    returned_value = missingReport(source_url, bucket, source_name, s3Minio, graphendpoint, milled=milled, summon=summon)
    r = str('load repoort returned value:{}'.format(returned_value))
    report = json.dumps(returned_value, indent=2)
    s3Minio.putReportFile(bucket, source_name, "load_report_s3.json", report)
    get_dagster_logger().info(f"load s3 report  returned  {r} ")
    return


''' Return results of what  JSON-LD SOS is the S3 store, and compares it to the 'Named' graphs
in the graph store. This extends the load report s3.
This includes the number of url in the sitemap, how many jsonLD were 'summoned'
There may be multiple json-ld per web page, so this needs to be monitored over time.
And how many made it into milled (this is how good the conversion at a single jsonld to RDF is.
It then compares what identifiers are in the S3 store (summon path), and the Named Graph URI's
'''

@asset(
key_prefix=f"{PROJECT}_ingest",
    group_name="load",
op_tags={"ingest": "report"},
       deps=[release_nabu_run], partitions_def=sources_partitions_def, required_resource_keys={"gleanerio"}
  #  , backfill_policy=BackfillPolicy.single_run()
)
def load_report_graph(context):
    gleaner_resource = context.resources.gleanerio
    s3_resource = context.resources.gleanerio.gs3.s3
    gleaner_s3 =  context.resources.gleanerio.gs3
    gleaner_triplestore = context.resources.gleanerio.triplestore

    source_name = context.asset_partition_key_for_output()
    # source = getSitemapSourcesFromGleaner(gleaner_resource.GLEANERIO_GLEANER_CONFIG_PATH, sourcename=source_name)
    source = getSource(context, source_name)
    source_url = source.get('url')
    s3Minio = utils_s3.MinioDatastore(PythonMinioAddress(gleaner_s3.GLEANERIO_MINIO_ADDRESS,
                                                          gleaner_s3.GLEANERIO_MINIO_PORT),
                                       gleaner_s3.MinioOptions()
                                      )
    bucket = gleaner_s3.GLEANERIO_MINIO_BUCKET

    graphendpoint = gleaner_triplestore.GraphEndpoint(gleaner_resource.GLEANERIO_GRAPH_NAMESPACE)
    milled = False
    summon = True
    returned_value = missingReport(source_url, bucket, source_name, s3Minio, graphendpoint, milled=milled, summon=False) # summon false. we want the graph
    r = str('load repoort graph returned value:{}'.format(returned_value))
    report = json.dumps(returned_value, indent=2)
    s3Minio.putReportFile(bucket, source_name, "load_report_graph.json", report)
    get_dagster_logger().info(f"load  report to graph returned  {r} ")
    return
class S3ObjectInfo:
    bucket_name=""
    object_name=""


def _spatial_query_text(filename):
    return (Path(__file__).resolve().parent.parent / "files" / filename).read_text()


def _construct_to_quads(ntriples_text, graph_iri):
    quads = []
    for line in ntriples_text.splitlines():
        triple = line.strip()
        if not triple:
            continue
        quads.append(f"{triple.removesuffix(' .')} <{graph_iri}> .")
    return "\n".join(quads) + ("\n" if quads else "")


def _bulk_load(store, release):
    """Load an n-quads release, from bytes or a readable, into ``store``.

    rdflib parsed this fine, but its SPARQL evaluator is roughly quadratic in
    graph size: 23k quads took 45s of query time, 46k took 179s, so a real
    release never finished. Oxigraph does 2.45M quads in ~4s end to end.

    lenient: releases in the wild contain named graph URNs that nabu mints from
    the identifier, like <urn:gleaner.io:eco:geocodes_examples:data:[OTLAS.1]>.
    Square brackets are reserved for IPv6 literals and are not legal in an IRI,
    so a validating parser rejects them -- and one bad quad aborts the whole
    load, not just that line. rdflib accepted them, so this keeps the previous
    behaviour rather than dropping sources on the floor. 756 of the 2920 quads
    in the geocodes_examples release are affected.
    """
    store.bulk_load(release, format=ox.RdfFormat.N_QUADS, lenient=True)
    return store


def _load_release_store(release_bytes):
    """In memory store from a release already held in memory. Used by the tests."""
    return _bulk_load(ox.Store(), release_bytes)


def _release_object_size(gleaner_s3, object_name):
    """Size of the release object, or None if it cannot be determined."""
    try:
        head = gleaner_s3.s3.get_client().head_object(
            Bucket=gleaner_s3.GLEANERIO_MINIO_BUCKET, Key=object_name
        )
        return head.get("ContentLength")
    except Exception as ex:  # a missing size only costs us the on disk decision
        get_dagster_logger().info(f"Spatial. Could not size {object_name}: {ex}")
        return None


@contextmanager
def _release_store(gleaner_s3, object_name):
    """Open a store over a release, on disk if the release is big enough.

    The body is streamed straight from s3 into the parser rather than read into
    a bytes object first. On r2r that is 480MB of peak RSS saved for ~0.8s of
    wall clock, and it is the difference that actually moves the needle -- see
    SPATIAL_ONDISK_THRESHOLD_BYTES for why the on disk path is not the default.
    """
    size = _release_object_size(gleaner_s3, object_name)
    on_disk = size is not None and size >= SPATIAL_ONDISK_THRESHOLD_BYTES
    tempdir = tempfile.mkdtemp(prefix="spatial_release_") if on_disk else None
    store = None
    try:
        store = ox.Store(path=str(Path(tempdir) / "store")) if on_disk else ox.Store()
        get_dagster_logger().info(
            f"Spatial. Loading {object_name} ({size} bytes) into "
            f"{'an on disk store at ' + tempdir if on_disk else 'an in memory store'}"
        )
        _bulk_load(store, gleaner_s3.getFile(object_name))
        yield store
    finally:
        if tempdir is not None:
            # the store holds the rocksdb files open and pyoxigraph exposes no
            # close(), so drop the reference and collect before unlinking
            store = None
            gc.collect()
            shutil.rmtree(tempdir, ignore_errors=True)


def _run_construct_query(store, query):
    # the release puts every dataset in its own named graph, and nothing in the
    # default graph. rdflib's ConjunctiveGraph queried the union implicitly;
    # oxigraph is spec correct and would otherwise match nothing at all.
    triples = store.query(query, use_default_graph_as_union=True)
    return ox.serialize(triples, format=ox.RdfFormat.N_TRIPLES).decode("utf-8")


@asset(group_name="load",key_prefix=f"{PROJECT}_ingest",
       name="release_summarize",
       deps=[release_nabu_run], partitions_def=sources_partitions_def, required_resource_keys={"gleanerio"}
   # , backfill_policy=BackfillPolicy.single_run()
       )
def release_summarize(context) :
    gleaner_resource = context.resources.gleanerio
    s3_resource = context.resources.gleanerio.gs3.s3
    gleaner_s3 =  context.resources.gleanerio.gs3
    triplestore =context.resources.gleanerio.triplestore
    source_name = context.asset_partition_key_for_output()
    #source = getSitemapSourcesFromGleaner(gleaner_resource.GLEANERIO_GLEANER_CONFIG_PATH, sourcename=source_name)
    source = getSource(context,source_name)
    source_url = source.get('url')
    s3Minio = utils_s3.MinioDatastore(PythonMinioAddress(gleaner_s3.GLEANERIO_MINIO_ADDRESS,
                                                          gleaner_s3.GLEANERIO_MINIO_PORT),
                                       gleaner_s3.MinioOptions()
                                      )
    bucket = gleaner_s3.GLEANERIO_MINIO_BUCKET

    endpoint = triplestore.GraphEndpoint(gleaner_resource.GLEANERIO_GRAPH_NAMESPACE)
    # getting data, not uploading data
    #summary_namespace = _graphSummaryEndpoint()

    try:
        temp_namespace = f"{source_name}_temp"
        bg = ManageBlazegraph(triplestore.GLEANERIO_GRAPH_URL, temp_namespace)
        try:
            msg = bg.createNamespace(quads=True)
            context.log.info(f"temp graph creation  {temp_namespace} {triplestore.GLEANERIO_GRAPH_URL} {msg}")

        except Exception as ex:
            context.log.error(f"temp graph creation failed {temp_namespace} {triplestore.GLEANERIO_GRAPH_URL} {ex}")
            raise Exception(f"temp graph creation failed {temp_namespace} {triplestore.GLEANERIO_GRAPH_URL} {ex}")
        try:
            filename = f"https://{PythonMinioAddress(gleaner_s3.GLEANERIO_MINIO_ADDRESS,gleaner_s3.GLEANERIO_MINIO_PORT)}/{bucket}/{RELEASE_PATH}/{source_name}_release.nq"
            endpoint = triplestore.GraphEndpoint(temp_namespace)
            triplestore.post_to_graph(source_name, path=RELEASE_PATH, extension="nq", graphendpoint=endpoint)
            context.log.info(f"temp graph {filename}  loaded  {temp_namespace} {triplestore.GLEANERIO_GRAPH_URL} {msg}")

        except Exception as ex:
            context.log.error(f"temp graph {filename} load failed {temp_namespace} {triplestore.GLEANERIO_GRAPH_URL} {ex}")
            raise Exception(f"temp graph {filename}  load failed {temp_namespace} {triplestore.GLEANERIO_GRAPH_URL} {ex}")

        summarydf = get_summary4repoSubset(endpoint, source_name)

        try:
            msg = bg.deleteNamespace()
            context.log.info(f"temp graph deletion  {temp_namespace} {triplestore.GLEANERIO_GRAPH_URL} {msg}")

        except Exception as ex:
            context.log.error(f"temp graph deletion failed {temp_namespace} {triplestore.GLEANERIO_GRAPH_URL} {ex}")
            raise Exception(f"temp graph deletion failed {temp_namespace} {triplestore.GLEANERIO_GRAPH_URL} {ex}")
        # rg = ReleaseGraph()
        # rg.read_release(PythonMinioAddress(gleaner_s3.GLEANERIO_MINIO_ADDRESS,
        #                                                   gleaner_s3.GLEANERIO_MINIO_PORT),
        #                 bucket,
        #                 source_name,
        #                 options=gleaner_s3.MinioOptions())
        # summarydf = rg.summarize()
        nt, g = summaryDF2ttl(summarydf, source_name)  # let's try the new generator
        summaryttl = g.serialize(format='longturtle')
        line_count = len(summaryttl.split('\n'))
        # Lets always write out file to s3, and insert as a separate process
        # we might be able to make this an asset..., but would need to be acessible by http
        # if not stored in s3
        objectname = f"{SUMMARY_PATH}/{source_name}_release_summary.ttl"  # needs to match that is expected by post
        s3ObjectInfo = S3ObjectInfo()
        s3ObjectInfo.bucket_name = bucket
        s3ObjectInfo.object_name = objectname

        bucket_name, object_name =s3Minio.putTextFileToStore(summaryttl, s3ObjectInfo)
        context.add_output_metadata(
            metadata={
                "source": source_name,  # Metadata can be any key-value pair
                "run": "release_summarize",
                "bucket_name": bucket_name,  # Metadata can be any key-value pair
                "object_name": object_name,
                "line_count": line_count,
                # The `MetadataValue` class has useful static methods to build Metadata
            }
        )
        # inserted = sumnsgraph.insert(bytes(summaryttl, 'utf-8'), content_type="application/x-turtle")
        # if not inserted:
        #    raise Exception("Loading to graph failed.")
    except Exception as e:
        # use dagster logger
        get_dagster_logger().error(f"Summary. Issue creating graph  {str(e)} ")
        raise Exception(f"Loading Summary graph failed. {str(e)}")
        return 1

    return


@asset(group_name="load",key_prefix=f"{PROJECT}_ingest",
       deps=[release_nabu_run], partitions_def=sources_partitions_def, required_resource_keys={"gleanerio"}
       )
def spatial_release_quads(context):
    gleaner_s3 = context.resources.gleanerio.gs3
    source_name = context.asset_partition_key_for_output()
    s3Minio = utils_s3.MinioDatastore(PythonMinioAddress(gleaner_s3.GLEANERIO_MINIO_ADDRESS,
                                                          gleaner_s3.GLEANERIO_MINIO_PORT),
                                       gleaner_s3.MinioOptions()
                                      )
    bucket = gleaner_s3.GLEANERIO_MINIO_BUCKET
    graph_iri = SPATIAL_GRAPH_NAMESPACE.format(source=source_name)
    try:
        with _release_store(gleaner_s3, f"{RELEASE_PATH}/{source_name}_release.nq") as release_store:
            spatial_nq = "".join(
                _construct_to_quads(_run_construct_query(release_store, _spatial_query_text(query_file)), graph_iri)
                for query_file in SPATIAL_QUERY_FILES
            )
        objectname = f"{SPATIAL_PATH}/{source_name}_spatial.nq"
        # a source with no spatial coverage produces no quads. writing that as an
        # empty object just publishes a zero byte file for nabu to pick up, so
        # skip the upload and say so in the metadata instead.
        if not spatial_nq.strip():
            get_dagster_logger().info(
                f"Spatial. No spatial quads constructed for {source_name}, skipping upload of {objectname}"
            )
            context.add_output_metadata(
                metadata={
                    "source": source_name,
                    "run": "spatial_release_quads",
                    "bucket_name": bucket,
                    "object_name": "",
                    "line_count": 0,
                    "graph": graph_iri,
                    "uploaded": False,
                }
            )
            return
        s3ObjectInfo = S3ObjectInfo()
        s3ObjectInfo.bucket_name = bucket
        s3ObjectInfo.object_name = objectname
        bucket_name, object_name = s3Minio.putTextFileToStore(spatial_nq, s3ObjectInfo)
        context.add_output_metadata(
            metadata={
                "source": source_name,
                "run": "spatial_release_quads",
                "bucket_name": bucket_name,
                "object_name": object_name,
                "line_count": len(spatial_nq.splitlines()),
                "graph": graph_iri,
                "uploaded": True,
            }
        )
    except Exception as e:
        get_dagster_logger().error(f"Spatial. Issue creating graph  {str(e)} ")
        raise Exception(f"Loading spatial graph failed. {str(e)}")
    return

@asset(group_name="load",key_prefix=f"{PROJECT}_ingest",
       deps=[gleanerio_run],
op_tags={"ingest": "report"},
       partitions_def=sources_partitions_def, required_resource_keys={"gleanerio"}
   # , backfill_policy=BackfillPolicy.single_run()
       )
def identifier_stats(context):
    gleaner_resource = context.resources.gleanerio
    s3_resource = context.resources.gleanerio.gs3.s3
    gleaner_s3 =  context.resources.gleanerio.gs3
    triplestore =context.resources.gleanerio.triplestore
    source_name = context.asset_partition_key_for_output()
    # source = getSitemapSourcesFromGleaner(gleaner_resource.GLEANERIO_GLEANER_CONFIG_PATH, sourcename=source_name)
    source = getSource(context, source_name)
    source_url = source.get('url')
    s3Minio = utils_s3.MinioDatastore(PythonMinioAddress(gleaner_s3.GLEANERIO_MINIO_ADDRESS,
                                                          gleaner_s3.GLEANERIO_MINIO_PORT),
                                       gleaner_s3.MinioOptions()
                                      )
    bucket = gleaner_s3.GLEANERIO_MINIO_BUCKET


    returned_value = generateIdentifierRepo(source_name, bucket, s3Minio)
    r = str('returned value:{}'.format(returned_value))
    #r = str('identifier stats returned value:{}'.format(returned_value))
    report = returned_value.to_json()
    s3Minio.putReportFile(bucket, source_name, "identifier_stats.json", report)
    get_dagster_logger().info(f"identifier stats report  returned  {r} ")
    return

@asset(group_name="load",key_prefix=f"{PROJECT}_ingest",
       deps=[gleanerio_run],
op_tags={"ingest": "report"},
       partitions_def=sources_partitions_def, required_resource_keys={"gleanerio"}
   # , backfill_policy=BackfillPolicy.single_run()
       )
def bucket_urls(context):
    gleaner_resource = context.resources.gleanerio
    s3_resource = context.resources.gleanerio.gs3.s3
    gleaner_s3 =  context.resources.gleanerio.gs3
    triplestore =context.resources.gleanerio.triplestore
    source_name = context.asset_partition_key_for_output()
    # source = getSitemapSourcesFromGleaner(gleaner_resource.GLEANERIO_GLEANER_CONFIG_PATH, sourcename=source_name)
    source = getSource(context, source_name)
    source_url = source.get('url')
    s3Minio = utils_s3.MinioDatastore(PythonMinioAddress(gleaner_s3.GLEANERIO_MINIO_ADDRESS,
                                                          gleaner_s3.GLEANERIO_MINIO_PORT),
                                       gleaner_s3.MinioOptions()
                                      )
    bucket = gleaner_s3.GLEANERIO_MINIO_BUCKET


    res = s3Minio.listSummonedUrls(bucket, source_name)
    r = str('returned value:{}'.format(res))
    bucketurls =  pd.DataFrame(res).to_csv(index=False, quoting=csv.QUOTE_NONNUMERIC)
    s3Minio.putReportFile(bucket, source_name, "bucketutil_urls.csv", bucketurls)
    get_dagster_logger().info(f"bucker urls report  returned  {r} ")
    return

# original code. inlined.
# def _releaseUrl( source, path=RELEASE_PATH, extension="nq"):
#     proto = "http"
#     if GLEANER_MINIO_USE_SSL:
#         proto = "https"
#     address = _pythonMinioAddress(GLEANER_MINIO_ADDRESS, GLEANER_MINIO_PORT)
#     bucket = GLEANER_MINIO_BUCKET
#     release_url = f"{proto}://{address}/{bucket}/{path}/{source}_release.{extension}"
#     return release_url
@asset(group_name="load",key_prefix=f"{PROJECT}_ingest",
       deps=[release_nabu_run],
op_tags={"ingest": "report"},
       partitions_def=sources_partitions_def, required_resource_keys={"gleanerio"}
   # , backfill_policy=BackfillPolicy.single_run()
       )
def graph_stats_report(context) :
    gleaner_resource = context.resources.gleanerio
    s3_resource = context.resources.gleanerio.gs3.s3
    gleaner_s3 = context.resources.gleanerio.gs3
    triplestore = context.resources.gleanerio.triplestore
    source_name = context.asset_partition_key_for_output()
    # source = getSitemapSourcesFromGleaner(gleaner_resource.GLEANERIO_GLEANER_CONFIG_PATH, sourcename=source_name)
    source = getSource(context, source_name)
    source_url = source.get('url')
    s3Minio = utils_s3.MinioDatastore(PythonMinioAddress(gleaner_s3.GLEANERIO_MINIO_ADDRESS,
                                                         gleaner_s3.GLEANERIO_MINIO_PORT),
                                      gleaner_s3.MinioOptions()
                                      )
    bucket = gleaner_s3.GLEANERIO_MINIO_BUCKET

    #returned_value = generateGraphReportsRepo(source_name,  graphendpoint, reportList=reportTypes["repo_detailed"])
    proto = "http"
    if gleaner_s3.GLEANERIO_MINIO_USE_SSL:
        proto = "https"
    address = PythonMinioAddress(gleaner_s3.GLEANERIO_MINIO_ADDRESS, gleaner_s3.GLEANERIO_MINIO_PORT)

    s3FileUrl = f"{proto}://{address}/{bucket}/{RELEASE_PATH}/{source_name}_release.nq"

    endpoint = triplestore.GraphEndpoint(gleaner_resource.GLEANERIO_GRAPH_NAMESPACE)
    # getting data, not uploading data
    # summary_namespace = _graphSummaryEndpoint()

    try:
        temp_namespace = f"{source_name}_report_temp"
        bg = ManageBlazegraph(triplestore.GLEANERIO_GRAPH_URL, temp_namespace)
        endpoint = triplestore.GraphEndpoint(temp_namespace)
        context.log.info(f"temp {temp_namespace} graph endpoint  {endpoint}")

        try:
            msg = bg.createNamespace(quads=True)
            context.log.info(f"temp graph creation  {temp_namespace} {triplestore.GLEANERIO_GRAPH_URL} {msg}")
        except Exception as ex:
            context.log.error(f"temp graph creation failed {temp_namespace} {triplestore.GLEANERIO_GRAPH_URL} {ex}")
            raise Exception(f"temp graph creation failed {temp_namespace} {triplestore.GLEANERIO_GRAPH_URL} {ex}")
        try:
            triplestore.post_to_graph(source_name, path=RELEASE_PATH, extension="nq", graphendpoint=endpoint)
            context.log.info(f"temp graph {s3FileUrl}  loaded  {temp_namespace} {triplestore.GLEANERIO_GRAPH_URL} {msg}")

        except Exception as ex:
            context.log.error(
                f"temp graph {s3FileUrl} load failed {temp_namespace} {triplestore.GLEANERIO_GRAPH_URL} {ex}")
            raise Exception(
                f"temp graph {s3FileUrl}  load failed {temp_namespace} {triplestore.GLEANERIO_GRAPH_URL} {ex}")

        #returned_value = generateGraphReportsRelease(source_name, s3FileUrl)
        returned_value = generateGraphReportsRepo(source_name, endpoint, reportList=reportTypes["repo"])
        try:

            msg = bg.deleteNamespace()
            context.log.info(f"temp graph deletion  {temp_namespace} {triplestore.GLEANERIO_GRAPH_URL} {msg}")

        except Exception as ex:
            context.log.error(f"temp graph deletion failed {temp_namespace} {triplestore.GLEANERIO_GRAPH_URL} {ex}")
            raise Exception(f"temp graph deletion failed {temp_namespace} {triplestore.GLEANERIO_GRAPH_URL} {ex}")
        r = str('returned value:{}'.format(returned_value))
        # report = json.dumps(returned_value, indent=2) # value already json.dumps
        report = returned_value
        s3Minio.putReportFile(bucket, source_name, "graph_stats.json", report)
        get_dagster_logger().info(f"graph stats  returned  {r} ")
        return
    except Exception as e:
        # use dagster logger
        get_dagster_logger().error(f"Summary. Issue creating graph  {str(e)} ")
        raise Exception(f"Loading Summary graph failed. {str(e)}")
        return 1


# below loaded data into an rdflib and tran stats. this is slow.
def graph_stats_report_releasefile(context) :
    gleaner_resource = context.resources.gleanerio
    s3_resource = context.resources.gleanerio.gs3.s3
    gleaner_s3 = context.resources.gleanerio.gs3
    triplestore = context.resources.gleanerio.triplestore
    source_name = context.asset_partition_key_for_output()
    # source = getSitemapSourcesFromGleaner(gleaner_resource.GLEANERIO_GLEANER_CONFIG_PATH, sourcename=source_name)
    source = getSource(context, source_name)
    source_url = source.get('url')
    s3Minio = utils_s3.MinioDatastore(PythonMinioAddress(gleaner_s3.GLEANERIO_MINIO_ADDRESS,
                                                         gleaner_s3.GLEANERIO_MINIO_PORT),
                                      gleaner_s3.MinioOptions()
                                      )
    bucket = gleaner_s3.GLEANERIO_MINIO_BUCKET

    #returned_value = generateGraphReportsRepo(source_name,  graphendpoint, reportList=reportTypes["repo_detailed"])
    proto = "http"
    if gleaner_s3.GLEANERIO_MINIO_USE_SSL:
        proto = "https"
    address = PythonMinioAddress(gleaner_s3.GLEANERIO_MINIO_ADDRESS, gleaner_s3.GLEANERIO_MINIO_PORT)

    s3FileUrl = f"{proto}://{address}/{bucket}/{RELEASE_PATH}/{source_name}_release.nq"
    #s3FileUrl = _releaseUrl(source_name )
    get_dagster_logger().info(f"get release for {source_name} from   returned  {s3FileUrl} ")
    returned_value = generateGraphReportsRelease(source_name,s3FileUrl)
    r = str('returned value:{}'.format(returned_value))
    #report = json.dumps(returned_value, indent=2) # value already json.dumps
    report = returned_value
    s3Minio.putReportFile(bucket, source_name, "graph_stats.json", report)
    get_dagster_logger().info(f"graph stats  returned  {r} ")
    return

#might need to use this https://docs.dagster.io/_apidocs/repositories#dagster.RepositoryDefinition.get_asset_value_loader
#@sensor(job=summon_asset_job)
# @sensor(asset_selection=AssetSelection.keys("gleanerio_orgs"))
# def sources_sensor(context ):
#     sources =  gleanerio_orgs
#     new_sources = [
#         source
#         for source in sources
#         if not sources_partitions_def.has_partition_key(
#             source, dynamic_partitions_store=context.instance
#         )
#     ]
#
#     return SensorResult(
#         run_requests=[
#             RunRequest(partition_key=source) for source in new_sources
#         ],
#         dynamic_partitions_requests=[
#             sources_partitions_def.build_add_request(new_sources)
#         ],
#     )

# need to add a sensor to add paritions when one is added
# https://docs.dagster.io/concepts/partitions-schedules-sensors/partitioning-assets#dynamically-partitioned-assets


# #########
# CRUFT
#  worked to see if this could be a graph with an assent, and really a defiend asset job works better

# ## partitioning
# ####
# class HarvestOpConfig(Config):
#     source_name: str
# @dynamic_partitioned_config(partition_fn=gleanerio_orgs)
# def harvest_config(partition_key: str):
#     return {
#         "ops":
#             {"harvest_and_release":
#                  {"config": {"source_name": partition_key},
#                   "ops": {
#                       "gleanerio_run":
#                            {"config": {"source_name": partition_key}
#                             },
#                       "nabu_release_run":
#                            {"config": {"source_name": partition_key}
#                             }
#                   }
#                   }
#              }
#     }
#
# # ops:
# #   harvest_and_release:
# #     ops:
# #       gleanerio_run:
# #         config:
# #           source_name: ""
# #       nabu_release_run:
# #         config:
# #           source_name: ""
#
# @graph_asset(partitions_def=sources_partitions_def)
# #@graph_asset( )
# def harvest_and_release() :
#     #source = context.asset_partition_key_for_output()
#     #containers = getImage()
#     #harvest = gleanerio_run(start=containers)
#     harvest = gleanerio_run()
#     release = nabu_release_run(harvest)
#     return release
#
# #@asset
# # def harvest_op(context, config: HarvestOpConfig):
# #     context.log.info(config.source_name)
# #     harvest = gleanerio_run()
# #     release = nabu_release_run(harvest)
# #     return release
#
# # @job(config=harvest_config)
# # def harvest_job( ):
# #     harvest_op()
#     #harvest_and_release()
# # @schedule(cron_schedule="0 0 * * *", job=harvest_job)
# # def geocodes_schedule():
# #     return RunRequest(partition_key="iris")
