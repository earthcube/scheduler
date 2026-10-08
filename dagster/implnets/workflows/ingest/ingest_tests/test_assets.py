
import importlib.util
import io
import json
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


def _load_ingest_module():
    module_name = "workflows.ingest.ingest"
    module_path = Path(__file__).resolve().parent.parent / "ingest" / "__init__.py"

    for name in [
        module_name,
        "workflows",
        "workflows.ingest",
        "workflows.ingest.ingest.assets",
        "workflows.ingest.ingest.resources",
        "workflows.ingest.ingest.resources.graph",
        "workflows.ingest.ingest.resources.gleanerio",
        "workflows.ingest.ingest.resources.gleanerS3",
        "workflows.ingest.ingest.jobs",
        "workflows.ingest.ingest.jobs.summon_assets",
        "workflows.ingest.ingest.sensors",
        "workflows.ingest.ingest.sensors.gleaner_summon",
        "workflows.ingest.ingest.utils",
        "dagster",
        "dagster_aws",
        "dagster_aws.s3",
        "dagster_aws.s3.resources",
        "dagster_aws.s3.ops",
        "dagster_slack",
        "pydantic",
    ]:
        sys.modules.pop(name, None)

    class _Definitions:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _EnvVar:
        def __init__(self, name):
            self.name = name

        def get_value(self):
            return "test"

    dagster = _stub_module(
        "dagster",
        Definitions=_Definitions,
        load_assets_from_modules=lambda modules: ["assets", modules],
        load_asset_checks_from_modules=lambda modules: ["asset_checks", modules],
        EnvVar=_EnvVar,
        RunFailureSensorContext=type("RunFailureSensorContext", (), {}),
        AssetSelection=object(),
        define_asset_job=lambda *args, **kwargs: None,
    )
    dagster.__path__ = []
    dagster_aws = _stub_module("dagster_aws")
    dagster_aws.__path__ = []
    dagster_aws_s3 = _stub_module("dagster_aws.s3")
    dagster_aws_s3.__path__ = []
    _stub_module("dagster_aws.s3.resources", S3Resource=lambda **kwargs: ("S3Resource", kwargs))
    _stub_module("dagster_aws.s3.ops", S3Coordinate=object())
    _stub_module(
        "dagster_slack",
        SlackResource=lambda **kwargs: ("SlackResource", kwargs),
        make_slack_on_run_failure_sensor=lambda *args, **kwargs: "slack_sensor",
    )
    _stub_module("pydantic", Field=lambda *args, **kwargs: None)

    workflows = _stub_module("workflows")
    workflows.__path__ = []
    workflows_ingest = _stub_module("workflows.ingest")
    workflows_ingest.__path__ = []
    workflows_ingest_ingest = _stub_module("workflows.ingest.ingest")
    workflows_ingest_ingest.__path__ = []
    workflows_ingest_resources = _stub_module("workflows.ingest.ingest.resources")
    workflows_ingest_resources.__path__ = []
    workflows_ingest_jobs = _stub_module("workflows.ingest.ingest.jobs")
    workflows_ingest_jobs.__path__ = []
    workflows_ingest_sensors = _stub_module("workflows.ingest.ingest.sensors")
    workflows_ingest_sensors.__path__ = []

    assets = _stub_module("workflows.ingest.ingest.assets", gleanerio_run=object(), release_nabu_run=object())
    _stub_module(
        "workflows.ingest.ingest.resources.graph",
        BlazegraphResource=lambda **kwargs: ("BlazegraphResource", kwargs),
        GraphResource=type("GraphResource", (), {}),
    )
    _stub_module(
        "workflows.ingest.ingest.resources.gleanerio",
        GleanerioResource=lambda **kwargs: ("GleanerioResource", kwargs),
    )
    _stub_module(
        "workflows.ingest.ingest.resources.gleanerS3",
        gleanerS3Resource=lambda **kwargs: types.SimpleNamespace(**kwargs),
    )
    _stub_module(
        "workflows.ingest.ingest.jobs.summon_assets",
        summon_asset_job="summon_asset_job",
    )
    workflows_ingest_jobs.summon_asset_job = "summon_asset_job"
    workflows_ingest_jobs.sources_asset_job = "sources_asset_job"
    workflows_ingest_jobs.sources_partitions_def = "sources_partitions_def"
    workflows_ingest_jobs.tenant_asset_job = "tenant_asset_job"
    workflows_ingest_jobs.tenant_namespaces_job = "tenant_namespaces_job"
    workflows_ingest_jobs.release_asset_job = "release_asset_job"
    workflows_ingest_jobs.tenant_rebuild_namespaces_job = "tenant_rebuild_namespaces_job"
    workflows_ingest_sensors.release_file_sensor = "release_file_sensor"
    workflows_ingest_sensors.release_file_sensor_v2 = "release_file_sensor_v2"
    workflows_ingest_sensors.sources_sensor = "sources_sensor"
    workflows_ingest_sensors.tenant_names_sensor = "tenant_names_sensor"
    workflows_ingest_sensors.sources_s3_sensor = "sources_s3_sensor"
    workflows_ingest_sensors.tenant_s3_sensor = "tenant_s3_sensor"
    _stub_module(
        "workflows.ingest.ingest.sensors.gleaner_summon",
        sources_schedule="sources_schedule",
    )
    _stub_module(
        "workflows.ingest.ingest.utils",
        PythonMinioAddress=lambda *args, **kwargs: "minio-address",
    )

    spec = importlib.util.spec_from_file_location(
        module_name,
        module_path,
        submodule_search_locations=[str(module_path.parent)],
    )
    module = importlib.util.module_from_spec(spec)
    module.assets = assets
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


