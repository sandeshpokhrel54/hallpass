"""Load the NeurIPS 2025 schedule and index it into Elasticsearch.

Usage:  uv run python -m hallpass.ingest [--recreate] [--limit N]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
from elasticsearch import helpers

from hallpass import es as hes
from hallpass.schema import to_doc

# Snapshot archived 2025-12-01, before the poster sessions (Dec 3-5): exactly the
# data an attendee had on day one.
SOURCE_URL = (
    "https://web.archive.org/web/20251201235309id_/"
    "https://neurips.cc/static/virtual/data/neurips-2025-orals-posters.json"
)
RAW_PATH = Path("data/raw/neurips-2025-20251201.json")


def load_raw(path: Path = RAW_PATH) -> list[dict]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {SOURCE_URL}")
        resp = httpx.get(SOURCE_URL, follow_redirects=True, timeout=300)
        resp.raise_for_status()
        path.write_bytes(resp.content)
    return json.loads(path.read_text())["results"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recreate", action="store_true", help="drop and recreate the index")
    ap.add_argument("--limit", type=int, help="index only the first N posters (for testing)")
    args = ap.parse_args()

    docs = [d for d in map(to_doc, load_raw()) if d]
    if args.limit:
        docs = docs[: args.limit]
    print(f"{len(docs)} posters to index into '{hes.INDEX}'")

    es = hes.client()
    hes.create_index(es, recreate=args.recreate)
    actions = ({"_index": hes.INDEX, "_id": d["id"], "_source": d} for d in docs)
    # Small chunks: each bulk request triggers ELSER inference on the cluster.
    ok, errors = helpers.bulk(es, actions, chunk_size=50, raise_on_error=False)
    print(f"indexed {ok}, errors {len(errors)}")
    for e in errors[:5]:
        print("  ", e)


if __name__ == "__main__":
    main()
