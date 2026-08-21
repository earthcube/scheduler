"""crawl4ai-backed fetch engine.

Plain sources go through crawl4ai's AsyncHTTPCrawlerStrategy (httpx, no
browser); headless sources use a browser connected over CDP to the same
chromedp/headless-shell service the native engine talks to. crawl4ai's
dispatcher supplies concurrency, politeness delays, and retry with backoff
on 429/503 — which the native engine does not have.

crawl4ai is imported lazily so the rest of pysummon (and the Dagster code
location) loads without it installed; the asset layer falls back to the
native engine in that case.
"""
import asyncio
from types import SimpleNamespace

from . import FetchResult

DEFAULT_TIMEOUT = 30
# distinct token so harvested sites can tell the engines apart in logs
USER_AGENT = "EarthCube-pysummon/0.1 crawl4ai (+https://github.com/earthcube/scheduler)"


def _imports():
    from crawl4ai import (AsyncWebCrawler, BrowserConfig, CacheMode,
                          CrawlerRunConfig, HTTPCrawlerConfig)
    from crawl4ai.async_crawler_strategy import AsyncHTTPCrawlerStrategy
    try:
        from crawl4ai import RateLimiter, SemaphoreDispatcher
    except ImportError:
        from crawl4ai.async_dispatcher import RateLimiter, SemaphoreDispatcher
    return SimpleNamespace(
        AsyncWebCrawler=AsyncWebCrawler, BrowserConfig=BrowserConfig,
        CacheMode=CacheMode, CrawlerRunConfig=CrawlerRunConfig,
        HTTPCrawlerConfig=HTTPCrawlerConfig,
        AsyncHTTPCrawlerStrategy=AsyncHTTPCrawlerStrategy,
        RateLimiter=RateLimiter, SemaphoreDispatcher=SemaphoreDispatcher)


class Crawl4aiEngine:
    def __init__(self, cdp_endpoint=None, timeout=DEFAULT_TIMEOUT):
        self.cdp_endpoint = cdp_endpoint
        self.timeout = timeout

    def fetch_all(self, urls, *, accept, headless, headlesswait, delay_ms,
                  threads, logger=None):
        urls = list(urls)
        if not urls:
            return
        results = asyncio.run(self._crawl(
            urls, accept=accept, headless=headless, headlesswait=headlesswait,
            delay_ms=delay_ms, threads=threads))
        from pysummon import summon
        for r in results:
            error = getattr(r, "error_message", "") or \
                f"HTTP {getattr(r, 'status_code', '?')}"
            if getattr(r, "success", False):
                yield FetchResult(url=r.url,
                                  docs=summon.docs_from_body(r.html or ""),
                                  rendered=headless)
            elif "anti-bot" in error and getattr(r, "html", None) and \
                    (docs := summon.docs_from_body(r.html)):
                # crawl4ai's block heuristics misread terse metadata pages
                # (e.g. no <body> tag) as block pages; if the body still
                # yields JSON-LD the fetch actually worked
                yield FetchResult(url=r.url, docs=docs, rendered=headless)
            else:
                yield FetchResult(url=r.url, error=error)

    async def _crawl(self, urls, *, accept, headless, headlesswait, delay_ms,
                     threads):
        c4 = _imports()
        delay_s = (delay_ms or 0) / 1000.0
        dispatcher = c4.SemaphoreDispatcher(
            max_session_permit=1 if (delay_s or headless) else threads,
            rate_limiter=c4.RateLimiter(
                base_delay=(delay_s, delay_s) if delay_s else (0.2, 1.0),
                max_retries=3))
        # weekly harvests must refetch; crawl4ai's cache would mask updates
        run_config = c4.CrawlerRunConfig(
            cache_mode=c4.CacheMode.BYPASS,
            page_timeout=self.timeout * 1000,
            wait_until="networkidle",
            delay_before_return_html=headlesswait if headless else 0)

        if headless:
            if not self.cdp_endpoint:
                raise ValueError(
                    "headless source but no CDP endpoint configured "
                    "(is the headless service running?)")
            crawler = c4.AsyncWebCrawler(config=c4.BrowserConfig(
                browser_mode="custom", cdp_url=self.cdp_endpoint,
                use_managed_browser=True, headless=True,
                user_agent=USER_AGENT))
        else:
            crawler = c4.AsyncWebCrawler(
                crawler_strategy=c4.AsyncHTTPCrawlerStrategy(
                    browser_config=c4.HTTPCrawlerConfig(
                        method="GET", follow_redirects=True,
                        headers={"Accept": accept, "User-Agent": USER_AGENT})))

        async with crawler:
            return await crawler.arun_many(urls=urls, config=run_config,
                                           dispatcher=dispatcher)
