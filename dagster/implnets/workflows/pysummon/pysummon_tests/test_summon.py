import json

import pytest

from pysummon.summon import (
    parse_sitemap, extract_jsonld, summon_source, SummonStats, _loads_tolerant,
)

URLSET = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.org/dataset/1</loc></url>
  <url><loc>https://example.org/dataset/2</loc><lastmod>2024-01-01</lastmod></url>
</urlset>"""

INDEX = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.org/sitemap-a.xml</loc></sitemap>
  <sitemap><loc>https://example.org/sitemap-b.xml</loc></sitemap>
</sitemapindex>"""

URLSET_B = b"""<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.org/dataset/3</loc></url>
</urlset>"""

NO_NAMESPACE = b"""<urlset>
  <url><loc>https://example.org/plain/1</loc></url>
</urlset>"""


def _fixture_fetch(mapping):
    return lambda url: mapping[url]


def test_parse_urlset():
    urls = parse_sitemap("https://example.org/sitemap.xml",
                         fetch=_fixture_fetch({"https://example.org/sitemap.xml": URLSET}))
    assert urls == ["https://example.org/dataset/1", "https://example.org/dataset/2"]


def test_parse_sitemapindex_recurses():
    urls = parse_sitemap("https://example.org/sitemap.xml", fetch=_fixture_fetch({
        "https://example.org/sitemap.xml": INDEX,
        "https://example.org/sitemap-a.xml": URLSET,
        "https://example.org/sitemap-b.xml": URLSET_B,
    }))
    assert urls == ["https://example.org/dataset/1", "https://example.org/dataset/2",
                    "https://example.org/dataset/3"]


def test_parse_sitemap_without_namespace():
    urls = parse_sitemap("https://example.org/s.xml",
                         fetch=_fixture_fetch({"https://example.org/s.xml": NO_NAMESPACE}))
    assert urls == ["https://example.org/plain/1"]


# ── extract_jsonld ───────────────────────────────────────────────────

HTML = """<html><head>
<script type="application/ld+json">
{"@context": "https://schema.org/", "@type": "Dataset", "name": "one"}
</script>
<script type="application/ld+json">
[{"@type": "Dataset", "name": "two"}, {"@type": "Dataset", "name": "three"}]
</script>
<script type="application/ld+json">
{ this is not json }
</script>
<script type="text/javascript">var x = 1;</script>
</head><body></body></html>"""


def test_extract_multiple_scripts_broken_json_tolerated():
    docs = extract_jsonld(HTML)
    assert [d["name"] for d in docs] == ["one", "two", "three"]


def test_extract_no_jsonld():
    assert extract_jsonld("<html><body><p>hi</p></body></html>") == []


def test_loads_tolerant_control_chars_and_comments():
    assert _loads_tolerant('{"name": "a\x01b"}')["name"] == "a b"
    assert _loads_tolerant('<!-- {"name": "x"} -->')["name"] == "x"


# ── summon_source orchestration ─────────────────────────────────────

def test_summon_sitemap_source(monkeypatch):
    pages = {
        "https://example.org/dataset/1": [{"@type": "Dataset", "name": "one"}],
        "https://example.org/dataset/2": [{"@type": "Dataset", "name": "two"},
                                          {"@type": "Dataset", "name": "extra"}],
    }
    monkeypatch.setattr("pysummon.summon.parse_sitemap",
                        lambda url, fetch=None, _depth=0: list(pages.keys()))
    monkeypatch.setattr("pysummon.summon.fetch_page",
                        lambda url, accept=None, timeout=None: pages[url])

    seen = []
    stats = summon_source(
        {"name": "test", "sourcetype": "sitemap", "url": "https://example.org/sitemap.xml",
         "headless": False},
        sink=lambda doc, url: seen.append((doc["name"], url)),
        summoner={"threads": 2},
    )
    assert stats.sitemap_urls == 2
    assert stats.pages_fetched == 2
    assert stats.pages_failed == 0
    assert stats.docs == 3
    assert sorted(n for n, _ in seen) == ["extra", "one", "two"]


def test_summon_records_failures(monkeypatch):
    monkeypatch.setattr("pysummon.summon.parse_sitemap",
                        lambda url, fetch=None, _depth=0: ["https://example.org/bad"])

    def boom(url, accept=None, timeout=None):
        raise RuntimeError("504")

    monkeypatch.setattr("pysummon.summon.fetch_page", boom)
    stats = summon_source(
        {"name": "test", "sourcetype": "sitemap", "url": "x", "headless": False},
        sink=lambda doc, url: None)
    assert stats.pages_failed == 1
    assert stats.failed_urls == ["https://example.org/bad"]
    assert stats.docs == 0


def test_summon_sitegraph(monkeypatch):
    class FakeResp:
        text = json.dumps([{"@type": "Dataset", "name": "g1"},
                           {"@type": "Dataset", "name": "g2"}])

        def raise_for_status(self):
            pass

    monkeypatch.setattr("pysummon.summon._get",
                        lambda url, accept=None, timeout=None: FakeResp())
    seen = []
    stats = summon_source(
        {"name": "aqua", "sourcetype": "sitegraph", "url": "https://example.org/g.json"},
        sink=lambda doc, url: seen.append(doc["name"]))
    assert stats.docs == 2
    assert seen == ["g1", "g2"]


def test_headless_requires_renderer(monkeypatch):
    monkeypatch.setattr("pysummon.summon.parse_sitemap",
                        lambda url, fetch=None, _depth=0: ["https://example.org/1"])
    with pytest.raises(ValueError, match="headless"):
        summon_source({"name": "h", "sourcetype": "sitemap", "url": "x", "headless": True},
                      sink=lambda doc, url: None)


def test_headless_uses_renderer(monkeypatch):
    monkeypatch.setattr("pysummon.summon.parse_sitemap",
                        lambda url, fetch=None, _depth=0: ["https://example.org/1"])

    class FakeRenderer:
        rendered = []

        def render(self, url, headlesswait=0, timeout=None):
            self.rendered.append((url, headlesswait))
            return HTML

    r = FakeRenderer()
    stats = summon_source(
        {"name": "h", "sourcetype": "sitemap", "url": "x",
         "headless": True, "headlesswait": 2},
        sink=lambda doc, url: None, renderer=r)
    assert r.rendered == [("https://example.org/1", 2)]
    assert stats.headless_rendered == 1
    assert stats.docs == 3  # three parseable docs in the fixture HTML
