import distutils

from dagster import op, graph, get_dagster_logger
import subprocess
import os, json, io
import urllib
from urllib import request
from dagster import job, op, get_dagster_logger
from ec.gleanerio.gleaner import getGleaner, getSitemapSourcesFromGleaner
from minio import Minio
from minio.error import S3Error
from datetime import datetime
from ec.reporting.report import missingReport, generateGraphReportsRepo, reportTypes
from ec.datastore import s3
from ec.graph.manageGraph import ManageBlazegraph as mg

import requests
import logging as log

from urllib.error import HTTPError
from ec.reporting.report import missingReport
from ec.datastore import s3

DEBUG=os.environ.get('DEBUG')
GLEANER_CONFIG_VOLUME=os.environ.get('GLEANER_CONFIG_VOLUME')
# Vars and Envs
GLEANER_HEADLESS_NETWORK=os.environ.get('GLEANER_HEADLESS_NETWORK')
# env items
URL = os.environ.get('PORTAINER_URL')
APIKEY = os.environ.get('PORTAINER_KEY')


GLEANER_MINIO_ADDRESS = os.environ.get('GLEANER_MINIO_ADDRESS')
GLEANER_MINIO_PORT = os.environ.get('GLEANER_MINIO_PORT')
GLEANER_MINIO_USE_SSL = os.environ.get('GLEANER_MINIO_USE_SSL')
GLEANER_MINIO_SECRET_KEY = os.environ.get('GLEANER_MINIO_SECRET_KEY')
GLEANER_MINIO_ACCESS_KEY = os.environ.get('GLEANER_MINIO_ACCESS_KEY')
GLEANER_MINIO_BUCKET = os.environ.get('GLEANER_MINIO_BUCKET')
GLEANER_HEADLESS_ENDPOINT = os.environ.get('GLEANER_HEADLESS_ENDPOINT')
# using GLEANER, even though this is a nabu property... same prefix seems easier
GLEANER_GRAPH_URL = os.environ.get('GLEANER_GRAPH_URL')
GLEANER_GRAPH_NAMESPACE = os.environ.get('GLEANER_GRAPH_NAMESPACE')


def _graphEndpoint():
    url = f"{os.environ.get('GLEANER_GRAPH_URL')}/namespace/{os.environ.get('GLEANER_GRAPH_NAMESPACE')}/sparql"
    return url

def _pythonMinioUrl(url):

    if (url.endswith(".amazonaws.com")):
        PYTHON_MINIO_URL = "s3.amazonaws.com"
    else:
        PYTHON_MINIO_URL = url
    return PYTHON_MINIO_URL
def read_file_bytestream(image_path):
    data = open(image_path, 'rb').read()
    return data


def load_data(file_or_url):
    try:
        with urllib.request.urlopen(file_or_url) as f:
            data = f.read()
    except ValueError:
        with open(file_or_url, 'rb') as f:
            data = f.read()
    return data


def s3reader(object):
    server =  _pythonMinioUrl(os.environ.get('GLEANER_MINIO_ADDRESS')) + ":" + os.environ.get('GLEANER_MINIO_PORT')
    get_dagster_logger().info(f"S3 URL    : {str(os.environ.get('GLEANER_MINIO_ADDRESS'))}")
    get_dagster_logger().info(f"S3 PYTHON SERVER : {server}")
    get_dagster_logger().info(f"S3 PORT   : {str(os.environ.get('GLEANER_MINIO_PORT'))}")
    # get_dagster_logger().info(f"S3 read started : {str(os.environ.get('GLEANER_MINIO_KEY'))}")
    # get_dagster_logger().info(f"S3 read started : {str(os.environ.get('GLEANER_MINIO_SECRET'))}")
    get_dagster_logger().info(f"S3 BUCKET : {str(os.environ.get('GLEANER_MINIO_BUCKET'))}")
    get_dagster_logger().info(f"S3 object : {str(object)}")

    client = Minio(
        server,
        # secure=True,
        secure = bool(distutils.util.strtobool(os.environ.get('GLEANER_MINIO_USE_SSL'))),
        access_key=os.environ.get('GLEANER_MINIO_ACCESS_KEY'),
        secret_key=os.environ.get('GLEANER_MINIO_SECRET_KEY'),
    )
    try:
        data = client.get_object(os.environ.get('GLEANER_MINIO_BUCKET'), object)
        return data
    except S3Error as err:
        get_dagster_logger().info(f"S3 read error : {str(err)}")


