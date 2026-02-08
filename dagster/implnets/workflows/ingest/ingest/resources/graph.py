import os
from typing import Any, Dict

import pydash
from dagster import ConfigurableResource, Config, EnvVar, get_dagster_logger

#from dagster import Field
from pydantic import Field
import requests

from .gleanerS3 import gleanerS3Resource
#Let's try to use dasgeter aws as the minio configuration
from ..utils import PythonMinioAddress

# class AirtableConfig(Config):
# DAGSTER_GLEANER_CONFIG_PATH = os.environ.get('DAGSTER_GLEANER_CONFIG_PATH', "/scheduler/gleanerconfig.yaml")
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


class GraphResource(ConfigurableResource):
    GLEANERIO_GRAPH_URL: str =  Field(
         description="GLEANERIO_GRAPH_URL.")
    GLEANERIO_GRAPH_NAMESPACE: str =  Field(
         description="GLEANERIO_GRAPH_NAMESPACE.")
    gs3: gleanerS3Resource

# need multiple namespaces. let's do this.
    def GraphEndpoint(self, namespace):
        url = f"{self.GLEANERIO_GRAPH_URL}/namespace/{namespace}/sparql"
        return url


    def post_to_graph(self, source, path='graphs/latest', extension="nq", graphendpoint=None, suffix='release'):
        if graphendpoint is None:
            graphendpoint = self.GraphEndpoint()
        # revision of EC utilities, will have a insertFromURL
        #instance =  mg.ManageBlazegraph(os.environ.get('GLEANER_GRAPH_URL'),os.environ.get('GLEANER_GRAPH_NAMESPACE') )
        proto = "http"
# this need to get file from s3.

        if self.gs3.GLEANERIO_MINIO_USE_SSL:
            proto = "https"
        port = self.gs3.GLEANERIO_MINIO_PORT
        address = PythonMinioAddress(self.gs3.GLEANERIO_MINIO_ADDRESS, self.gs3.GLEANERIO_MINIO_PORT)
        bucket = self.gs3.GLEANERIO_MINIO_BUCKET
        release_url = f"{proto}://{address}/{bucket}/{path}/{source}_{suffix}.{extension}"
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
        get_dagster_logger().debug(f' status:{r.status_code}')  # status:404
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

class BlazegraphResource(GraphResource):
    """Blazegraph triple store - uses SPARQL UPDATE LOAD command."""
    pass


class GraphDBResource(GraphResource):
    """GraphDB triple store - uses SPARQL UPDATE LOAD command.

    GraphDB uses a repository-based structure. The endpoint URL should include
    the repository path, e.g., http://graphdb:7200/repositories/geocodes
    """
    repository: str = Field(default="", description="GraphDB repository name (optional, can be in URL)")

    def GraphEndpoint(self, namespace):
        """GraphDB endpoint structure: /repositories/{repo}/statements or just use namespace as repo."""
        if self.repository:
            url = f"{self.GLEANERIO_GRAPH_URL}/repositories/{self.repository}"
        else:
            # Use namespace as repository name
            url = f"{self.GLEANERIO_GRAPH_URL}/repositories/{namespace}"
        return url

    def post_to_graph(self, source, path='graphs/latest', extension="nq", graphendpoint=None, suffix='release'):
        """Load data into GraphDB using SPARQL UPDATE LOAD command."""
        if graphendpoint is None:
            graphendpoint = self.GraphEndpoint(self.GLEANERIO_GRAPH_NAMESPACE)

        proto = "https" if self.gs3.GLEANERIO_MINIO_USE_SSL else "http"
        address = PythonMinioAddress(self.gs3.GLEANERIO_MINIO_ADDRESS, self.gs3.GLEANERIO_MINIO_PORT)
        bucket = self.gs3.GLEANERIO_MINIO_BUCKET
        release_url = f"{proto}://{address}/{bucket}/{path}/{source}_{suffix}.{extension}"

        # GraphDB uses /statements endpoint for updates
        url = f"{graphendpoint}/statements"
        get_dagster_logger().info(f'GraphDB: insert "{source}" to {url}')

        loadfrom = {'update': f'LOAD <{release_url}>'}
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}

        r = requests.post(url, headers=headers, data=loadfrom)
        get_dagster_logger().debug(f'status:{r.status_code}')
        get_dagster_logger().info(f'GraphDB: LOAD from {release_url}: status:{r.status_code}')

        if r.status_code in [200, 204]:
            get_dagster_logger().info(f'GraphDB load response: {str(r.text)}')
            return True
        else:
            get_dagster_logger().info(f'GraphDB: error {str(r.text)}')
            raise Exception(f'GraphDB: failed, LOAD from {release_url}: status:{r.status_code}')


