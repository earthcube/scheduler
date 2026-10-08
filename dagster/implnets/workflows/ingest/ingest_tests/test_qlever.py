from unittest.mock import patch, MagicMock

from workflows.ingest.ingest.assets.qlever import is_qlever_tenant, update_qlever_service


def test_is_qlever_tenant():
    assert is_qlever_tenant({"graph": {"type": "QLever"}})
    assert not is_qlever_tenant({"graph": {"main_namespace": "x"}})
    assert not is_qlever_tenant({})


def test_update_qlever_service():
    get = MagicMock()
    get.json.return_value = {"ID": "abc", "Version": {"Index": 7}, "Spec": {"TaskTemplate": {}}}
    with patch("workflows.ingest.ingest.assets.qlever.requests") as req:
        req.get.return_value = get
        assert update_qlever_service("http://p/api/endpoints/1/docker/", "k", "ql") == "abc"
        args, kwargs = req.post.call_args
        assert args[0] == "http://p/api/endpoints/1/docker/services/abc/update"
        assert kwargs["params"] == {"version": 7}
        assert kwargs["json"]["TaskTemplate"]["ForceUpdate"] == 1
