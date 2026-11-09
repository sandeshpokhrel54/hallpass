"""HallPass HTTP API.

Run:  uv run uvicorn hallpass.api:app --reload
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from elasticsearch import ApiError, TransportError
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from opentelemetry import trace
from pydantic import BaseModel, Field

from hallpass import es as hes
from hallpass import layout, telemetry
from hallpass.venues import DEFAULT as DEFAULT_VENUE
from hallpass.venues import VENUES, Venue

log = logging.getLogger("hallpass")
app = FastAPI(title="HallPass")
telemetry.setup(app)


@app.exception_handler(ApiError)
@app.exception_handler(TransportError)
async def es_unavailable(request: Request, exc: Exception) -> JSONResponse:
    """Elasticsearch failures become a clear 502 (and a logged, traced error), not a bare 500."""
    log.error("elasticsearch error on %s: %s", request.url.path, exc)
    trace.get_current_span().record_exception(exc)
    return JSONResponse({"detail": "search backend unavailable, try again"}, status_code=502)


def _observe(kind: str, n: int, started: float, **attrs) -> None:
    span = trace.get_current_span()
    span.set_attribute("hallpass.kind", kind)
    span.set_attribute("hallpass.results", n)
    for k, v in attrs.items():
        if v is not None:
            span.set_attribute(f"hallpass.{k}", v)
    telemetry.searches.add(1, {"kind": kind, "empty": n == 0})
    telemetry.results_returned.record(n, {"kind": kind})
    log.info("%s returned %d results in %.0f ms", kind, n, (time.perf_counter() - started) * 1000,
             extra={"hallpass.kind": kind, "hallpass.results": n, **{f"hallpass.{k}": v for k, v in attrs.items() if v is not None}})
_es = None


def es():
    global _es
    if _es is None:
        _es = hes.client()
    return _es


VERSION = os.getenv("APP_VERSION", "dev")


INDEX_HTML = Path(__file__).parent / "static" / "index.html"
DASH0_SDK = "https://cdn.jsdelivr.net/npm/@dash0/sdk-web@0.28.3/dist/dash0.iife.js"


def _rum_snippet() -> str:
    """Dash0 browser monitoring, only when a dedicated ingest-only RUM token is set.
    The token is public by design (it ships to browsers) but stays out of git.
    Same-origin API calls carry trace context, so browser and backend spans join up."""
    token = os.getenv("DASH0_RUM_TOKEN")
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not (token and endpoint):
        return ""
    cfg = json.dumps({
        "serviceName": "hallpass-web",
        "serviceVersion": VERSION,
        "environment": os.getenv("DEPLOY_ENV", "local"),
        "endpoint": {"url": endpoint.rstrip("/"), "authToken": token},
    }).replace("</", "<\\/")
    return (
        "<script>(function(d,a,s,h,z){d[a]||((z=d[a]=function(){h.push(arguments)}),"
        "(z._t=new Date()),(z._v=1),(h=z._q=[]))})(window,'dash0');"
        f"dash0('init',{cfg});</script>\n"
        f'<script defer crossorigin="anonymous" src="{DASH0_SDK}"></script>'
    )


@app.get("/", response_model=None)
def root(request: Request) -> dict | HTMLResponse:
    """Browsers get the hall map; curl and deploy checks get the JSON version."""
    if "text/html" in request.headers.get("accept", ""):
        return HTMLResponse(INDEX_HTML.read_text().replace("<!--DASH0_RUM-->", _rum_snippet()))
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
    rerank: bool = Query(False, description="re-order the top 30 with Jina reranker v3"),
) -> list[dict]:
    started = time.perf_counter()
    resp = es().search(index=hes.INDEX, body=hes.search_body(q, session, size, rerank))
    out = [{"score": h["_score"], **h["_source"]} for h in resp["hits"]["hits"]]
    _observe("search", len(out), started, session=session, query_chars=len(q), rerank=rerank)
    return out


def _venue(venue_id: str) -> Venue:
    if venue_id not in VENUES:
        raise HTTPException(422, f"unknown venue {venue_id!r}; see /venues")
    return VENUES[venue_id]


@app.get("/venues")
def venues() -> list[dict]:
    return [v.public() for v in VENUES.values()]


def _spot_or_422(board: int, venue: Venue = VENUES[DEFAULT_VENUE]) -> layout.Spot:
    where = venue.spot(board)
    if where is None:
        raise HTTPException(422, f"board {board} has no hall position (expected row*100+slot)")
    return where


def _with_distance(hit: dict, here: layout.Spot, venue: Venue = VENUES[DEFAULT_VENUE]) -> dict:
    src = hit["_source"]
    where = venue.spot(src["board"]) if src.get("board") else None
    return {
        "_id": hit.get("_id"),
        "score": hit.get("_score"),
        "walk_m": round(layout.walk_m(here, where), 1) if where else None,
        **src,
    }


def _walk_decay(walk: float, offset: float = 6.0, scale: float = 20.0, decay: float = 0.5) -> float:
    """Gaussian decay on walking metres (same shape as Elasticsearch's gauss)."""
    d = max(0.0, walk - offset)
    return decay ** ((d / scale) ** 2)


def rank_near(
    hits: list[dict], here: layout.Spot, with_query: bool, size: int,
    venue: Venue = VENUES[DEFAULT_VENUE],
) -> list[dict]:
    """Re-rank candidates by real walking distance: nearest first, or
    relevance x walking-distance decay when there's a query."""
    rows = [_with_distance(h, here, venue) for h in hits]
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
    venue: str = Query(DEFAULT_VENUE),
) -> list[dict]:
    """What's worth seeing within a short walk: nearest posters, or relevant-and-near with q."""
    started = time.perf_counter()
    v = _venue(venue)
    here = _spot_or_422(board, v)
    # Pre-filter in the index's single-hall coordinates (including the other
    # floor's lift area when it's within walking budget); rank with venue geometry.
    # Step 1: every candidate in the circle, board numbers only (~50 KB instead of ~1 MB
    # of abstracts; Elasticsearch itself answers in ~60 ms, the rest was transfer).
    body = hes.near_candidates_body(v.search_areas(here, hes.NEAR_RADIUS_M), session, q)
    resp = es().search(index=hes.INDEX, body=body, filter_path=hes.NEAR_FILTER_PATH)
    hits = resp.get("hits", {}).get("hits", [])
    ranked = rank_near(hits, here, bool(q), size, v)
    # Step 2: full details for the few we return.
    ids = [r["_id"] for r in ranked if r.get("_id")]
    docs = {}
    if ids:
        got = es().mget(index=hes.INDEX, ids=ids, source=hes.SOURCE_FIELDS)
        docs = {d["_id"]: d["_source"] for d in got["docs"] if d.get("found")}
    out = [{**docs.get(r.pop("_id"), {}), **r} for r in ranked]
    _observe("near", len(out), started, session=session, board=board, candidates=len(hits), with_query=bool(q))
    return out