def test_non_zero_length_check_result_omits_size_metadata_when_unknown():
    module = _load_gleaner_summon_assets()

    result = module._non_zero_length_check_result(
        _FakeGleanerS3(None),
        "graphs/latest/example_release.nq",
    )

    assert result.passed is False
    assert result.metadata == {
        "bucket_name": "test-bucket",
        "object_name": "graphs/latest/example_release.nq",
    }


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
    module = _load_ingest_module()

    assert module.all_asset_checks[0] == "asset_checks"
    assert module.defs.asset_checks == module.all_asset_checks


# ── delete_stale_s3_files tests ──────────────────────────────────────────────

class _FakeS3Client:
    """Minimal boto3 S3 client stub that records delete_object calls."""

    def __init__(self, last_modified=None):
        self.deleted = []
        self._last_modified = last_modified

    def delete_object(self, Bucket, Key):
        self.deleted.append({"Bucket": Bucket, "Key": Key})

    def head_object(self, Bucket, Key):
        return {"LastModified": self._last_modified}


class _FakeMinioDatastore:
    """Minimal MinioDatastore stub for delete_stale_s3_files tests."""

    def __init__(self, files):
        # files: dict mapping object_name -> bytes/str content
        self._files = files
        self._put = {}

    def getFileFromStore(self, s3_object_info):
        key = s3_object_info["object_name"]
        if key not in self._files:
            raise KeyError(f"Not found: {key}")
        return self._files[key]

    def putReportFile(self, bucket, source, filename, data):
        self._put[(source, filename)] = data


def _make_gleaner_s3(fake_client):
    class _GleanerS3:
        GLEANERIO_MINIO_ADDRESS = "localhost"
        GLEANERIO_MINIO_PORT = "9000"
        GLEANERIO_MINIO_BUCKET = "test-bucket"

        class _S3Res:
            def __init__(self, client):
                self._client = client

            def get_client(self):
                return self._client

        def __init__(self, client):
            self.s3 = self._S3Res(client)

        def MinioOptions(self):
            return {}

    return _GleanerS3(fake_client)


