import distutils
import logging
import time

from dagster import job, op, graph,In, Nothing, get_dagster_logger
import os, json, io
import urllib
from urllib import request
from urllib.error import HTTPError

from docker.types import RestartPolicy, ServiceMode
from ec.gleanerio.gleaner import getGleaner, getSitemapSourcesFromGleaner, endpointUpdateNamespace
import json

from minio import Minio
from minio.error import S3Error
from datetime import datetime
from ec.reporting.report import missingReport, generateGraphReportsRepo, reportTypes, generateIdentifierRepo
from ec.datastore import s3
from ec.summarize import summaryDF2ttl, get_summary4graph, get_summary4repoSubset
from ec.graph.manageGraph import ManageBlazegraph as mg
import requests
import logging as log
from urllib.error import HTTPError

from typing import Any, Mapping, Optional, Sequence

import docker
from dagster import Field, In, Nothing, OpExecutionContext, StringSource, op
from dagster._annotations import experimental
from dagster._core.utils import parse_env_var
from dagster._serdes.utils import hash_str

from dagster_docker.container_context import DockerContainerContext
from dagster_docker.docker_run_launcher import DockerRunLauncher
from dagster_docker.utils import DOCKER_CONFIG_SCHEMA, validate_docker_image
from docker.types.services import ContainerSpec, TaskTemplate, ConfigReference

DEBUG=(os.getenv('DEBUG', 'False').lower()  == 'true')
# #
# path to gleaner config in Dagster-daemon is "/scheduler/gleanerconfig.yaml" (config file mounted)
#  WHEN RUNNING dagster-dev, this needs to be a path to a local file
##
DAGSTER_GLEANER_CONFIG_PATH = os.environ.get('DAGSTER_GLEANER_CONFIG_PATH', "/scheduler/gleanerconfig.yaml")

# Vars and Envs
GLEANER_HEADLESS_NETWORK=os.environ.get('GLEANERIO_HEADLESS_NETWORK', "headless_gleanerio")
# env items
URL = os.environ.get('PORTAINER_URL')
APIKEY = os.environ.get('PORTAINER_KEY')
CONTAINER_WAIT_TIMEOUT= os.environ.get('GLEANERIO_CONTAINER_WAIT_SECONDS', 5)

GLEANER_MINIO_ADDRESS = str(os.environ.get('GLEANERIO_MINIO_ADDRESS'))
GLEANER_MINIO_PORT = str(os.environ.get('GLEANERIO_MINIO_PORT'))
GLEANER_MINIO_USE_SSL = bool(distutils.util.strtobool(os.environ.get('GLEANERIO_MINIO_USE_SSL')))
GLEANER_MINIO_SECRET_KEY = str(os.environ.get('GLEANERIO_MINIO_SECRET_KEY'))
GLEANER_MINIO_ACCESS_KEY = str(os.environ.get('GLEANERIO_MINIO_ACCESS_KEY'))
GLEANER_MINIO_BUCKET =str( os.environ.get('GLEANERIO_MINIO_BUCKET'))

# set for the earhtcube utiltiies
MINIO_OPTIONS={"secure":GLEANER_MINIO_USE_SSL

              ,"access_key": GLEANER_MINIO_ACCESS_KEY
              ,"secret_key": GLEANER_MINIO_SECRET_KEY
               }

GLEANER_HEADLESS_ENDPOINT = str(os.environ.get('GLEANERIO_HEADLESS_ENDPOINT', "http://headless:9222"))
# using GLEANER, even though this is a nabu property... same prefix seems easier
GLEANER_GRAPH_URL = str(os.environ.get('GLEANERIO_GRAPH_URL'))
GLEANER_GRAPH_NAMESPACE = str(os.environ.get('GLEANERIO_GRAPH_NAMESPACE'))
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
GLEANERIO_NABU_DOCKER_CONFIG=str(os.environ.get('GLEANERIO_NABU_DOCKER_CONFIG', 'nabu'))
#GLEANERIO_SUMMARY_GRAPH_ENDPOINT = os.environ.get('GLEANERIO_SUMMARY_GRAPH_ENDPOINT')
GLEANERIO_SUMMARY_GRAPH_NAMESPACE = os.environ.get('GLEANERIO_SUMMARY_GRAPH_NAMESPACE',f"{GLEANER_GRAPH_NAMESPACE}_summary" )

