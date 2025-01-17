import os
from typing import Any, Dict
from abc import ABC, abstractmethod

import pydash
from dagster import ConfigurableResource, Config, EnvVar, get_dagster_logger

#from dagster import Field
from pydantic import Field
import requests

from .gleanerS3 import gleanerS3Resource
from ec.graph.manageGraph import ManageBlazegraph, ManageGraphdb

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


class GraphResource(ConfigurableResource, ABC):
    GLEANERIO_GRAPH_URL: str =  Field(
         description="GLEANERIO_GRAPH_URL.")
    GLEANERIO_GRAPH_NAMESPACE: str =  Field(
         description="GLEANERIO_GRAPH_NAMESPACE.")
    GLEANERIO_GRAPH_USERNAME: str = Field(description="GLEANERIO_GRAPH_USERNAME.")
    GLEANERIO_GRAPH_PASSWORD: str = Field(description="GLEANERIO_GRAPH_PASSWORD.")
    gs3: gleanerS3Resource

# need multiple namespaces. let's do this.
    @abstractmethod
    def GraphEndpoint(self, namespace=GLEANERIO_GRAPH_NAMESPACE):
        url = f"{self.GLEANERIO_GRAPH_URL}/namespace/{namespace}/sparql"
        return url


    @abstractmethod
    def post_to_graph(self, source, path='graphs/latest', extension="nq", namespace=GLEANERIO_GRAPH_NAMESPACE, suffix='release'):
        return NotImplemented

    @abstractmethod
    def deleteNamespace(self, namespace=GLEANERIO_GRAPH_NAMESPACE):
        return NotImplemented

    @abstractmethod
    def createNamespace(self, namespace=GLEANERIO_GRAPH_NAMESPACE, quads=True):
        return NotImplemented



    #def loadRealeaseToNamespace(self,source_name, path=RELEASE_PATH, extension="nq", graphendpoint=endpoint):
    def loadReleaseFromS3(self, source_name, path, extension="nq", namespace=GLEANERIO_GRAPH_NAMESPACE, suffix='release'):
        url = self.gs3.releaseFileUrl(source=source_name, path=path, suffix=suffix, extension=extension )
        get_dagster_logger().debug(f' loadReleaseFromS3 <{url}> , {suffix}, {namespace} {source_name} ')

        return self.loadReleaseFromUrl(url=url, source=source_name, namespace=namespace, suffix=suffix)

    @abstractmethod
    def loadReleaseFromUrl(self, url=None, source=None, namespace=GLEANERIO_GRAPH_NAMESPACE, suffix='release'):
        return NotImplemented
