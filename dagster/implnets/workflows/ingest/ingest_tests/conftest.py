"""Importing the ingest package instantiates the dagster resources at module
scope, and those resources are pydantic models with required str fields fed from
the environment. Without these, collection fails with a ValidationError before a
single test runs. The values are placeholders: nothing here talks to minio,
blazegraph or docker.
"""

import os

_TEST_ENV = {
    "PROJECT": "eco",
    "GLEANERIO_MINIO_BUCKET": "test",
    "GLEANERIO_MINIO_ADDRESS": "localhost",
    "GLEANERIO_MINIO_PORT": "9000",
    "GLEANERIO_CONFIG_PATH": "scheduler/configs/test/",
    "GLEANERIO_SOURCES_FILENAME": "gleanerconfig.yaml",
    "GLEANERIO_TENANT_FILENAME": "tenant.yaml",
    "GLEANERIO_GRAPH_URL": "http://localhost:9999/blazegraph",
    "GLEANERIO_GRAPH_NAMESPACE": "test",
    "GLEANERIO_GRAPH_SUMMARY_NAMESPACE": "test_summary",
    "GLEANERIO_GLEANER_IMAGE": "nsfearthcube/gleaner:test",
    "GLEANERIO_NABU_IMAGE": "nsfearthcube/nabu:test",
    "GLEANERIO_DOCKER_HEADLESS_NETWORK": "headless_gleanerio",
    "GLEANERIO_HEADLESS_ENDPOINT": "http://localhost:9222",
    "GLEANERIO_LOG_PREFIX": "scheduler/logs/",
    "GLEANERIO_GLEANER_CONFIG_PATH": "scheduler/configs/test/",
}

for _key, _value in _TEST_ENV.items():
    os.environ.setdefault(_key, _value)
