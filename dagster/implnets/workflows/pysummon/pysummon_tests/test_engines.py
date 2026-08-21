"""Engine seam tests: summon_source consuming an injected engine, and the
crawl4ai engine against a stubbed crawl4ai API (no network, no browser)."""
from types import SimpleNamespace

import pytest

from pysummon.engines import FetchResult
from pysummon.engines.crawl4ai_engine import Crawl4aiEngine
from pysummon.summon import summon_source


class FakeEngine:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def fetch_all(self, urls, **kwargs):
        self.calls.append((list(urls), kwargs))
        yield from self.results


def test_summon_source_with_injected_engine(monkeypatch):
    monkeypatch.setattr(
        "pysummon.summon.parse_sitemap",
        lambda url, fetch=None, _depth=0: ["http://x/1", "http://x/2", "http://x/3"])
    engine = FakeEngine([
        FetchResult(url="http://x/1", docs=[{"@type": "Dataset"}, {"@type": "Person"}]),
        FetchResult(url="http://x/2", error="HTTP 500"),
        FetchResult(url="http://x/3", docs=[{"@type": "Dataset"}], rendered=True),
    ])
    sunk = []
    stats = summon_source(
        {"name": "s", "sourcetype": "sitemap", "url": "http://x/sitemap.xml"},
        lambda doc, url: sunk.append((doc, url)),
        summoner={"threads": 4}, engine=engine)

    assert stats.sitemap_urls == 3
    assert stats.pages_fetched == 2
    assert stats.pages_failed == 1
    assert stats.failed_urls == ["http://x/2"]
    assert stats.docs == 3
    assert stats.headless_rendered == 1
    assert len(sunk) == 3
    urls, kwargs = engine.calls[0]
    assert urls == ["http://x/1", "http://x/2", "http://x/3"]
    assert kwargs["threads"] == 4


def test_injected_engine_skips_headless_renderer_check(monkeypatch):
    # with an engine (e.g. crawl4ai) a headless source needs no renderer
    monkeypatch.setattr("pysummon.summon.parse_sitemap",
                        lambda url, fetch=None, _depth=0: ["http://x/1"])
    engine = FakeEngine([FetchResult(url="http://x/1", docs=[], rendered=True)])
    stats = summon_source(
        {"name": "s", "url": "http://x/sitemap.xml", "headless": True},
        lambda doc, url: None, engine=engine)
    assert stats.pages_fetched == 1
    assert engine.calls[0][1]["threads"] == 1  # headless stays sequential


def _stub_c4(monkeypatch, results, captured):
    class StubCrawler:
        def __init__(self, config=None, crawler_strategy=None):
            captured["browser_config"] = config
            captured["strategy"] = crawler_strategy

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def arun_many(self, urls, config=None, dispatcher=None):
            captured["urls"] = list(urls)
            captured["run_config"] = config
            captured["dispatcher"] = dispatcher
            return results

    ns = SimpleNamespace(
        AsyncWebCrawler=StubCrawler,
        BrowserConfig=lambda **kw: SimpleNamespace(**kw),
        CacheMode=SimpleNamespace(BYPASS="bypass"),
        CrawlerRunConfig=lambda **kw: SimpleNamespace(**kw),
        HTTPCrawlerConfig=lambda **kw: SimpleNamespace(**kw),
        AsyncHTTPCrawlerStrategy=lambda **kw: SimpleNamespace(**kw),
        RateLimiter=lambda **kw: SimpleNamespace(**kw),
        SemaphoreDispatcher=lambda **kw: SimpleNamespace(**kw),
    )
    monkeypatch.setattr("pysummon.engines.crawl4ai_engine._imports", lambda: ns)


HTML = '<html><script type="application/ld+json">{"@type": "Dataset"}</script></html>'


