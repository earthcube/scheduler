
import importlib.util
import sys
import types
from pathlib import Path


def _stub_module(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _load_gleaner_summon_assets():
    module_name = "workflows.ingest.ingest.assets.gleaner_summon_assets"
    module_path = (
        Path(__file__).resolve().parent.parent / "ingest" / "assets" / "gleaner_summon_assets.py"
    )

    for name in [
        module_name,
        "workflows",
        "workflows.ingest",
        "workflows.ingest.ingest",
        "workflows.ingest.ingest.assets",
        "workflows.ingest.ingest.assets.gleaner_sources",
        "workflows.ingest.ingest.utils",
        "dagster",
        "pandas",
        "pyoxigraph",
        "ec",
        "ec.datastore",
        "ec.datastore.s3",
        "ec.sitemap",
        "ec.gleanerio",
        "ec.gleanerio.gleaner",
        "ec.reporting",
        "ec.reporting.report",
        "ec.graph",
        "ec.graph.release_graph",
        "ec.graph.manageGraph",
        "ec.summarize",
    ]:
        sys.modules.pop(name, None)

    class _Logger:
        def info(self, *_args, **_kwargs):
            return None

        def error(self, *_args, **_kwargs):
            return None

    class _AssetCheckResult:
        def __init__(self, passed, metadata=None):
            self.passed = passed
            self.metadata = metadata or {}

    class _Output:
        def __class_getitem__(cls, _item):
            return cls

        def __init__(self, value=None, metadata=None):
            self.value = value
            self.metadata = metadata or {}

    def _decorator(*_args, **_kwargs):
        def _wrap(fn):
            return fn

        return _wrap

    _stub_module(
        "dagster",
        asset=_decorator,
        asset_check=_decorator,
        op=_decorator,
        Config=type("Config", (), {}),
        Output=_Output,
        AssetKey=lambda *args, **kwargs: ("AssetKey", args, kwargs),
        define_asset_job=lambda *args, **kwargs: None,
        AssetSelection=object(),
        get_dagster_logger=lambda: _Logger(),
        BackfillPolicy=type("BackfillPolicy", (), {}),
        AssetCheckExecutionContext=object,
        AssetCheckResult=_AssetCheckResult,
    )
    _stub_module("pandas")
    _stub_module(
        "pyoxigraph",
        RdfFormat=type("RdfFormat", (), {"N_QUADS": "nq", "N_TRIPLES": "nt"}),
        Store=type("Store", (), {}),
        serialize=lambda *_args, **_kwargs: b"",
    )

    ec = _stub_module("ec")
    ec.__path__ = []
    ec_datastore = _stub_module("ec.datastore")
    ec_datastore.__path__ = []
    _stub_module("ec.datastore.s3", MinioDatastore=type("MinioDatastore", (), {}))
    _stub_module("ec.sitemap", Sitemap=type("Sitemap", (), {}))
    ec_gleanerio = _stub_module("ec.gleanerio")
    ec_gleanerio.__path__ = []
    _stub_module(
        "ec.gleanerio.gleaner",
        getGleaner=lambda *_args, **_kwargs: None,
        getSitemapSourcesFromGleaner=lambda *_args, **_kwargs: None,
        endpointUpdateNamespace=lambda *_args, **_kwargs: None,
    )
    ec_reporting = _stub_module("ec.reporting")
    ec_reporting.__path__ = []
    _stub_module(
        "ec.reporting.report",
        missingReport=lambda *_args, **_kwargs: None,
        generateIdentifierRepo=lambda *_args, **_kwargs: None,
        generateGraphReportsRelease=lambda *_args, **_kwargs: None,
        generateGraphReportsRepo=lambda *_args, **_kwargs: None,
        reportTypes=None,
    )
    ec_graph = _stub_module("ec.graph")
    ec_graph.__path__ = []
    _stub_module("ec.graph.release_graph", ReleaseGraph=type("ReleaseGraph", (), {}))
    _stub_module("ec.graph.manageGraph", ManageBlazegraph=type("ManageBlazegraph", (), {}))
    _stub_module(
        "ec.summarize",
        summaryDF2ttl=lambda *_args, **_kwargs: (None, None),
        get_summary4graph=lambda *_args, **_kwargs: None,
        get_summary4repoSubset=lambda *_args, **_kwargs: None,
    )

    workflows = _stub_module("workflows")
    workflows.__path__ = []
    workflows_ingest = _stub_module("workflows.ingest")
    workflows_ingest.__path__ = []
    workflows_ingest_ingest = _stub_module("workflows.ingest.ingest")
    workflows_ingest_ingest.__path__ = []
    workflows_ingest_assets = _stub_module("workflows.ingest.ingest.assets")
    workflows_ingest_assets.__path__ = []

    _stub_module(
        "workflows.ingest.ingest.assets.gleaner_sources",
        sources_partitions_def=object(),
    )
    _stub_module(
        "workflows.ingest.ingest.utils",
        PythonMinioAddress=lambda *args, **kwargs: "minio-address",
    )

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class _FakeGleanerS3:
    GLEANERIO_MINIO_BUCKET = "test-bucket"

    def __init__(self, size):
        outer = self

        class _Client:
            def head_object(self, Bucket, Key):
                return {"ContentLength": outer.size}

        class _S3:
            def get_client(self):
                return _Client()

        self.size = size
        self.s3 = _S3()


def test_non_zero_length_check_result_passes_for_non_empty_object():
    module = _load_gleaner_summon_assets()

    result = module._non_zero_length_check_result(
        _FakeGleanerS3(17),
        "graphs/latest/example_release.nq",
    )

    assert result.passed is True
    assert result.metadata == {
        "bucket_name": "test-bucket",
        "object_name": "graphs/latest/example_release.nq",
        "size_bytes": 17,
    }


def test_non_zero_length_check_result_fails_for_zero_byte_object():
    module = _load_gleaner_summon_assets()

    result = module._non_zero_length_check_result(
        _FakeGleanerS3(0),
        "graphs/summary/example_release_summary.ttl",
    )

    assert result.passed is False
    assert result.metadata["size_bytes"] == 0


def test_release_and_summary_checks_target_the_expected_objects():
    module = _load_gleaner_summon_assets()
    context = types.SimpleNamespace(
        partition_key="example",
        resources=types.SimpleNamespace(
            gleanerio=types.SimpleNamespace(gs3=_FakeGleanerS3(9))
        ),
    )

    release_result = module.release_nabu_run_non_zero_length(context)
    summary_result = module.release_summary_non_zero_length(context)

    assert release_result.metadata["object_name"] == "graphs/latest/example_release.nq"
    assert summary_result.metadata["object_name"] == "graphs/summary/example_release_summary.ttl"


def test_ingest_definitions_load_asset_checks():
    init_text = (Path(__file__).resolve().parent.parent / "ingest" / "__init__.py").read_text()

    assert "load_asset_checks_from_modules" in init_text
    assert "asset_checks=all_asset_checks" in init_text
