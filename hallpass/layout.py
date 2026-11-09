"""Physical hall geometry and walking routes, inferred from board numbers.

Model (see boards.py for how numbers map to rows/walls):

* Rows 2k-1 and 2k are the two faces of wall k. Row r therefore faces aisle
  ``r // 2``: row 1 faces aisle 0, rows 2 and 3 face aisle 1, and so on.
* Within a row, slot s sits ``s * SLOT_M`` metres from the hall's left end.
* You can only change aisles at either end of the walls, so the walking
  distance between two aisles goes around the nearer end.

The numbers are estimates (no official floor plan); they only need to rank
"near" vs "far" and order a route sensibly.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

SLOT_M = 3.0  # board-to-board pitch along a wall
AISLE_M = 5.0  # aisle-to-aisle distance across walls
MAX_SLOT = 19  # slots run 0..19
WALL_LEN_M = MAX_SLOT * SLOT_M
M_PER_DEG = 111_320.0  # metres per degree at the equator (for geo_point)


@dataclass(frozen=True)
class Spot:
    board: int
    aisle: int
    x: float  # metres along the aisle
    y: float  # metres across the hall


def spot(row: int, slot: int, board: int | None = None) -> Spot:
    aisle = row // 2
    return Spot(board=board if board is not None else row * 100 + slot,
                aisle=aisle, x=slot * SLOT_M, y=aisle * AISLE_M)


def spot_for_board(board: int) -> Spot | None:
    """Spot for a 3-4 digit board number (row*100+slot); None for plain numbering."""
    if board < 100:
        return None
    row, slot = divmod(board, 100)
    return spot(row, slot, board)


def geo_point(s: Spot) -> dict[str, float]:
    """Map hall metres onto a tiny patch of lat/lon around (0, 0), so Elasticsearch
    geo queries (distance, decay scoring) work on indoor positions."""
    return {"lat": round(s.y / M_PER_DEG, 9), "lon": round(s.x / M_PER_DEG, 9)}


def walk_m(a: Spot, b: Spot) -> float:
    """Estimated walking distance in metres."""
    if a.aisle == b.aisle:
        return abs(a.x - b.x)
    around_left = a.x + b.x
    around_right = (WALL_LEN_M - a.x) + (WALL_LEN_M - b.x)
    return abs(a.y - b.y) + min(around_left, around_right)


def waypoints(a: Spot, b: Spot) -> list[tuple[float, float]]:
    """Corner points of the walk from a to b, for drawing the route."""
    if a.aisle == b.aisle:
        return [(a.x, a.y), (b.x, b.y)]
    end = 0.0 if a.x + b.x <= 2 * WALL_LEN_M - a.x - b.x else WALL_LEN_M
    return [(a.x, a.y), (end, a.y), (end, b.y), (b.x, b.y)]


def route_length(order: list[Spot]) -> float:
    return sum(walk_m(a, b) for a, b in pairwise(order))


def plan_route(stops: list[Spot], start: Spot | None = None) -> list[Spot]:
    """Order stops for a short walk: nearest-neighbour, then 2-opt improvement.

    If ``start`` is given (where the attendee is standing), the route begins
    there; it is not included in the result.
    """
    stops = list(dict.fromkeys(stops))  # dedupe, keep order
    if len(stops) <= 1:
        return stops

    remaining = stops[:]
    cur = start or min(remaining, key=lambda s: (s.aisle, s.x))
    order: list[Spot] = []
    if start is None:
        order.append(cur)
        remaining.remove(cur)
    while remaining:
        nxt = min(remaining, key=lambda s: walk_m(cur, s))
        order.append(nxt)
        remaining.remove(nxt)
        cur = nxt

    def cost(path: list[Spot]) -> float:
        return route_length([start, *path] if start else path)

    improved = True
    while improved:
        improved = False
        for i in range(len(order) - 1):
            for j in range(i + 1, len(order)):
                cand = order[:i] + order[i : j + 1][::-1] + order[j + 1 :]
                if cost(cand) < cost(order) - 1e-9:
                    order, improved = cand, True
    return order
