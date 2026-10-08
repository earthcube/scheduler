"""Counting records in a release, for the community reports.

The pyoxigraph helpers below are a copy of the ones in
workflows/ingest/ingest/assets/gleaner_summon_assets.py, which spatial_release_quads
uses to run CONSTRUCT queries over a release. The tasks workflow is a separate
package and must not import from the ingest one, so they are duplicated rather
than shared; the originals are left untouched. Diff the two if either changes.
"""
import gc
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from dagster import (
    asset, AssetIn, AssetKey, AutoMaterializePolicy, Output, get_dagster_logger,
)
import pyoxigraph as ox

PROJECT = os.environ.get('PROJECT')
RELEASE_PATH = 'graphs/latest'

# Releases at or above this size are loaded into a temporary on disk store rather
# than an in memory one. Measured on r2r, the largest release at 462MB / 2.45M
# quads, on disk is worse on every axis than streaming into memory:
#
#   in memory, whole file read into bytes   2.50 GB rss   3.0s
#   in memory, streamed                     2.02 GB rss   3.8s
#   on disk, streamed                       2.53 GB rss   9.0s   + 918 MB disk
#
# RocksDB's write buffers during a bulk load cost more than the on disk
# representation saves, so the default sits above every current release and this
# is a safety valve for growth rather than something that fires today. Shares
# GLEANERIO_SPATIAL_ONDISK_THRESHOLD_BYTES with the ingest copy so one knob
# governs both.
RELEASE_ONDISK_THRESHOLD_BYTES = int(
    os.environ.get("GLEANERIO_SPATIAL_ONDISK_THRESHOLD_BYTES", 2 * 1024 ** 3)
)


def _bulk_load(store, release):
    """Load an n-quads release, from bytes or a readable, into ``store``.

    lenient: releases in the wild contain named graph URNs that nabu mints from
    the identifier, like <urn:gleaner.io:eco:geocodes_examples:data:[OTLAS.1]>.
    Square brackets are reserved for IPv6 literals and are not legal in an IRI,
    so a validating parser rejects them -- and one bad quad aborts the whole
    load, not just that line. 756 of the 2920 quads in the geocodes_examples
    release are affected, so a strict load would drop that source entirely.
    """
    store.bulk_load(release, format=ox.RdfFormat.N_QUADS, lenient=True)
    return store


def _load_release_store(release_bytes):
    """In memory store from a release already held in memory. Used by the tests."""
    return _bulk_load(ox.Store(), release_bytes)


def _release_object_size(gleaner_s3, object_name):
    """Size of the release object, or None if it cannot be determined."""
    try:
        head = gleaner_s3.s3.get_client().head_object(
            Bucket=gleaner_s3.GLEANERIO_MINIO_BUCKET, Key=object_name
        )
        return head.get("ContentLength")
    except Exception as ex:  # a missing object is a normal state, see below
        get_dagster_logger().info(f"Release. Could not size {object_name}: {ex}")
        return None


@contextmanager
def _release_store(gleaner_s3, object_name):
    """Open a store over a release, on disk if the release is big enough.

    The body is streamed straight from s3 into the parser rather than read into
    a bytes object first. On r2r that is 480MB of peak RSS saved for ~0.8s of
    wall clock -- see RELEASE_ONDISK_THRESHOLD_BYTES for why the on disk path is
    not the default.
    """
    size = _release_object_size(gleaner_s3, object_name)
    on_disk = size is not None and size >= RELEASE_ONDISK_THRESHOLD_BYTES
    tempdir = tempfile.mkdtemp(prefix="stats_release_") if on_disk else None
    store = None
    try:
        store = ox.Store(path=str(Path(tempdir) / "store")) if on_disk else ox.Store()
        get_dagster_logger().info(
            f"Release. Loading {object_name} ({size} bytes) into "
            f"{'an on disk store at ' + tempdir if on_disk else 'an in memory store'}"
        )
        _bulk_load(store, gleaner_s3.getFile(object_name))
        yield store
    finally:
        if tempdir is not None:
            # the store holds the rocksdb files open and pyoxigraph exposes no
            # close(), so drop the reference and collect before unlinking
            store = None
            gc.collect()
            shutil.rmtree(tempdir, ignore_errors=True)


def count_named_graphs(store) -> int:
    """Distinct named graphs in a loaded release, ie. its record count.

    The release puts every dataset in its own named graph and nothing in the
    default graph, so this is the dataset count. named_graphs() reads the
    store's graph index rather than going through the query planner; a
    SELECT (COUNT(DISTINCT ?g) ...) gives the same answer. bulk_load only ever
    creates a graph that has quads in it, so there are no empty graphs to skew
    the count.
    """
    return sum(1 for _ in store.named_graphs())


def release_record_count(gleaner_s3, source, logger=None) -> int:
    """Records in graphs/latest/{source}_release.nq. 0 if it is not there.

    A source that has never been harvested, or whose release failed to write, is
    a normal state and must not fail the caller -- it reports 0 records, which
    is what an absent row in the summary graph used to give.
    """
    log = logger or get_dagster_logger()
    object_name = f"{RELEASE_PATH}/{source}_release.nq"

    size = _release_object_size(gleaner_s3, object_name)
    if not size:
        log.info(f"No release at {object_name}, {source} reports 0 records")
        return 0

    try:
        with _release_store(gleaner_s3, object_name) as store:
            return count_named_graphs(store)
    except Exception as ex:
        # a malformed release costs one number, not the whole report
        log.error(f"Could not count records in {object_name}: {ex}")
        return 0


def release_record_counts(gleaner_s3, sources, logger=None) -> dict:
    """{source name: record count} over ``sources``, one release at a time."""
    return {source: release_record_count(gleaner_s3, source, logger)
            for source in sources}


@asset(group_name="community", key_prefix=f"{PROJECT}_task",
       required_resource_keys={"s3"},
       ins={"task_sources_config": AssetIn(
           key=AssetKey([f"{PROJECT}_task", "task_sources_config"]))},
       auto_materialize_policy=AutoMaterializePolicy.eager())
def source_release_counts(context, task_sources_config) -> Output[dict]:
    """Record count per source, parsed once per run and shared by every community.

    loadstatsCommunity is partitioned per community and communities overlap
    heavily -- tenant_prod.yaml has bcodmo and r2r in both production and
    deepoceans, plus a geocodesall community that is every source. Counting
    inline would re-download and re-parse the same release once per community
    that contains it, and partitions can run concurrently, so that is
    concurrent memory as well as repeated wall clock. Hoisting it here makes it
    one parse per source per run however many communities there are.
    """
    sources = [s.get('name') for s in task_sources_config if s.get('name')]
    counts = release_record_counts(context.resources.s3, sources, context.log)

    return Output(
        counts,
        metadata={
            "sources": len(counts),
            "total_records": sum(counts.values()),
            "sources_without_a_release": [n for n, c in counts.items() if c == 0],
        },
    )
