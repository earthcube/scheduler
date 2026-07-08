from pipeline.rdf_utils import to_nquads, graph_uri, datacatalog_doc
from pipeline.reporting import aggregate, extract_keywords, counter_to_csv


DOC = {
    "@context": {"@vocab": "https://schema.org/"},
    "@id": "https://example.org/dataset/1",
    "@type": "Dataset",
    "name": "Test Dataset",
    "keywords": "ocean, seismology; geology",
    "creator": {"@id": "https://example.org/person/ada", "@type": "Person",
                "name": "Ada Lovelace"},
    "publisher": {"@type": "Organization", "@id": "https://example.org/org",
                  "name": "Example Org"},
    "spatialCoverage": {"@type": "Place", "@id": "https://example.org/place",
                        "name": "Pacific Ocean"},
}


def test_to_nquads_named_graph():
    g = graph_uri("testsource", "abc123")
    nq = to_nquads(dict(DOC), g)
    assert "<urn:gleaner:testsource:abc123>" in nq
    assert "<https://schema.org/name>" in nq
    # every quad carries the graph label
    lines = [l for l in nq.strip().split("\n") if l]
    assert all(g in line for line in lines)
    assert len(lines) >= 5


def test_datacatalog_doc_and_quads():
    source = {"name": "opentopography", "propername": "OpenTopography",
              "domain": "http://www.opentopography.org/",
              "logo": "https://example.org/logo.png",
              "pid": "https://www.re3data.org/repository/r3d100010655"}
    doc = datacatalog_doc(source)
    assert doc["@type"] == "DataCatalog"
    assert doc["@id"] == source["pid"]
    assert doc["name"] == "OpenTopography"
    nq = to_nquads(doc, graph_uri("opentopography", "datacatalog"))
    assert "DataCatalog" in nq
    assert "<urn:gleaner:opentopography:datacatalog>" in nq


def test_datacatalog_doc_without_pid_minted():
    doc = datacatalog_doc({"name": "somesource"})
    assert doc["@id"] == "https://geocodes.earthcube.org/id/catalog/somesource"


def test_extract_keywords_splits_lists():
    assert extract_keywords(DOC) == ["ocean", "seismology", "geology"]


def test_aggregate_counts():
    stats = aggregate([dict(DOC), dict(DOC)])
    assert stats["documents"] == 2
    assert stats["datasets"] == 2
    assert stats["keywords"]["ocean"] == 2
    assert stats["authors"]["Ada Lovelace"] == 2
    assert stats["publishers"]["Example Org"] == 2
    assert stats["places"]["Pacific Ocean"] == 2
    csv_text = counter_to_csv(stats["keywords"], ["keyword", "count"])
    assert csv_text.splitlines()[0] == "keyword,count"
    assert "ocean,2" in csv_text
