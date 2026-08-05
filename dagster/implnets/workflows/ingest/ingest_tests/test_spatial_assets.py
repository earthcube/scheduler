from workflows.ingest.ingest.assets.gleaner_summon_assets import (
    SPATIAL_GRAPH_NAMESPACE,
    _construct_to_quads,
    _run_construct_query,
)
from rdflib import ConjunctiveGraph


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
