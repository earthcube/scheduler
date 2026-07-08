# Phase 3 — convert enhanced JSON-LD to RDF and build the release file.
#
# Reads  enhanced/{source}/
# Writes graphs/latest/{source}_release.nq
#
# Each document lands in its own named graph urn:gleaner:{source}:{sha};
# a schema:DataCatalog node for the source (from its gleanerconfig entry)
# is appended in urn:gleaner:{source}:datacatalog. The release path matches
# what Nabu produced, so the Qleverfile and FacetSearch need no change.
import os
from typing import Any

import orjson
from dagster import asset, AssetKey, AssetIn, Output, get_dagster_logger

from .sources import sources_partitions_def, PREFIX
from .phase1_harvest import get_source
from .phase2_enhance import enhanced_jsonld, ENHANCED_PATH
from ..rdf_utils import graph_uri, to_nquads, datacatalog_doc

PROJECT = os.environ.get('PROJECT')

RELEASE_PATH = "graphs/latest"


@asset(group_name="phase3_release", key_prefix=PREFIX,
       op_tags={"ingest": "report"},
       partitions_def=sources_partitions_def,
       required_resource_keys={"gs3"})
def source_datacatalog(context) -> Output[Any]:
    """schema:DataCatalog JSON-LD describing this source, built from its
    gleanerconfig.yaml entry (propername, domain, logo, pid)."""
    source_name = context.asset_partition_key_for_output()
    source = get_source(context, source_name)
    doc = datacatalog_doc(source)
    return Output(doc, metadata={
        "source": source_name,
        "catalog_id": doc["@id"],
        "name": doc["name"],
    })


@asset(group_name="phase3_release", key_prefix=PREFIX,
       op_tags={"ingest": "report"},
       deps=[enhanced_jsonld],
       ins={"source_datacatalog": AssetIn(AssetKey([PREFIX, "source_datacatalog"]))},
       partitions_def=sources_partitions_def,
       required_resource_keys={"gs3"})
def release_nquads(context, source_datacatalog) -> Output[Any]:
    """Release N-Quads file for one source: every enhanced document converted
    into its own named graph, plus the source DataCatalog."""
    gs3 = context.resources.gs3
    source = context.asset_partition_key_for_output()

    prefix = f"{ENHANCED_PATH}/{source}/"
    objects = gs3.listPath(path=prefix)
    client = gs3.s3.get_client()

    parts = []
    converted = 0
    errors = 0
    quad_count = 0
    for obj in objects:
        key = obj["Key"]
        sha = key.rsplit("/", 1)[-1].removesuffix(".jsonld")
        try:
            result = client.get_object(Bucket=gs3.GLEANERIO_MINIO_BUCKET, Key=key)
            doc = orjson.loads(result["Body"].read())
            nq = to_nquads(doc, graph_uri(source, sha))
        except Exception as e:
            get_dagster_logger().warning(f"conversion failed for {key}: {e}")
            errors += 1
            continue
        if nq:
            parts.append(nq)
            quad_count += nq.count("\n")
            converted += 1

    try:
        catalog_nq = to_nquads(source_datacatalog, graph_uri(source, "datacatalog"))
        parts.append(catalog_nq)
        quad_count += catalog_nq.count("\n")
    except Exception as e:
        get_dagster_logger().warning(f"DataCatalog conversion failed for {source}: {e}")

    if objects and converted == 0:
        raise Exception(f"phase3: all {len(objects)} documents for {source} failed to convert")

    release_key = f"{RELEASE_PATH}/{source}_release.nq"
    gs3.putFile(release_key, "".join(parts), content_type="application/n-quads")

    return Output(release_key, metadata={
        "source": source,
        "release": release_key,
        "documents_converted": converted,
        "errors": errors,
        "quad_count": quad_count,
    })