SUMMARY_PATH = 'graphs/summary'
RELEASE_PATH = 'graphs/latest'
def _graphEndpoint():
    url = f"{GLEANER_GRAPH_URL}/namespace/{GLEANER_GRAPH_NAMESPACE}/sparql"
    return url
def _graphSummaryEndpoint():
    url = f"{GLEANER_GRAPH_URL}/namespace/{GLEANERIO_SUMMARY_GRAPH_NAMESPACE}/sparql"
    return url
def _pythonMinioAddress(url, port = None):

    if (url.endswith(".amazonaws.com")):
        PYTHON_MINIO_URL = "s3.amazonaws.com"
    else:
        PYTHON_MINIO_URL = url
    if port is not None:
        PYTHON_MINIO_URL = f"{PYTHON_MINIO_URL}:{port}"
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
    server =  _pythonMinioAddress(GLEANER_MINIO_ADDRESS,GLEANER_MINIO_PORT )
    get_dagster_logger().info(f"S3 URL    : {GLEANER_MINIO_ADDRESS}")
    get_dagster_logger().info(f"S3 PYTHON SERVER : {server}")
    get_dagster_logger().info(f"S3 PORT   : {GLEANER_MINIO_PORT}")
    # get_dagster_logger().info(f"S3 read started : {str(os.environ.get('GLEANER_MINIO_KEY'))}")
    # get_dagster_logger().info(f"S3 read started : {str(os.environ.get('GLEANER_MINIO_SECRET'))}")
    get_dagster_logger().info(f"S3 BUCKET : {GLEANER_MINIO_BUCKET}")
    get_dagster_logger().debug(f"S3 object : {str(object)}")

    client = Minio(
        server,
        # secure=True,
        secure = GLEANER_MINIO_USE_SSL,
        access_key=GLEANER_MINIO_ACCESS_KEY,
        secret_key=GLEANER_MINIO_SECRET_KEY,
    )
    try:
        data = client.get_object(GLEANER_MINIO_BUCKET, object)
        return data
    except S3Error as err:
        get_dagster_logger().info(f"S3 read error : {str(err)}")


def s3loader(data, name, date_string=datetime.now().strftime("%Y_%m_%d_%H_%M_%S")):
    secure= GLEANER_MINIO_USE_SSL

    server = _pythonMinioAddress(GLEANER_MINIO_ADDRESS, GLEANER_MINIO_PORT)

    client = Minio(
        server,
        secure=secure,
        #secure = bool(distutils.util.strtobool(os.environ.get('GLEANER_MINIO_SSL'))),
        access_key=GLEANER_MINIO_ACCESS_KEY,
        secret_key=GLEANER_MINIO_SECRET_KEY,
    )

    # Make 'X' bucket if not exist.
    # found = client.bucket_exists("X")
    # if not found:
    #     client.make_bucket("X")
    # else:
    #     print("Bucket 'X' already exists")

    # now = datetime.now()
    # date_string = now.strftime("%Y_%m_%d_%H_%M_%S")

    logname = name + '_{}.log'.format(date_string)
    objPrefix = GLEANERIO_LOG_PREFIX + logname
    f = io.BytesIO()
    #length = f.write(bytes(json_str, 'utf-8'))
    length = f.write(data)
    f.seek(0)
    client.put_object(GLEANER_MINIO_BUCKET,
                      objPrefix,
                      f, #io.BytesIO(data),
                      length, #len(data),
                      content_type="text/plain"
                         )
    get_dagster_logger().info(f"Log uploaded: {str(objPrefix)}")
