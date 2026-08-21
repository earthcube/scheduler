"""Native fetch engine: requests + ThreadPoolExecutor, with headless pages
rendered through a HeadlessRenderer (Playwright over CDP).

This is the original pysummon fetch loop. It looks fetch_page/extract_jsonld
up on the pysummon.summon module at call time so tests can keep
monkeypatching them there.
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import FetchResult


class NativeEngine:
    def __init__(self, renderer=None):
        self.renderer = renderer

    def fetch_all(self, urls, *, accept, headless, headlesswait, delay_ms,
                  threads, logger=None):
        from pysummon import summon

        def fetch_one(url):
            if headless:
                html = self.renderer.render(url, headlesswait=headlesswait)
                return summon.extract_jsonld(html), True
            return summon.fetch_page(url, accept=accept), False

        if threads == 1:
            for url in urls:
                try:
                    docs, rendered = fetch_one(url)
                    yield FetchResult(url=url, docs=docs, rendered=rendered)
                except Exception as e:
                    yield FetchResult(url=url, error=str(e))
                if delay_ms:
                    time.sleep(delay_ms / 1000.0)
        else:
            with ThreadPoolExecutor(max_workers=threads) as pool:
                futures = {pool.submit(fetch_one, url): url for url in urls}
                for future in as_completed(futures):
                    url = futures[future]
                    try:
                        docs, rendered = future.result()
                        yield FetchResult(url=url, docs=docs, rendered=rendered)
                    except Exception as e:
                        yield FetchResult(url=url, error=str(e))
