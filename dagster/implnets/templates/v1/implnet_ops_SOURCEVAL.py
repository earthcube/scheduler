import distutils

from dagster import op, graph, get_dagster_logger
import subprocess
import os, json, io
import urllib
from urllib import request
from urllib.error import HTTPError
from dagster import job, op, get_dagster_logger
from minio import Minio
from minio.error import S3Error
from datetime import datetime

# Vars and Envs

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


def gleanerio(mode, source):
    ## ------------   Create

    get_dagster_logger().info(f"Create: {str(mode)}")

    if str(mode) == "gleaner":
        IMAGE = os.environ.get('GLEANERIO_GLEANER_IMAGE')
        ARCHIVE_FILE = os.environ.get('GLEANERIO_GLEANER_ARCHIVE_OBJECT')
        ARCHIVE_PATH = os.environ.get('GLEANERIO_GLEANER_ARCHIVE_PATH')
        CMD = ["--cfg", "/gleaner/gleanerconfig.yaml", "--source", source, "--rude"]
        NAME = "gleaner01_" + source
        # LOGFILE = 'log_gleaner.txt'  # only used for local log file writing
    elif (str(mode) == "nabu"):
        IMAGE = os.environ.get('GLEANERIO_NABU_IMAGE')
        ARCHIVE_FILE = os.environ.get('GLEANERIO_NABU_ARCHIVE_OBJECT')
        ARCHIVE_PATH = os.environ.get('GLEANERIO_NABU_ARCHIVE_PATH')
        CMD = ["--cfg", "/nabu/nabuconfig.yaml", "prune", "--prefix", "summoned/" + source]
        NAME = "nabu01_" + source
        # LOGFILE = 'log_nabu.txt'  # only used for local log file writing
    elif (str(mode) == "prov"):
        IMAGE = os.environ.get('GLEANERIO_NABU_IMAGE')
        ARCHIVE_FILE = os.environ.get('GLEANERIO_NABU_ARCHIVE_OBJECT')
        ARCHIVE_PATH = os.environ.get('GLEANERIO_NABU_ARCHIVE_PATH')
        CMD = ["--cfg", "/nabu/nabuconfig.yaml", "prefix", "--prefix", "prov/" + source]
        NAME = "nabu01_" + source
        # LOGFILE = 'log_nabu.txt'  # only used for local log file writing
    elif (str(mode) == "orgs"):
        IMAGE = os.environ.get('GLEANERIO_NABU_IMAGE')
        ARCHIVE_FILE = os.environ.get('GLEANERIO_NABU_ARCHIVE_OBJECT')
        ARCHIVE_PATH = os.environ.get('GLEANERIO_NABU_ARCHIVE_PATH')
        CMD = ["--cfg", "/nabu/nabuconfig.yaml", "prefix", "--prefix", "orgs"]
        NAME = "nabu01_" + source
        # LOGFILE = 'log_nabu.txt'  # only used for local log file writing
    elif (str(mode) == "release"):
        IMAGE = os.environ.get('GLEANERIO_NABU_IMAGE')
        ARCHIVE_FILE = os.environ.get('GLEANERIO_NABU_ARCHIVE_OBJECT')
        ARCHIVE_PATH = os.environ.get('GLEANERIO_NABU_ARCHIVE_PATH')
        CMD = ["--cfg", "/nabu/nabuconfig.yaml", "release", "--prefix", "summoned/" + source]
        NAME = "nabu01_" + source
        # LOGFILE = 'log_nabu.txt'  # only used for local log file writing
    else:
        return 1

    data = {}
    data["Image"] = IMAGE
    data["Cmd"] = CMD

    # add in env variables here"Env": ["FOO=bar","BAZ=quux"],
    enva = []
    enva.append(str("MINIO_ADDRESS={}".format(GLEANER_MINIO_ADDRESS)))
    enva.append(str("GLEANER_MINIO_PORT={}".format(GLEANER_MINIO_PORT)))
    enva.append(str("MINIO_USE_SSL={}".format(GLEANER_MINIO_USE_SSL)))
    enva.append(str("MINIO_SECRET_KEY={}".format(GLEANER_MINIO_SECRET_KEY)))
    enva.append(str("MINIO_ACCESS_KEY={}".format(GLEANER_MINIO_ACCESS_KEY)))
    enva.append(str("GLEANER_MINIO_BUCKET={}".format(GLEANER_MINIO_BUCKET)))
    enva.append(str("GLEANER_HEADLESS_ENDPOINT={}".format(GLEANER_HEADLESS_ENDPOINT)))

    data["Env"] = enva

    url = URL + 'containers/create'
    params = {
        "name": NAME
    }
    query_string = urllib.parse.urlencode(params)
    url = url + "?" + query_string

    get_dagster_logger().info(f"URL: {str(url)}")

    req = request.Request(url, str.encode(json.dumps(data)))
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
    except HTTPError as err:
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

    # print(cid)

    ## ------------  Archive to load, which is how to send in the config (from where?)

    url = URL + 'containers/' + cid + '/archive'
    params = {
        'path': ARCHIVE_PATH
    }
    query_string = urllib.parse.urlencode(params)
    url = url + "?" + query_string

    # print(url)

    # DATA = read_file_bytestream(ARCHIVE_FILE)
    DATA = s3reader(ARCHIVE_FILE)

    req = request.Request(url, data=DATA, method="PUT")
    req.add_header('X-API-Key', APIKEY)
    req.add_header('content-type', 'application/x-compressed')
    req.add_header('accept', 'application/json')
    r = request.urlopen(req)

    print(r.status)
    get_dagster_logger().info(f"Archive: {str(r.status)}")

    # c = r.read()
    # print(c)
    # d = json.loads(c)
    # print(d)

    ## ------------  Start

    url = URL + 'containers/' + cid + '/start'
    req = request.Request(url, method="POST")
    req.add_header('X-API-Key', APIKEY)
    req.add_header('content-type', 'application/json')
    req.add_header('accept', 'application/json')
    r = request.urlopen(req)
    print(r.status)
    get_dagster_logger().info(f"Start: {str(r.status)}")

    ## ------------  Wait expect 200

    url = URL + 'containers/' + cid + '/wait'
    req = request.Request(url, method="POST")
    req.add_header('X-API-Key', APIKEY)
    req.add_header('content-type', 'application/json')
    req.add_header('accept', 'application/json')
    r = request.urlopen(req)
    print(r.status)
    get_dagster_logger().info(f"Wait: {str(r.status)}")

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
    c = r.read().decode()

    # write to file
    # f = open(LOGFILE, 'w')
    # f.write(str(c))
    # f.close()

    # write to s3

    s3loader(str(c).encode(), NAME)  # s3loader needs a bytes like object
    #s3loader(str(c).encode('utf-8'), NAME)  # s3loader needs a bytes like object
    # write to minio (would need the minio info here)

    get_dagster_logger().info(f"Logs: {str(r.status)}")

    ## ------------  Remove   expect 204

    url = URL + 'containers/' + cid
    req = request.Request(url, method="DELETE")
    req.add_header('X-API-Key', APIKEY)
    # req.add_header('content-type', 'application/json')
    req.add_header('accept', 'application/json')
    r = request.urlopen(req)
    print(r.status)
    get_dagster_logger().info(f"Remove: {str(r.status)}")

    return 0

