"""Pure Python summoner: sitemap -> pages -> JSON-LD documents.

Replaces the Gleaner Go binary. No Dagster or S3 dependencies here — the
asset layer supplies a sink callable — so everything is unit-testable with
fixture HTML/XML.

Headless rendering uses Playwright connected over CDP to a running
chromedp/headless-shell container; no browser is installed in this image.
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup
from lxml import etree

DEFAULT_TIMEOUT = 30
DEFAULT_THREADS = 5
DEFAULT_ACCEPT = "application/ld+json, text/html"
USER_AGENT = "EarthCube-pysummon/0.1 (+https://github.com/earthcube/scheduler)"

_SM_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
# control characters that break json.loads but appear in real-world JSON-LD
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


@dataclass
class SummonStats:
    sitemap_urls: int = 0
    pages_fetched: int = 0
    pages_failed: int = 0
    docs: int = 0
    headless_rendered: int = 0
    failed_urls: list = field(default_factory=list)


def _get(url, accept=DEFAULT_ACCEPT, timeout=DEFAULT_TIMEOUT):
    return requests.get(url, timeout=timeout,
                        headers={"Accept": accept, "User-Agent": USER_AGENT})


def parse_sitemap(url, fetch=None, _depth=0):
    """Return the list of page URLs in a sitemap. Handles <urlset> and
    recursive <sitemapindex> documents; tolerates missing namespaces.

    fetch: optional callable url -> bytes (tests inject fixtures)."""
    if _depth > 3:
        return []
    fetch = fetch or (lambda u: _get(u, accept="application/xml, text/xml, */*").content)
    content = fetch(url)
    root = etree.fromstring(content, parser=etree.XMLParser(recover=True, huge_tree=True))
    if root is None:
        return []
    tag = etree.QName(root.tag).localname if isinstance(root.tag, str) else ""
    urls = []
    if tag == "sitemapindex":
        for loc in root.iter(f"{_SM_NS}loc", "loc"):
            child = (loc.text or "").strip()
            if child:
                urls.extend(parse_sitemap(child, fetch=fetch, _depth=_depth + 1))
    else:  # urlset (or unknown root: still look for loc elements)
        for loc in root.iter(f"{_SM_NS}loc", "loc"):
            page = (loc.text or "").strip()
            if page:
                urls.append(page)
    return urls


def validate_sitemap(url):
    """Cheap validity check used by the config assets: the sitemap fetches,
    parses, and contains at least one URL."""
    try:
        return len(parse_sitemap(url)) > 0
    except Exception:
        return False


def _loads_tolerant(text):
    """json.loads with the cleanups real publisher JSON-LD needs."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        cleaned = _CTRL_RE.sub(" ", text.strip())
        # some publishers emit multiple JSON objects concatenated or wrap in
        # HTML comments
        cleaned = cleaned.removeprefix("<!--").removesuffix("-->").strip()
        return json.loads(cleaned)


def extract_jsonld(html):
    """All parseable JSON-LD documents from a page's script blocks."""
    soup = BeautifulSoup(html, "lxml")
    docs = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.string or script.get_text()
        if not text or not text.strip():
            continue
        try:
            doc = _loads_tolerant(text)
        except Exception:
            continue
        if isinstance(doc, list):
            docs.extend(d for d in doc if isinstance(d, dict))
        elif isinstance(doc, dict):
            docs.append(doc)
    return docs


def fetch_page(url, accept=DEFAULT_ACCEPT, timeout=DEFAULT_TIMEOUT):
    """Fetch one page and return its JSON-LD documents.

    A response that is already JSON(-LD) is used directly (sources whose
    sitemap points at .json/.jsonld resources); HTML goes through
    extract_jsonld."""
    resp = _get(url, accept=accept, timeout=timeout)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "")
    body = resp.text
    if "json" in content_type or body.lstrip()[:1] in ("{", "["):
        try:
            doc = _loads_tolerant(body)
            if isinstance(doc, list):
                return [d for d in doc if isinstance(d, dict)]
            if isinstance(doc, dict):
                return [doc]
        except Exception:
            pass  # fall through and try HTML extraction
    return extract_jsonld(body)


