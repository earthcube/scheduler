# pysummon — Python summoner (standalone Dagster project)

Replaces the Gleaner Go binary with Python running inside Dagster, built as
its **own project/code location** so it can run in parallel with the
gleaner-based `pipeline` project until it's trusted.

## Workflow

| Group | Asset(s) | Writes (under `PYSUMMON_DATA_PREFIX`, default `pysummon/`) |
|---|---|---|
| summon | `validate_sitemap_url`, `summon_source`, `identifier_manifest` | `summoned/{source}/`, `metadata/{source}/identifiers.csv` |
| enhance | `enhanced_jsonld` | `enhanced/{source}/` |
| reports | `source_report` | `reports/{source}/` |
| release | `source_datacatalog`, `release_nquads` | `graphs/latest/{source}_release.nq` |
| publish | `community_load_files`, `sparql_update_load` | `tenants/{community}/Qleverfile`, `tenants/{community}/load.rq`; optional POST to `sparql_endpoint` |

Default enhancement chain: `fix_context → promote_identifiers →
split_keywords → skolemize` (promote gives typed nodes an ORCID/ROR/DOI/
re3data/wikidata `@id` found in their own identifier/sameAs/url values;
skolemize mints deterministic IRIs for whatever is left). Overridable per
source in `pipelineconfig.yaml`, same file the pipeline project reads.

## Fetch engines

Harvesting runs through a pluggable fetch engine (`pysummon/engines/`):

- **crawl4ai** (default): non-headless sources use crawl4ai's HTTP-only
  strategy (httpx, no browser); headless sources connect its browser over
  CDP. Its dispatcher adds politeness delays and **retry with backoff on
  429/503**. Do not run `crawl4ai-setup` — no local browser is needed.
- **native**: the original requests + ThreadPoolExecutor path, with
  Playwright `connect_over_cdp` for headless sources. Also the automatic
  fallback (with a logged warning) when crawl4ai isn't installed.

Select globally in gleanerconfig's `summoner:` section (`engine: crawl4ai`
or `engine: native`) or per source with `fetcher: native` /
`fetcher: crawl4ai` on the source entry (gleaner ignores the extra key).
The asset's `engine` metadata records which one a run used.

## Headless sources

Sources flagged `headless: true` in gleanerconfig.yaml render through a
`chromedp/headless-shell` container over CDP — no chromium in the Dagster
image. Endpoint: `PYSUMMON_HEADLESS_ENDPOINT` (default
`http://headless:9222`). Per-source `headlesswait` and `delay` are honored;
`delay` or `headless` forces sequential fetching, otherwise the summoner
uses the gleanerconfig `summoner.threads` (default 5). These knobs apply to
both engines.

## Parallel running & promotion

- Both projects read the same config files and crawl the same source list;
  outputs are isolated by `PYSUMMON_DATA_PREFIX`.
- Compare: `metadata/{source}/identifiers.csv` and each asset's doc counts
  vs the gleaner pipeline's `load_report_s3`/manifest for the same source.
- Both weekly schedules default RUNNING; pause either from the Dagster UI
  (note both hitting the same remote sitemaps weekly is intentional during
  the comparison window).
- **Promote pysummon**: set `PYSUMMON_DATA_PREFIX=""`, pause the pipeline
  project's schedule, and let the qlever rebuild (pipeline project) or a
  per-community Qleverfile point at the now-primary release files.

## Deployment image

The simple stack (geocodes `deployment/simple`) runs webserver, daemon, and
both code locations from one image: **`nsfearthcube/dagster-summon`**, built
from `build/Dockerfile_summon` by the `containerize_summon.yaml` GitHub
workflow. It pip-installs `pipeline` and `pysummon` as top-level packages
(what workspace.yaml's `python_module` entries load). The legacy
`dagster-gleanerio` images are unchanged and remain for the gleaner stack.

## Running locally

```
pip install -e ../pipeline -e .[dev]
export PROJECT=geocodes GLEANERIO_MINIO_ADDRESS=...   # see definitions.py
dagster dev -m pysummon.definitions
```

Tests (no network): `python -m pytest pysummon_tests/`
