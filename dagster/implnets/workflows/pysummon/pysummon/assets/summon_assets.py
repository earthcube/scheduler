# Summon phase: python harvest replacing the Gleaner container, plus the
# identifier-provenance manifest.
#
# Writes {PYSUMMON_DATA_PREFIX}summoned/{source}/{sha}.jsonld  (url+date in
# S3 user metadata, like Gleaner) and metadata/{source}/identifiers.csv.
import csv
import hashlib
import io
import os
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError

import orjson
from dagster import asset, AssetKey, Output, get_dagster_logger

from .sources import sources_partitions_def, PREFIX
from ..paths import SUMMONED_PATH, METADATA_PATH
from .. import summon as summon_lib

PROJECT = os.environ.get('PROJECT')


def get_sources_config(context):
    return context.repository_def.load_asset_value(AssetKey([PREFIX, "sources_all"]))


def get_source(context, source_name):
    config = get_sources_config(context)
    matches = [s for s in config["sources"] if s["name"] == source_name]
    return matches[0], config.get("summoner", {})


@asset(group_name="summon", key_prefix=PREFIX,
       deps=[AssetKey([PREFIX, "sources_names_active"])],
       partitions_def=sources_partitions_def)
def validate_sitemap_url(context):
    source_name = context.asset_partition_key_for_output()
    source, _ = get_source(context, source_name)
    if source['sourcetype'] == "sitemap":
        if not summon_lib.validate_sitemap(source['url']):
            raise HTTPError(url=source['url'], code=404, hdrs=None, fp=None,
                            msg=f"Bad sitemap for {source['name']}: {source['url']}")
        return source['url']


@asset(group_name="summon", key_prefix=PREFIX,
       op_tags={"ingest": "summon"},
       deps=[validate_sitemap_url],
       partitions_def=sources_partitions_def,
       required_resource_keys={"gs3", "headless"})
def summon_source(context) -> Output[Any]:
    """Python summoner for one source: sitemap/sitegraph -> pages -> JSON-LD
    objects in S3. Headless sources are rendered via the CDP endpoint."""
    gs3 = context.resources.gs3
    source_name = context.asset_partition_key_for_output()
    source, summoner_cfg = get_source(context, source_name)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    written = set()

    def sink(doc, url):
        data = orjson.dumps(doc)
        sha = hashlib.sha1(data).hexdigest()
        if sha in written:  # identical doc found on multiple pages
            return
        written.add(sha)
        gs3.putFile(
            f"{SUMMONED_PATH}/{source_name}/{sha}.jsonld", data,
            content_type="application/ld+json",
            metadata={"url": url, "date": date, "summoner": "pysummon"})

    renderer = None
    if source.get("headless"):
        renderer = context.resources.headless.renderer()
    try:
        stats = summon_lib.summon_source(
            source, sink, summoner=summoner_cfg, renderer=renderer,
            logger=lambda msg: context.log.info(msg))
    finally:
        if renderer is not None:
            renderer.close()

    if stats.sitemap_urls > 0 and stats.pages_fetched == 0:
        raise Exception(
            f"summon: all {stats.sitemap_urls} pages failed for {source_name}")

    return Output(f"{SUMMONED_PATH}/{source_name}/", metadata={
        "source": source_name,
        "sitemap_urls": stats.sitemap_urls,
        "pages_fetched": stats.pages_fetched,
        "pages_failed": stats.pages_failed,
        "docs_written": len(written),
        "docs_seen": stats.docs,
        "headless_rendered": stats.headless_rendered,
        "failed_urls_sample": stats.failed_urls[:20],
    })


def _first(value):
    if isinstance(value, list):
        return _first(value[0]) if value else None
    if isinstance(value, dict):
        return value.get("@id") or value.get("value") or value.get("name")
    return value


def _classify_identifier(doc):
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


@asset(group_name="summon", key_prefix=PREFIX,
       op_tags={"ingest": "report"},
       deps=[summon_source],
       partitions_def=sources_partitions_def,
       required_resource_keys={"gs3"})
def identifier_manifest(context) -> Output[Any]:
    """Identifier provenance for every summoned object: the identifier found,
    where it came from (@id/identifier/sameAs/none), and the page URL."""
    gs3 = context.resources.gs3
    source = context.asset_partition_key_for_output()
    objects = gs3.listPath(path=f"{SUMMONED_PATH}/{source}/")
    client = gs3.s3.get_client()

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["object_key", "content_sha", "identifier", "identifier_origin",
                     "harvested_from", "last_modified"])
    counts = {"@id": 0, "identifier": 0, "sameAs": 0, "none": 0, "unreadable": 0}
    for obj in objects:
        key = obj["Key"]
        sha = key.rsplit("/", 1)[-1].removesuffix(".jsonld")
        harvested_from = ""
        try:
            result = client.get_object(Bucket=gs3.GLEANERIO_MINIO_BUCKET, Key=key)
            harvested_from = (result.get("Metadata", {}) or {}).get("url", "")
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
    })
