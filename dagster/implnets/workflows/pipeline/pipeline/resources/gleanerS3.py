# S3 resource for the phased pipeline.
# Adapted from ingest/resources/gleanerS3.py with:
#   - paginated listPath (list_objects_v2 paginator; the original capped at 1000 keys)
#   - putFile / putReportFile / putTextFile write helpers used by phases 1-3
import io

from dagster import get_dagster_logger, ConfigurableResource
from dagster_aws.s3 import S3Resource
from pydantic import Field


class gleanerS3Resource(ConfigurableResource):
    s3: S3Resource
    GLEANERIO_MINIO_BUCKET: str = Field(description="S3 bucket for harvested data.")
    GLEANERIO_MINIO_ADDRESS: str = Field(description="S3 endpoint address.")
    GLEANERIO_MINIO_PORT: str = Field(description="S3 endpoint port.")
    GLEANERIO_MINIO_USE_SSL: bool = Field(default=False)
    GLEANERIO_CONFIG_PATH: str = Field(
        description="Prefix holding gleanerconfig/tenant yaml.", default="scheduler/configs/")
    GLEANERIO_TENANT_FILENAME: str = Field(default="tenant.yaml")
    GLEANERIO_SOURCES_FILENAME: str = Field(default="gleanerconfig.yaml")
    GLEANERIO_MINIO_ACCESS_KEY: str = Field(description="S3 access key")
    GLEANERIO_MINIO_SECRET_KEY: str = Field(description="S3 secret key")

    def listPath(self, path="orgs"):
        """Return all object summaries under a prefix (paginated)."""
        paginator = self.s3.get_client().get_paginator("list_objects_v2")
        contents = []
        for page in paginator.paginate(Bucket=self.GLEANERIO_MINIO_BUCKET, Prefix=path):
            contents.extend(page.get("Contents", []))
        return contents

    def getFile(self, path="test"):
        try:
            result = self.s3.get_client().get_object(
                Bucket=self.GLEANERIO_MINIO_BUCKET,
                Key=path,
            )
            return result["Body"]
        except Exception as ex:
            get_dagster_logger().info(
                f"file {path} not found in {self.GLEANERIO_MINIO_BUCKET} at {self.s3.endpoint_url} {ex}")

    def getFileBytes(self, path):
        body = self.getFile(path)
        return body.read() if body is not None else None

    def putFile(self, path, data, content_type="application/octet-stream", metadata=None):
        """Write bytes (or str) to an object; returns the key written."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        f = io.BytesIO(data)
        kwargs = dict(
            Bucket=self.GLEANERIO_MINIO_BUCKET,
            Key=path,
            Body=f,
            ContentLength=len(data),
            ContentType=content_type,
        )
        if metadata:
            kwargs["Metadata"] = metadata
        self.s3.get_client().put_object(**kwargs)
        return path

    def putTextFile(self, path, text, content_type="text/plain", metadata=None):
        return self.putFile(path, text, content_type=content_type, metadata=metadata)

    def putReportFile(self, source, filename, text, content_type="text/csv"):
        return self.putTextFile(f"reports/{source}/{filename}", text, content_type=content_type)

    def getTennatFile(self, path=""):
        if path == "":
            path = f"{self.GLEANERIO_CONFIG_PATH}{self.GLEANERIO_TENANT_FILENAME}"
        get_dagster_logger().info(f"tenant_path {path}")
        return self.getFile(path=path)

    def getSourcesFile(self, path=""):
        if path == "":
            path = f"{self.GLEANERIO_CONFIG_PATH}{self.GLEANERIO_SOURCES_FILENAME}"
        get_dagster_logger().info(f"sources_path {path}")
        return self.getFile(path=path)

    def s3ConfigUrl(self, filename):
        proto = "https" if self.GLEANERIO_MINIO_USE_SSL else "http"
        return (f"{proto}://{self.GLEANERIO_MINIO_ADDRESS}:{self.GLEANERIO_MINIO_PORT}"
                f"/{self.GLEANERIO_MINIO_BUCKET}/{self.GLEANERIO_CONFIG_PATH}{filename}")

    def s3ConfigGleaner(self):
        return self.s3ConfigUrl(self.GLEANERIO_SOURCES_FILENAME)
