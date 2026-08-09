import pytest

from workflows.ingest.ingest.assets.gleaner_summon_assets import (
    SPATIAL_GRAPH_NAMESPACE,
    _construct_to_quads,
    _load_release_store,
    _run_construct_query,
    _spatial_query_text,
)

# the release is n-quads, everything in a named graph and nothing in the default
# graph, so the fixtures below have to be quads too: a triples only fixture would
# pass under rdflib's ConjunctiveGraph but match nothing under oxigraph.
GRAPH = "<https://example.org/graph/1>"

# nabu skolemises blank nodes, so in a real release the spatialCoverage and geo
# nodes are https://gleaner.io/xid/genid/... IRIs rather than _:b0 style blank
# nodes. Every release checked looks like this, so it is the default fixture.
GEO = "<https://gleaner.io/xid/genid/testgeo>"

_DATASET = (
    f'<https://example.org/ds> <https://schema.org/spatialCoverage> '
    f'<https://gleaner.io/xid/genid/testsc> {GRAPH} .\n'
    f'<https://gleaner.io/xid/genid/testsc> <https://schema.org/geo> {GEO} {GRAPH} .\n'
    f'<https://example.org/ds> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> '
    f'<https://schema.org/Dataset> {GRAPH} .\n'
)

# the unskolemised shape, which the bbox query still has to cope with
_DATASET_BNODE = (
    f'<https://example.org/ds> <https://schema.org/spatialCoverage> _:b0 {GRAPH} .\n'
    f'_:b0 <https://schema.org/geo> _:b1 {GRAPH} .\n'
    f'<https://example.org/ds> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> '
    f'<https://schema.org/Dataset> {GRAPH} .\n'
)


def _store(data):
    return _load_release_store(data.encode("utf-8"))


