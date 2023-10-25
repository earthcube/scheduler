
from dagster_aws.s3 import  S3Resource

#from dagster import Field
from pydantic import Field

def _pythonMinioAddress(url, port=None):
    if (url.endswith(".amazonaws.com")):
        PYTHON_MINIO_URL = "s3.amazonaws.com"
    else:
        PYTHON_MINIO_URL = url
    if port is not None:
        PYTHON_MINIO_URL = f"{PYTHON_MINIO_URL}:{port}"
    return PYTHON_MINIO_URL

class gleanerS3Resource(S3Resource):
    GLEANERIO_MINIO_BUCKET: str =  Field(
         description="GLEANERIO_MINIO_BUCKET.")
    GLEANERIO_MINIO_ADDRESS: str =  Field(
         description="GLEANERIO_MINIO_BUCKET.")
    GLEANERIO_MINIO_PORT: str =  Field(
         description="GLEANERIO_MINIO_BUCKET.")



  #  endpoint_url =_pythonMinioAddress(GLEANER_MINIO_ADDRESS, port=GLEANER_MINIO_PORT)
