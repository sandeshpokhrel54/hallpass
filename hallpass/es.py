"""Elasticsearch client, index mapping and search queries."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

load_dotenv()

INDEX = os.getenv("ES_INDEX", "hallpass-neurips-2025-v2")

DENSE_MODEL = ".jina-embeddings-v5-text-small"
RERANK_MODEL = ".jina-reranker-v3"

MAPPINGS: dict[str, Any] = {
    "properties": {
        "id": {"type": "keyword"},
        "title": {"type": "text", "fields": {"raw": {"type": "keyword"}}},
        "abstract": {"type": "text"},
        # Uses the cluster's default inference endpoint (ELSER on Elastic Cloud),
        # so no external embedding API is needed.
        "semantic_content": {"type": "semantic_text"},
        # Same text, embedded densely by Jina v5 (Elastic Inference Service).
        "semantic_dense": {"type": "semantic_text", "inference_id": DENSE_MODEL},
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

SOURCE_FIELDS = [f for f in MAPPINGS["properties"] if not f.startswith("semantic_")]


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


# Walking distance is never shorter than straight-line distance, so every poster
# within NEAR_RADIUS_M on foot is inside this straight-line radius. Elasticsearch
# finds those candidates; the API then re-ranks them by real walking distance
# (around wall ends), which a straight-line geo query can't express.
NEAR_RADIUS_M = 50
NEAR_CANDIDATES = 400


def near_candidates_body(
    origin: dict[str, float], session: str, q: str | None = None
) -> dict[str, Any]:
    filters = [
        {"term": {"session": session}},
        {"geo_distance": {"distance": f"{NEAR_RADIUS_M}m", "loc": origin}},
    ]
    query: dict[str, Any] = {"bool": {"filter": filters}}
    if q:
        query["bool"]["must"] = {"semantic": {"field": "semantic_content", "query": q}}
    return {"query": query, "size": NEAR_CANDIDATES, "_source": SOURCE_FIELDS}


RERANK_WINDOW = 30


def _filtered(query: dict[str, Any], filters: list[dict]) -> dict[str, Any]:
    return {"standard": {"query": {"bool": {"must": query, "filter": filters}}}}


def search_body(
    q: str, session: str | None = None, size: int = 20, rerank: bool = False
) -> dict[str, Any]:
    """Three-way hybrid search, then a cross-encoder rerank, all in one Elasticsearch query.

    Stage 1 (recall): three retrievers, fused with reciprocal rank fusion:
      - BM25 keyword match on title / abstract / authors / topic
      - ELSER learned-sparse semantic match (term expansion)
      - Jina v5 dense embedding match
    Stage 2 (optional): Jina reranker v3 re-reads the titles of the top
    RERANK_WINDOW candidates against the query. Off by default: on our test
    queries it helped some (agent reliability) and hurt others (dropped the best
    diffusion-segmentation match); reading full abstracts was worse still.
    """
    filters = [{"term": {"session": session}}] if session else []
    fused = {
        "rrf": {
            "retrievers": [
                _filtered(
                    {"multi_match": {"query": q, "fields": ["title^3", "abstract", "authors^2", "topic"]}},
                    filters,
                ),
                _filtered({"semantic": {"field": "semantic_content", "query": q}}, filters),
                _filtered({"semantic": {"field": "semantic_dense", "query": q}}, filters),
            ],
            "rank_window_size": 100,
        }
    }
    retriever = fused
    if rerank:
        retriever = {
            "text_similarity_reranker": {
                "retriever": fused,
                "field": "title",
                "inference_id": RERANK_MODEL,
                "inference_text": q,
                "rank_window_size": max(RERANK_WINDOW, size),
            }
        }
    return {"retriever": retriever, "size": size, "_source": SOURCE_FIELDS}
