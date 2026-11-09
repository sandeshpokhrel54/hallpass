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
FLOOR_CHANGE_M = 40.0  # lift/stairs ride, expressed as equivalent walking metres


@dataclass(frozen=True)
class Spot:
    board: int
    aisle: int
    x: float  # metres along the aisle
    y: float  # metres across the hall
    floor: int = 0  # each floor/room is its own grid, joined by a lift at the front


def lift(floor: int) -> Spot:
    """The lift/stairs on a floor: front aisle, middle of the walls."""
    return Spot(board=-1, aisle=0, x=WALL_LEN_M / 2, y=0.0, floor=floor)


def spot(row: int, slot: int, board: int | None = None, floor: int = 0) -> Spot:
    aisle = row // 2
    return Spot(board=board if board is not None else row * 100 + slot,
                aisle=aisle, x=slot * SLOT_M, y=aisle * AISLE_M, floor=floor)


def spot_for_board(board: int) -> Spot | None:
    """Spot for a 3-4 digit board number (row*100+slot); None for plain numbering
    or a slot outside the modelled wall (which would give negative distances)."""
    if board < 100:
        return None
    row, slot = divmod(board, 100)
    if slot > MAX_SLOT:
        return None
    return spot(row, slot, board)


def geo_point(s: Spot) -> dict[str, float]:
    """Map hall metres onto a tiny patch of lat/lon around (0, 0), so Elasticsearch
    geo queries (distance, decay scoring) work on indoor positions."""
    return {"lat": round(s.y / M_PER_DEG, 9), "lon": round(s.x / M_PER_DEG, 9)}


def _floor_walk(a: Spot, b: Spot) -> float:
    if a.aisle == b.aisle:
        return abs(a.x - b.x)
    around_left = a.x + b.x
    around_right = (WALL_LEN_M - a.x) + (WALL_LEN_M - b.x)
    return abs(a.y - b.y) + min(around_left, around_right)


def walk_m(a: Spot, b: Spot) -> float:
    """Estimated walking distance in metres (via the lift when floors differ)."""
    if a.floor == b.floor:
        return _floor_walk(a, b)
    return _floor_walk(a, lift(a.floor)) + FLOOR_CHANGE_M + _floor_walk(lift(b.floor), b)


def _floor_points(a: Spot, b: Spot) -> list[tuple[float, float, int]]:
    f = a.floor
    if a.aisle == b.aisle:
        return [(a.x, a.y, f), (b.x, b.y, f)]
    end = 0.0 if a.x + b.x <= 2 * WALL_LEN_M - a.x - b.x else WALL_LEN_M
    return [(a.x, a.y, f), (end, a.y, f), (end, b.y, f), (b.x, b.y, f)]


def waypoints(a: Spot, b: Spot) -> list[tuple[float, float, int]]:
    """Points (x, y, floor) of the walk from a to b, for drawing the route.
    A floor change appears as consecutive points on different floors (the lift)."""
    if a.floor == b.floor:
        return _floor_points(a, b)
    return _floor_points(a, lift(a.floor)) + _floor_points(lift(b.floor), b)


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

    # 2-opt: reversing order[i..j] only changes the edge into i and the edge out
    # of j (walk_m is symmetric), so compare just those two: O(1) per candidate.
    def before(i: int) -> Spot | None:
        return order[i - 1] if i > 0 else start

    def after(j: int) -> Spot | None:
        return order[j + 1] if j + 1 < len(order) else None

    def edge(a: Spot | None, b: Spot | None) -> float:
        return walk_m(a, b) if a is not None and b is not None else 0.0

    improved = True
    while improved:
        improved = False
        for i in range(len(order) - 1):
            for j in range(i + 1, len(order)):
                p, n = before(i), after(j)
                old = edge(p, order[i]) + edge(order[j], n)
                new = edge(p, order[j]) + edge(order[i], n)
                if new < old - 1e-9:
                    order[i : j + 1] = order[i : j + 1][::-1]
                    improved = True
    return order