def s3loader(data, name):
    secure= bool(distutils.util.strtobool(os.environ.get('GLEANER_MINIO_USE_SSL')))
    if (os.environ.get('GLEANER_MINIO_PORT') and os.environ.get('GLEANER_MINIO_PORT') == 80
             and secure == False):
        server = _pythonMinioUrl(os.environ.get('GLEANER_MINIO_ADDRESS'))
    elif (os.environ.get('GLEANER_MINIO_PORT') and os.environ.get('GLEANER_MINIO_PORT') == 443
                and secure == True):
        server = _pythonMinioUrl(os.environ.get('GLEANER_MINIO_ADDRESS'))
    else:
        # it's not on a normal port
        server = f"{_pythonMinioUrl(os.environ.get('GLEANER_MINIO_ADDRESS'))}:{os.environ.get('GLEANER_MINIO_PORT')}"

    client = Minio(
        server,
        secure=secure,
        #secure = bool(distutils.util.strtobool(os.environ.get('GLEANER_MINIO_SSL'))),
        access_key=os.environ.get('GLEANER_MINIO_ACCESS_KEY'),
        secret_key=os.environ.get('GLEANER_MINIO_SECRET_KEY'),
    )

    # Make 'X' bucket if not exist.
    # found = client.bucket_exists("X")
    # if not found:
    #     client.make_bucket("X")
    # else:
    #     print("Bucket 'X' already exists")

    now = datetime.now()
    date_string = now.strftime("%Y_%m_%d_%H_%M_%S")

    logname = name + '_{}.log'.format(date_string)
    objPrefix = os.environ.get('GLEANERIO_LOG_PREFIX') + logname
    f = io.BytesIO()
    #length = f.write(bytes(json_str, 'utf-8'))
    length = f.write(data)
    f.seek(0)
    client.put_object(os.environ.get('GLEANER_MINIO_BUCKET'),
                      objPrefix,
                      f, #io.BytesIO(data),
                      length, #len(data),
                      content_type="text/plain"
                         )
    get_dagster_logger().info(f"Log uploaded: {str(objPrefix)}")
def postRelease(source):
    # revision of EC utilities, will have a insertFromURL
    #instance =  mg.ManageBlazegraph(os.environ.get('GLEANER_GRAPH_URL'),os.environ.get('GLEANER_GRAPH_NAMESPACE') )
    proto = "http"

    if os.environ.get('GLEANER_MINIO_USE_SSL'):
        proto = "https"
    port = os.environ.get('GLEANER_MINIO_PORT')
    address = os.environ.get('GLEANER_MINIO_ADDRESS')
    bucket = os.environ.get('GLEANER_MINIO_BUCKET')
    path = "graphs/latest"
    release_url = f"{proto}://{address}:{port}/{bucket}/{path}/{source}_release.nq"
    url = f"{_graphEndpoint()}?uri={release_url}" # f"{os.environ.get('GLEANER_GRAPH_URL')}/namespace/{os.environ.get('GLEANER_GRAPH_NAMESPACE')}/sparql?uri={release_url}"
    get_dagster_logger().info(f'graph: insert "{source}" to {url} ')
    r = requests.post(url)
    log.debug(f' status:{r.status_code}')  # status:404
    get_dagster_logger().info(f'graph: insert: status:{r.status_code}')
    if r.status_code == 200:
        # '<?xml version="1.0"?><data modified="0" milliseconds="7"/>'
        if 'data modified="0"' in r.text:
            get_dagster_logger().info(f'graph: no data inserted ')
            raise Exception("No Data Added: " + r.text)
        return True
    else:
        get_dagster_logger().info(f'graph: error')
        raise Exception(f' graph: insert failed: status:{r.status_code}')


