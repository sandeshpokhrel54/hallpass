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


def test_route_orders_boards_and_reports_distance():
    r = client.post("/route", json={"boards": [4902, 105, 110], "start": 101})
    assert r.status_code == 200
    body = r.json()
    assert body["order"][:2] == [105, 110]
    assert body["total_m"] > 0
    assert len(body["legs"]) == 3


def test_route_rejects_unplaceable_board():
    assert client.post("/route", json={"boards": [12]}).status_code == 422


def test_near_rejects_unplaceable_board():
    assert client.get("/near", params={"board": 12, "session": "x"}).status_code == 422
