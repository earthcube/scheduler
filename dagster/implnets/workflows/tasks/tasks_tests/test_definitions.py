"""The tasks Definitions load, with the new assets and checks registered.

load_assets_from_modules / load_asset_checks_from_modules scan the attributes of
the assets package module rather than recursing into its submodules, so an asset
or a check that is not re-exported from assets/__init__.py is silently absent.
That is invisible until a deployment, which is what this catches.
"""

from workflows.tasks.tasks import defs

EXPECTED_ASSETS = {
    "eco_task/loadstatsCommunity",
    "eco_task/loadstatsHistory",
    "eco_task/sos_types",
    "eco_task/source_list",
    "eco_task/source_release_counts",
    "eco_task/task_sources_config",
    "eco_task/task_tenant_names",
    "eco_task/task_tenant_sources",
}

EXPECTED_CHECKS = {
    "eco_task/loadstatsHistory:non_zero_length",
    "eco_task/loadstatsHistory:non_zero_rows",
}


def _graph():
    return defs.resolve_asset_graph()


def test_every_asset_is_registered():
    keys = {k.to_user_string() for k in _graph().get_all_asset_keys()}

    assert keys == EXPECTED_ASSETS


def test_both_loadstats_history_checks_are_registered():
    checks = {c.to_user_string() for c in _graph().asset_check_keys}

    assert checks == EXPECTED_CHECKS


def test_loadstatsCommunity_depends_on_the_config_and_the_counts():
    """The counts asset exists so the releases are parsed once per run rather
    than once per community; that only holds if the dependency is real."""
    graph = _graph()
    key = next(k for k in graph.get_all_asset_keys()
               if k.to_user_string() == "eco_task/loadstatsCommunity")
    parents = {k.to_user_string() for k in graph.get(key).parent_keys}

    assert "eco_task/task_tenant_sources" in parents
    assert "eco_task/task_sources_config" in parents
    assert "eco_task/source_release_counts" in parents
