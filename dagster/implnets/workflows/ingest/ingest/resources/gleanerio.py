import io
import os
from typing import Any, Mapping, Optional, Sequence

#from dagster import Field
from pydantic import Field

import pydash
from dagster import ConfigurableResource, Config, EnvVar, get_dagster_logger



import time
from datetime import datetime
import requests

import docker
from docker.types import RestartPolicy, ServiceMode

from dagster import In, Nothing, OpExecutionContext, StringSource, op

from dagster._core.utils import parse_env_var


from dagster_docker.container_context import DockerContainerContext
from dagster_docker.docker_run_launcher import DockerRunLauncher
from dagster_docker.utils import DOCKER_CONFIG_SCHEMA, validate_docker_image
from docker.types.services import ContainerSpec, TaskTemplate, ConfigReference

from .graph import GraphResource,BlazegraphResource
from .gleanerS3 import gleanerS3Resource

import os
PROJECT=os.environ.get('PROJECT')
# this will probably need to handle the client, and the
class GleanerioResource(ConfigurableResource):

    DEBUG_CONTAINER: bool
    # docker/portainer API
    GLEANERIO_DOCKER_URL: str =  Field(
         description="Docker Endpoint URL.")
    GLEANERIO_PORTAINER_APIKEY: str =  Field(
         description="Portainer API Key.")
    # Dokcerhub container images
    GLEANERIO_GLEANER_IMAGE: str = Field(
        description="GLEANERIO_GLEANER_IMAGE.")
    GLEANERIO_NABU_IMAGE: str = Field(
        description="GLEANERIO_NABU_IMAGE.")

    # docker swarm resources. Presently a network and config names
    GLEANERIO_DOCKER_HEADLESS_NETWORK: str = Field(
        description="GLEANERIO_HEADLESS_NETWORK.")

    GLEANERIO_HEADLESS_ENDPOINT:str = Field(
        description="GLEANERIO_HEADLESS_NETWORK.", default="http://headless:9000/")

