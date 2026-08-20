"""load_report_release reads the release rather than a graph endpoint."""
from io import BytesIO

import pytest

from workflows.ingest.ingest.assets.gleaner_summon_assets import (
    RELEASE_REPORT_KEY_RENAMES,
    _as_release_report,
    _load_release_store,
    _release_store,
    release_graph_urns,
)

G1 = "<urn:gleaner.io:eco:iris:data:aaaa>"
G2 = "<urn:gleaner.io:eco:iris:data:bbbb>"

TWO_GRAPHS = (
    f'<https://example.org/a> <https://schema.org/name> "A" {G1} .\n'
    f'<https://example.org/a> <https://schema.org/description> "d" {G1} .\n'
    f'<https://example.org/b> <https://schema.org/name> "B" {G2} .\n'
)


class _FakeS3:
    GLEANERIO_MINIO_BUCKET = "test"

    def __init__(self, objects=None):
        self.objects = objects or {}
        self.s3 = self

    def get_client(self):
        return self

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise RuntimeError(f"NoSuchKey: {Key}")
        return {"ContentLength": len(self.objects[Key])}

    def getFile(self, path):
        return BytesIO(self.objects[path])


def test_release_graph_urns_returns_the_urns_not_a_count():
    """missingReport needs the urn strings -- it takes the sha off each one."""
    urns = release_graph_urns(_load_release_store(TWO_GRAPHS.encode("utf-8")))

    assert sorted(urns) == [
        "urn:gleaner.io:eco:iris:data:aaaa",
        "urn:gleaner.io:eco:iris:data:bbbb",
    ]


def test_quads_in_the_default_graph_contribute_no_urn():
    store = _load_release_store(
        (TWO_GRAPHS + '<https://example.org/d> <https://schema.org/name> "D" .\n').encode("utf-8"))

    assert len(release_graph_urns(store)) == 2


def test_an_empty_release_has_no_urns():
    assert release_graph_urns(_load_release_store(b"")) == []


def test_urns_read_through_the_release_store():
    s3 = _FakeS3({"graphs/latest/iris_release.nq": TWO_GRAPHS.encode("utf-8")})

    with _release_store(s3, "graphs/latest/iris_release.nq") as store:
        assert len(release_graph_urns(store)) == 2


def test_key_remap_renames_every_graph_named_key():
    response = {
        "source": "iris",
        "graph": "http://graph/namespace/decoder/sparql",
        "graph_urn_count": 2,
        "missing_summon_graph_count": 1,
        "missing_summon_graph": ["cccc"],
        "graph_sha_urn_time": 0.5,
        "sitemap_count": 7,
    }

    renamed = _as_release_report(response, "graphs/latest/iris_release.nq")

    assert renamed["release"] == "graphs/latest/iris_release.nq"
    assert renamed["release_urn_count"] == 2
    assert renamed["missing_summon_release_count"] == 1
    assert renamed["missing_summon_release"] == ["cccc"]
    assert renamed["release_sha_urn_time"] == 0.5
    # untouched keys survive
    assert renamed["sitemap_count"] == 7
    assert renamed["source"] == "iris"


def test_no_graph_named_key_survives_the_remap():
    """The point of the rename: nothing left implies a live graph."""
    response = {k: "x" for k in RELEASE_REPORT_KEY_RENAMES}

    renamed = _as_release_report(response, "graphs/latest/iris_release.nq")

    assert not [k for k in renamed if k.startswith("graph")]