@op
def SOURCEVAL_gleaner(context):
    returned_value = gleanerio(("gleaner"), "SOURCEVAL")
    r = str('returned value:{}'.format(returned_value))
    get_dagster_logger().info(f"Gleaner notes are  {r} ")
    return r

@op
def SOURCEVAL_nabu(context, msg: str):
    returned_value = gleanerio(("nabu"), "SOURCEVAL")
    r = str('returned value:{}'.format(returned_value))
    return msg + r

@op
def SOURCEVAL_nabuprov(context, msg: str):
    returned_value = gleanerio(("prov"), "SOURCEVAL")
    r = str('returned value:{}'.format(returned_value))
    return msg + r

@op
def SOURCEVAL_nabuorg(context, msg: str):
    returned_value = gleanerio(("orgs"), "SOURCEVAL")
    r = str('returned value:{}'.format(returned_value))
    return msg + r

@op
def SOURCEVAL_naburelease(context, msg: str):
    returned_value = gleanerio(("release"), "SOURCEVAL")
    r = str('returned value:{}'.format(returned_value))
    return msg + r

@graph
def harvest_SOURCEVAL():
    harvest = SOURCEVAL_gleaner()
    load1 = SOURCEVAL_nabu(harvest)
    load2 = SOURCEVAL_nabuprov(load1)
    load3 = SOURCEVAL_nabuorg(load2)
    load4 = SOURCEVAL_naburelease(load3)
