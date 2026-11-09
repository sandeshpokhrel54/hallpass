"""HallPass HTTP API.

Run:  uv run uvicorn hallpass.api:app --reload
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from hallpass import es as hes
from hallpass import layout

app = FastAPI(title="HallPass")
_es = None


def es():
    global _es
    if _es is None:
        _es = hes.client()
    return _es


VERSION = os.getenv("APP_VERSION", "dev")


INDEX_HTML = Path(__file__).parent / "static" / "index.html"


@app.get("/", response_model=None)
def root(request: Request) -> dict | HTMLResponse:
    """Browsers get the hall map; curl and deploy checks get the JSON version."""
    if "text/html" in request.headers.get("accept", ""):
        return HTMLResponse(INDEX_HTML.read_text())
    return {"app": "hallpass", "version": VERSION}


@app.get("/healthz")
def healthz() -> dict:
    """Liveness: the process is up."""
    return {"ok": True}


@app.get("/readyz")
def readyz() -> dict:
    """Readiness: configured to reach Elasticsearch. Deliberately no network call,
    so a brief Elasticsearch blip doesn't pull every pod out of the Service."""
    if not (os.getenv("ES_URL") and os.getenv("ES_API_KEY")):
        raise HTTPException(503, "ES_URL / ES_API_KEY not configured")
    return {"ok": True}


@app.get("/sessions")
def sessions() -> list[dict]:
    """Poster sessions with their time and poster count."""
    resp = es().search(
        index=hes.INDEX,
        size=0,
        aggs={
            "s": {
                "terms": {"field": "session", "size": 50},
                "aggs": {"start": {"min": {"field": "start"}}},
            }
        },
    )
    out = [
        {"session": b["key"], "posters": b["doc_count"], "start": b["start"]["value_as_string"]}
        for b in resp["aggregations"]["s"]["buckets"]
    ]
    return sorted(out, key=lambda s: (s["start"], s["session"]))


@app.get("/search")
def search(
    q: str = Query(..., min_length=2, description="keywords, a sentence, or your own abstract"),
    session: str | None = None,
    size: int = Query(20, ge=1, le=100),
) -> list[dict]:
    resp = es().search(index=hes.INDEX, body=hes.search_body(q, session, size))
    return [{"score": h["_score"], **h["_source"]} for h in resp["hits"]["hits"]]


def _spot_or_422(board: int) -> layout.Spot:
    where = layout.spot_for_board(board)
    if where is None:
        raise HTTPException(422, f"board {board} has no hall position (expected row*100+slot)")
    return where


def _with_distance(hit: dict, here: layout.Spot) -> dict:
    src = hit["_source"]
    where = layout.spot_for_board(src["board"]) if src.get("board") else None
    return {
        "score": hit.get("_score"),
        "walk_m": round(layout.walk_m(here, where), 1) if where else None,
        **src,
    }


def _walk_decay(walk: float, offset: float = 6.0, scale: float = 20.0, decay: float = 0.5) -> float:
    """Gaussian decay on walking metres (same shape as Elasticsearch's gauss)."""
    d = max(0.0, walk - offset)
    return decay ** ((d / scale) ** 2)


def rank_near(hits: list[dict], here: layout.Spot, with_query: bool, size: int) -> list[dict]:
    """Re-rank candidates by real walking distance: nearest first, or
    relevance x walking-distance decay when there's a query."""
    rows = [_with_distance(h, here) for h in hits]
    rows = [r for r in rows if r["walk_m"] is not None and r["walk_m"] <= hes.NEAR_RADIUS_M]
    if with_query:
        for r in rows:
            r["score"] = (r["score"] or 0.0) * _walk_decay(r["walk_m"])
        rows.sort(key=lambda r: -r["score"])
    else:
        rows.sort(key=lambda r: r["walk_m"])
    return rows[:size]


@app.get("/near")
def near(
    board: int = Query(..., description="the board you're standing at, e.g. 3407"),
    session: str = Query(...),
    q: str | None = Query(None, min_length=2, description="optional: what you're interested in"),
    size: int = Query(10, ge=1, le=50),
) -> list[dict]:
    """What's worth seeing within a short walk: nearest posters, or relevant-and-near with q."""
    here = _spot_or_422(board)
    body = hes.near_candidates_body(layout.geo_point(here), session, q)
    resp = es().search(index=hes.INDEX, body=body)
    return rank_near(resp["hits"]["hits"], here, bool(q), size)


class RouteRequest(BaseModel):
    boards: list[int] = Field(..., min_length=1, max_length=60)
    start: int | None = Field(None, description="board you're starting from")


@app.post("/route")
def route(req: RouteRequest) -> dict:
    """Order boards into a short walk through the hall (no Elasticsearch needed)."""
    stops = [_spot_or_422(b) for b in req.boards]
    start = _spot_or_422(req.start) if req.start is not None else None
    order = layout.plan_route(stops, start)
    path = [start, *order] if start else order
    legs = [layout.waypoints(a, b) for a, b in zip(path, path[1:])]
    return {
        "order": [s.board for s in order],
        "total_m": round(layout.route_length(path)),
        "legs": legs,
    }


@app.get("/hall")
def hall(session: str) -> list[dict]:
    """Every placed poster in a session, for drawing the map."""
    resp = es().search(
        index=hes.INDEX,
        query={"bool": {"filter": [{"term": {"session": session}}, {"exists": {"field": "row"}}]}},
        size=1500,
        _source=["id", "title", "board", "board_label", "row", "slot", "topic_area", "topic", "authors"],
    )
    out = []
    for h in resp["hits"]["hits"]:
        src = h["_source"]
        if layout.spot_for_board(src["board"]) is None:
            continue
        src["authors"] = (src.get("authors") or [])[:3]
        out.append(src)
    return out


@app.get("/zones")
def zones(session: str) -> list[dict]:
    """Label each wall with the topics that are *unusually* common there compared with
    the whole hall (significant_terms), so the map labels itself."""
    resp = es().search(
        index=hes.INDEX,
        size=0,
        query={"bool": {"filter": [{"term": {"session": session}}, {"exists": {"field": "wall"}}]}},
        aggs={
            "walls": {
                "terms": {"field": "wall", "size": 60, "order": {"_key": "asc"}},
                "aggs": {
                    "area": {"terms": {"field": "topic_area", "size": 1}},
                    "standout": {"significant_terms": {"field": "topic", "size": 3, "min_doc_count": 3}},
                },
            }
        },
    )
    out = []
    for b in resp["aggregations"]["walls"]["buckets"]:
        area = b["area"]["buckets"]
        out.append({
            "wall": b["key"],
            "posters": b["doc_count"],
            "area": area[0]["key"] if area else None,
            "labels": [
                lbl for t in b["standout"]["buckets"]
                if (lbl := t["key"].split("->")[-1]) not in ("Everything Else", "Other")
            ],
        })
    return out
