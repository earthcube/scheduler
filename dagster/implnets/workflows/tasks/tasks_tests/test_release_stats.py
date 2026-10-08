"""Counting records in a release.

The fixtures are n-quads with everything in a named graph and nothing in the
default graph, because that is what a release looks like -- a triples only
fixture would count nothing.
"""
from io import BytesIO

import pytest

from workflows.tasks.tasks.assets import release_stats
from workflows.tasks.tasks.assets.release_stats import (
    _load_release_store,
    _release_store,
    count_named_graphs,
    release_record_count,
    release_record_counts,
)

G1 = "<urn:ec-geocodes:iris:aaa>"
G2 = "<urn:ec-geocodes:iris:bbb>"

TWO_GRAPHS = (
    f'<https://example.org/a> <https://schema.org/name> "A" {G1} .\n'
    f'<https://example.org/a> <https://schema.org/description> "d" {G1} .\n'
    f'<https://example.org/b> <https://schema.org/name> "B" {G2} .\n'
)

# nabu mints named graph urns from the identifier, and square brackets are
# reserved for IPv6 literals so a validating parser rejects the whole load, not
# just the line. 756 of the 2920 quads in the geocodes_examples release look
# like this, which is what lenient=True is for.
BRACKETED = (
    '<https://example.org/c> <https://schema.org/name> "C" '
    '<urn:gleaner.io:eco:geocodes_examples:data:[OTLAS.022013.26910.2]> .\n'
)


class _FakeS3:
    """Enough of gleanerS3Resource for the release helpers."""

    GLEANERIO_MINIO_BUCKET = "test"

    def __init__(self, objects=None, head_raises=False):
        self.objects = objects or {}
        self.head_raises = head_raises
        self.s3 = self

    def get_client(self):
        return self

    def head_object(self, Bucket, Key):
        if self.head_raises:
            raise RuntimeError("boom")
        if Key not in self.objects:
            raise RuntimeError(f"NoSuchKey: {Key}")
        return {"ContentLength": len(self.objects[Key])}

    def getFile(self, path):
        return BytesIO(self.objects[path])


def _release(source, body):
    return {f"graphs/latest/{source}_release.nq": body.encode("utf-8")}


def test_counts_distinct_named_graphs():
    assert count_named_graphs(_load_release_store(TWO_GRAPHS.encode("utf-8"))) == 2


def test_quads_in_the_default_graph_are_not_counted():
    store = _load_release_store(
        (TWO_GRAPHS + '<https://example.org/d> <https://schema.org/name> "D" .\n').encode("utf-8"))

    assert count_named_graphs(store) == 2


def test_an_empty_release_counts_zero():
    assert count_named_graphs(_load_release_store(b"")) == 0


def test_a_bracketed_graph_urn_still_loads():
    """A strict parser aborts the whole load on one of these, dropping the
    source entirely rather than one quad."""
    assert count_named_graphs(_load_release_store((TWO_GRAPHS + BRACKETED).encode("utf-8"))) == 3


def test_release_record_count_reads_the_release():
    s3 = _FakeS3(_release("iris", TWO_GRAPHS))

    assert release_record_count(s3, "iris") == 2


def test_a_missing_release_is_zero_not_an_error():
    """A source that has never been harvested is a normal state."""
    assert release_record_count(_FakeS3({}), "neverharvested") == 0


def test_an_empty_release_object_is_zero():
    assert release_record_count(_FakeS3(_release("iris", "")), "iris") == 0


def test_a_failing_head_is_zero_not_an_error():
    assert release_record_count(_FakeS3(head_raises=True), "iris") == 0


def test_an_unparseable_release_is_zero_not_an_error():
    """A malformed release costs one number, not the whole community report."""
    s3 = _FakeS3({"graphs/latest/iris_release.nq": b"this is not n-quads at all"})

    assert release_record_count(s3, "iris") == 0


def test_release_record_counts_over_several_sources():
    objects = {}
    objects.update(_release("iris", TWO_GRAPHS))
    objects.update(_release("bcodmo", BRACKETED))

    counts = release_record_counts(_FakeS3(objects), ["iris", "bcodmo", "missing"])

    assert counts == {"iris": 2, "bcodmo": 1, "missing": 0}


def test_the_on_disk_path_loads_and_cleans_up(monkeypatch, tmp_path):
    monkeypatch.setattr(release_stats, "RELEASE_ONDISK_THRESHOLD_BYTES", 1)
    created = []
    real_mkdtemp = release_stats.tempfile.mkdtemp

    def _record(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created.append(path)
        return path

    monkeypatch.setattr(release_stats.tempfile, "mkdtemp", _record)

    s3 = _FakeS3(_release("iris", TWO_GRAPHS))
    with _release_store(s3, "graphs/latest/iris_release.nq") as store:
        assert count_named_graphs(store) == 2

    assert created, "expected the on disk path to be taken"
    assert not any(release_stats.Path(p).exists() for p in created)