class HeadlessRenderer:
    """Renders pages via a remote chromedp/headless-shell over CDP.

    One Playwright/browser connection per instance (per asset run); a fresh
    context per page keeps state from leaking between pages.
    """

    def __init__(self, cdp_endpoint):
        self.cdp_endpoint = cdp_endpoint
        self._playwright = None
        self._browser = None

    def _connect(self):
        if self._browser is None:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.connect_over_cdp(self.cdp_endpoint)
        return self._browser

    def render(self, url, headlesswait=0, timeout=DEFAULT_TIMEOUT):
        browser = self._connect()
        context = browser.new_context(user_agent=USER_AGENT)
        try:
            page = context.new_page()
            page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
            if headlesswait and headlesswait > 0:
                time.sleep(headlesswait)
            return page.content()
        finally:
            context.close()

    def close(self):
        try:
            if self._browser is not None:
                self._browser.close()
            if self._playwright is not None:
                self._playwright.stop()
        finally:
            self._browser = None
            self._playwright = None


def summon_source(source, sink, summoner=None, renderer=None, logger=None):
    """Harvest one source and hand every JSON-LD doc to sink(doc, page_url).

    source:   a gleanerconfig source entry (sourcetype, url, headless,
              headlesswait, delay, acceptcontenttype, ...)
    sink:     callable(doc: dict, url: str) — the asset layer writes S3
    summoner: the gleanerconfig 'summoner' section ({threads: N, ...})
    renderer: HeadlessRenderer (required when source.headless is true)

    Returns SummonStats.
    """
    summoner = summoner or {}
    log = logger or (lambda msg: None)
    stats = SummonStats()
    accept = source.get("acceptcontenttype") or DEFAULT_ACCEPT
    headless = bool(source.get("headless"))
    headlesswait = max(int(source.get("headlesswait") or 0), 0)
    delay_ms = source.get("delay") or 0

    if source.get("sourcetype") == "sitegraph":
        # one JSON resource holding the whole graph
        resp = _get(source["url"], accept="application/json, application/ld+json")
        resp.raise_for_status()
        doc = _loads_tolerant(resp.text)
        entries = doc if isinstance(doc, list) else doc.get("@graph", [doc])
        stats.sitemap_urls = 1
        stats.pages_fetched = 1
        for entry in entries:
            if isinstance(entry, dict):
                sink(entry, source["url"])
                stats.docs += 1
        return stats

    urls = parse_sitemap(source["url"])
    stats.sitemap_urls = len(urls)
    log(f"{source['name']}: {len(urls)} urls in sitemap")

    if headless and renderer is None:
        raise ValueError(
            f"source {source.get('name')} requires headless rendering but no "
            "renderer was provided (is the headless service running?)")

    # a per-request delay forces sequential fetching (politeness);
    # headless also runs sequentially over one CDP connection
    threads = 1 if (delay_ms or headless) else int(summoner.get("threads") or DEFAULT_THREADS)

    def fetch_one(url):
        if headless:
            html = renderer.render(url, headlesswait=headlesswait)
            stats.headless_rendered += 1
            return extract_jsonld(html)
        return fetch_page(url, accept=accept)

    def handle(url):
        docs = fetch_one(url)
        for doc in docs:
            sink(doc, url)
        return len(docs)

    if threads == 1:
        for url in urls:
            try:
                stats.docs += handle(url)
                stats.pages_fetched += 1
            except Exception as e:
                stats.pages_failed += 1
                stats.failed_urls.append(url)
                log(f"fetch failed {url}: {e}")
            if delay_ms:
                time.sleep(delay_ms / 1000.0)
    else:
        with ThreadPoolExecutor(max_workers=threads) as pool:
            futures = {pool.submit(handle, url): url for url in urls}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    stats.docs += future.result()
                    stats.pages_fetched += 1
                except Exception as e:
                    stats.pages_failed += 1
                    stats.failed_urls.append(url)
                    log(f"fetch failed {url}: {e}")
    return stats