def _make_ctx(gleaner_s3):
    """Return a minimal Dagster-like context for delete_stale_s3_files tests."""
    class _Ctx:
        def asset_partition_key_for_output(self):
            return "wifire"

        @property
        def resources(self):
            return types.SimpleNamespace(gleanerio=types.SimpleNamespace(gs3=gleaner_s3))

    return _Ctx()


def test_check_url_status_returns_status_code(monkeypatch):
    module = _load_gleaner_summon_assets()

    class _Resp:
        status_code = 404

    monkeypatch.setattr(module._requests, "head", lambda *a, **k: _Resp())
    assert module._check_url_status("http://example.com/gone") == 404


def test_check_url_status_returns_200(monkeypatch):
    module = _load_gleaner_summon_assets()

    class _Resp:
        status_code = 200

    monkeypatch.setattr(module._requests, "head", lambda *a, **k: _Resp())
    assert module._check_url_status("http://example.com/exists") == 200


def test_check_url_status_returns_none_on_exception(monkeypatch):
    module = _load_gleaner_summon_assets()

    def _raise(*a, **k):
        raise ConnectionError("no network")

    monkeypatch.setattr(module._requests, "head", _raise)
    assert module._check_url_status("http://example.com/error") is None


def test_delete_stale_s3_files_no_extras(monkeypatch):
    """When extra_in_summon is empty, no deletions should occur."""

    module = _load_gleaner_summon_assets()

    load_report = json.dumps({"extra_in_summon": [], "extra_in_summon_count": 0})
    fake_store = _FakeMinioDatastore(
        {"reports/wifire/latest/load_report_s3.json": load_report}
    )
    fake_client = _FakeS3Client()
    gleaner_s3 = _make_gleaner_s3(fake_client)

    original_cls = module.utils_s3.MinioDatastore
    module.utils_s3 = types.SimpleNamespace(MinioDatastore=lambda *a, **k: fake_store)

    try:
        module.delete_stale_s3_files(_make_ctx(gleaner_s3))
    finally:
        module.utils_s3 = types.SimpleNamespace(MinioDatastore=original_cls)

    assert fake_client.deleted == []
    report = json.loads(fake_store._put[("wifire", "deleted_s3.json")])
    assert report["deleted_count"] == 0
    assert report["deleted"] == []


def test_delete_stale_s3_files_deletes_on_http_error(monkeypatch):
    """URLs that return an HTTP error (other than 403) should be deleted from S3."""
    import csv as csv_module
    from datetime import datetime, timezone

    module = _load_gleaner_summon_assets()

    extra_url = "https://wifire-data.sdsc.edu/dataset/gone-dataset"
    load_report = json.dumps({
        "extra_in_summon_count": 1,
        "extra_in_summon": [extra_url],
    })
    csv_rows = [
        ["url", "object_name"],
        [extra_url, "summoned/wifire/abc123.jsonld"],
    ]
    csv_buf = io.StringIO()
    writer = csv_module.writer(csv_buf, quoting=csv_module.QUOTE_NONNUMERIC)
    writer.writerows(csv_rows)
    csv_content = csv_buf.getvalue()

    last_mod = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    fake_store = _FakeMinioDatastore({
        "reports/wifire/latest/load_report_s3.json": load_report,
        "reports/wifire/latest/bucketutil_urls.csv": csv_content,
    })
    fake_client = _FakeS3Client(last_modified=last_mod)
    gleaner_s3 = _make_gleaner_s3(fake_client)

    original_cls = module.utils_s3.MinioDatastore
    module.utils_s3 = types.SimpleNamespace(MinioDatastore=lambda *a, **k: fake_store)
    module._check_url_status = lambda url: 404

    try:
        module.delete_stale_s3_files(_make_ctx(gleaner_s3))
    finally:
        module.utils_s3 = types.SimpleNamespace(MinioDatastore=original_cls)

    assert len(fake_client.deleted) == 1
    assert fake_client.deleted[0]["Key"] == "summoned/wifire/abc123.jsonld"
    assert fake_client.deleted[0]["Bucket"] == "test-bucket"

    report = json.loads(fake_store._put[("wifire", "deleted_s3.json")])
    assert report["deleted_count"] == 1
    entry = report["deleted"][0]
    assert entry["url"] == extra_url
    assert entry["http_status"] == 404
    assert entry["created_at"] == last_mod.isoformat()


