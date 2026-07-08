# pipeline — phased geocodes ingest

A restructuring of the ingest workflow into discrete phases decoupled through
S3. Each phase reads the previous phase's S3 prefix and writes its own, so
phases can be re-run, inspected, and extended independently — and the steps
that run for each source are configurable.

| Phase | Asset(s) | Reads | Writes |
|---|---|---|---|
| 1 harvest | `validate_sitemap_url`, `harvest_source`, `identifier_manifest` | sitemaps (Gleaner) | `summoned/{source}/`, `metadata/{source}/identifiers.csv` |
| 2 enhance | `enhanced_jsonld` | `summoned/{source}/` | `enhanced/{source}/` |
| 2.1 reports | `source_report` | `enhanced/{source}/` | `reports/{source}/` (keywords, authors, places, publishers, summary) |
| 2.2 vocab *(stub)* | `keyword_vocab_map` | `reports/{source}/` | `vocab/{source}/` |
| 3 release | `source_datacatalog`, `release_nquads` | `enhanced/{source}/` | `graphs/latest/{source}_release.nq` |
| 4 index | `qlever_index_rebuild` | release files (via Qlever) | Qlever index |
| 5 enrich *(stub)* | `spatial_enhance` | release files | `graphs/latest/{source}_spatial.nq` |
| 6 publish *(stub)* | `community_load_files` | releases + tenant.yaml | per-community load files/queries |

## Per-source step configuration

Some sources need additional enhancement steps, others need none. Configure
this separately from the code in S3 at
`{GLEANERIO_CONFIG_PATH}pipelineconfig.yaml`:

```yaml
defaults:
  steps: [fix_context, skolemize]
  reports: true
sources:
  obis:
    steps: []           # pass through untouched
  earthchem:
    steps: [fix_context, skolemize]
    reports: false
```

The file is optional — without it every source runs the defaults. Available
steps are registered in `pipeline/steps.py` (`STEP_REGISTRY`); add a step by
writing `def step(doc, source) -> (doc, metadata)` and registering it.

## Identifiers

Phase 1 writes `metadata/{source}/identifiers.csv` recording, for every
summoned document, the identifier found and where it came from
(`@id` / `identifier` / `sameAs` / none) plus the URL it was harvested from.

Phase 2's `skolemize` step mints deterministic IRIs for blank nodes from
their salient attributes (`@type`, name, url, title, value):
`https://geocodes.earthcube.org/.well-known/genid/{source}/{sha1}`.
Identical content gets an identical IRI, deduplicating repeated entities.
Custom identifier strategies (ORCID, ROR, …) plug into
`jsonld_utils.skolemize(strategies=[...])`.

## Running

```
pip install -e .[dev]
export PROJECT=geocodes GLEANERIO_MINIO_ADDRESS=... # see definitions.py header
dagster dev -m pipeline.definitions
```

Workspace entry:

```yaml
load_from:
  - python_module:
      module_name: pipeline.definitions
      location_name: pipeline
```

Weekly schedule fans out one `{PROJECT}_pipeline_source_job` run per active
source; the `qlever_rebuild_sensor` triggers a single index rebuild after
release files land. Reload one source by launching the job for just that
partition.

Tests: `python -m pytest pipeline_tests/` (pure helpers only, no Dagster
instance needed).