def gleanerio(mode, source):
    ## ------------   Create

    get_dagster_logger().info(f"Create: {str(mode)}")

    if str(mode) == "gleaner":
        IMAGE = os.environ.get('GLEANERIO_GLEANER_IMAGE')
        ARCHIVE_FILE = os.environ.get('GLEANERIO_GLEANER_ARCHIVE_OBJECT')
        ARCHIVE_PATH = os.environ.get('GLEANERIO_GLEANER_ARCHIVE_PATH')
       # CMD = f"gleaner --cfg/gleaner/gleanerconfig.yaml -source {source} --rude"
        CMD = ["--cfg", "/gleaner/gleanerconfig.yaml","-source", source, "--rude"]
        NAME = "gleaner01_" + source
        WorkingDir = "/gleaner/"
        #Entrypoint = ["/gleaner/gleaner", "--cfg", "/gleaner/gleanerconfig.yaml", "-source", source, "--rude"]
        # LOGFILE = 'log_gleaner.txt'  # only used for local log file writing
    elif (str(mode) == "nabu"):
        IMAGE = os.environ.get('GLEANERIO_NABU_IMAGE')
        ARCHIVE_FILE = os.environ.get('GLEANERIO_NABU_ARCHIVE_OBJECT')
        ARCHIVE_PATH = os.environ.get('GLEANERIO_NABU_ARCHIVE_PATH')
        CMD = ["--cfg", "/nabu/nabuconfig.yaml", "prune", "--prefix", "summoned/" + source]
        NAME = f"nabu01_{source}_prune"
        WorkingDir = "/nabu/"
        Entrypoint = "nabu"
        # LOGFILE = 'log_nabu.txt'  # only used for local log file writing
    elif (str(mode) == "prov"):
        IMAGE = os.environ.get('GLEANERIO_NABU_IMAGE')
        ARCHIVE_FILE = os.environ.get('GLEANERIO_NABU_ARCHIVE_OBJECT')
        ARCHIVE_PATH = os.environ.get('GLEANERIO_NABU_ARCHIVE_PATH')
        CMD = ["--cfg", "/nabu/nabuconfig.yaml", "prefix", "--prefix", "prov/" + source]
        NAME = f"nabu01_{source}_prov"
        WorkingDir = "/nabu/"
        Entrypoint = "nabu"
        # LOGFILE = 'log_nabu.txt'  # only used for local log file writing
    elif (str(mode) == "orgs"):
        IMAGE = os.environ.get('GLEANERIO_NABU_IMAGE')
        ARCHIVE_FILE = os.environ.get('GLEANERIO_NABU_ARCHIVE_OBJECT')
        ARCHIVE_PATH = os.environ.get('GLEANERIO_NABU_ARCHIVE_PATH')
        CMD = ["--cfg", "/nabu/nabuconfig.yaml", "prefix", "--prefix", "orgs"]
        NAME = f"nabu01_{source}_orgs"
        WorkingDir = "/nabu/"
        Entrypoint = "nabu"
        # LOGFILE = 'log_nabu.txt'  # only used for local log file writing
    elif (str(mode) == "release"):
        IMAGE = os.environ.get('GLEANERIO_NABU_IMAGE')
        ARCHIVE_FILE = os.environ.get('GLEANERIO_NABU_ARCHIVE_OBJECT')
        ARCHIVE_PATH = os.environ.get('GLEANERIO_NABU_ARCHIVE_PATH')
        CMD = ["--cfg", "/nabu/nabuconfig.yaml", "release", "--prefix", "summoned/" + source]
        NAME = f"nabu01_{source}_release"
        WorkingDir = "/nabu/"
        Entrypoint = "nabu"
        # LOGFILE = 'log_nabu.txt'  # only used for local log file writing
    else:
        return 1
    try:
        # setup data/body for  container create
        data = {}
        data["Image"] = IMAGE
        data["WorkingDir"] = WorkingDir
        #data["Entrypoint"] = Entrypoint
        data["Cmd"] = CMD
