import pytest
from fastapi.testclient import TestClient

from hallpass.api import app

client = TestClient(app)


@pytest.mark.parametrize("size", [-1, 0, 101])
def test_search_rejects_out_of_range_size(size):
    # Validation happens before any Elasticsearch call, so no cluster is needed.
    assert client.get("/search", params={"q": "diffusion", "size": size}).status_code == 422


def test_healthz():
    assert client.get("/healthz").json() == {"ok": True}


def test_root_reports_version():
    assert client.get("/").json()["app"] == "hallpass"


def test_readyz_requires_es_config(monkeypatch):
    monkeypatch.delenv("ES_URL", raising=False)
    assert client.get("/readyz").status_code == 503
    monkeypatch.setenv("ES_URL", "https://es.example")
    monkeypatch.setenv("ES_API_KEY", "x")
    assert client.get("/readyz").status_code == 200