def post_to_graph(source, path=RELEASE_PATH, extension="nq", graphendpoint=_graphEndpoint()):
    # revision of EC utilities, will have a insertFromURL
    #instance =  mg.ManageBlazegraph(os.environ.get('GLEANER_GRAPH_URL'),os.environ.get('GLEANER_GRAPH_NAMESPACE') )
    proto = "http"

    if GLEANER_MINIO_USE_SSL:
        proto = "https"
    port = GLEANER_MINIO_PORT
    address = _pythonMinioAddress(GLEANER_MINIO_ADDRESS, GLEANER_MINIO_PORT)
    bucket = GLEANER_MINIO_BUCKET
    release_url = f"{proto}://{address}/{bucket}/{path}/{source}_release.{extension}"
    # BLAZEGRAPH SPECIFIC
    # url = f"{_graphEndpoint()}?uri={release_url}"  # f"{os.environ.get('GLEANER_GRAPH_URL')}/namespace/{os.environ.get('GLEANER_GRAPH_NAMESPACE')}/sparql?uri={release_url}"
    # get_dagster_logger().info(f'graph: insert "{source}" to {url} ')
    # r = requests.post(url)
    # log.debug(f' status:{r.status_code}')  # status:404
    # get_dagster_logger().info(f'graph: insert: status:{r.status_code}')
    # if r.status_code == 200:
    #     # '<?xml version="1.0"?><data modified="0" milliseconds="7"/>'
    #     if 'data modified="0"' in r.text:
    #         get_dagster_logger().info(f'graph: no data inserted ')
    #         raise Exception("No Data Added: " + r.text)
    #     return True
    # else:
    #     get_dagster_logger().info(f'graph: error')
    #     raise Exception(f' graph: insert failed: status:{r.status_code}')

    ### GENERIC LOAD FROM
    url = f"{graphendpoint}" # f"{os.environ.get('GLEANER_GRAPH_URL')}/namespace/{os.environ.get('GLEANER_GRAPH_NAMESPACE')}/sparql?uri={release_url}"
    get_dagster_logger().info(f'graph: insert "{source}" to {url} ')
    loadfrom = {'update': f'LOAD <{release_url}>'}
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    r = requests.post(url, headers=headers, data=loadfrom )
    log.debug(f' status:{r.status_code}')  # status:404
    get_dagster_logger().info(f'graph: LOAD from {release_url}: status:{r.status_code}')
    if r.status_code == 200:
        get_dagster_logger().info(f'graph load response: {str(r.text)} ')
        # '<?xml version="1.0"?><data modified="0" milliseconds="7"/>'
        if 'mutationCount=0' in r.text:
            get_dagster_logger().info(f'graph: no data inserted ')
            #raise Exception("No Data Added: " + r.text)
        return True
    else:
        get_dagster_logger().info(f'graph: error {str(r.text)}')
        raise Exception(f' graph: failed,  LOAD from {release_url}: status:{r.status_code}')

def _get_client(docker_container_context: DockerContainerContext):
    headers = {'X-API-Key': APIKEY}
    client = docker.DockerClient(base_url=URL, version="1.43" )
    #client = docker.APIClient(base_url=URL, version="1.35")
    get_dagster_logger().info(f"create docker client")
    if (client.api._general_configs):
        client.api._general_configs["HttpHeaders"] = headers
    else:
        client.api._general_configs={"HttpHeaders":headers}
    client.api.headers['X-API-Key'] = APIKEY
    get_dagster_logger().info(f" docker version {client.version()}")
    if docker_container_context.registry:
        client.login(
            registry=docker_container_context.registry["url"],
            username=docker_container_context.registry["username"],
            password=docker_container_context.registry["password"],
        )
    return client


def _create_service(
    op_context: OpExecutionContext,
    client,
    container_context: DockerContainerContext,
    image: str,
    entrypoint: Optional[Sequence[str]],
    command: Optional[Sequence[str]],
        name="",
        workingdir="/",

):
    env_vars = dict([parse_env_var(env_var) for env_var in container_context.env_vars])
    get_dagster_logger().info(f"create docker service for {name}")
    ## thoguhts
    # return service, container, since there is one
    restart_policy  = RestartPolicy(condition='none')
    # docker.py if replicated job, total completions = replicas
    # replicas =0 you do not get a container
    serivce_mode = ServiceMode("replicated-job",concurrency=1,replicas=1)
    get_dagster_logger().info(str(client.configs.list()))
  #  gleanerid = client.configs.list(filters={"name":{"gleaner-eco": "true"}})
    gleanerconfig = client.configs.list(filters={"name": [GLEANERIO_GLEANER_DOCKER_CONFIG]})
    get_dagster_logger().info(f"docker config gleaner id {str(gleanerconfig[0].id)}")
    nabuconfig = client.configs.list(filters={"name":[GLEANERIO_NABU_DOCKER_CONFIG]})
    get_dagster_logger().info(f"docker config nabu id {str(nabuconfig[0].id)}")
    get_dagster_logger().info(f"create docker service for {name}")
    gleaner = ConfigReference(gleanerconfig[0].id, GLEANERIO_GLEANER_DOCKER_CONFIG,GLEANERIO_GLEANER_CONFIG_PATH)
    nabu = ConfigReference(nabuconfig[0].id, GLEANERIO_NABU_DOCKER_CONFIG,GLEANERIO_NABU_CONFIG_PATH)
    configs = [gleaner,nabu]
   # name = name if len(name) else _get_container_name(op_context.run_id, op_context.op.name, op_context.retry_number),
    service = client.services.create(
        image,
        args=command,
        env= env_vars,
        name=name ,
        networks= container_context.networks if len(container_context.networks) else None,
        restart_policy = restart_policy,
        mode=serivce_mode,
        workdir=workingdir,
        configs=configs
    )
    wait_count =0
    while True:
        time.sleep(1)
        wait_count+=1
        get_dagster_logger().debug(str(service.tasks()))

        container_task = service.tasks(filters={"service":name})

        containers = client.containers.list(all=True, filters={"label":f"com.docker.swarm.service.name={name}"})
        if len(containers)> 0:
            break
        if wait_count > 12:
            raise f"Container  for service {name} not starting"

    get_dagster_logger().info(len(containers))
    return service, containers[0]




