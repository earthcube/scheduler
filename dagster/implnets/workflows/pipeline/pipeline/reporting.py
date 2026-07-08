"""Pure extraction/aggregation helpers for phase 2.1 community reports.

Works directly on (enhanced) JSON-LD dicts — no triplestore required.
The fields mirror the FacetSearch facets (kw, placenames, pubname,
resourceType) so report numbers match what the UI shows.
"""
import re

_SPLIT_RE = re.compile(r"[,;]")


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _name_of(value):
    """Human name out of a JSON-LD value: strings pass through, node objects
    contribute their name."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        name = value.get("name") or value.get("@value")
        if isinstance(name, list):
            name = name[0] if name else None
        return str(name).strip() if name else None
    return None


def extract_keywords(doc):
    """schema:keywords as a flat list of terms; comma/semicolon-packed
    strings are split (phase 2.2 'break keywords into lists')."""
    terms = []
    for kw in _as_list(doc.get("keywords")):
        name = _name_of(kw)
        if not name:
            continue
        if _SPLIT_RE.search(name):
            terms.extend(t.strip() for t in _SPLIT_RE.split(name) if t.strip())
        else:
            terms.append(name)
    return terms


def extract_author_names(doc):
    names = []
    for prop in ("creator", "author", "contributor"):
        for entity in _as_list(doc.get(prop)):
            name = _name_of(entity)
            if name:
                names.append(name)
    return names


def extract_publisher_names(doc):
    names = []
    for prop in ("publisher", "provider", "sdPublisher"):
        for entity in _as_list(doc.get(prop)):
            name = _name_of(entity)
            if name:
                names.append(name)
    return names


def extract_place_names(doc):
    names = []
    for cov in _as_list(doc.get("spatialCoverage")):
        name = _name_of(cov)
        if name:
            names.append(name)
    return names


def extract_types(doc):
    types = doc.get("@type") or doc.get("type")
    return [str(t) for t in _as_list(types)]


def aggregate(docs):
    """Aggregate a stream of JSON-LD dicts into report counters.

    Returns a dict of Counters/values ready to serialize:
      keywords, authors, publishers, places, types: {term: count}
      documents, datasets: int
    """
    from collections import Counter

    counters = {
        "keywords": Counter(),
        "authors": Counter(),
        "publishers": Counter(),
        "places": Counter(),
        "types": Counter(),
    }
    documents = 0
    datasets = 0
    for doc in docs:
        if isinstance(doc, list):
            for d in doc:
                if isinstance(d, dict):
                    _aggregate_one(d, counters)
                    documents += 1
                    datasets += "Dataset" in extract_types(d)
            continue
        if not isinstance(doc, dict):
            continue
        graph = doc.get("@graph")
        nodes = graph if isinstance(graph, list) else [doc]
        for d in nodes:
            if isinstance(d, dict):
                _aggregate_one(d, counters)
                documents += 1
                datasets += "Dataset" in extract_types(d)
    return {
        **counters,
        "documents": documents,
        "datasets": datasets,
    }


def _aggregate_one(doc, counters):
    counters["keywords"].update(extract_keywords(doc))
    counters["authors"].update(extract_author_names(doc))
    counters["publishers"].update(extract_publisher_names(doc))
    counters["places"].update(extract_place_names(doc))
    counters["types"].update(extract_types(doc))


def counter_to_csv(counter, header):
    """Serialize a Counter to 'term,count' CSV text, most common first."""
    import csv
    import io
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    for term, count in counter.most_common():
        writer.writerow([term, count])
    return out.getvalue()