class QleverResource(GraphResource):
    """Qlever triple store - generates config files listing release files to load.

    Unlike Blazegraph/GraphDB, Qlever doesn't support SPARQL LOAD.
    Instead, we generate a configuration file that lists the release files.
    """
    config_output_path: str = Field(
        default="graphs/qlever",
        description="S3 path where Qlever config files will be written"
    )

    def GraphEndpoint(self, namespace):
        """Qlever endpoint - used for queries, not for loading."""
        url = f"{self.GLEANERIO_GRAPH_URL}/{namespace}/sparql"
        return url

    def get_release_url(self, source, path='graphs/latest', extension="nq", suffix='release'):
        """Generate the URL for a release file."""
        proto = "https" if self.gs3.GLEANERIO_MINIO_USE_SSL else "http"
        address = PythonMinioAddress(self.gs3.GLEANERIO_MINIO_ADDRESS, self.gs3.GLEANERIO_MINIO_PORT)
        bucket = self.gs3.GLEANERIO_MINIO_BUCKET
        return f"{proto}://{address}/{bucket}/{path}/{source}_{suffix}.{extension}"

    def post_to_graph(self, source, path='graphs/latest', extension="nq", graphendpoint=None, suffix='release'):
        """For Qlever, we add the source to the config file instead of SPARQL LOAD."""
        import json
        from datetime import datetime

        namespace = self.GLEANERIO_GRAPH_NAMESPACE
        if graphendpoint:
            # Extract namespace from endpoint if provided
            parts = graphendpoint.rstrip('/').split('/')
            if len(parts) >= 2:
                namespace = parts[-2] if parts[-1] == 'sparql' else parts[-1]

        config_key = f"{self.config_output_path}/{namespace}_config.json"

        # Try to load existing config
        try:
            existing_config = self.gs3.getFile(path=config_key)
            # getFile returns a StreamingBody, need to read it
            if hasattr(existing_config, 'read'):
                existing_config = existing_config.read().decode('utf-8')
            config = json.loads(existing_config)
        except Exception:
            config = {
                "namespace": namespace,
                "files": [],
                "created": datetime.utcnow().isoformat()
            }

        release_url = self.get_release_url(source, path, extension, suffix)

        # Add or update source entry
        file_entry = {
            "source": source,
            "url": release_url,
            "format": extension,
            "updated": datetime.utcnow().isoformat()
        }

        # Remove existing entry for this source if present
        config["files"] = [f for f in config["files"] if f.get("source") != source]
        config["files"].append(file_entry)
        config["last_updated"] = datetime.utcnow().isoformat()

        # Write config back to S3
        config_json = json.dumps(config, indent=2)
        self.gs3.putTextFileToS3(content=config_json, s3path=config_key)

        get_dagster_logger().info(f'Qlever: added "{source}" to config {config_key}')
        return True

    def generate_full_config(self, sources: list, path='graphs/latest', extension="nq", suffix='release'):
        """Generate a complete config file for all specified sources."""
        import json
        from datetime import datetime

        namespace = self.GLEANERIO_GRAPH_NAMESPACE
        config_key = f"{self.config_output_path}/{namespace}_config.json"

        files = []
        for source in sources:
            release_url = self.get_release_url(source, path, extension, suffix)
            files.append({
                "source": source,
                "url": release_url,
                "format": extension,
                "updated": datetime.utcnow().isoformat()
            })

        config = {
            "namespace": namespace,
            "files": files,
            "created": datetime.utcnow().isoformat(),
            "last_updated": datetime.utcnow().isoformat()
        }

        config_json = json.dumps(config, indent=2)
        self.gs3.putTextFileToS3(content=config_json, s3path=config_key)

        get_dagster_logger().info(f'Qlever: generated full config with {len(sources)} sources at {config_key}')
        return config_key


def get_graph_resource_for_tenant(tenant_config: Dict, default_triplestore: GraphResource) -> GraphResource:
    """Factory function to get the appropriate graph resource for a tenant.

    Args:
        tenant_config: The tenant configuration dict containing 'graph' block
        default_triplestore: The default triplestore resource to use if no store config

    Returns:
        A GraphResource instance configured for the tenant's store type
    """
    graph_config = tenant_config.get('graph', {})
    store_config = graph_config.get('store', {})

    if not store_config:
        # No store config - use default (backwards compatible)
        return default_triplestore

    store_type = store_config.get('type', 'blazegraph').lower()

    if store_type == 'blazegraph':
        return BlazegraphResource(
            GLEANERIO_GRAPH_URL=store_config.get('endpoint_url', default_triplestore.GLEANERIO_GRAPH_URL),
            GLEANERIO_GRAPH_NAMESPACE=graph_config.get('main_namespace', default_triplestore.GLEANERIO_GRAPH_NAMESPACE),
            gs3=default_triplestore.gs3
        )
    elif store_type == 'graphdb':
        return GraphDBResource(
            GLEANERIO_GRAPH_URL=store_config.get('endpoint_url', default_triplestore.GLEANERIO_GRAPH_URL),
            GLEANERIO_GRAPH_NAMESPACE=graph_config.get('main_namespace', default_triplestore.GLEANERIO_GRAPH_NAMESPACE),
            repository=store_config.get('repository', ''),
            gs3=default_triplestore.gs3
        )
    elif store_type == 'qlever':
        return QleverResource(
            GLEANERIO_GRAPH_URL=store_config.get('endpoint_url', default_triplestore.GLEANERIO_GRAPH_URL),
            GLEANERIO_GRAPH_NAMESPACE=graph_config.get('main_namespace', default_triplestore.GLEANERIO_GRAPH_NAMESPACE),
            config_output_path=store_config.get('config_path', 'graphs/qlever'),
            gs3=default_triplestore.gs3
        )
    else:
        get_dagster_logger().warning(f"Unknown store type '{store_type}', using default Blazegraph")
        return default_triplestore

