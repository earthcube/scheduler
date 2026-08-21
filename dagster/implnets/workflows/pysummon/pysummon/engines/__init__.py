"""Fetch engines for the summoner.

An engine turns a list of page URLs into FetchResults; everything around it
(sitemap parsing, sitegraph handling, sinking to S3, stats) lives in
pysummon.summon. Engines are duck-typed: anything with

    fetch_all(urls, *, accept, headless, headlesswait, delay_ms, threads,
              logger) -> Iterator[FetchResult]

works. Two implementations ship here:

- native.NativeEngine: requests + ThreadPoolExecutor, Playwright-over-CDP
  for headless sources (the original pysummon code path)
- crawl4ai_engine.Crawl4aiEngine: crawl4ai's HTTP strategy / CDP browser
  with its dispatcher, rate limiting, and 429/503 retry
"""
from dataclasses import dataclass


@dataclass
class FetchResult:
    """Outcome for one page URL: either docs (parsed JSON-LD dicts) or an
    error message. rendered marks pages that went through a headless browser."""
    url: str
    docs: list = None
    error: str = None
    rendered: bool = False