#### gleaner
        # v.BindEnv("minio.address", "MINIO_ADDRESS")
        # v.BindEnv("minio.port", "MINIO_PORT")
        # v.BindEnv("minio.ssl", "MINIO_USE_SSL")
        # v.BindEnv("minio.accesskey", "MINIO_ACCESS_KEY")
        # v.BindEnv("minio.secretkey", "MINIO_SECRET_KEY")
        # v.BindEnv("minio.bucket", "MINIO_BUCKET")
        # // v.BindEnv("minio.region", "MINIO_REGION")
        # v.BindEnv("sparql.endpoint", "SPARQL_ENDPOINT")
        # v.BindEnv("sparql.authenticate", "SPARQL_AUTHENTICATE")
        # v.BindEnv("sparql.username", "SPARQL_USERNAME")
        # v.BindEnv("sparql.password", "SPARQL_PASSWORD")
        # v.BindEnv("s3.domain", "S3_DOMAIN")
### gleaner summoner config
        # viperSubtree.BindEnv("headless", "GLEANER_HEADLESS_ENDPOINT")
        # viperSubtree.BindEnv("threads", "GLEANER_THREADS")
        # viperSubtree.BindEnv("mode", "GLEANER_MODE")

        #### NABU config
        # minioSubtress.BindEnv("address", "MINIO_ADDRESS")
        # minioSubtress.BindEnv("port", "MINIO_PORT")
        # minioSubtress.BindEnv("ssl", "MINIO_USE_SSL")
        # minioSubtress.BindEnv("accesskey", "MINIO_ACCESS_KEY")
        # minioSubtress.BindEnv("secretkey", "MINIO_SECRET_KEY")
        # minioSubtress.BindEnv("secretkey", "MINIO_SECRET_KEY")
        # minioSubtress.BindEnv("bucket", "MINIO_BUCKET")
        # viperSubtree.BindEnv("endpoint", "SPARQL_ENDPOINT")
        ###### nabu sparql config
        # viperSubtree.BindEnv("endpointBulk", "SPARQL_ENDPOINTBULK")
        # viperSubtree.BindEnv("endpointMethod", "SPARQL_ENDPOINTMETHOD")
        # viperSubtree.BindEnv("contentType", "SPARQL_CONTENTTYPE")
        # viperSubtree.BindEnv("authenticate", "SPARQL_AUTHENTICATE")
        # viperSubtree.BindEnv("username", "SPARQL_USERNAME")
        # viperSubtree.BindEnv("password", "SPARQL_PASSWORD")
        ### NABU object
        # viperSubtree.BindEnv("bucket", "MINIO_BUCKET")
        # viperSubtree.BindEnv("domain", "S3_DOMAIN")
        # add in env variables here"Env": ["FOO=bar","BAZ=quux"],

        # TODO: Build SPARQL_ENDPOINT from  GLEANER_GRAPH_URL, GLEANER_GRAPH_NAMESPACE
        enva = []
        enva.append(str("MINIO_ADDRESS={}".format(GLEANER_MINIO_ADDRESS)))
        enva.append(str("MINIO_PORT={}".format(GLEANER_MINIO_PORT)))
        enva.append(str("MINIO_USE_SSL={}".format(GLEANER_MINIO_USE_SSL)))
        enva.append(str("MINIO_SECRET_KEY={}".format(GLEANER_MINIO_SECRET_KEY)))
        enva.append(str("MINIO_ACCESS_KEY={}".format(GLEANER_MINIO_ACCESS_KEY)))
        enva.append(str("MINIO_BUCKET={}".format(GLEANER_MINIO_BUCKET)))
        enva.append(str("SPARQL_ENDPOINT={}".format(_graphEndpoint())))
        enva.append(str("GLEANER_HEADLESS_ENDPOINT={}".format(os.environ.get('GLEANER_HEADLESS_ENDPOINT'))))
        enva.append(str("GLEANER_HEADLESS_NETWORK={}".format(os.environ.get('GLEANER_HEADLESS_NETWORK'))))

        data["Env"] = enva
        data["HostConfig"] = {
            "NetworkMode": GLEANER_HEADLESS_NETWORK,
            "Binds":  [f"{GLEANER_CONFIG_VOLUME}:/configs"]
        }
        # data["Volumes"] = [
        #     "dagster-project:/configs"
        # ]
        # we would like this to be "dagster-${PROJECT:-eco}" but that is a bit tricky
        # end setup of data

        url = URL + 'containers/create'
        params = {
            "name": NAME

        }

        query_string = urllib.parse.urlencode(params)
        url = url + "?" + query_string

        get_dagster_logger().info(f"URL: {str(url)}")
        get_dagster_logger().info(f"container config: {str(json.dumps(data))}")
        req = request.Request(url, str.encode(json.dumps(data) ))
        req.add_header('X-API-Key', APIKEY)
        req.add_header('content-type', 'application/json')
        req.add_header('accept', 'application/json')
        try:
            r = request.urlopen(req)
            c = r.read()
            d = json.loads(c)
            cid = d['Id']
            print(r.status)
            get_dagster_logger().info(f"Create: {str(r.status)}")
        except HTTPError or requests.HTTPError as err:
            if (err.code == 409):
                print("failed to create container: container exists; use docker container ls -a : ", err)
                get_dagster_logger().info(f"Create Failed: exsting container:  container exists; use docker container ls -a : {str(err)}")
            elif (err.code == 404):
                print("failed to create container: missing GLEANER_CONTAINER_IMAGE: load into portainer/docker : ", err)
                get_dagster_logger().info(f"Create Failed: bad GLEANER_CONTAINER_IMAGE: load into portainer/docker : reason {str(err)}")
            else:
                print("failed to create container:  unknown reason: ", err)
                get_dagster_logger().info(f"Create Failed: unknown reason {str(err)}")
            raise err
        except Exception as err:
            print("failed to create container:  unknown reason: ", err)
            get_dagster_logger().info(f"Create Failed: unknown reason {str(err)}")
            raise err
        print(f"containerid:{cid}")

        ## ------------  Archive to load, which is how to send in the config (from where?)

        url = URL + 'containers/' + cid + '/archive'
        params = {
            'path': ARCHIVE_PATH
        }
        query_string = urllib.parse.urlencode(params)
        url = url + "?" + query_string

        get_dagster_logger().info(f"Container archive url: {url}")

        # DATA = read_file_bytestream(ARCHIVE_FILE)
        DATA = s3reader(ARCHIVE_FILE)

        req = request.Request(url, data=DATA, method="PUT")
        req.add_header('X-API-Key', APIKEY)
        req.add_header('content-type', 'application/x-compressed')
        req.add_header('accept', 'application/json')
        r = request.urlopen(req)

        print(r.status)
        get_dagster_logger().info(f"Container Archive added: {str(r.status)}")

        # c = r.read()
        # print(c)
        # d = json.loads(c)
        # print(d)

        ## ------------  Start
        ## note new issue:
        # {"message": "starting container with non-empty request body was deprecated since API v1.22 and removed in v1.24"}
        EMPTY_DATA="{}".encode('utf-8')
        url = URL + 'containers/' + cid + '/start'
        get_dagster_logger().info(f"Container start url: {url}")
        req = request.Request(url,data=EMPTY_DATA, method="POST")
        req.add_header('X-API-Key', APIKEY)
        req.add_header('content-type', 'application/json')
        req.add_header('accept', 'application/json')
        try:
            r = request.urlopen(req)
        except HTTPError as err:
            get_dagster_logger().fatal(f"Container Start failed: {str(err.code)} reason: {err.reason}")
            raise err
        except Exception as err:
            print("failed to start container:  unknown reason: ", err)
            get_dagster_logger().info(f"Create Failed: unknown reason {str(err)}")
            raise err
        print(r.status)
        get_dagster_logger().info(f"Start container: {str(r.status)}")

        ## ------------  Wait expect 200

        url = URL + 'containers/' + cid + '/wait'
        req = request.Request(url, data=EMPTY_DATA, method="POST")
        req.add_header('X-API-Key', APIKEY)
        req.add_header('content-type', 'application/json')
        req.add_header('accept', 'application/json')
        r = request.urlopen(req)
        print(r.status)
        get_dagster_logger().info(f"Container Wait: {str(r.status)}")

        ## ------------  Copy logs  expect 200

        url = URL + 'containers/' + cid + '/logs'
        params = {
            'stdout': 'true',
            'stderr': 'false'
        }
        query_string = urllib.parse.urlencode(params)

        url = url + "?" + query_string
        req = request.Request(url, method="GET")
        req.add_header('X-API-Key', APIKEY)
        req.add_header('accept', 'application/json')
        r = request.urlopen(req)
        print(r.status)
        c = r.read().decode('latin-1')

        # write to file
        # f = open(LOGFILE, 'w')
        # f.write(str(c))
        # f.close()

        # write to s3

        s3loader(str(c).encode(), NAME)  # s3loader needs a bytes like object
        #s3loader(str(c).encode('utf-8'), NAME)  # s3loader needs a bytes like object
        # write to minio (would need the minio info here)

        get_dagster_logger().info(f"container Logs to s3: {str(r.status)}")