# Execution parameter. The logs from LOG_PREFIX will be uploaded to s3 every n seconds.
    GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT: int = Field(
        description="CONTAINER_WAIT_TIMEOUT.", default=600)
    GLEANERIO_LOG_PREFIX: str = Field(
        description="GLEANERIO_DOCKER_LOG_PREFIX.")

    gs3: gleanerS3Resource   # this will be a botocore.client.S3.
    triplestore: GraphResource  # should be a blazegraph... but let's try generic
    GLEANERIO_GRAPH_NAMESPACE:str = Field(
        description="GLEANERIO_GRAPH_NAMESPACE for Project.")
    GLEANERIO_GRAPH_SUMMARY_NAMESPACE:str = Field(
        description="GLEANERIO_GRAPH_SUMMARY_NAMESPACE for Project.")

    # at present, these are hard coded as os.getenv in sensors.gleaner_summon.sources_schedule
    GLEANERIO_SCHEDULE_DEFAULT :str = Field(
        description="GLEANERIO_SCHEDULE_DEFAULT for Project.", default="@weekly")
    GLEANERIO_SCHEDULE_DEFAULT_TIMEZONE :str = Field(
        description="GLEANERIO_SCHEDULE_DEFAULT_TIMEZONE for Project.", default="America/Los_Angeles")

    def _get_client(self, docker_container_context: DockerContainerContext):
        headers = {'X-API-Key': self.GLEANERIO_PORTAINER_APIKEY}
        client = docker.DockerClient(base_url=self.GLEANERIO_DOCKER_URL, version="1.43") # my build needs 1.47, make a .env entry?
        # client = docker.APIClient(base_url=URL, version="1.35")
        get_dagster_logger().info(f"create docker client")
        if (client.api._general_configs):
            client.api._general_configs["HttpHeaders"] = headers
        else:
            client.api._general_configs = {"HttpHeaders": headers}
        client.api.headers['X-API-Key'] =  self.GLEANERIO_PORTAINER_APIKEY
        get_dagster_logger().info(f" docker version {client.version()}")
        if docker_container_context.registry:
            client.login(
                registry=docker_container_context.registry["url"],
                username=docker_container_context.registry["username"],
                password=docker_container_context.registry["password"],
            )
        return client

    def _create_service(self,
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
        get_dagster_logger().info(f"create docker service for {PROJECT} {name}")
        restart_policy = RestartPolicy(condition='none')
        # docker.py if replicated job, total completions = replicas
        # replicas =0 you do not get a container
        serivce_mode = ServiceMode("replicated-job", concurrency=1, replicas=1)
        get_dagster_logger().info(str(client.configs.list()))
        get_dagster_logger().info(f"create docker service for {name}")
        service = client.services.create(
            image,
            args=command,
            env=env_vars,
            name=name,
            networks=container_context.networks if len(container_context.networks) else None,
            restart_policy=restart_policy,
            mode=serivce_mode,
            workdir=workingdir,
        )
        wait_count = 0
        while True:
            time.sleep(1)
            wait_count += 1
            get_dagster_logger().debug(str(service.tasks()))

            container_task = service.tasks(filters={"service": name})

            containers = client.containers.list(all=True, filters={"label": f"com.docker.swarm.service.name={name}"})
            if len(containers) > 0:
                break
            if wait_count > 12:
                raise f"Container  for service {name} not starting"

        get_dagster_logger().info(len(containers))
        return service, containers[0]

    def getImage(self,context):
        run_container_context = DockerContainerContext.create_for_run(
            context.dagster_run,
            context.instance.run_launcher
            if isinstance(context.instance.run_launcher, DockerRunLauncher)
            else None,
        )
        get_dagster_logger().info(f"call docker _get_client: ")
        client = self.get_client(run_container_context)
        client.images.pull(self.GLEANERIO_GLEANER_IMAGE)
        client.images.pull(self.GLEANERIO_NABU_IMAGE)

    def s3loader(self,data, name, date_string=datetime.now().strftime("%Y_%m_%d_%H_%M_%S")):
        logname = name + '_{}.log'.format(date_string)
        objPrefix = self.GLEANERIO_LOG_PREFIX + logname
        f = io.BytesIO()
        length = f.write(data)
        f.seek(0)
        self.gs3.s3.get_client().put_object(Bucket=self.gs3.GLEANERIO_MINIO_BUCKET,
                          Key=objPrefix,
                          Body=f,
                          ContentLength=length,
                          ContentType="text/plain"
                          )
        get_dagster_logger().info(f"Log uploaded: {str(objPrefix)}")

    def execute(self,context, mode, source):
        ## ------------   Create
        returnCode = 0
        get_dagster_logger().info(f"Gleanerio mode: {str(mode)}")
        date_string = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        gleaner_url = self.gs3.s3ConfigGleaner()
        nabu_url = self.gs3.s3ConfigNabu()
        get_dagster_logger().info(f"gleanerurl: {gleaner_url} ")
        get_dagster_logger().info(f"nabu_url: {nabu_url} ")
        if str(mode) == "gleaner":
            IMAGE =self.GLEANERIO_GLEANER_IMAGE
            ARGS = ["--cfgURL", gleaner_url, "-source", source, "--rude"]
            NAME = f"sch_{PROJECT}_{source}_{str(mode)}"
            WorkingDir = "/gleaner/"
        elif (str(mode) == "prune"):
            IMAGE = self.GLEANERIO_NABU_IMAGE
            ARGS = ["--cfgURL", nabu_url, "prune", "--prefix", "summoned/" + source]
            NAME = f"sch_{PROJECT}_{source}_{str(mode)}"
            WorkingDir = "/nabu/"
            Entrypoint = "nabu"
        elif (str(mode) == "prov"):
            IMAGE = self.GLEANERIO_NABU_IMAGE
            ARGS = ["--cfgURL",  nabu_url, "prefix", "--prefix", "prov/" + source]
            NAME = f"sch_{PROJECT}_{source}_{str(mode)}"
            WorkingDir = "/nabu/"
            Entrypoint = "nabu"
        elif (str(mode) == "orgs"):
            IMAGE = self.GLEANERIO_NABU_IMAGE
            ARGS = ["--cfgURL",  nabu_url, "prefix", "--prefix", "orgs"]
            NAME = f"sch_{PROJECT}_{source}_{str(mode)}"
            WorkingDir = "/nabu/"
            Entrypoint = "nabu"
        elif (str(mode) == "release"):
            IMAGE = self.GLEANERIO_NABU_IMAGE
            ARGS = ["--cfgURL",  nabu_url, "release", "--prefix", "summoned/" + source]
            NAME = f"sch_{PROJECT}_{source}_{str(mode)}"
            WorkingDir = "/nabu/"
            Entrypoint = "nabu"
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
            data["Cmd"] = ARGS

            enva = []
            enva.append(str("MINIO_ADDRESS={}".format(self.gs3.GLEANERIO_MINIO_ADDRESS)))
            enva.append(str("MINIO_PORT={}".format(self.gs3.GLEANERIO_MINIO_PORT)))
            enva.append(str("MINIO_USE_SSL={}".format(self.gs3.s3.use_ssl)))
            enva.append(str("MINIO_SECRET_KEY={}".format(self.gs3.s3.aws_secret_access_key)))
            enva.append(str("MINIO_ACCESS_KEY={}".format(self.gs3.s3.aws_access_key_id)))
            enva.append(str("MINIO_BUCKET={}".format(self.gs3.GLEANERIO_MINIO_BUCKET)))

            # Only set SPARQL_ENDPOINT when a triplestore URL is configured.
            # Leave it unset for Qlever deployments: Qlever rebuilds its index
            # from S3 release files on container restart (qlever_index_rebuild
            # asset), so Nabu should skip the SPARQL upload step entirely.
            graph_endpoint = self.triplestore.GraphEndpoint(self.GLEANERIO_GRAPH_NAMESPACE)
            if graph_endpoint and graph_endpoint.startswith("http"):
                enva.append(str("SPARQL_ENDPOINT={}".format(graph_endpoint)))
            else:
                get_dagster_logger().info(
                    "GLEANERIO_GRAPH_URL not set; skipping SPARQL_ENDPOINT for Nabu "
                    "(Qlever deployment — index rebuilt via qlever_index_rebuild asset)"
                )

            enva.append(str("GLEANER_HEADLESS_ENDPOINT={}".format(self.GLEANERIO_HEADLESS_ENDPOINT)))
            enva.append(str("GLEANERIO_DOCKER_HEADLESS_NETWORK={}".format(self.GLEANERIO_DOCKER_HEADLESS_NETWORK)))

            data["Env"] = enva
            data["HostConfig"] = {
                "NetworkMode": self.GLEANERIO_DOCKER_HEADLESS_NETWORK,
            }

            get_dagster_logger().info(f"start docker code region: ")

            op_container_context = DockerContainerContext(
                env_vars=enva,
                networks=[self.GLEANERIO_DOCKER_HEADLESS_NETWORK],
                container_kwargs={"working_dir": data["WorkingDir"],},
            )
            container_context = run_container_context.merge(op_container_context)
            get_dagster_logger().info(f"call docker _get_client: ")
            client = self._get_client(container_context)

            try:
                get_dagster_logger().info(f"try docker _create_service: ")
                service, container = self._create_service(
                    context, client, container_context, IMAGE, "", data["Cmd"], name=NAME,
                    workingdir=data["WorkingDir"]
                )
            except Exception as err:
                raise err

            cid = container.id

            wait_count = 0
            while True:
                wait_count += 1
                try:
                    container.wait(timeout=self.GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT)
                    exit_status = container.wait()["StatusCode"]
                    get_dagster_logger().info(f"Container Wait Exit status:  {exit_status}")
                    returnCode = exit_status
                    c = container.logs(stdout=True, stderr=True, stream=False, follow=False).decode('latin-1')

                    self.s3loader(str(c).encode(), NAME, date_string=date_string)

                    get_dagster_logger().info(f"container Logs to s3: ")
                    path = f"{WorkingDir}/logs"
                    tar_archive_stream, tar_stat = container.get_archive(path)
                    archive = bytearray()
                    for chunk in tar_archive_stream:
                        archive.extend(chunk)
                    self.s3loader(archive, f"{source}_{mode}_runlogs", date_string=date_string)
                    get_dagster_logger().info(f"uploaded logs : {source}_{mode}_runlogs to  {path}")
                    break
                except requests.exceptions.ReadTimeout as ex:
                    path = f"{WorkingDir}/logs"
                    tar_archive_stream, tar_stat = container.get_archive(path)
                    archive = bytearray()
                    for chunk in tar_archive_stream:
                        archive.extend(chunk)
                    self.s3loader(archive, f"{source}_{mode}_runlogs", date_string=date_string)
                    get_dagster_logger().info(f"uploaded {wait_count}th log : {source}_{mode}_runlogs to  {path}")
                except docker.errors.APIError as ex:
                    get_dagster_logger().info(f"Container Wait docker API error :  {str(ex)}")
                    returnCode = 1
                    break
                if container.status == 'exited' or container.status == 'removed':
                    get_dagster_logger().info(f"Container exited or removed. status:  {container.status}")
                    exit_status = container.wait()["StatusCode"]
                    returnCode = exit_status
                    self.s3loader(str(c).encode(), NAME)
                    get_dagster_logger().info(f"container Logs to s3: ")
                    path = f"{WorkingDir}/logs"
                    tar_archive_stream, tar_stat = container.get_archive(path)
                    archive = bytearray()
                    for chunk in tar_archive_stream:
                        archive.extend(chunk)
                    self.s3loader(archive, f"{source}_{mode}_runlogs", date_string=date_string)
                    get_dagster_logger().info(f"uploaded logs : {source}_{mode}_runlogs to  {path}")
                    break

            if exit_status != 0:
                raise Exception(f"Gleaner/Nabu container returned exit code {exit_status}")
        finally:
            if (not self.DEBUG_CONTAINER) :
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
