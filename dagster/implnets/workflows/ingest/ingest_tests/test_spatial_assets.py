import pytest

from workflows.ingest.ingest.assets.gleaner_summon_assets import (
    SPATIAL_GRAPH_NAMESPACE,
    _construct_to_quads,
    _run_construct_query,
    _spatial_query_text,
)
from rdflib import ConjunctiveGraph


def _graph_with_box(box):
    graph = ConjunctiveGraph()
    graph.parse(
        data='<https://example.org/ds> <https://schema.org/spatialCoverage> _:b0 .\n'
             '_:b0 <https://schema.org/geo> _:b1 .\n'
             f'_:b1 <https://schema.org/box> "{box}" .\n'
             '_:b1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://schema.org/GeoShape> .\n'
             '<https://example.org/ds> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://schema.org/Dataset> .\n',
        format="nt",
    )
    return graph


def _bbox_wkt(box):
    result = _run_construct_query(_graph_with_box(box), _spatial_query_text("spatial_construct_bbox.rq"))
    wkt = [line for line in result.splitlines() if "asWKT" in line]
    return wkt


def test_construct_to_quads_adds_graph_namespace():
    graph_iri = SPATIAL_GRAPH_NAMESPACE.format(source="example")
    triples = "<s> <p> <o> .\n<s2> <p2> \"literal\" .\n"

    result = _construct_to_quads(triples, graph_iri)

    assert result == (
        "<s> <p> <o> <https://gleaner.io/enhancement/spatial/example> .\n"
        "<s2> <p2> \"literal\" <https://gleaner.io/enhancement/spatial/example> .\n"
    )


def test_construct_to_quads_skips_blank_lines():
    graph_iri = SPATIAL_GRAPH_NAMESPACE.format(source="example")

    result = _construct_to_quads("\n<s> <p> <o> .\n\n", graph_iri)

    assert result == "<s> <p> <o> <https://gleaner.io/enhancement/spatial/example> .\n"


def test_run_construct_query_uses_local_graph():
    graph = ConjunctiveGraph()
    graph.parse(
        data='<https://example.org/ds> <https://schema.org/spatialCoverage> _:b0 .\n'
             '_:b0 <https://schema.org/geo> _:b1 .\n'
             '_:b1 <https://schema.org/box> "1, 2 3, 4" .\n'
             '_:b1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://schema.org/GeoShape> .\n'
             '<https://example.org/ds> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://schema.org/Dataset> .\n',
        format="nt",
    )

    result = _run_construct_query(
        graph,
        """
        PREFIX schema: <https://schema.org/>
        CONSTRUCT { ?s schema:spatialCoverage ?spatialcoverage . }
        WHERE {
          ?s a schema:Dataset .
          ?s schema:spatialCoverage ?spatialcoverage .
        }
        """,
    )

    assert "<https://example.org/ds> <https://schema.org/spatialCoverage>" in result


# schema:box is "minLat minLong maxLat maxLong". Both separator styles below are
# present in the harvested data, and WKT wants "x y" == "long lat", so the
# coordinates come back swapped relative to the source order.
@pytest.mark.parametrize(
    "box",
    [
        "25.0 -126.0 49.0 -81.0",       # space separated, as in geochemistry_custom
        "25.0,-126.0 49.0,-81.0",       # "lat,long lat,long", as in geocodes_examples
        "25.0, -126.0, 49.0, -81.0",    # fully comma separated
        "  25.0   -126.0   49.0   -81.0  ",  # stray whitespace
    ],
)
def test_bbox_query_handles_box_separator_variants(box):
    wkt = _bbox_wkt(box)

    assert len(wkt) == 1
    assert (
        "POLYGON((-126.0 25.0, -81.0 25.0, -81.0 49.0, -126.0 49.0, -126.0 25.0))"
        in wkt[0]
    )


@pytest.mark.parametrize(
    "box",
    [
        "",                     # empty literal
        "25.0 -126.0",          # too few values
        "25.0 -126.0 49.0",     # still too few
        "north south east west",  # non numeric
        "25.0 -126.0 49.0 -81.0 12.0",  # too many values
    ],
)
def test_bbox_query_emits_nothing_for_unparseable_box(box):
    # a malformed box must yield no geometry at all, rather than a wkt literal
    # with empty coordinate slots like "POLYGON(( ,  ,  ,  ,  ))".
    assert _bbox_wkt(box) == []


def test_bbox_query_ignores_language_tagged_box():
    graph = ConjunctiveGraph()
    graph.parse(
        data='<https://example.org/ds> <https://schema.org/spatialCoverage> _:b0 .\n'
             '_:b0 <https://schema.org/geo> _:b1 .\n'
             '_:b1 <https://schema.org/box> "25.0 -126.0 49.0 -81.0"@en .\n'
             '_:b1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://schema.org/GeoShape> .\n'
             '<https://example.org/ds> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://schema.org/Dataset> .\n',
        format="nt",
    )

    result = _run_construct_query(graph, _spatial_query_text("spatial_construct_bbox.rq"))

    assert "POLYGON((-126.0 25.0" in result
