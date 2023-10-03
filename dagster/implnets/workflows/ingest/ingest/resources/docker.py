import os
from typing import Any, Dict

import pydash
from dagster import ConfigurableResource, Config, EnvVar
from pyairtable import Api, Table
from pydantic import Field

#Let's try to use dasgeter aws as the minio configuration

#
# # Vars and Envs
# GLEANER_HEADLESS_NETWORK=os.environ.get('GLEANERIO_HEADLESS_NETWORK', "headless_gleanerio")
# # env items
# URL = os.environ.get('PORTAINER_URL')
# APIKEY = os.environ.get('PORTAINER_KEY')
# CONTAINER_WAIT_TIMEOUT= os.environ.get('GLEANERIO_CONTAINER_WAIT_SECONDS', 5)
#
# Let's try to use dasgeter aws as the minio configuration
# GLEANER_MINIO_ADDRESS = str(os.environ.get('GLEANERIO_MINIO_ADDRESS'))
# GLEANER_MINIO_PORT = str(os.environ.get('GLEANERIO_MINIO_PORT'))
# GLEANER_MINIO_USE_SSL = bool(distutils.util.strtobool(os.environ.get('GLEANERIO_MINIO_USE_SSL')))
# GLEANER_MINIO_SECRET_KEY = str(os.environ.get('GLEANERIO_MINIO_SECRET_KEY'))
# GLEANER_MINIO_ACCESS_KEY = str(os.environ.get('GLEANERIO_MINIO_ACCESS_KEY'))
# GLEANER_MINIO_BUCKET =str( os.environ.get('GLEANERIO_MINIO_BUCKET'))
#
# # set for the earhtcube utiltiies
# MINIO_OPTIONS={"secure":GLEANER_MINIO_USE_SSL
#
#               ,"access_key": GLEANER_MINIO_ACCESS_KEY
#               ,"secret_key": GLEANER_MINIO_SECRET_KEY
#                }
#
# GLEANER_HEADLESS_ENDPOINT = str(os.environ.get('GLEANERIO_HEADLESS_ENDPOINT', "http://headless:9222"))
# # using GLEANER, even though this is a nabu property... same prefix seems easier
# GLEANER_GRAPH_URL = str(os.environ.get('GLEANERIO_GRAPH_URL'))
# GLEANER_GRAPH_NAMESPACE = str(os.environ.get('GLEANERIO_GRAPH_NAMESPACE'))
# GLEANERIO_GLEANER_CONFIG_PATH= str(os.environ.get('GLEANERIO_GLEANER_CONFIG_PATH', "/gleaner/gleanerconfig.yaml"))
# GLEANERIO_NABU_CONFIG_PATH= str(os.environ.get('GLEANERIO_NABU_CONFIG_PATH', "/nabu/nabuconfig.yaml"))
# GLEANERIO_GLEANER_IMAGE =str( os.environ.get('GLEANERIO_GLEANER_IMAGE', 'nsfearthcube/gleaner:latest'))
# GLEANERIO_NABU_IMAGE = str(os.environ.get('GLEANERIO_NABU_IMAGE', 'nsfearthcube/nabu:latest'))
# GLEANERIO_LOG_PREFIX = str(os.environ.get('GLEANERIO_LOG_PREFIX', 'scheduler/logs/')) # path to logs in nabu/gleaner
# GLEANERIO_GLEANER_ARCHIVE_OBJECT = str(os.environ.get('GLEANERIO_GLEANER_ARCHIVE_OBJECT', 'scheduler/configs/GleanerCfg.tgz'))
# GLEANERIO_GLEANER_ARCHIVE_PATH = str(os.environ.get('GLEANERIO_GLEANER_ARCHIVE_PATH', '/gleaner/'))
# GLEANERIO_NABU_ARCHIVE_OBJECT=str(os.environ.get('GLEANERIO_NABU_ARCHIVE_OBJECT', 'scheduler/configs/NabuCfg.tgz'))
# GLEANERIO_NABU_ARCHIVE_PATH=str(os.environ.get('GLEANERIO_NABU_ARCHIVE_PATH', '/nabu/'))
# GLEANERIO_GLEANER_DOCKER_CONFIG=str(os.environ.get('GLEANERIO_GLEANER_DOCKER_CONFIG', 'gleaner'))
# GLEANERIO_NABU_DOCKER_CONFIG=str(os.environ.get('GLEANERIO_NABU_DOCKER_CONFIG', 'nabu'))
# #GLEANERIO_SUMMARY_GRAPH_ENDPOINT = os.environ.get('GLEANERIO_SUMMARY_GRAPH_ENDPOINT')
# GLEANERIO_SUMMARY_GRAPH_NAMESPACE = os.environ.get('GLEANERIO_SUMMARY_GRAPH_NAMESPACE',f"{GLEANER_GRAPH_NAMESPACE}_summary" )
#
# SUMMARY_PATH = 'graphs/summary'
# RELEASE_PATH = 'graphs/latest'

