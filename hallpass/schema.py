"""Turn raw NeurIPS virtual-site records into HallPass documents."""

from __future__ import annotations

from typing import Any

from hallpass.boards import parse_board
from hallpass.layout import geo_point, spot

VIRTUAL_SITE = "https://neurips.cc"


def _clean(value: Any) -> Any:
    return None if value in (None, "", "None") else value


def to_doc(rec: dict[str, Any]) -> dict[str, Any] | None:
    """Map one raw record to an index document. Returns None for records we skip."""
    if rec.get("eventtype") != "Poster" or not _clean(rec.get("session")):
        return None  # orals and unscheduled entries have no board to walk to

    title = (rec.get("name") or "").strip()
    abstract = (rec.get("abstract") or "").strip()
    authors = rec.get("authors") or []
    topic = _clean(rec.get("topic"))
    session = rec["session"]
    board = parse_board(_clean(rec.get("poster_position")))
    virtual = _clean(rec.get("virtualsite_url"))
    where = spot(board.row, board.slot, board.number) if board and board.row is not None else None

    return {
        "id": str(rec["id"]),
        "title": title,
        "abstract": abstract,
        # Embedded by Elasticsearch at index time (semantic_text field).
        "semantic_content": f"{title}\n\n{abstract}",
        "semantic_dense": f"{title}\n\n{abstract}",
        "authors": [a.get("fullname") for a in authors if a.get("fullname")],
        "institutions": sorted({a["institution"] for a in authors if a.get("institution")}),
        "topic": topic,
        "topic_area": topic.split("->")[0] if topic else None,
        "kind": (rec.get("event_type") or "").replace("{location}", "").strip() or "Poster",
        "venue": "Mexico City" if session.startswith("Mexico City") else "San Diego",
        "session": session,
        "start": _clean(rec.get("starttime")),
        "end": _clean(rec.get("endtime")),
        "room": _clean(rec.get("room_name")),
        "board": board.number if board else None,
        "board_label": _clean(rec.get("poster_position")),
        "row": board.row if board else None,
        "slot": board.slot if board else None,
        "wall": board.wall if board else None,
        "side": board.side if board else None,
        "aisle": where.aisle if where else None,
        # Indoor position mapped onto lat/lon so geo distance and decay queries work.
        "loc": geo_point(where) if where else None,
        "openreview_url": _clean(rec.get("paper_url")),
        "virtual_url": f"{VIRTUAL_SITE}{virtual}" if virtual else None,
    }