def gleanerio(context, mode, source):
    ## ------------   Create
    returnCode = 0
    get_dagster_logger().info(f"Gleanerio mode: {str(mode)}")
    date_string = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    if str(mode) == "gleaner":
        IMAGE =GLEANERIO_GLEANER_IMAGE

       # ARGS = f"gleaner --cfg/gleaner/gleanerconfig.yaml -source {source} --rude"
        ARGS = ["--cfg", GLEANERIO_GLEANER_CONFIG_PATH,"-source", source, "--rude"]
        NAME = f"sch_{source}_{str(mode)}"
        WorkingDir = "/gleaner/"
        #Entrypoint = ["/gleaner/gleaner", "--cfg", "/gleaner/gleanerconfig.yaml", "-source", source, "--rude"]
        # LOGFILE = 'log_gleaner.txt'  # only used for local log file writing
    elif (str(mode) == "prune"):
        IMAGE = GLEANERIO_NABU_IMAGE

        ARGS = ["--cfg", GLEANERIO_NABU_CONFIG_PATH, "prune", "--prefix", "summoned/" + source]
        NAME = f"sch_{source}_{str(mode)}"
        WorkingDir = "/nabu/"
        Entrypoint = "nabu"
        # LOGFILE = 'log_nabu.txt'  # only used for local log file writing
    elif (str(mode) == "prov"):
        IMAGE = GLEANERIO_NABU_IMAGE

        ARGS = ["--cfg",  GLEANERIO_NABU_CONFIG_PATH, "prefix", "--prefix", "prov/" + source]
        NAME = f"sch_{source}_{str(mode)}"
        WorkingDir = "/nabu/"
        Entrypoint = "nabu"
        # LOGFILE = 'log_nabu.txt'  # only used for local log file writing
    elif (str(mode) == "orgs"):
        IMAGE = GLEANERIO_NABU_IMAGE

        ARGS = ["--cfg",  GLEANERIO_NABU_CONFIG_PATH, "prefix", "--prefix", "orgs"]
        NAME = f"sch_{source}_{str(mode)}"
        WorkingDir = "/nabu/"
        Entrypoint = "nabu"
        # LOGFILE = 'log_nabu.txt'  # only used for local log file writing
    elif (str(mode) == "release"):
        IMAGE = GLEANERIO_NABU_IMAGE

        ARGS = ["--cfg",  GLEANERIO_NABU_CONFIG_PATH, "release", "--prefix", "summoned/" + source]
        NAME = f"sch_{source}_{str(mode)}"
        WorkingDir = "/nabu/"
        Entrypoint = "nabu"
        # LOGFILE = 'log_nabu.txt'  # only used for local log file writing
    else:

        returnCode = 1
        return returnCode

    # from docker0dagster
    run_container_context = DockerContainerContext.create_for_run(
        context.dagster_run,
        context.instance.run_launcher
        if isinstance(context.instance.run_launcher, DockerRunLauncher)
        else None,
    )
    validate_docker_image(IMAGE)

    try:
        # setup data/body for  container create
        data = {}
        data["Image"] = IMAGE
        data["WorkingDir"] = WorkingDir
        #data["Entrypoint"] = Entrypoint
        data["Cmd"] = ARGS
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
        enva.append(str("MINIO_ADDRESS={}".format(GLEANER_MINIO_ADDRESS))) # the python needs to be wrapped, this does not
        enva.append(str("MINIO_PORT={}".format(GLEANER_MINIO_PORT)))
        enva.append(str("MINIO_USE_SSL={}".format(GLEANER_MINIO_USE_SSL)))
        enva.append(str("MINIO_SECRET_KEY={}".format(GLEANER_MINIO_SECRET_KEY)))
        enva.append(str("MINIO_ACCESS_KEY={}".format(GLEANER_MINIO_ACCESS_KEY)))
        enva.append(str("MINIO_BUCKET={}".format(GLEANER_MINIO_BUCKET)))
        enva.append(str("SPARQL_ENDPOINT={}".format(_graphEndpoint())))
        enva.append(str("GLEANER_HEADLESS_ENDPOINT={}".format(GLEANER_HEADLESS_ENDPOINT)))
        enva.append(str("GLEANER_HEADLESS_NETWORK={}".format(GLEANER_HEADLESS_NETWORK)))

        data["Env"] = enva
        data["HostConfig"] = {
            "NetworkMode": GLEANER_HEADLESS_NETWORK,
        }


