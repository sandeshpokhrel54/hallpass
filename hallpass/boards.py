"""Parse poster board numbers into an inferred physical layout.

NeurIPS 2025 board numbers encode ``row * 100 + slot`` (e.g. ``#4902`` -> row 49,
slot 2). Rows come in pairs with identical poster counts (1&2, 3&4, ...), which
we interpret as the two faces of one double-sided wall. This layout is
*inferred* from the numbering, not taken from an official floor plan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_DIGITS = re.compile(r"\d+")


@dataclass(frozen=True)
class Board:
    number: int
    row: int | None  # None when the venue uses plain sequential numbering
    slot: int
    wall: int | None  # rows (2k-1, 2k) share wall k
    side: str | None  # "A" for odd rows, "B" for even rows


def parse_board(raw: str | None) -> Board | None:
    """Return the inferred board location, or None if there is no usable number."""
    if not raw:
        return None
    m = _DIGITS.search(raw)
    if not m:
        return None
    number = int(m.group())
    if not raw.strip().startswith("#") or number < 100:
        # Small venues (e.g. the Mexico City satellite) use plain 1..N numbering.
        return Board(number=number, row=None, slot=number, wall=None, side=None)
    row, slot = divmod(number, 100)
    return Board(
        number=number,
        row=row,
        slot=slot,
        wall=(row + 1) // 2,
        side="A" if row % 2 else "B",
    )
