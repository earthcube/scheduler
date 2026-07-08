# Phase 1 — harvest schema.org JSON-LD into S3 and record identifier
# provenance (what each object's identifier is and where it came from).
#
# S3 outputs:
#   summoned/{source}/          raw harvested JSON-LD (written by Gleaner)
#   metadata/{source}/identifiers.csv   identifier manifest for the source
import csv
import io
import json
import os
from typing import Any
from urllib.error import HTTPError

import orjson
from dagster import asset, AssetKey, Output, get_dagster_logger
from ec.sitemap import Sitemap

from .sources import sources_partitions_def, PREFIX

PROJECT = os.environ.get('PROJECT')

SUMMONED_PATH = "summoned"
METADATA_PATH = "metadata"


def get_source(context, source_name):
    sources = context.repository_def.load_asset_value(AssetKey([PREFIX, "sources_all"]))
    source = list(filter(lambda t: t["name"] == source_name, sources))
    return source[0]


@asset(group_name="phase1_harvest", key_prefix=PREFIX,
       deps=[AssetKey([PREFIX, "sources_names_active"])],
       partitions_def=sources_partitions_def)
def validate_sitemap_url(context):
    source_name = context.asset_partition_key_for_output()
    source = get_source(context, source_name)
    if source['sourcetype'] == "sitemap":  # sitegraph sources have no sitemap
        sm = Sitemap(source['url'], no_progress_bar=True)
        if not sm.validUrl():
            context.log.error(f"source: {source['name']} bad url: {source['url']}")
            raise HTTPError(url=source['url'], code=404, hdrs=None, fp=None,
                            msg=f"Bad URL source: {source['name']} bad url: {source['url']}")
        return source['url']


@asset(group_name="phase1_harvest", key_prefix=PREFIX,
       op_tags={"ingest": "docker"},
       deps=[validate_sitemap_url],
       partitions_def=sources_partitions_def,
       required_resource_keys={"gleanerio"})
def harvest_source(context) -> Output[Any]:
    """Run Gleaner for one source: sitemap -> summoned/{source}/ JSON-LD."""
    source = context.asset_partition_key_for_output()
    result = context.resources.gleanerio.harvest(context, source)
    return Output(result, metadata={"source": source, "run": "gleaner"})


def _first(value):
    """First scalar out of a possibly-list JSON-LD value."""
    if isinstance(value, list):
        return _first(value[0]) if value else None
    if isinstance(value, dict):
        return value.get("@id") or value.get("value") or value.get("name")
    return value


def _classify_identifier(doc):
    """Where does this document's identifier come from?

    Returns (identifier, origin) where origin is one of
    '@id' | 'identifier' | 'sameAs' | 'none' (falls back to the content sha).
    """
    if not isinstance(doc, dict):
        return None, "none"
    doc_id = doc.get("@id") or doc.get("id")
    if doc_id and not str(doc_id).startswith("_:"):
        return doc_id, "@id"
    ident = _first(doc.get("identifier"))
    if ident:
        return ident, "identifier"
    same_as = _first(doc.get("sameAs"))
    if same_as:
        return same_as, "sameAs"
    return None, "none"


@asset(group_name="phase1_harvest", key_prefix=PREFIX,
       op_tags={"ingest": "report"},
       deps=[harvest_source],
       partitions_def=sources_partitions_def,
       required_resource_keys={"gs3"})
def identifier_manifest(context) -> Output[Any]:
    """Manifest of every summoned object's identifier and its provenance.

    Columns: object key, content sha (from the object name), the identifier
    found in the document, where it came from (@id/identifier/sameAs/none),
    the URL the page was harvested from (Gleaner object metadata when
    present), and the object's last-modified date.

    Written to metadata/{source}/identifiers.csv.
    """
    gs3 = context.resources.gs3
    source = context.asset_partition_key_for_output()
    prefix = f"{SUMMONED_PATH}/{source}/"
    objects = gs3.listPath(path=prefix)

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["object_key", "content_sha", "identifier", "identifier_origin",
                     "harvested_from", "last_modified"])
    counts = {"@id": 0, "identifier": 0, "sameAs": 0, "none": 0, "unreadable": 0}
    client = gs3.s3.get_client()
    for obj in objects:
        key = obj["Key"]
        sha = key.rsplit("/", 1)[-1].removesuffix(".jsonld")
        harvested_from = ""
        try:
            result = client.get_object(Bucket=gs3.GLEANERIO_MINIO_BUCKET, Key=key)
            # Gleaner records the crawled URL in S3 user metadata
            meta = result.get("Metadata", {}) or {}
            harvested_from = meta.get("url", meta.get("uniqueid", ""))
            doc = orjson.loads(result["Body"].read())
        except Exception as e:
            get_dagster_logger().warning(f"unreadable summoned object {key}: {e}")
            counts["unreadable"] += 1
            writer.writerow([key, sha, "", "unreadable", harvested_from,
                             str(obj.get("LastModified", ""))])
            continue
        if isinstance(doc, list):
            doc = doc[0] if doc else {}
        identifier, origin = _classify_identifier(doc)
        counts[origin] += 1
        writer.writerow([key, sha, identifier or "", origin, harvested_from,
                         str(obj.get("LastModified", ""))])

    manifest_key = f"{METADATA_PATH}/{source}/identifiers.csv"
    gs3.putTextFile(manifest_key, out.getvalue(), content_type="text/csv")
    return Output(manifest_key, metadata={
        "source": source,
        "objects": len(objects),
        "origin_at_id": counts["@id"],
        "origin_identifier": counts["identifier"],
        "origin_sameAs": counts["sameAs"],
        "origin_none": counts["none"],
        "unreadable": counts["unreadable"],
        "manifest": manifest_key,
    })