def _graph_with_box(box, datatype_or_lang="", geo=GEO, dataset=_DATASET):
    return _store(
        dataset
        + f'{geo} <https://schema.org/box> "{box}"{datatype_or_lang} {GRAPH} .\n'
        + f'{geo} <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> '
          f'<https://schema.org/GeoShape> {GRAPH} .\n'
    )


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
    store = _graph_with_box("1, 2 3, 4")

    result = _run_construct_query(
        store,
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


def test_run_construct_query_reads_named_graphs():
    # the query has no GRAPH clause, so this only matches if the store is queried
    # with the named graphs as the default graph union.
    store = _graph_with_box("25.0 -126.0 49.0 -81.0")

    result = _run_construct_query(
        store,
        "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
    )

    assert "<https://example.org/ds>" in result


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
    result = _run_construct_query(
        _graph_with_box("25.0 -126.0 49.0 -81.0", "@en"),
        _spatial_query_text("spatial_construct_bbox.rq"),
    )

    assert "POLYGON((-126.0 25.0" in result


def test_bbox_geometry_iri_is_derived_from_the_geo_node():
    # the published form. Keeping it identical matters: these IRIs are already in
    # the enhancement graph, and changing their shape would orphan every geometry
    # published so far.
    result = _run_construct_query(
        _graph_with_box("25.0 -126.0 49.0 -81.0"),
        _spatial_query_text("spatial_construct_bbox.rq"),
    )

    assert f"{GEO} <http://www.opengis.net/ont/geosparql#hasGeometry> " in result
    assert "<https://gleaner.io/xid/genid/testgeo/geometry>" in result


def test_bbox_query_still_emits_a_geometry_for_an_unskolemised_geo_node():
    # STR() of a blank node is a type error in SPARQL, so a spec correct engine
    # drops the solution and emits nothing at all. rdflib instead minted invalid
    # relative IRIs like <N793220240ebb.../geometry>. Neither is useful, so the
    # query falls back to keying off the dataset IRI.
    result = _run_construct_query(
        _graph_with_box("25.0 -126.0 49.0 -81.0", geo="_:b1", dataset=_DATASET_BNODE),
        _spatial_query_text("spatial_construct_bbox.rq"),
    )

    assert "POLYGON((-126.0 25.0" in result
    assert "<https://example.org/ds/geometry/bbox/" in result


def test_bbox_query_keeps_multiple_boxes_on_one_geo_node_distinct():
    store = _store(
        _DATASET
        + f'{GEO} <https://schema.org/box> "25.0 -126.0 49.0 -81.0" {GRAPH} .\n'
        + f'{GEO} <https://schema.org/box> "10.0 -20.0 30.0 -40.0" {GRAPH} .\n'
        + f'{GEO} <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> '
          f'<https://schema.org/GeoShape> {GRAPH} .\n'
    )

    result = _run_construct_query(store, _spatial_query_text("spatial_construct_bbox.rq"))
    wkt = [line for line in result.splitlines() if "asWKT" in line]

    # both boxes hang off the same geo node, so they share a geometry IRI -- as
    # they always have. This documents the existing behaviour rather than
    # endorsing it.
    assert len(wkt) == 2
    assert len({line.split(" ", 1)[0] for line in wkt}) == 1


def test_release_with_invalid_iris_still_loads():
    # nabu mints named graph URNs from the identifier, and identifiers containing
    # square brackets come through verbatim: square brackets are reserved for IPv6
    # literals and are not legal in an IRI. A validating parser rejects the quad,
    # and one bad quad aborts the entire load -- 756 of the 2920 quads in the
    # geocodes_examples release are affected, so this is not a corner case.
    store = _store(
        '<https://example.org/ds> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> '
        '<https://schema.org/Dataset> '
        '<urn:gleaner.io:eco:geocodes_examples:data:[OTLAS.022013.26910.2]> .\n'
    )

    assert len(store) == 1


def test_multipoint_coordinates_do_not_carry_a_binary_expansion():
    # coordinates arrive as xsd:double in scientific notation, and casting a
    # double to xsd:decimal is exact, so an unrounded cast yields
    # 166.662669999999975424 rather than 166.66267.
    store = _store(
        '<https://example.org/ds> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> '
        f'<https://schema.org/Dataset> {GRAPH} .\n'
        f'<https://example.org/ds> <https://schema.org/spatialCoverage> _:s0 {GRAPH} .\n'
        f'_:s0 <https://schema.org/geo> _:g0 {GRAPH} .\n'
        f'_:g0 <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> '
        f'<https://schema.org/GeoCoordinates> {GRAPH} .\n'
        f'_:g0 <https://schema.org/latitude> "-7.785067E1"'
        f'^^<http://www.w3.org/2001/XMLSchema#double> {GRAPH} .\n'
        f'_:g0 <https://schema.org/longitude> "1.6666267E2"'
        f'^^<http://www.w3.org/2001/XMLSchema#double> {GRAPH} .\n'
    )

    result = _run_construct_query(store, _spatial_query_text("spatial_construct_multipoint.rq"))

    assert "MULTIPOINT((166.66267 -77.85067))" in result
    # and no scientific notation leaking into the WKT either
    assert "E2" not in result


def test_multipoint_query_groups_points_per_dataset():
    store = _store(
        '<https://example.org/ds> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> '
        f'<https://schema.org/Dataset> {GRAPH} .\n'
        f'<https://example.org/ds> <https://schema.org/spatialCoverage> _:s0 {GRAPH} .\n'
        f'_:s0 <https://schema.org/geo> _:g0 {GRAPH} .\n'
        f'_:g0 <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> '
        f'<https://schema.org/GeoCoordinates> {GRAPH} .\n'
        f'_:g0 <https://schema.org/latitude> "30.5" {GRAPH} .\n'
        f'_:g0 <https://schema.org/longitude> "-100.5" {GRAPH} .\n'
    )

    result = _run_construct_query(store, _spatial_query_text("spatial_construct_multipoint.rq"))

    assert "MULTIPOINT((-100.5 30.5))" in result
    assert "<https://example.org/ds/geometry>" in result
