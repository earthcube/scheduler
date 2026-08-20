"""Resolving a community's sources from tenant.yaml + gleanerconfig.yaml."""

from workflows.tasks.tasks.assets.tenants import (
    _expand_tenant_sources,
    _sources_by_name,
)

# shaped like configs/eco/gleanerconfig.yaml, where amgeo and aquadocs are
# active: false
SOURCES_CONFIG = [
    {"name": "amgeo", "propername": "AMGeO", "domain": "https://amgeo.colorado.edu/",
     "url": "https://amgeo-dev.colorado.edu/sitemap.xml", "active": False},
    {"name": "iris", "propername": "IRIS", "domain": "https://ds.iris.edu",
     "url": "https://ds.iris.edu/sitemap.xml", "active": True},
    {"name": "geocodes_demo_datasets", "propername": "Demo", "domain": "https://example.org",
     "url": "https://example.org/sitemap.xml", "active": True},
]


class _Logger:
    def __init__(self):
        self.warnings = []

    def warning(self, message):
        self.warnings.append(message)


def test_sources_by_name_keys_on_name():
    by_name = _sources_by_name(SOURCES_CONFIG)

    assert set(by_name) == {"amgeo", "iris", "geocodes_demo_datasets"}
    assert by_name["iris"]["propername"] == "IRIS"


def test_a_literal_source_list_resolves_to_itself():
    names = _expand_tenant_sources(
        ["iris", "geocodes_demo_datasets"], _sources_by_name(SOURCES_CONFIG), _Logger())

    assert names == ["iris", "geocodes_demo_datasets"]


def test_all_means_every_active_source():
    """tenant.yaml and tenant_prod.yaml both declare a geocodesall community
    with sources: [all]."""
    names = _expand_tenant_sources(["all"], _sources_by_name(SOURCES_CONFIG), _Logger())

    assert names == ["iris", "geocodes_demo_datasets"]
    assert "amgeo" not in names


def test_all_wins_over_the_other_entries():
    names = _expand_tenant_sources(
        ["iris", "all"], _sources_by_name(SOURCES_CONFIG), _Logger())

    assert names == ["iris", "geocodes_demo_datasets"]


def test_all_is_matched_case_insensitively():
    assert _expand_tenant_sources(["All"], _sources_by_name(SOURCES_CONFIG), _Logger()) \
        == ["iris", "geocodes_demo_datasets"]


def test_a_source_missing_from_gleanerconfig_is_dropped_with_a_warning():
    """The two files are edited independently and drift; one stale name should
    not take a community's whole report down."""
    logger = _Logger()

    names = _expand_tenant_sources(
        ["iris", "retired_last_year"], _sources_by_name(SOURCES_CONFIG), logger)

    assert names == ["iris"]
    assert any("retired_last_year" in w for w in logger.warnings)


def test_duplicates_are_removed_and_order_preserved():
    names = _expand_tenant_sources(
        ["geocodes_demo_datasets", "iris", "geocodes_demo_datasets"],
        _sources_by_name(SOURCES_CONFIG), _Logger())

    assert names == ["geocodes_demo_datasets", "iris"]


def test_no_sources_resolves_to_nothing():
    assert _expand_tenant_sources(None, _sources_by_name(SOURCES_CONFIG), _Logger()) == []
    assert _expand_tenant_sources([], _sources_by_name(SOURCES_CONFIG), _Logger()) == []



def test_a_community_missing_from_the_tenant_file_skips_instead_of_failing():
    """community_sensor adds dynamic partitions and never removes them, so a
    community deleted from tenant.yaml leaves a partition that would otherwise
    fail on every run. On dev this was an IndexError on t[0].

    The stub resource raises on any attribute access, so this also pins that
    the skip happens before any resource is touched.
    """
    from dagster import build_asset_context

    from workflows.tasks.tasks.assets.tenants import loadstatsCommunity

    class _Unusable:
        """Raises on the attributes the asset would use. Dagster introspects
        private ones while building the context, so those fall through."""

        def __getattr__(self, name):
            if name.startswith("_"):
                raise AttributeError(name)
            raise AssertionError(
                f"a skipped partition must not touch resources (asked for {name})")

    tenants = {"tenant": [{"community": "geocodesall", "sources": ["all"]}]}

    context = build_asset_context(partition_key="dev",
                                  resources={"triplestore": _Unusable()})
    result = loadstatsCommunity(context, tenants, SOURCES_CONFIG, {})

    assert result.value == ""
    # dagster wraps metadata values
    assert result.metadata["skipped"].value == "not in the tenant file"
    assert result.metadata["community"].value == "dev"