## get log files

        ## ------------  Remove   expect 204
        url = URL + 'containers/' + cid + '/archive'
        params = {
            'path': f"{WorkingDir}/logs"
        }
        query_string = urllib.parse.urlencode(params)
        url = url + "?" + query_string

        # print(url)
        req = request.Request(url,  method="GET")
        req.add_header('X-API-Key', APIKEY)
        req.add_header('content-type', 'application/x-compressed')
        req.add_header('accept', 'application/json')
        r = request.urlopen(req)

        log.info(f"{r.status} ")
        get_dagster_logger().info(f"Container Archive Retrieved: {str(r.status)}")
       # s3loader(r.read().decode('latin-1'), NAME)
        s3loader(r.read(), f"{source}_runlogs")
    finally:
        if (not DEBUG) :
            if (cid):
                url = URL + 'containers/' + cid
                req = request.Request(url, method="DELETE")
                req.add_header('X-API-Key', APIKEY)
                # req.add_header('content-type', 'application/json')
                req.add_header('accept', 'application/json')
                r = request.urlopen(req)
                print(r.status)
                get_dagster_logger().info(f"Container Remove: {str(r.status)}")
            else:
                get_dagster_logger().info(f"Container Not created, so not removed.")
        else:
            get_dagster_logger().info(f"Container NOT Remove: DEBUG ENABLED")


    return 0