def test_delete_stale_s3_files_skips_403_urls(monkeypatch):
    """URLs that return 403 should be skipped (not deleted)."""
    import csv as csv_module

    module = _load_gleaner_summon_assets()

    extra_url = "https://wifire-data.sdsc.edu/dataset/auth-required"
    load_report = json.dumps({"extra_in_summon": [extra_url]})
    csv_buf = io.StringIO()
    writer = csv_module.writer(csv_buf, quoting=csv_module.QUOTE_NONNUMERIC)
    writer.writerows([["url", "object_name"], [extra_url, "summoned/wifire/auth.jsonld"]])
    csv_content = csv_buf.getvalue()

    fake_store = _FakeMinioDatastore({
        "reports/wifire/latest/load_report_s3.json": load_report,
        "reports/wifire/latest/bucketutil_urls.csv": csv_content,
    })
    fake_client = _FakeS3Client()
    gleaner_s3 = _make_gleaner_s3(fake_client)

    original_cls = module.utils_s3.MinioDatastore
    module.utils_s3 = types.SimpleNamespace(MinioDatastore=lambda *a, **k: fake_store)
    module._check_url_status = lambda url: 403

    try:
        module.delete_stale_s3_files(_make_ctx(gleaner_s3))
    finally:
        module.utils_s3 = types.SimpleNamespace(MinioDatastore=original_cls)

    assert fake_client.deleted == []
    report = json.loads(fake_store._put[("wifire", "deleted_s3.json")])
    assert report["deleted_count"] == 0
    skipped_entries = report["skipped"]
    assert len(skipped_entries) == 1
    assert skipped_entries[0]["url"] == extra_url
    assert skipped_entries[0]["http_status"] == 403


def test_delete_stale_s3_files_skips_on_network_error(monkeypatch):
    """URLs that cannot be reached (None status) should be skipped."""
    import csv as csv_module

    module = _load_gleaner_summon_assets()

    extra_url = "https://wifire-data.sdsc.edu/dataset/unreachable"
    load_report = json.dumps({"extra_in_summon": [extra_url]})
    csv_buf = io.StringIO()
    writer = csv_module.writer(csv_buf, quoting=csv_module.QUOTE_NONNUMERIC)
    writer.writerows([["url", "object_name"], [extra_url, "summoned/wifire/net.jsonld"]])
    csv_content = csv_buf.getvalue()

    fake_store = _FakeMinioDatastore({
        "reports/wifire/latest/load_report_s3.json": load_report,
        "reports/wifire/latest/bucketutil_urls.csv": csv_content,
    })
    fake_client = _FakeS3Client()
    gleaner_s3 = _make_gleaner_s3(fake_client)

    original_cls = module.utils_s3.MinioDatastore
    module.utils_s3 = types.SimpleNamespace(MinioDatastore=lambda *a, **k: fake_store)
    module._check_url_status = lambda url: None

    try:
        module.delete_stale_s3_files(_make_ctx(gleaner_s3))
    finally:
        module.utils_s3 = types.SimpleNamespace(MinioDatastore=original_cls)

    assert fake_client.deleted == []
    report = json.loads(fake_store._put[("wifire", "deleted_s3.json")])
    assert report["deleted_count"] == 0
    skipped_entries = report["skipped"]
    assert len(skipped_entries) == 1
    assert skipped_entries[0]["url"] == extra_url
    assert skipped_entries[0]["http_status"] is None
