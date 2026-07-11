from pipeline.jsonld_utils import (
    promote_known_ids, promote_identifiers, split_keywords, skolemize,
)
from pipeline.steps import resolve_steps, apply_steps


def test_orcid_promoted_from_identifier():
    doc = {
        "@id": "https://example.org/dataset/1",
        "@type": "Dataset",
        "creator": {"@type": "Person", "name": "Ada Lovelace",
                    "identifier": "https://orcid.org/0000-0002-1825-0097"},
    }
    doc, promoted = promote_known_ids(doc)
    assert promoted == 1
    assert doc["creator"]["@id"] == "https://orcid.org/0000-0002-1825-0097"


def test_ror_promoted_from_sameas_list():
    doc = {
        "@type": "Dataset",
        "publisher": {"@type": "Organization", "name": "Example Org",
                      "sameAs": ["https://twitter.com/example",
                                 "https://ror.org/013cjyk83"]},
    }
    doc, promoted = promote_known_ids(doc)
    assert doc["publisher"]["@id"] == "https://ror.org/013cjyk83"
    assert promoted == 1


def test_bare_doi_normalized():
    node = {"@type": "Dataset", "identifier": "10.5066/F7VX0DMQ"}
    assert promote_identifiers(node) == "https://doi.org/10.5066/F7VX0DMQ"


def test_propertyvalue_identifier():
    node = {"@type": "Person",
            "identifier": {"@type": "PropertyValue", "propertyID": "orcid",
                           "value": "https://orcid.org/0000-0002-1825-0097"}}
    assert promote_identifiers(node) == "https://orcid.org/0000-0002-1825-0097"


def test_wikidata_and_re3data_patterns():
    assert promote_identifiers(
        {"sameAs": "https://www.wikidata.org/entity/Q42"}) == "https://www.wikidata.org/entity/Q42"
    assert promote_identifiers(
        {"url": "https://www.re3data.org/repository/r3d100010655"}) \
        == "https://www.re3data.org/repository/r3d100010655"


def test_plain_url_not_promoted():
    # an ordinary landing-page url is not a persistent identifier
    node = {"@type": "Organization", "url": "https://www.example.org/about"}
    assert promote_identifiers(node) is None


def test_existing_id_not_overwritten():
    doc = {"@type": "Dataset",
           "creator": {"@id": "https://example.org/people/ada", "@type": "Person",
                       "identifier": "https://orcid.org/0000-0002-1825-0097"}}
    doc, promoted = promote_known_ids(doc)
    assert promoted == 0
    assert doc["creator"]["@id"] == "https://example.org/people/ada"


# ── split_keywords ───────────────────────────────────────────────────

def test_packed_keywords_split_to_array():
    doc = {"@type": "Dataset", "keywords": "ocean, seismology; geology"}
    doc, rewritten = split_keywords(doc)
    assert doc["keywords"] == ["ocean", "seismology", "geology"]
    assert rewritten == 1


def test_keyword_list_with_packed_entries():
    doc = {"@type": "Dataset", "keywords": ["ocean", "a; b"]}
    doc, _ = split_keywords(doc)
    assert doc["keywords"] == ["ocean", "a", "b"]


def test_clean_keyword_array_unchanged():
    doc = {"@type": "Dataset", "keywords": ["ocean", "geology"]}
    doc, rewritten = split_keywords(doc)
    assert doc["keywords"] == ["ocean", "geology"]
    assert rewritten == 0


def test_defined_term_keywords_preserved():
    term = {"@type": "DefinedTerm", "name": "ocean"}
    doc = {"@type": "Dataset", "keywords": [term]}
    doc, rewritten = split_keywords(doc)
    assert doc["keywords"] == [term]
    assert rewritten == 0


# ── full chain ordering ──────────────────────────────────────────────

def test_pysummon_default_chain():
    doc = {
        "@type": "Dataset",
        "name": "Chained",
        "keywords": "a, b",
        "creator": {"@type": "Person", "name": "Ada",
                    "identifier": "https://orcid.org/0000-0002-1825-0097"},
        "publisher": {"@type": "Organization", "name": "No PID Org"},
    }
    steps = resolve_steps(
        {"steps": ["fix_context", "promote_identifiers", "split_keywords", "skolemize"]},
        "s")
    out, meta = apply_steps(doc, "s", steps)
    # promotion beat skolemization for the ORCID'd person
    assert out["creator"]["@id"] == "https://orcid.org/0000-0002-1825-0097"
    # the org without a PID got a skolem IRI
    assert out["publisher"]["@id"].startswith(
        "https://geocodes.earthcube.org/.well-known/genid/s/")
    assert out["keywords"] == ["a", "b"]
    assert meta["ids_promoted"] == 1
    assert meta["ids_minted"] == 1
    assert meta["keywords_split"] == 1


def test_skolemize_strategy_hook_still_works():
    doc = {"@id": "https://example.org/1", "@type": "Dataset",
           "creator": {"@type": "Person", "name": "Ada",
                       "identifier": "https://orcid.org/0000-0002-1825-0097"}}
    doc, _ = skolemize(doc, "s", strategies=[promote_identifiers])
    assert doc["creator"]["@id"] == "https://orcid.org/0000-0002-1825-0097"