@op
def amgeo_gleaner(context):
    returned_value = gleanerio(("gleaner"), "amgeo")
    r = str('returned value:{}'.format(returned_value))
    get_dagster_logger().info(f"Gleaner notes are  {r} ")
    return r

@op
def amgeo_nabu_prune(context, msg: str):
    returned_value = gleanerio(("nabu"), "amgeo")
    r = str('returned value:{}'.format(returned_value))
    return msg + r

@op
def amgeo_nabuprov(context, msg: str):
    returned_value = gleanerio(("prov"), "amgeo")
    r = str('returned value:{}'.format(returned_value))
    return msg + r

@op
def amgeo_nabuorg(context, msg: str):
    returned_value = gleanerio(("orgs"), "amgeo")
    r = str('returned value:{}'.format(returned_value))
    return msg + r

@op
def amgeo_naburelease(context, msg: str):
    returned_value = gleanerio(("release"), "amgeo")
    r = str('returned value:{}'.format(returned_value))
    return msg + r
@op
def amgeo_uploadrelease(context, msg: str):
    returned_value = postRelease("amgeo")
    r = str('returned value:{}'.format(returned_value))
    return msg + r


@op
def amgeo_missingreport_s3(context, msg: str):
    source = getSitemapSourcesFromGleaner("/scheduler/gleanerconfig.yaml", sourcename="amgeo")
    source_url = source.get('url')
    s3Minio = s3.MinioDatastore(_pythonMinioUrl(GLEANER_MINIO_ADDRESS), None)
    bucket = GLEANER_MINIO_BUCKET
    source_name = "amgeo"
    graphendpoint = None
    milled = False
    summon = True
    returned_value = missingReport(source_url, bucket, source_name, s3Minio, graphendpoint, milled=milled, summon=summon)
    r = str('missing repoort returned value:{}'.format(returned_value))
    report = json.dumps(returned_value, indent=2)
    s3Minio.putReportFile(bucket, source_name, "missing_report_s3.json", report)
    return msg + r
