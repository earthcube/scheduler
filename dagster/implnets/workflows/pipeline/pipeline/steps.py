"""Per-source pipeline step configuration.

Sources differ: some need context repair and skolemization, some need extra
enhancement, some need nothing at all. Which steps run for which source is
configured separately from the code, in S3 at
    {GLEANERIO_CONFIG_PATH}pipelineconfig.yaml
(default scheduler/configs/pipelineconfig.yaml):

    defaults:
      steps: [fix_context, skolemize]
      reports: true
    sources:
      geocodes_demo_datasets: {}            # use defaults
      obis:
        steps: []                           # pass through untouched
      earthchem:
        steps: [fix_context, skolemize]     # explicit
        reports: false

A missing file means every source runs the defaults. Unknown step names fail
fast at resolution time so a typo doesn't silently skip work.

To add a step: write a function step(doc, source) -> (doc, metadata_dict)
and register it in STEP_REGISTRY. Steps run in the order listed.
"""
import logging

import yaml

from . import jsonld_utils

PIPELINE_CONFIG_FILENAME = "pipelineconfig.yaml"
DEFAULT_STEPS = ["fix_context", "skolemize"]


def _step_fix_context(doc, source):
    jsonld_utils.normalize_context(doc)
    return doc, {}


def _step_promote_identifiers(doc, source):
    doc, promoted = jsonld_utils.promote_known_ids(doc)
    return doc, {"ids_promoted": promoted}


def _step_split_keywords(doc, source):
    doc, rewritten = jsonld_utils.split_keywords(doc)
    return doc, {"keywords_split": rewritten}


def _step_skolemize(doc, source):
    doc, minted = jsonld_utils.skolemize(doc, source)
    return doc, {"ids_minted": minted}


STEP_REGISTRY = {
    "fix_context": _step_fix_context,
    # give typed nodes an authoritative @id (ORCID/ROR/DOI/re3data/wikidata)
    # found in their own identifier/sameAs/url values; run before skolemize
    "promote_identifiers": _step_promote_identifiers,
    # break comma/semicolon-packed keyword strings into arrays
    "split_keywords": _step_split_keywords,
    # mint deterministic IRIs for whatever blank nodes remain
    "skolemize": _step_skolemize,
    # future: "standard_form", vocabulary linking (phase 2.2), ...
}


def load_pipeline_config(gs3):
    """Read pipelineconfig.yaml from S3; returns {} when absent."""
    path = f"{gs3.GLEANERIO_CONFIG_PATH}{PIPELINE_CONFIG_FILENAME}"
    body = gs3.getFile(path=path)
    if body is None:
        logging.getLogger(__name__).info(
            f"{path} not found; every source uses default steps {DEFAULT_STEPS}")
        return {}
    return yaml.safe_load(body.read()) or {}


def source_settings(config, source):
    """Merged defaults + per-source settings for one source."""
    defaults = config.get("defaults", {}) if config else {}
    per_source = (config.get("sources", {}) or {}).get(source, {}) if config else {}
    settings = {
        "steps": DEFAULT_STEPS,
        "reports": True,
        "release": True,
        **defaults,
        **per_source,
    }
    return settings


def resolve_steps(settings, source):
    """Turn a settings dict into an ordered list of (name, callable).

    Raises on unknown step names.
    """
    names = settings.get("steps", DEFAULT_STEPS)
    unknown = [n for n in names if n not in STEP_REGISTRY]
    if unknown:
        raise ValueError(
            f"pipelineconfig.yaml: unknown step(s) {unknown} for source {source}; "
            f"known steps: {sorted(STEP_REGISTRY)}")
    return [(n, STEP_REGISTRY[n]) for n in names]


def apply_steps(doc, source, steps):
    """Run the resolved steps over one document; returns (doc, merged_metadata)."""
    merged = {}
    for name, fn in steps:
        doc, meta = fn(doc, source)
        for k, v in meta.items():
            if isinstance(v, int):
                merged[k] = merged.get(k, 0) + v
            else:
                merged[k] = v
    return doc, merged