# docker dagster
        get_dagster_logger().info(f"start docker code region: ")


        # trying to get headers in:
        # https://github.com/docker/docker-py/blob/84414e343e526cf93f285284dd2c2c40f703e4a9/docker/utils/decorators.py#L45
        op_container_context = DockerContainerContext(
            # registry=registry,
            env_vars=enva,
            networks=[GLEANER_HEADLESS_NETWORK],
            container_kwargs={"working_dir": data["WorkingDir"],
                              # "volumes": {
                              #                             f"{GLEANER_CONFIG_VOLUME}":
                              #                                 {'bind': '/configs', 'mode': 'rw'}
                              #                             },


            },
        )
        container_context = run_container_context.merge(op_container_context)
        get_dagster_logger().info(f"call docker _get_client: ")
        client = _get_client(container_context)

        try:
            get_dagster_logger().info(f"try docker _create_service: ")
            service, container = _create_service(
                context, client, container_context, IMAGE, "", data["Cmd"], name=NAME,
                workingdir=data["WorkingDir"]
            )
        except Exception as err:
            raise err


        cid = container.id # legacy til the start get's fixed


# Removed watching the logs, in favor of periodic upload
        wait_count = 0
        while True:
            wait_count += 1
            try:
                container.wait(timeout=CONTAINER_WAIT_TIMEOUT)
                exit_status = container.wait()["StatusCode"]
                get_dagster_logger().info(f"Container Wait Exit status:  {exit_status}")
                # WE PULL THE LOGS, then will throw an error
                returnCode = exit_status
                c = container.logs(stdout=True, stderr=True, stream=False, follow=False).decode('latin-1')

                # write to s3

                s3loader(str(c).encode(), NAME, date_string=date_string)  # s3loader needs a bytes like object
                # s3loader(str(c).encode('utf-8'), NAME)  # s3loader needs a bytes like object
                # write to minio (would need the minio info here)

                get_dagster_logger().info(f"container Logs to s3: ")
