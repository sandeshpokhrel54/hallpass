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


def test_root_serves_map_to_browsers():
    r = client.get("/", headers={"accept": "text/html,application/xhtml+xml"})
    assert r.status_code == 200
    assert "<title>HallPass" in r.text


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


def _hit(board, score=1.0):
    return {"_score": score, "_source": {"board": board, "title": str(board)}}


def test_near_ranks_by_walking_not_straight_line():
    from hallpass.api import rank_near
    from hallpass.layout import spot_for_board
    here = spot_for_board(310)
    # #410 is 5 m away in a straight line but behind the wall (59 m walk);
    # #318 is 24 m down the same aisle.
    rows = rank_near([_hit(410), _hit(318)], here, with_query=False, size=10)
    assert [r["board"] for r in rows] == [318]  # 410 is beyond the walking radius
    assert rows[0]["walk_m"] == 24


def test_near_with_query_balances_relevance_and_walk():
    from hallpass.api import rank_near
    from hallpass.layout import spot_for_board
    here = spot_for_board(1205)
    rows = rank_near([_hit(1206, 0.5), _hit(1215, 1.0), _hit(1219, 0.9)], here, with_query=True, size=10)
    assert rows[0]["board"] == 1206  # 3 m and decent beats 30 m and great
    assert all(r["score"] <= 1.0 for r in rows)
