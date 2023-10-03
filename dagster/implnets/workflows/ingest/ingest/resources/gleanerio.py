import os
from typing import Any, Dict

import pydash
from dagster import ConfigurableResource, Config, EnvVar
from pyairtable import Api, Table
from pydantic import Field

#Let's try to use dasgeter aws as the minio configuration

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
def _graphEndpoint():
    url = f"{GLEANER_GRAPH_URL}/namespace/{GLEANER_GRAPH_NAMESPACE}/sparql"
    return url
def _graphSummaryEndpoint():
    url = f"{GLEANER_GRAPH_URL}/namespace/{GLEANERIO_SUMMARY_GRAPH_NAMESPACE}/sparql"
    return url


class GleanerioResource(ConfigurableResource):
    DAGSTER_GLEANER_CONFIG_PATH: str =  Field(
         description="DAGSTER_GLEANER_CONFIG_PATH for Project.")
    GLEANER_HEADLESS_NETWORK: str =  Field(
         description="GLEANER_HEADLESS_NETWORK.")
    GLEANERIO_GLEANER_CONFIG_PATH: str =  Field(
         description="GLEANERIO_GLEANER_CONFIG_PATH.")
    GLEANERIO_GLEANER_IMAGE: str =  Field(
         description="GLEANERIO_GLEANER_IMAGE.")
    GLEANERIO_NABU_CONFIG_PATH: str =  Field(
         description="GLEANERIO_NABU_CONFIG_PATH.")
    GLEANERIO_NABU_IMAGE: str =  Field(
         description="GLEANERIO_NABU_IMAGE.")
    GLEANERIO_LOG_PREFIX: str =  Field(
         description="GLEANERIO_LOG_PREFIX.")
    GLEANERIO_GLEANER_DOCKER_CONFIG: str =  Field(
         description="GLEANERIO_GLEANER_DOCKER_CONFIG.")
    GLEANERIO_NABU_DOCKER_CONFIG: str =  Field(
         description="GLEANERIO_NABU_DOCKER_CONFIG.")

    # Let's try to use dasgeter aws as the minio configuration
    def GraphEndpoint(self):
        url = f"{GLEANER_GRAPH_URL}/namespace/{GLEANER_GRAPH_NAMESPACE}/sparql"
        return url
    def GraphSummaryEndpoint(self):
        url = f"{GLEANER_GRAPH_URL}/namespace/{GLEANERIO_SUMMARY_GRAPH_NAMESPACE}/sparql"
        return url