# this needs to be address at some point. https://www.appsloveworld.com/docker/100/85/docker-py-getarchive-destination-folder
                path = f"{WorkingDir}/logs"
                tar_archive_stream, tar_stat = container.get_archive(path)
                archive = bytearray()
                for chunk in tar_archive_stream:
                    archive.extend(chunk)
                s3loader(archive, f"{source}_{mode}_runlogs", date_string=date_string)
                get_dagster_logger().info(f"uploaded logs : {source}_{mode}_runlogs to  {path}")
                break
            except requests.exceptions.ReadTimeout as ex:
                path = f"{WorkingDir}/logs"
                tar_archive_stream, tar_stat = container.get_archive(path)
                archive = bytearray()
                for chunk in tar_archive_stream:
                    archive.extend(chunk)
                s3loader(archive, f"{source}_{mode}_runlogs", date_string=date_string)
                get_dagster_logger().info(f"uploaded {wait_count}th log : {source}_{mode}_runlogs to  {path}")
            except docker.errors.APIError as ex:
                get_dagster_logger().info(f"Container Wait docker API error :  {str(ex)}")
                returnCode = 1
                break
            if container.status == 'exited' or container.status == 'removed':
                get_dagster_logger().info(f"Container exited or removed. status:  {container.status}")
                exit_status = container.wait()["StatusCode"]
                returnCode = exit_status
                s3loader(str(c).encode(), NAME)  # s3loader needs a bytes like object
                # s3loader(str(c).encode('utf-8'), NAME)  # s3loader needs a bytes like object
                # write to minio (would need the minio info here)

                get_dagster_logger().info(f"container Logs to s3: ")
                # this needs to be address at some point. https://www.appsloveworld.com/docker/100/85/docker-py-getarchive-destination-folder
                path = f"{WorkingDir}/logs"
                tar_archive_stream, tar_stat = container.get_archive(path)
                archive = bytearray()
                for chunk in tar_archive_stream:
                    archive.extend(chunk)
                s3loader(archive, f"{source}_{mode}_runlogs", date_string=date_string)
                get_dagster_logger().info(f"uploaded logs : {source}_{mode}_runlogs to  {path}")
                break

    # ABOVE Future, need to extraxct files, and upload
    # pw_tar = tarfile.TarFile(fileobj=StringIO(d.decode('utf-8')))
    #    pw_tar.extractall("extract_to/")


        if exit_status != 0:
            raise Exception(f"Gleaner/Nabu container returned exit code {exit_status}")
    finally:
        if (not DEBUG) :
            if (service):
                service.remove()
                get_dagster_logger().info(f"Service Remove: {service.name}")
            else:
                get_dagster_logger().info(f"Service Not created, so not removed.")

        else:
            get_dagster_logger().info(f"Service {service.name} NOT Removed : DEBUG ENABLED")


    if (returnCode != 0):
        get_dagster_logger().info(f"Gleaner/Nabu container non-zero exit code. See logs in S3")
        raise Exception("Gleaner/Nabu container non-zero exit code. See logs in S3")
    return returnCode

@op
def SOURCEVAL_getImage(context):
    run_container_context = DockerContainerContext.create_for_run(
        context.dagster_run,
        context.instance.run_launcher
        if isinstance(context.instance.run_launcher, DockerRunLauncher)
        else None,
    )
    get_dagster_logger().info(f"call docker _get_client: ")
    client = _get_client(run_container_context)
    client.images.pull(GLEANERIO_GLEANER_IMAGE)
    client.images.pull(GLEANERIO_NABU_IMAGE)
@op(ins={"start": In(Nothing)})
def SOURCEVAL_gleaner(context):
    returned_value = gleanerio(context, ("gleaner"), "SOURCEVAL")
    r = str('returned value:{}'.format(returned_value))
    get_dagster_logger().info(f"Gleaner returned  {r} ")
    return

@op(ins={"start": In(Nothing)})
def SOURCEVAL_nabu_prune(context):
    returned_value = gleanerio(context,("prune"), "SOURCEVAL")
    r = str('returned value:{}'.format(returned_value))
    get_dagster_logger().info(f"nabu prune returned  {r} ")
    return

@op(ins={"start": In(Nothing)})
def SOURCEVAL_nabuprov(context):
    returned_value = gleanerio(context,("prov"), "SOURCEVAL")
    r = str('returned value:{}'.format(returned_value))
    get_dagster_logger().info(f"nabu prov returned  {r} ")
    return

@op(ins={"start": In(Nothing)})
def SOURCEVAL_nabuorg(context):
    returned_value = gleanerio(context,("orgs"), "SOURCEVAL")
    r = str('returned value:{}'.format(returned_value))
    get_dagster_logger().info(f"nabu org load returned  {r} ")
    return

@op(ins={"start": In(Nothing)})
def SOURCEVAL_naburelease(context):
    returned_value = gleanerio(context,("release"), "SOURCEVAL")
    r = str('returned value:{}'.format(returned_value))
    get_dagster_logger().info(f"nabu release returned  {r} ")
    return
@op(ins={"start": In(Nothing)})
def SOURCEVAL_uploadrelease(context):
    returned_value = post_to_graph("SOURCEVAL", extension="nq")
    r = str('returned value:{}'.format(returned_value))
    get_dagster_logger().info(f"upload release returned  {r} ")
    return


@op(ins={"start": In(Nothing)})
def SOURCEVAL_missingreport_s3(context):
    source = getSitemapSourcesFromGleaner(DAGSTER_GLEANER_CONFIG_PATH, sourcename="SOURCEVAL")
    source_url = source.get('url')
    s3Minio = s3.MinioDatastore(_pythonMinioAddress(GLEANER_MINIO_ADDRESS, GLEANER_MINIO_PORT), MINIO_OPTIONS)
    bucket = GLEANER_MINIO_BUCKET
    source_name = "SOURCEVAL"
    graphendpoint = None
    milled = False
    summon = True
    returned_value = missingReport(source_url, bucket, source_name, s3Minio, graphendpoint, milled=milled, summon=summon)
    r = str('missing repoort returned value:{}'.format(returned_value))
    report = json.dumps(returned_value, indent=2)
    s3Minio.putReportFile(bucket, source_name, "missing_report_s3.json", report)
    get_dagster_logger().info(f"missing s3 report  returned  {r} ")
    return