@op
def amgeo_missingreport_graph(context, msg: str):
    source = getSitemapSourcesFromGleaner("/scheduler/gleanerconfig.yaml", sourcename="amgeo")
    source_url = source.get('url')
    s3Minio = s3.MinioDatastore(_pythonMinioUrl(GLEANER_MINIO_ADDRESS), None)
    bucket = GLEANER_MINIO_BUCKET
    source_name = "amgeo"

    graphendpoint = _graphEndpoint()# f"{os.environ.get('GLEANER_GRAPH_URL')}/namespace/{os.environ.get('GLEANER_GRAPH_NAMESPACE')}/sparql"

    milled = True
    summon = False # summon only off
    returned_value = missingReport(source_url, bucket, source_name, s3Minio, graphendpoint, milled=milled, summon=summon)
    r = str('missing report graph returned value:{}'.format(returned_value))
    report = json.dumps(returned_value, indent=2)

    s3Minio.putReportFile(bucket, source_name, "missing_report_graph.json", report)

    return msg + r
@op
def amgeo_graph_reports(context, msg: str):
    source = getSitemapSourcesFromGleaner("/scheduler/gleanerconfig.yaml", sourcename="amgeo")
    #source_url = source.get('url')
    s3Minio = s3.MinioDatastore(_pythonMinioUrl(GLEANER_MINIO_ADDRESS), None)
    bucket = GLEANER_MINIO_BUCKET
    source_name = "amgeo"

    graphendpoint = _graphEndpoint() # f"{os.environ.get('GLEANER_GRAPH_URL')}/namespace/{os.environ.get('GLEANER_GRAPH_NAMESPACE')}/sparql"

    milled = False
    summon = True
    returned_value = generateGraphReportsRepo(source_name,  graphendpoint, reportList=reportTypes["repo_detailed"])
    r = str('returned value:{}'.format(returned_value))
    #report = json.dumps(returned_value, indent=2) # value already json.dumps
    report = returned_value
    s3Minio.putReportFile(bucket, source_name, "graph_stats.json", report)

    return msg + r

#Can we simplify and use just a method. Then import these methods?
# def missingreport_s3(context, msg: str, source="amgeo"):
#
#     source= getSitemapSourcesFromGleaner("/scheduler/gleanerconfig.yaml", sourcename=source)
#     source_url = source.get('url')
#     s3Minio = s3.MinioDatastore(_pythonMinioUrl(GLEANER_MINIO_ADDRESS), None)
#     bucket = GLEANER_MINIO_BUCKET
#     source_name="amgeo"
#
#     graphendpoint = None
#     milled = False
#     summon = True
#     returned_value = missingReport(source_url, bucket, source_name, s3Minio, graphendpoint, milled=milled, summon=summon)
#     r = str('returned value:{}'.format(returned_value))
#     return msg + r
@graph
def harvest_amgeo():
    harvest = amgeo_gleaner()

    report1 =amgeo_missingreport_s3(harvest)
    #report1 = missingreport_s3(harvest, source="amgeo")
    load1 = amgeo_nabu_prune(harvest)
    load2 = amgeo_nabuprov(load1)
    load3 = amgeo_nabuorg(load2)
    load4 = amgeo_naburelease(load3)
    load5 = amgeo_uploadrelease(load4)
    report2=amgeo_missingreport_graph(load5)
    report3=amgeo_graph_reports(report2)