class BlazegraphResource(GraphResource):
    def GraphEndpoint(self, namespace):
        url = f"{self.GLEANERIO_GRAPH_URL}/namespace/{namespace}/sparql"
        return url
    def createNamespace(self, namespace, quads=True):
        if namespace is None or namespace == '' :
            raise Exception('Namespace cannot be empty')
        bg = ManageBlazegraph(self.GLEANERIO_GRAPH_URL, namespace)
        status = bg.createNamespace(quads)
        if status=='Created' or status=='Exists':
            return status

    def deleteNamespace(self, namespace):
        if namespace is None or namespace == '' :
            raise Exception('Namespace cannot be empty')
        bg = ManageBlazegraph(self.GLEANERIO_GRAPH_URL, namespace)
        bg.deleteNamespace()
    def loadReleaseFromUrl(self, url=None, source=None, namespace=None, suffix='release'):
        if url is None:
            raise ValueError("url must be provided")
        else:
            release_url = url
            # if namespace is None:
            #     graphendpoint = self.GraphEndpoint()
            # else:
            #     graphendpoint = self.GraphEndpoint(namespace=namespace)

            bg = ManageBlazegraph(self.GLEANERIO_GRAPH_URL, namespace)
            get_dagster_logger().info(f' upload summary <{release_url}> , {suffix}, {namespace} {source} ')
            bg.loadReleaseFromUrl(url=release_url, source=source, namespace=namespace, suffix='release')
        # url = f"{graphendpoint}"  # f"{os.environ.get('GLEANER_GRAPH_URL')}/namespace/{os.environ.get('GLEANER_GRAPH_NAMESPACE')}/sparql?uri={release_url}"
        # get_dagster_logger().info(f'graph: insert "{source}" to {url} ')
        # loadfrom = {'update': f'LOAD <{release_url}>'}
        # headers = {
        #     'Content-Type': 'application/x-www-form-urlencoded'
        # }
        # r = requests.post(url, headers=headers, data=loadfrom)
        # get_dagster_logger().debug(f' status:{r.status_code}')  # status:404
        # get_dagster_logger().info(f'graph: LOAD from {release_url}: status:{r.status_code}')
        # if r.status_code == 200:
        #     get_dagster_logger().info(f'graph load response: {str(r.text)} ')
        #     # '<?xml version="1.0"?><data modified="0" milliseconds="7"/>'
        #     if 'mutationCount=0' in r.text:
        #         get_dagster_logger().info(f'graph: no data inserted ')
        #         # raise Exception("No Data Added: " + r.text)
        #     return True
        # else:
        #     get_dagster_logger().info(f'graph: error {str(r.text)}')
        #     raise Exception(f' graph: failed,  LOAD from {release_url}: status:{r.status_code}')
    def post_to_graph(self, source, path='graphs/latest', extension="nq", namespace=None, suffix='release'):
        get_dagster_logger().info(f'graph: change function to loadReleaseFromS3')
        return self.loadReleaseFromS3(source,path=path,extension=extension,namespace=namespace, suffix=suffix)

        # if namespace is None:
        #     graphendpoint = self.GraphEndpoint()
        # else:
        #     graphendpoint = self.GraphEndpoint(namespace=namespace)
        # # revision of EC utilities, will have a insertFromURL
        # # instance =  mg.ManageBlazegraph(os.environ.get('GLEANER_GRAPH_URL'),os.environ.get('GLEANER_GRAPH_NAMESPACE') )
        # proto = "http"
        # # this need to get file from s3.
        #
        # if self.gs3.GLEANERIO_MINIO_USE_SSL:
        #     proto = "https"
        # port = self.gs3.GLEANERIO_MINIO_PORT
        # address = PythonMinioAddress(self.gs3.GLEANERIO_MINIO_ADDRESS, self.gs3.GLEANERIO_MINIO_PORT)
        # bucket = self.gs3.GLEANERIO_MINIO_BUCKET
        # release_url = f"{proto}://{address}/{bucket}/{path}/{source}_{suffix}.{extension}"
        # # BLAZEGRAPH SPECIFIC
        # # url = f"{_graphEndpoint()}?uri={release_url}"  # f"{os.environ.get('GLEANER_GRAPH_URL')}/namespace/{os.environ.get('GLEANER_GRAPH_NAMESPACE')}/sparql?uri={release_url}"
        # # get_dagster_logger().info(f'graph: insert "{source}" to {url} ')
        # # r = requests.post(url)
        # # log.debug(f' status:{r.status_code}')  # status:404
        # # get_dagster_logger().info(f'graph: insert: status:{r.status_code}')
        # # if r.status_code == 200:
        # #     # '<?xml version="1.0"?><data modified="0" milliseconds="7"/>'
        # #     if 'data modified="0"' in r.text:
        # #         get_dagster_logger().info(f'graph: no data inserted ')
        # #         raise Exception("No Data Added: " + r.text)
        # #     return True
        # # else:
        # #     get_dagster_logger().info(f'graph: error')
        # #     raise Exception(f' graph: insert failed: status:{r.status_code}')
        #
        # ### GENERIC LOAD FROM
        # url = f"{graphendpoint}"  # f"{os.environ.get('GLEANER_GRAPH_URL')}/namespace/{os.environ.get('GLEANER_GRAPH_NAMESPACE')}/sparql?uri={release_url}"
        # get_dagster_logger().info(f'graph: insert "{source}" to {url} ')
        # loadfrom = {'update': f'LOAD <{release_url}>'}
        # headers = {
        #     'Content-Type': 'application/x-www-form-urlencoded'
        # }
        # r = requests.post(url, headers=headers, data=loadfrom)
        # get_dagster_logger().debug(f' status:{r.status_code}')  # status:404
        # get_dagster_logger().info(f'graph: LOAD from {release_url}: status:{r.status_code}')
        # if r.status_code == 200:
        #     get_dagster_logger().info(f'graph load response: {str(r.text)} ')
        #     # '<?xml version="1.0"?><data modified="0" milliseconds="7"/>'
        #     if 'mutationCount=0' in r.text:
        #         get_dagster_logger().info(f'graph: no data inserted ')
        #         # raise Exception("No Data Added: " + r.text)
        #     return True
        # else:
        #     get_dagster_logger().info(f'graph: error {str(r.text)}')
        #     raise Exception(f' graph: failed,  LOAD from {release_url}: status:{r.status_code}')


class GraphdbResource(GraphResource):
    def GraphEndpoint(self, namespace):
        if namespace is None or namespace == '' :
            url = f"{self.baseurl}repositories/{self.namespace}/"
        else:
            url = f"{self.baseurl}repositories/{namespace}/"
        return url

    def createNamespace(self, namespace, quads=True):
        bg = ManageGraphdb(self.GLEANERIO_GRAPH_URL, namespace, self.GLEANERIO_GRAPH_USERNAME, self.GLEANERIO_GRAPH_PASSWORD)
        status = bg.createNamespace(quads)
        if status == 'Created' or status == 'Exists':
            return status

    def deleteNamespace(self, namespace):
        bg = ManageGraphdb(self.GLEANERIO_GRAPH_URL, namespace, self.GLEANERIO_GRAPH_USERNAME, self.GLEANERIO_GRAPH_PASSWORD)
        bg.deleteNamespace()

    def loadReleaseFromUrl(self, url=None, source=None, namespace=None):
        if url is None:
            raise ValueError("url must be provided")
        else:
            release_url = url
        # if namespace is None:
        #     graphendpoint = self.GraphEndpoint()
        # else:
        #     graphendpoint = self.GraphEndpoint(namespace=namespace)

        bg = ManageGraphdb(self.GLEANERIO_GRAPH_URL, namespace, self.GLEANERIO_GRAPH_USERNAME, self.GLEANERIO_GRAPH_PASSWORD)
        bg.loadReleaseFromUrl(url=release_url, source=source, namespace=namespace)


