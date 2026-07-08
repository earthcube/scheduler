# Gleaner harvest resource for the phased pipeline.
# Trimmed from ingest/resources/gleanerio.py: only the "gleaner" (harvest) mode
# remains. RDF conversion/release is done in-process by phase 3
# (assets/phase3_release.py), so the Nabu modes and triplestore wiring are gone.
import io
import time
from datetime import datetime
from typing import Optional, Sequence

import docker
import requests
from dagster import ConfigurableResource, OpExecutionContext, get_dagster_logger
from dagster._core.utils import parse_env_var
from dagster_docker.container_context import DockerContainerContext
from dagster_docker.docker_run_launcher import DockerRunLauncher
from dagster_docker.utils import validate_docker_image
from docker.types import RestartPolicy, ServiceMode
from pydantic import Field

from .gleanerS3 import gleanerS3Resource

import os
PROJECT = os.environ.get('PROJECT')


class GleanerioResource(ConfigurableResource):
    DEBUG_CONTAINER: bool
    GLEANERIO_DOCKER_URL: str = Field(description="Docker Endpoint URL.")
    GLEANERIO_PORTAINER_APIKEY: str = Field(
        description="Portainer API Key (ignored by a direct docker socket).", default="not-used")
    GLEANERIO_GLEANER_IMAGE: str = Field(description="Gleaner container image.")
    GLEANERIO_DOCKER_HEADLESS_NETWORK: str = Field(
        description="Attachable overlay network with internet access for crawls.")
    GLEANERIO_HEADLESS_ENDPOINT: str = Field(
        description="Headless chromium endpoint for JS-rendered sources.",
        default="http://headless:9222")
    GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT: int = Field(
        description="Seconds to wait on the harvest container between log flushes.", default=600)
    GLEANERIO_LOG_PREFIX: str = Field(description="S3 prefix for container logs.")

    gs3: gleanerS3Resource

    def _get_client(self, docker_container_context: DockerContainerContext):
        headers = {'X-API-Key': self.GLEANERIO_PORTAINER_APIKEY}
        client = docker.DockerClient(base_url=self.GLEANERIO_DOCKER_URL, version="1.43")
        get_dagster_logger().info("create docker client")
        if client.api._general_configs:
            client.api._general_configs["HttpHeaders"] = headers
        else:
            client.api._general_configs = {"HttpHeaders": headers}
        client.api.headers['X-API-Key'] = self.GLEANERIO_PORTAINER_APIKEY
        if docker_container_context.registry:
            client.login(
                registry=docker_container_context.registry["url"],
                username=docker_container_context.registry["username"],
                password=docker_container_context.registry["password"],
            )
        return client

    def _create_service(
            self,
            op_context: OpExecutionContext,
            client,
            container_context: DockerContainerContext,
            image: str,
            command: Optional[Sequence[str]],
            name="",
            workingdir="/",
    ):
        env_vars = dict([parse_env_var(env_var) for env_var in container_context.env_vars])
        get_dagster_logger().info(f"create docker service for {PROJECT} {name}")
        restart_policy = RestartPolicy(condition='none')
        service_mode = ServiceMode("replicated-job", concurrency=1, replicas=1)
        service = client.services.create(
            image,
            args=command,
            env=env_vars,
            name=name,
            networks=container_context.networks if len(container_context.networks) else None,
            restart_policy=restart_policy,
            mode=service_mode,
            workdir=workingdir,
        )
        wait_count = 0
        while True:
            time.sleep(1)
            wait_count += 1
            containers = client.containers.list(
                all=True, filters={"label": f"com.docker.swarm.service.name={name}"})
            if len(containers) > 0:
                break
            if wait_count > 12:
                raise Exception(f"Container for service {name} not starting")
        return service, containers[0]

    def s3loader(self, data, name, date_string=None):
        if date_string is None:
            date_string = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        logname = name + '_{}.log'.format(date_string)
        objPrefix = self.GLEANERIO_LOG_PREFIX + logname
        f = io.BytesIO()
        length = f.write(data)
        f.seek(0)
        self.gs3.s3.get_client().put_object(
            Bucket=self.gs3.GLEANERIO_MINIO_BUCKET,
            Key=objPrefix,
            Body=f,
            ContentLength=length,
            ContentType="text/plain",
        )
        get_dagster_logger().info(f"Log uploaded: {str(objPrefix)}")

    def harvest(self, context, source):
        """Run a Gleaner harvest for one source. Writes summoned/{source}/ and
        prov/{source}/ to S3. Raises on non-zero container exit."""
        returnCode = 0
        date_string = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        gleaner_url = self.gs3.s3ConfigGleaner()
        get_dagster_logger().info(f"gleanerurl: {gleaner_url}")

        IMAGE = self.GLEANERIO_GLEANER_IMAGE
        ARGS = ["--cfgURL", gleaner_url, "-source", source, "--rude"]
        NAME = f"sch_{PROJECT}_{source}_gleaner"
        WorkingDir = "/gleaner/"

        run_container_context = DockerContainerContext.create_for_run(
            context.dagster_run,
            context.instance.run_launcher
            if isinstance(context.instance.run_launcher, DockerRunLauncher)
            else None,
        )
        validate_docker_image(IMAGE)

        service = None
        try:
            enva = []
            enva.append(f"MINIO_ADDRESS={self.gs3.GLEANERIO_MINIO_ADDRESS}")
            enva.append(f"MINIO_PORT={self.gs3.GLEANERIO_MINIO_PORT}")
            enva.append(f"MINIO_USE_SSL={self.gs3.s3.use_ssl}")
            enva.append(f"MINIO_SECRET_KEY={self.gs3.s3.aws_secret_access_key}")
            enva.append(f"MINIO_ACCESS_KEY={self.gs3.s3.aws_access_key_id}")
            enva.append(f"MINIO_BUCKET={self.gs3.GLEANERIO_MINIO_BUCKET}")
            enva.append(f"GLEANER_HEADLESS_ENDPOINT={self.GLEANERIO_HEADLESS_ENDPOINT}")
            enva.append(f"GLEANERIO_DOCKER_HEADLESS_NETWORK={self.GLEANERIO_DOCKER_HEADLESS_NETWORK}")

            op_container_context = DockerContainerContext(
                env_vars=enva,
                networks=[self.GLEANERIO_DOCKER_HEADLESS_NETWORK],
                container_kwargs={"working_dir": WorkingDir},
            )
            container_context = run_container_context.merge(op_container_context)
            client = self._get_client(container_context)

            service, container = self._create_service(
                context, client, container_context, IMAGE, ARGS, name=NAME,
                workingdir=WorkingDir,
            )

            exit_status = None
            while True:
                try:
                    container.wait(timeout=self.GLEANERIO_DOCKER_CONTAINER_WAIT_TIMEOUT)
                    exit_status = container.wait()["StatusCode"]
                    get_dagster_logger().info(f"Container Wait Exit status: {exit_status}")
                    returnCode = exit_status
                    c = container.logs(stdout=True, stderr=True, stream=False,
                                       follow=False).decode('latin-1')
                    self.s3loader(str(c).encode(), NAME, date_string=date_string)
                    path = f"{WorkingDir}/logs"
                    tar_archive_stream, tar_stat = container.get_archive(path)
                    archive = bytearray()
                    for chunk in tar_archive_stream:
                        archive.extend(chunk)
                    self.s3loader(archive, f"{source}_gleaner_runlogs", date_string=date_string)
                    break
                except requests.exceptions.ReadTimeout:
                    # periodic log flush while the crawl is still running
                    path = f"{WorkingDir}/logs"
                    tar_archive_stream, tar_stat = container.get_archive(path)
                    archive = bytearray()
                    for chunk in tar_archive_stream:
                        archive.extend(chunk)
                    self.s3loader(archive, f"{source}_gleaner_runlogs", date_string=date_string)
                except docker.errors.APIError as ex:
                    get_dagster_logger().info(f"Container Wait docker API error: {str(ex)}")
                    returnCode = 1
                    break

            if exit_status != 0:
                raise Exception(f"Gleaner container returned exit code {exit_status}")
        finally:
            if not self.DEBUG_CONTAINER:
                if service:
                    service.remove()
                    get_dagster_logger().info(f"Service Remove: {service.name}")
            else:
                get_dagster_logger().info("Service NOT Removed: DEBUG ENABLED")

        if returnCode != 0:
            raise Exception("Gleaner container non-zero exit code. See logs in S3")
        return returnCode
