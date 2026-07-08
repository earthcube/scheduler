import copy

from pipeline.jsonld_utils import (
    normalize_context, skolemize, INLINE_SCHEMA_CONTEXT, SCHEMA_ORG,
)
from pipeline.steps import (
    source_settings, resolve_steps, apply_steps, DEFAULT_STEPS,
)
import pytest


# ── normalize_context ────────────────────────────────────────────────

def test_missing_context_injected():
    doc = {"@type": "Dataset", "name": "x"}
    normalize_context(doc)
    assert doc["@context"] == INLINE_SCHEMA_CONTEXT


def test_http_schema_org_string_normalized():
    for url in ("http://schema.org", "https://schema.org/", "http://schema.org/"):
        doc = {"@context": url, "@type": "Dataset"}
        normalize_context(doc)
        assert doc["@context"] == INLINE_SCHEMA_CONTEXT


def test_non_schema_context_untouched():
    doc = {"@context": "https://example.org/context.jsonld"}
    normalize_context(doc)
    assert doc["@context"] == "https://example.org/context.jsonld"


def test_dict_context_schema_values_replaced():
    doc = {"@context": {"@vocab": "http://schema.org/", "dct": "http://purl.org/dc/terms/"}}
    normalize_context(doc)
    assert doc["@context"]["@vocab"] == SCHEMA_ORG
    assert doc["@context"]["dct"] == "http://purl.org/dc/terms/"


# ── skolemize ────────────────────────────────────────────────────────

def _dataset():
    return {
        "@context": {"@vocab": SCHEMA_ORG},
        "@id": "https://example.org/dataset/1",
        "@type": "Dataset",
        "name": "Test",
        "creator": {"@type": "Person", "name": "Ada Lovelace"},
        "distribution": [
            {"@type": "DataDownload", "url": "https://example.org/d1.csv"},
            {"@type": "DataDownload", "url": "https://example.org/d2.csv"},
        ],
    }


def test_blank_nodes_get_ids():
    doc, minted = skolemize(_dataset(), "testsource")
    assert minted == 3
    assert doc["creator"]["@id"].startswith(
        "https://geocodes.earthcube.org/.well-known/genid/testsource/")
    for dist in doc["distribution"]:
        assert "@id" in dist


def test_skolemize_is_deterministic():
    a, _ = skolemize(_dataset(), "testsource")
    b, _ = skolemize(_dataset(), "testsource")
    assert a["creator"]["@id"] == b["creator"]["@id"]
    assert a["distribution"][0]["@id"] == b["distribution"][0]["@id"]


def test_distinct_attributes_distinct_iris():
    doc, _ = skolemize(_dataset(), "testsource")
    assert doc["distribution"][0]["@id"] != doc["distribution"][1]["@id"]


def test_same_entity_same_iri_across_docs():
    # the same author on two datasets from one source dedupes to one IRI
    d1, _ = skolemize(_dataset(), "testsource")
    d2 = _dataset()
    d2["@id"] = "https://example.org/dataset/2"
    d2["name"] = "Other"
    d2, _ = skolemize(d2, "testsource")
    assert d1["creator"]["@id"] == d2["creator"]["@id"]


def test_source_namespaces_iris():
    a, _ = skolemize(_dataset(), "source_a")
    b, _ = skolemize(_dataset(), "source_b")
    assert a["creator"]["@id"] != b["creator"]["@id"]


def test_existing_ids_untouched():
    doc = _dataset()
    doc["creator"]["@id"] = "https://orcid.org/0000-0001-2345-6789"
    doc, minted = skolemize(doc, "testsource")
    assert doc["creator"]["@id"] == "https://orcid.org/0000-0001-2345-6789"
    assert minted == 2  # only the two distributions


def test_explicit_blank_node_ids_replaced_consistently():
    doc = {
        "@type": "Dataset",
        "creator": {"@id": "_:b0", "@type": "Person", "name": "Ada"},
        "editor": {"@id": "_:b0", "@type": "Person", "name": "Ada"},
    }
    doc, _ = skolemize(doc, "testsource")
    assert not doc["creator"]["@id"].startswith("_:")
    assert doc["creator"]["@id"] == doc["editor"]["@id"]


def test_root_without_id_is_not_skolemized():
    doc = {"@type": "Dataset", "name": "no id"}
    doc, minted = skolemize(doc, "testsource")
    assert "@id" not in doc
    assert minted == 0


def test_value_objects_not_treated_as_nodes():
    doc = {
        "@id": "https://example.org/1",
        "@type": "Dataset",
        "description": {"@value": "text", "@language": "en"},
    }
    doc, minted = skolemize(doc, "testsource")
    assert minted == 0
    assert "@id" not in doc["description"]


def test_graph_documents_walked():
    doc = {
        "@context": {"@vocab": SCHEMA_ORG},
        "@graph": [
            {"@id": "https://example.org/1", "@type": "Dataset",
             "creator": {"@type": "Person", "name": "Ada"}},
        ],
    }
    doc, minted = skolemize(doc, "testsource")
    assert minted == 1
    assert "@id" in doc["@graph"][0]["creator"]


def test_custom_strategy_wins_over_hash():
    def orcid_strategy(node):
        if node.get("name") == "Ada Lovelace":
            return "https://orcid.org/0000-0000-0000-0000"
        return None

    doc, _ = skolemize(_dataset(), "testsource", strategies=[orcid_strategy])
    assert doc["creator"]["@id"] == "https://orcid.org/0000-0000-0000-0000"


# ── per-source step config ───────────────────────────────────────────

CONFIG = {
    "defaults": {"steps": ["fix_context", "skolemize"]},
    "sources": {
        "passthrough_source": {"steps": []},
        "custom_source": {"steps": ["fix_context"], "reports": False},
    },
}


def test_default_settings_without_config():
    s = source_settings({}, "anything")
    assert s["steps"] == DEFAULT_STEPS
    assert s["reports"] is True


def test_per_source_override():
    assert source_settings(CONFIG, "passthrough_source")["steps"] == []
    custom = source_settings(CONFIG, "custom_source")
    assert custom["steps"] == ["fix_context"]
    assert custom["reports"] is False


def test_unlisted_source_uses_defaults():
    assert source_settings(CONFIG, "other")["steps"] == ["fix_context", "skolemize"]


def test_unknown_step_raises():
    with pytest.raises(ValueError, match="unknown step"):
        resolve_steps({"steps": ["skolemizee"]}, "typo_source")


def test_apply_steps_passthrough():
    doc = {"@type": "Dataset", "creator": {"@type": "Person", "name": "Ada"}}
    original = copy.deepcopy(doc)
    out, meta = apply_steps(doc, "s", resolve_steps({"steps": []}, "s"))
    assert out == original
    assert meta == {}


def test_apply_steps_full_chain():
    doc = {"@type": "Dataset", "creator": {"@type": "Person", "name": "Ada"}}
    steps = resolve_steps({"steps": ["fix_context", "skolemize"]}, "s")
    out, meta = apply_steps(doc, "s", steps)
    assert out["@context"] == INLINE_SCHEMA_CONTEXT
    assert "@id" in out["creator"]
    assert meta["ids_minted"] == 1
