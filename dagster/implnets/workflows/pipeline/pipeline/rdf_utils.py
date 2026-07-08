"""Pure JSON-LD -> N-Quads conversion helpers for phase 3."""
from pyld import jsonld

from .jsonld_utils import INLINE_SCHEMA_CONTEXT


def graph_uri(source, sha):
    """Named-graph URI for one document, matching the existing urn scheme."""
    return f"urn:gleaner:{source}:{sha}"


def to_nquads(doc, graph):
    """Convert one JSON-LD document to N-Quads inside a named graph.

    Wraps the document body in {"@id": graph, "@graph": [...]} so pyld emits
    quads with the graph label instead of the default graph.
    """
    if isinstance(doc, list):
        ctx = dict(INLINE_SCHEMA_CONTEXT)
        body = doc
    else:
        ctx = doc.get("@context", dict(INLINE_SCHEMA_CONTEXT))
        body = doc.get("@graph") if isinstance(doc.get("@graph"), list) else [
            {k: v for k, v in doc.items() if k != "@context"}]
    wrapped = {"@context": ctx, "@id": graph, "@graph": body}
    return jsonld.to_rdf(wrapped, {"format": "application/n-quads"})


def datacatalog_doc(source_config, base="https://geocodes.earthcube.org/id/catalog/"):
    """Build a schema:DataCatalog JSON-LD document from a gleanerconfig
    source entry. The pid (usually a re3data or wikidata IRI) becomes the
    catalog identifier when present."""
    name = source_config.get("propername") or source_config["name"]
    catalog_id = source_config.get("pid") or f"{base}{source_config['name']}"
    doc = {
        "@context": dict(INLINE_SCHEMA_CONTEXT),
        "@id": catalog_id,
        "@type": "DataCatalog",
        "name": name,
        "identifier": source_config["name"],
        "url": source_config.get("domain") or source_config.get("url"),
    }
    if source_config.get("logo"):
        doc["image"] = source_config["logo"]
    if source_config.get("pid"):
        doc["sameAs"] = source_config["pid"]
    return doc
