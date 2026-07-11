from dagster import ConfigurableResource
from pydantic import Field

from ..summon import HeadlessRenderer


class HeadlessResource(ConfigurableResource):
    """Remote headless-chromium (CDP) endpoint for JS-rendered sources.

    Points at the chromedp/headless-shell service (port 9222). A renderer is
    created per asset run and must be closed by the caller."""
    HEADLESS_ENDPOINT: str = Field(
        description="CDP endpoint of the headless chromium service.",
        default="http://headless:9222")

    def renderer(self):
        return HeadlessRenderer(self.HEADLESS_ENDPOINT)