class RouteRequest(BaseModel):
    boards: list[int] = Field(..., min_length=1, max_length=60)
    start: int | None = Field(None, description="board you're starting from")
    venue: str = DEFAULT_VENUE


@app.post("/route")
def route(req: RouteRequest) -> dict:
    """Order boards into a short walk through the hall (no Elasticsearch needed)."""
    started = time.perf_counter()
    v = _venue(req.venue)
    stops = [_spot_or_422(b, v) for b in req.boards]
    start = _spot_or_422(req.start, v) if req.start is not None else None
    with telemetry.tracer.start_as_current_span("plan_route") as span:
        span.set_attribute("hallpass.stops", len(stops))
        order = layout.plan_route(stops, start)
    path = [start, *order] if start else order
    legs = [layout.waypoints(a, b) for a, b in zip(path, path[1:])]
    total = round(layout.route_length(path))
    telemetry.route_length.record(total)
    floor_changes = sum(1 for a, b in zip(path, path[1:]) if a.floor != b.floor)
    _observe("route", len(order), started, total_m=total, venue=v.id, floor_changes=floor_changes)
    return {"order": [s.board for s in order], "total_m": total, "legs": legs,
            "floor_changes": floor_changes}


@app.get("/hall")
def hall(session: str, venue: str = Query(DEFAULT_VENUE)) -> list[dict]:
    """Every placed poster in a session, for drawing the map."""
    v = _venue(venue)
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
        src["floor"], src["local_row"] = v.local_row(src["board"])
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
