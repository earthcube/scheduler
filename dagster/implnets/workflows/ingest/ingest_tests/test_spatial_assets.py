from workflows.ingest.ingest.assets.gleaner_summon_assets import (
    SPATIAL_GRAPH_NAMESPACE,
    _construct_to_quads,
)


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