@op(ins={"start": In(Nothing)})
def SOURCEVAL_missingreport_graph(context):
    source = getSitemapSourcesFromGleaner(DAGSTER_GLEANER_CONFIG_PATH, sourcename="SOURCEVAL")
    source_url = source.get('url')
    s3Minio = s3.MinioDatastore(_pythonMinioAddress(GLEANER_MINIO_ADDRESS, GLEANER_MINIO_PORT), MINIO_OPTIONS)
    bucket = GLEANER_MINIO_BUCKET
    source_name = "SOURCEVAL"

    graphendpoint = _graphEndpoint()# f"{os.environ.get('GLEANER_GRAPH_URL')}/namespace/{os.environ.get('GLEANER_GRAPH_NAMESPACE')}/sparql"

    milled = True
    summon = False # summon only off
    returned_value = missingReport(source_url, bucket, source_name, s3Minio, graphendpoint, milled=milled, summon=summon)
    r = str('missing report graph returned value:{}'.format(returned_value))
    report = json.dumps(returned_value, indent=2)

    s3Minio.putReportFile(bucket, source_name, "missing_report_graph.json", report)
    get_dagster_logger().info(f"missing graph  report  returned  {r} ")
    return
@op(ins={"start": In(Nothing)})
def SOURCEVAL_graph_reports(context) :
    source = getSitemapSourcesFromGleaner(DAGSTER_GLEANER_CONFIG_PATH, sourcename="SOURCEVAL")
    #source_url = source.get('url')
    s3Minio = s3.MinioDatastore(_pythonMinioAddress(GLEANER_MINIO_ADDRESS, GLEANER_MINIO_PORT), MINIO_OPTIONS)
    bucket = GLEANER_MINIO_BUCKET
    source_name = "SOURCEVAL"

    graphendpoint = _graphEndpoint() # f"{os.environ.get('GLEANER_GRAPH_URL')}/namespace/{os.environ.get('GLEANER_GRAPH_NAMESPACE')}/sparql"

    milled = False
    summon = True
    returned_value = generateGraphReportsRepo(source_name,  graphendpoint, reportList=reportTypes["repo_detailed"])
    r = str('returned value:{}'.format(returned_value))
    #report = json.dumps(returned_value, indent=2) # value already json.dumps
    report = returned_value
    s3Minio.putReportFile(bucket, source_name, "graph_stats.json", report)
    get_dagster_logger().info(f"graph report  returned  {r} ")
    return

@op(ins={"start": In(Nothing)})
def SOURCEVAL_identifier_stats(context):
    source = getSitemapSourcesFromGleaner(DAGSTER_GLEANER_CONFIG_PATH, sourcename="SOURCEVAL")
    s3Minio = s3.MinioDatastore(_pythonMinioAddress(GLEANER_MINIO_ADDRESS, GLEANER_MINIO_PORT), MINIO_OPTIONS)
    bucket = GLEANER_MINIO_BUCKET
    source_name = "SOURCEVAL"

    returned_value = generateIdentifierRepo(source_name, bucket, s3Minio)
    r = str('returned value:{}'.format(returned_value))
    #r = str('identifier stats returned value:{}'.format(returned_value))
    report = returned_value.to_json()
    s3Minio.putReportFile(bucket, source_name, "identifier_stats.json", report)
    get_dagster_logger().info(f"identifer stats report  returned  {r} ")
    return

@op(ins={"start": In(Nothing)})
def SOURCEVAL_bucket_urls(context):
    s3Minio = s3.MinioDatastore(_pythonMinioAddress(GLEANER_MINIO_ADDRESS, GLEANER_MINIO_PORT), MINIO_OPTIONS)
    bucket = GLEANER_MINIO_BUCKET
    source_name = "SOURCEVAL"

    res = s3Minio.listSummonedUrls(bucket, source_name)
    r = str('returned value:{}'.format(res))
    bucketurls = json.dumps(res, indent=2)
    s3Minio.putReportFile(GLEANER_MINIO_BUCKET, source_name, "bucketutil_urls.json", bucketurls)
    get_dagster_logger().info(f"bucker urls report  returned  {r} ")
    return