def test_crawl4ai_http_path(monkeypatch):
    captured = {}
    _stub_c4(monkeypatch, [
        SimpleNamespace(url="http://x/1", success=True, html=HTML),
        SimpleNamespace(url="http://x/2", success=True,
                        html='{"@graph": "no", "@type": "Dataset"}'),
        SimpleNamespace(url="http://x/3", success=False, html=None,
                        error_message="timeout", status_code=None),
    ], captured)
    engine = Crawl4aiEngine(cdp_endpoint="http://headless:9222")
    results = list(engine.fetch_all(
        ["http://x/1", "http://x/2", "http://x/3"],
        accept="application/ld+json, text/html", headless=False,
        headlesswait=0, delay_ms=0, threads=5))

    assert results[0].docs == [{"@type": "Dataset"}]  # extracted from HTML
    assert results[1].docs[0]["@type"] == "Dataset"   # JSON body used directly
    assert results[0].rendered is False
    assert results[2].error == "timeout"
    # HTTP-only strategy, no browser config
    assert captured["browser_config"] is None
    assert captured["strategy"] is not None
    assert captured["strategy"].browser_config.headers["Accept"] == \
        "application/ld+json, text/html"
    # full concurrency with default politeness delays
    assert captured["dispatcher"].max_session_permit == 5
    assert captured["dispatcher"].rate_limiter.base_delay == (0.2, 1.0)
    assert captured["run_config"].cache_mode == "bypass"


def test_crawl4ai_delay_forces_sequential(monkeypatch):
    captured = {}
    _stub_c4(monkeypatch,
             [SimpleNamespace(url="http://x/1", success=True, html=HTML)],
             captured)
    engine = Crawl4aiEngine()
    list(engine.fetch_all(["http://x/1"], accept="text/html", headless=False,
                          headlesswait=0, delay_ms=2000, threads=5))
    assert captured["dispatcher"].max_session_permit == 1
    assert captured["dispatcher"].rate_limiter.base_delay == (2.0, 2.0)


def test_crawl4ai_headless_path(monkeypatch):
    captured = {}
    _stub_c4(monkeypatch,
             [SimpleNamespace(url="http://x/1", success=True, html=HTML)],
             captured)
    engine = Crawl4aiEngine(cdp_endpoint="http://headless:9222")
    results = list(engine.fetch_all(
        ["http://x/1"], accept="text/html", headless=True, headlesswait=5,
        delay_ms=0, threads=5))
    assert results[0].rendered is True
    assert captured["strategy"] is None  # browser path, not HTTP strategy
    assert captured["browser_config"].cdp_url == "http://headless:9222"
    assert captured["browser_config"].browser_mode == "custom"
    assert captured["run_config"].delay_before_return_html == 5
    assert captured["dispatcher"].max_session_permit == 1


def test_crawl4ai_antibot_false_positive_recovered(monkeypatch):
    # crawl4ai flags bodyless pages as "Blocked by anti-bot protection";
    # if JSON-LD still extracts, the page counts as fetched
    captured = {}
    _stub_c4(monkeypatch, [
        SimpleNamespace(url="http://x/terse", success=False, html=HTML,
                        error_message="Blocked by anti-bot protection: "
                                      "Structural: no <body> tag (104 bytes)",
                        status_code=200),
        SimpleNamespace(url="http://x/blocked", success=False,
                        html="<html>Access denied</html>",
                        error_message="Blocked by anti-bot protection: "
                                      "Tier 1: challenge page",
                        status_code=403),
    ], captured)
    engine = Crawl4aiEngine()
    results = list(engine.fetch_all(
        ["http://x/terse", "http://x/blocked"], accept="text/html",
        headless=False, headlesswait=0, delay_ms=0, threads=2))
    assert results[0].docs == [{"@type": "Dataset"}]
    assert results[0].error is None
    assert results[1].docs is None
    assert "anti-bot" in results[1].error


def test_crawl4ai_headless_requires_cdp_endpoint(monkeypatch):
    captured = {}
    _stub_c4(monkeypatch, [], captured)
    engine = Crawl4aiEngine(cdp_endpoint=None)
    with pytest.raises(ValueError):
        list(engine.fetch_all(["http://x/1"], accept="text/html",
                              headless=True, headlesswait=0, delay_ms=0,
                              threads=1))
