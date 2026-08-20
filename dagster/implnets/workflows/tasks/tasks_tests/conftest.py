"""Importing the tasks package instantiates the dagster resources at module
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
    "GLEANERIO_MINIO_ACCESS_KEY": "test",
    "GLEANERIO_MINIO_SECRET_KEY": "test",
    "GLEANERIO_MINIO_USE_SSL": "false",
    "GLEANERIO_CONFIG_PATH": "scheduler/configs/test/",
    "GLEANERIO_SOURCES_FILENAME": "gleanerconfig.yaml",
    "GLEANERIO_TENANT_FILENAME": "tenant.yaml",
    "GLEANERIO_GRAPH_URL": "http://localhost:9999/blazegraph",
    "GLEANERIO_GRAPH_NAMESPACE": "test",
    "GLEANERIO_GRAPH_SUMMARY_NAMESPACE": "test_summary",
    "GLEANERIO_GRAPH_SUMMARIZE": "false",
    "SLACK_CHANNEL": "#test",
    "SLACK_TOKEN": "xoxb-test",
    "SCHED_HOSTNAME": "sched",
    "HOST": "example.org",
}

for _key, _value in _TEST_ENV.items():
    os.environ.setdefault(_key, _value)
