"""Elasticsearch client, index mapping and search queries."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

load_dotenv()

INDEX = os.getenv("ES_INDEX", "hallpass-neurips-2025")

MAPPINGS: dict[str, Any] = {
    "properties": {
        "id": {"type": "keyword"},
        "title": {"type": "text", "fields": {"raw": {"type": "keyword"}}},
        "abstract": {"type": "text"},
        # Uses the cluster's default inference endpoint (ELSER on Elastic Cloud),
        # so no external embedding API is needed.
        "semantic_content": {"type": "semantic_text"},
        "authors": {"type": "text", "fields": {"raw": {"type": "keyword"}}},
        "institutions": {"type": "keyword"},
        "topic": {"type": "keyword"},
        "topic_area": {"type": "keyword"},
        "kind": {"type": "keyword"},
        "venue": {"type": "keyword"},
        "session": {"type": "keyword"},
        "start": {"type": "date"},
        "end": {"type": "date"},
        "room": {"type": "keyword"},
        "board": {"type": "integer"},
        "board_label": {"type": "keyword"},
        "row": {"type": "integer"},
        "slot": {"type": "integer"},
        "wall": {"type": "integer"},
        "side": {"type": "keyword"},
        "aisle": {"type": "integer"},
        "loc": {"type": "geo_point"},
        "openreview_url": {"type": "keyword", "index": False},
        "virtual_url": {"type": "keyword", "index": False},
    }
}

SOURCE_FIELDS = [f for f in MAPPINGS["properties"] if f != "semantic_content"]


def client() -> Elasticsearch:
    url, key = os.getenv("ES_URL"), os.getenv("ES_API_KEY")
    if not url or not key:
        raise RuntimeError("Set ES_URL and ES_API_KEY (see .env.example).")
    return Elasticsearch(url, api_key=key, request_timeout=120)


def create_index(es: Elasticsearch, recreate: bool = False) -> None:
    if es.indices.exists(index=INDEX):
        if not recreate:
            return
        es.indices.delete(index=INDEX)
    es.indices.create(index=INDEX, mappings=MAPPINGS)


def near_body(
    origin: dict[str, float], session: str, q: str | None = None, size: int = 20
) -> dict[str, Any]:
    """Posters in this session near a hall position.

    Without ``q``: nearest first. With ``q``: semantic relevance multiplied by a
    gaussian distance decay, so a highly relevant poster two aisles away can
    still beat a mediocre one next to you, but a great one at the far end won't.
    """
    filters = [{"term": {"session": session}}, {"exists": {"field": "loc"}}]
    if not q:
        return {
            "query": {"bool": {"filter": filters}},
            "sort": [{"_geo_distance": {"loc": origin, "order": "asc", "unit": "m"}}],
            "size": size,
            "_source": SOURCE_FIELDS,
        }
    return {
        "query": {
            "function_score": {
                "query": {
                    "bool": {
                        "must": {"semantic": {"field": "semantic_content", "query": q}},
                        "filter": filters,
                    }
                },
                "functions": [
                    {"gauss": {"loc": {"origin": origin, "offset": "6m", "scale": "20m", "decay": 0.5}}}
                ],
                "boost_mode": "multiply",
            }
        },
        "size": size,
        "_source": SOURCE_FIELDS,
    }


def search_body(q: str, session: str | None = None, size: int = 20) -> dict[str, Any]:
    """Hybrid search: BM25 keyword + semantic (ELSER), fused with reciprocal rank fusion."""
    filters = [{"term": {"session": session}}] if session else []
    keyword = {
        "standard": {
            "query": {
                "bool": {
                    "must": {
                        "multi_match": {
                            "query": q,
                            "fields": ["title^3", "abstract", "authors^2", "topic"],
                        }
                    },
                    "filter": filters,
                }
            }
        }
    }
    semantic = {
        "standard": {
            "query": {
                "bool": {
                    "must": {"semantic": {"field": "semantic_content", "query": q}},
                    "filter": filters,
                }
            }
        }
    }
    return {
        "retriever": {"rrf": {"retrievers": [keyword, semantic], "rank_window_size": 100}},
        "size": size,
        "_source": SOURCE_FIELDS,
    }
