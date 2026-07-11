"""Pure JSON-LD correction and identifier utilities for phase 2.

No Dagster or S3 dependencies here so everything is unit-testable.
The step registry in steps.py wires these into the per-source pipeline.
"""
import hashlib
import json
import re

SCHEMA_ORG = "https://schema.org/"
# Inline replacement for remote schema.org contexts. Expanding against the
# remote context requires a network fetch per document; @vocab produces the
# same IRIs for plain schema.org documents.
INLINE_SCHEMA_CONTEXT = {"@vocab": SCHEMA_ORG}

DEFAULT_SKOLEM_BASE = "https://geocodes.earthcube.org/.well-known/genid/"

# attributes used to mint a deterministic identifier for a node (phase 2 spec:
# name, url, title, value — plus @type to separate same-named different things)
SALIENT_ATTRS = ("@type", "type", "name", "url", "title", "value")

# keys whose dict values are not node objects
_VALUE_KEYS = {"@value", "@list", "@set"}


def _is_schema_org(url):
    if not isinstance(url, str):
        return False
    u = url.rstrip("/").removesuffix("/docs/jsonldcontext.jsonld")
    return u in ("http://schema.org", "https://schema.org", "https://schema.org/docs/jsonldcontext.jsonld")


def normalize_context(doc):
    """Normalize a document's @context in place and return the doc.

    - missing context        -> inline schema.org vocab
    - schema.org URL string  -> inline schema.org vocab (avoids remote fetch,
                                 normalizes http:// vs https:// drift)
    - dict context           -> schema.org URL values replaced with https form;
                                 keeps custom prefixes
    - list context           -> each element normalized as above
    """
    ctx = doc.get("@context")
    if ctx is None:
        doc["@context"] = dict(INLINE_SCHEMA_CONTEXT)
    elif isinstance(ctx, str):
        if _is_schema_org(ctx):
            doc["@context"] = dict(INLINE_SCHEMA_CONTEXT)
    elif isinstance(ctx, dict):
        new = {}
        for k, v in ctx.items():
            if _is_schema_org(v):
                new[k] = SCHEMA_ORG
            else:
                new[k] = v
        # a dict of prefixes with no default vocab leaves bare terms unmapped
        if "@vocab" not in new and not any(_is_schema_org(v) for v in ctx.values()):
            new.setdefault("@vocab", SCHEMA_ORG)
        doc["@context"] = new
    elif isinstance(ctx, list):
        doc["@context"] = [
            dict(INLINE_SCHEMA_CONTEXT) if _is_schema_org(c) else c for c in ctx
        ]
    return doc


