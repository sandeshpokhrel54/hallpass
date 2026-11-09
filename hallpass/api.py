"""HallPass HTTP API.

Run:  uv run uvicorn hallpass.api:app --reload
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Query

from hallpass import es as hes

app = FastAPI(title="HallPass")
_es = None


def es():
    global _es
    if _es is None:
        _es = hes.client()
    return _es


VERSION = os.getenv("APP_VERSION", "dev")


@app.get("/")
def root() -> dict:
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
