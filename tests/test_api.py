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


def test_elasticsearch_failure_is_a_502(monkeypatch):
    from elasticsearch import ConnectionError as ESConnectionError

    import hallpass.api as api

    class Down:
        def search(self, **kw):
            raise ESConnectionError("connection refused")

    monkeypatch.setattr(api, "_es", Down())
    r = client.get("/search", params={"q": "diffusion"})
    assert r.status_code == 502


def test_search_body_three_way_and_optional_rerank():
    from hallpass.es import search_body
    plain = search_body("diffusion", "S1", 10)
    rrf = plain["retriever"]["rrf"]["retrievers"]
    assert len(rrf) == 3
    fields = [r["standard"]["query"]["bool"]["must"].get("semantic", {}).get("field") for r in rrf]
    assert fields[1:] == ["semantic_content", "semantic_dense"]
    rr = search_body("diffusion", "S1", 10, rerank=True)["retriever"]["text_similarity_reranker"]
    assert rr["field"] == "title" and rr["retriever"]["rrf"]


def test_route_across_floors_reports_floor_changes():
    r = client.post("/route", json={"boards": [305, 3305], "venue": "demo-two-floors"})
    assert r.status_code == 200
    body = r.json()
    assert body["floor_changes"] == 1
    assert {p[2] for leg in body["legs"] for p in leg} == {0, 1}


def test_unknown_venue_is_422():
    assert client.post("/route", json={"boards": [305], "venue": "nope"}).status_code == 422


def test_venues_lists_demo():
    ids = [v["id"] for v in client.get("/venues").json()]
    assert "neurips-2025" in ids and "demo-two-floors" in ids


def test_rum_snippet_only_with_token(monkeypatch):
    monkeypatch.delenv("DASH0_RUM_TOKEN", raising=False)
    html = client.get("/", headers={"accept": "text/html"}).text
    assert "dash0" not in html
    monkeypatch.setenv("DASH0_RUM_TOKEN", "tok</script><x>")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://ingress.example")
    html = client.get("/", headers={"accept": "text/html"}).text
    assert "dash0('init'" in html and "@dash0/sdk-web@0.28.3" in html
    assert "tok</script>" not in html  # escaped, can't break out of the script tag


def test_near_two_floor_venue_searches_indexed_coordinates(monkeypatch):
    """Level-2 board 3305 must be searched around its indexed (single-hall)
    position, and its Level-2 neighbours must come back ranked."""
    import hallpass.api as api
    from hallpass import layout
    from hallpass.schema import to_doc  # noqa: F401  (indexed loc comes from layout.spot)

    seen = {}

    class FakeES:
        def search(self, index, body, **kw):
            seen["body"] = body
            hits = [{"_id": str(b), "_score": 1.0, "_source": {"board": b}} for b in (3306, 3310, 505)]
            return {"hits": {"hits": hits}}

        def mget(self, index, ids, source):
            return {"docs": [{"_id": i, "found": True, "_source": {"board": int(i), "title": f"T{i}"}} for i in ids]}

    monkeypatch.setattr(api, "_es", FakeES())
    r = client.get("/near", params={"board": 3305, "session": "S", "venue": "demo-two-floors"})
    assert r.status_code == 200
    should = seen["body"]["query"]["bool"]["filter"][1]["bool"]["should"]
    centre = should[0]["geo_distance"]["loc"]
    assert centre == layout.geo_point(layout.spot_for_board(3305))
    boards = [x["board"] for x in r.json()]
    assert boards[:2] == [3306, 3310]  # same floor, 3 m and 15 m
    assert 505 not in boards  # Level 1, via the lift: too far


def test_near_by_the_lift_also_searches_the_other_floor():
    from hallpass import layout
    from hallpass.venues import VENUES
    v = VENUES["demo-two-floors"]
    by_lift = v.spot(2909)  # Level 2, front aisle, next to the lift
    areas = v.search_areas(by_lift, 50)
    assert len(areas) == 2
    assert areas[1][0] == v.indexed_geo(layout.lift(0))
    far = v.spot(5501)
    assert len(v.search_areas(far, 50)) == 1


def test_near_fetches_only_boards_then_details_for_top(monkeypatch):
    import hallpass.api as api
    from hallpass import es as hes
    calls = {}

    class FakeES:
        def search(self, index, body, **kw):
            calls["source"], calls["size"], calls["filter_path"] = body["_source"], body["size"], kw.get("filter_path")
            # 600 candidates: more than the old 400 cap
            hits = [{"_id": f"d{b}", "_score": 1.0, "_source": {"board": b}}
                    for b in [r * 100 + sl for r in range(1, 31) for sl in range(20)]]
            return {"hits": {"hits": hits}}

        def mget(self, index, ids, source):
            calls["mget_ids"] = ids
            return {"docs": [{"_id": i, "found": True, "_source": {"board": int(i[1:]), "title": "t", "abstract": "a"}} for i in ids]}

    monkeypatch.setattr(api, "_es", FakeES())
    r = client.get("/near", params={"board": 2915, "session": "S", "size": 5})
    assert r.status_code == 200
    assert calls["source"] == ["board"] and calls["size"] >= 950 and "_source.board" in calls["filter_path"]
    assert len(calls["mget_ids"]) == 5
    rows = r.json()
    # The board you're at (and the one facing it across the aisle) are found despite 600 candidates.
    zero = {x["board"] for x in rows if x["walk_m"] == 0}
    assert zero == {2915, 2815}
    assert all("title" in x and "_id" not in x for x in rows)