class S3ObjectInfo:
    bucket_name=""
    object_name=""

@op(ins={"start": In(Nothing)})
def SOURCEVAL_summarize(context) :
    s3Minio = s3.MinioDatastore(_pythonMinioAddress(GLEANER_MINIO_ADDRESS, GLEANER_MINIO_PORT), MINIO_OPTIONS)
    bucket = GLEANER_MINIO_BUCKET
    source_name = "SOURCEVAL"
    endpoint = _graphEndpoint() # getting data, not uploading data
    summary_namespace = _graphSummaryEndpoint()


    try:

        summarydf = get_summary4repoSubset(endpoint, source_name)
        nt, g = summaryDF2ttl(summarydf, source_name)  # let's try the new generator
        summaryttl = g.serialize(format='longturtle')
        # Lets always write out file to s3, and insert as a separate process
        # we might be able to make this an asset..., but would need to be acessible by http
        # if not stored in s3
        objectname = f"{SUMMARY_PATH}/{source_name}_release.ttl" # needs to match that is expected by post
        s3ObjectInfo= S3ObjectInfo()
        s3ObjectInfo.bucket_name=bucket
        s3ObjectInfo.object_name=objectname

        s3Minio.putTextFileToStore(summaryttl, s3ObjectInfo )
        #inserted = sumnsgraph.insert(bytes(summaryttl, 'utf-8'), content_type="application/x-turtle")
        #if not inserted:
        #    raise Exception("Loading to graph failed.")
    except Exception as e:
        # use dagster logger
        get_dagster_logger().error(f"Summary. Issue creating graph  {str(e)} ")
        raise Exception(f"Loading Summary graph failed. {str(e)}")
        return 1

    return

@op(ins={"start": In(Nothing)})
def SOURCEVAL_upload_summarize(context):
    returned_value = post_to_graph("SOURCEVAL",path=SUMMARY_PATH, extension="ttl", graphendpoint=_graphSummaryEndpoint())
    r = str('returned value:{}'.format(returned_value))
    get_dagster_logger().info(f"upload summary returned  {r} ")
    return

#Can we simplify and use just a method. Then import these methods?
# def missingreport_s3(context, msg: str, source="SOURCEVAL"):
#
#     source= getSitemapSourcesFromGleaner("/scheduler/gleanerconfig.yaml", sourcename=source)
#     source_url = source.get('url')
#     s3Minio = s3.MinioDatastore(_pythonMinioUrl(GLEANER_MINIO_ADDRESS, GLEANER_MINIO_PORT), MINIO_OPTIONS)
#     bucket = GLEANER_MINIO_BUCKET
#     source_name="SOURCEVAL"
#
#     graphendpoint = None
#     milled = False
#     summon = True
#     returned_value = missingReport(source_url, bucket, source_name, s3Minio, graphendpoint, milled=milled, summon=summon)
#     r = str('returned value:{}'.format(returned_value))
#     return msg + r
@graph
def harvest_SOURCEVAL():
    containers = SOURCEVAL_getImage()
    harvest = SOURCEVAL_gleaner(start=containers)

# defingin nothing dependencies
    # https://docs.dagster.io/concepts/ops-jobs-graphs/graphs#defining-nothing-dependencies

    report_ms3 = SOURCEVAL_missingreport_s3(start=harvest)
    report_idstat = SOURCEVAL_identifier_stats(start=report_ms3)
    # for some reason, this causes a msg parameter missing
    report_bucketurl = SOURCEVAL_bucket_urls(start=report_idstat)

    #report1 = missingreport_s3(harvest, source="SOURCEVAL")
    load_release = SOURCEVAL_naburelease(start=harvest)
    load_uploadrelease = SOURCEVAL_uploadrelease(start=load_release)

    load_prune = SOURCEVAL_nabu_prune(start=load_uploadrelease)
    load_prov = SOURCEVAL_nabuprov(start=load_prune)
    load_org = SOURCEVAL_nabuorg(start=load_prov)

    summarize = SOURCEVAL_summarize(start=load_uploadrelease)
    upload_summarize = SOURCEVAL_upload_summarize(start=summarize)

# run after load
    report_msgraph = SOURCEVAL_missingreport_graph(start=summarize)
    report_graph = SOURCEVAL_graph_reports(start=report_msgraph)