def _node_hash(node):
    """Deterministic hash for a node object.

    Prefers the salient attributes (name, url, title, value, @type); when the
    node has none of them, falls back to a canonical hash of the whole node.
    """
    salient = {}
    for attr in SALIENT_ATTRS:
        if attr in node:
            v = node[attr]
            # a nested object contributes its own name/url if present
            if isinstance(v, dict):
                v = v.get("name") or v.get("@id") or json.dumps(v, sort_keys=True)
            salient[attr] = v
    if salient:
        payload = json.dumps(salient, sort_keys=True, default=str)
    else:
        payload = json.dumps({k: v for k, v in node.items() if k != "@id"},
                             sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _is_node_object(value):
    """True for dicts that represent JSON-LD node objects (not value objects)."""
    if not isinstance(value, dict):
        return False
    if any(k in value for k in _VALUE_KEYS):
        return False
    return True


def _needs_id(node):
    node_id = node.get("@id") or node.get("id")
    if node_id is None:
        return True
    if isinstance(node_id, str) and node_id.startswith("_:"):
        return True
    return False


def skolemize(doc, source, base=DEFAULT_SKOLEM_BASE, strategies=None):
    """Assign deterministic IRIs to blank nodes ('blind nodes') in place.

    Every nested node object without an @id (or with an explicit _: blank node
    id) gets an IRI minted from its salient attributes:
        {base}{source}/{sha1(attrs)}
    Identical content maps to the identical IRI, which deduplicates repeated
    entities (e.g. the same author on many datasets from one source).

    strategies: optional ordered list of callables (node -> IRI or None) tried
    before the hash fallback. This is the hook for ORCID or other external
    identifier resolvers later.

    Returns (doc, count_of_ids_minted).
    """
    strategies = strategies or []
    minted = 0
    # consistent replacement for explicit _:b0 style ids within one document
    blank_map = {}

    def mint(node):
        for strategy in strategies:
            iri = strategy(node)
            if iri:
                return iri
        return f"{base}{source}/{_node_hash(node)}"

    def walk(value, is_root=False):
        nonlocal minted
        if isinstance(value, list):
            for v in value:
                walk(v, is_root=is_root)
            return
        if not _is_node_object(value):
            return
        # children first so a parent's fallback hash covers skolemized children
        for k, v in value.items():
            if k in ("@context",):
                continue
            walk(v)
        # the root node keeps its identity even when it lacks an @id: the
        # document itself is identified by the release named-graph URI
        if not is_root and _needs_id(value):
            old = value.get("@id")
            if isinstance(old, str) and old.startswith("_:"):
                if old not in blank_map:
                    blank_map[old] = mint(value)
                    minted += 1
                value["@id"] = blank_map[old]
            else:
                value["@id"] = mint(value)
                minted += 1

    if isinstance(doc, list):
        for d in doc:
            walk(d, is_root=True)
    else:
        graph = doc.get("@graph")
        if isinstance(graph, list):
            for d in graph:
                walk(d, is_root=True)
            # also walk root-level props other than @graph
            for k, v in doc.items():
                if k not in ("@context", "@graph"):
                    walk(v)
        else:
            walk(doc, is_root=True)
    return doc, minted


def document_sha(raw_bytes):
    """Content hash used to name enhanced objects; matches gleaner's
    identifiersha spirit (sha of the object content)."""
    return hashlib.sha1(raw_bytes).hexdigest()


# ── known-identifier promotion ───────────────────────────────────────
# Patterns for well-known persistent identifiers found in identifier /
# sameAs / url values. Used by promote_identifiers to give typed nodes an
# authoritative @id instead of a minted skolem IRI.
KNOWN_IDENTIFIER_PATTERNS = (
    re.compile(r"^https?://orcid\.org/\d{4}-\d{4}-\d{4}-\d{3}[\dX]$"),
    re.compile(r"^https?://ror\.org/[0-9a-z]{9}$"),
    re.compile(r"^https?://(?:dx\.)?doi\.org/10\.\S+$"),
    re.compile(r"^https?://(?:www\.)?re3data\.org/repository/r3d\d+$"),
    re.compile(r"^https?://(?:www\.)?wikidata\.org/(?:entity|wiki)/Q\d+$"),
    re.compile(r"^https?://(?:www\.)?isni\.org/(?:isni/)?\d{15}[\dX]$"),
)


def _known_identifier(value):
    """Return the value when it matches a known persistent-identifier
    pattern, else None. Accepts strings, PropertyValue dicts, and lists."""
    if isinstance(value, list):
        for v in value:
            match = _known_identifier(v)
            if match:
                return match
        return None
    if isinstance(value, dict):
        # schema:PropertyValue and friends
        for key in ("@id", "value", "url"):
            match = _known_identifier(value.get(key))
            if match:
                return match
        return None
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    # bare DOI form "10.1234/abc" -> normalize to a doi.org IRI
    if re.match(r"^10\.\d{4,}/\S+$", candidate):
        return f"https://doi.org/{candidate}"
    for pattern in KNOWN_IDENTIFIER_PATTERNS:
        if pattern.match(candidate):
            return candidate
    return None


def promote_identifiers(node):
    """IdentifierStrategy for skolemize(): typed nodes without an @id get a
    known persistent identifier (ORCID, ROR, DOI, re3data, wikidata, ISNI)
    found in their identifier / sameAs / url values, when present.

    Returns the IRI or None (None lets skolemize fall through to the next
    strategy / the attribute-hash mint).
    """
    for prop in ("identifier", "sameAs", "url"):
        match = _known_identifier(node.get(prop))
        if match:
            return match
    return None


def promote_known_ids(doc):
    """Walk a document and give every typed node object that lacks an @id a
    known persistent identifier when one is present in its own
    identifier/sameAs/url values. Runs before skolemize in the step chain so
    authoritative IDs win over minted skolem IRIs.

    Returns (doc, count_of_ids_promoted).
    """
    promoted = 0

    def walk(value):
        nonlocal promoted
        if isinstance(value, list):
            for v in value:
                walk(v)
            return
        if not _is_node_object(value):
            return
        if (value.get("@type") or value.get("type")) and _needs_id(value):
            iri = promote_identifiers(value)
            if iri:
                value["@id"] = iri
                promoted += 1
        for k, v in value.items():
            if k != "@context":
                walk(v)

    if isinstance(doc, dict) and isinstance(doc.get("@graph"), list):
        walk(doc["@graph"])
    else:
        walk(doc)
    return doc, promoted


# ── keyword splitting ────────────────────────────────────────────────
_KEYWORD_SPLIT_RE = re.compile(r"[,;]")


def split_keyword_string(value):
    """'ocean, seismology; geology' -> ['ocean', 'seismology', 'geology'];
    values without delimiters pass through unchanged (as a 1-list)."""
    if not isinstance(value, str):
        return [value]
    if not _KEYWORD_SPLIT_RE.search(value):
        return [value.strip()] if value.strip() else []
    return [t.strip() for t in _KEYWORD_SPLIT_RE.split(value) if t.strip()]


def split_keywords(doc):
    """Rewrite packed keyword strings into arrays, in place, on every node
    object in the document. Returns (doc, count_of_nodes_rewritten)."""
    rewritten = 0

    def walk(value):
        nonlocal rewritten
        if isinstance(value, list):
            for v in value:
                walk(v)
            return
        if not _is_node_object(value):
            return
        kw = value.get("keywords")
        if kw is not None:
            terms = []
            changed = False
            for item in kw if isinstance(kw, list) else [kw]:
                parts = split_keyword_string(item)
                if len(parts) != 1 or (parts and parts[0] != item):
                    changed = True
                terms.extend(parts)
            if not isinstance(kw, list):
                changed = True
            if changed:
                value["keywords"] = terms
                rewritten += 1
        for k, v in value.items():
            if k not in ("@context", "keywords"):
                walk(v)

    walk(doc.get("@graph") if isinstance(doc, dict) and isinstance(doc.get("@graph"), list)
         else doc)
    return doc, rewritten