# this will probably need to handle the client, and the
class DockerResource(ConfigurableResource):
    DOCKER_URL: str =  Field(
         description="Docker Endpoint URL.")
    DOCKER_PORTAINER_APIKEY: str =  Field(
         description="Portainer API Key.")
    DOCKER_CONTAINER_WAIT_TIMEOUT: str =  Field(
         description="CONTAINER_WAIT_TIMEOUT.")

    def _get_client(self, docker_container_context: DockerContainerContext):
        headers = {'X-API-Key': APIKEY}
        client = docker.DockerClient(base_url=URL, version="1.43")
        # client = docker.APIClient(base_url=URL, version="1.35")
        get_dagster_logger().info(f"create docker client")
        if (client.api._general_configs):
            client.api._general_configs["HttpHeaders"] = headers
        else:
            client.api._general_configs = {"HttpHeaders": headers}
        client.api.headers['X-API-Key'] = APIKEY
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
        get_dagster_logger().info(f"create docker service for {name}")
        ## thoguhts
        # return service, container, since there is one
        restart_policy = RestartPolicy(condition='none')
        # docker.py if replicated job, total completions = replicas
        # replicas =0 you do not get a container
        serivce_mode = ServiceMode("replicated-job", concurrency=1, replicas=1)
        get_dagster_logger().info(str(client.configs.list()))
        #  gleanerid = client.configs.list(filters={"name":{"gleaner-eco": "true"}})
        gleanerconfig = client.configs.list(filters={"name": [GLEANERIO_GLEANER_DOCKER_CONFIG]})
        get_dagster_logger().info(f"docker config gleaner id {str(gleanerconfig[0].id)}")
        nabuconfig = client.configs.list(filters={"name": [GLEANERIO_NABU_DOCKER_CONFIG]})
        get_dagster_logger().info(f"docker config nabu id {str(nabuconfig[0].id)}")
        get_dagster_logger().info(f"create docker service for {name}")
        gleaner = ConfigReference(gleanerconfig[0].id, GLEANERIO_GLEANER_DOCKER_CONFIG, GLEANERIO_GLEANER_CONFIG_PATH)
        nabu = ConfigReference(nabuconfig[0].id, GLEANERIO_NABU_DOCKER_CONFIG, GLEANERIO_NABU_CONFIG_PATH)
        configs = [gleaner, nabu]
        # name = name if len(name) else _get_container_name(op_context.run_id, op_context.op.name, op_context.retry_number),
        service = client.services.create(
            image,
            args=command,
            env=env_vars,
            name=name,
            networks=container_context.networks if len(container_context.networks) else None,
            restart_policy=restart_policy,
            mode=serivce_mode,
            workdir=workingdir,
            configs=configs
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
    # Let's try to use dasgeter aws as the minio configuration
