"""Venues: how a conference's board numbers map onto floors.

Each floor (or room) is its own grid; floors are joined by a lift at the front.
NeurIPS 2025's posters were all in one hall. The two-floor demo venue reuses the
same posters split across two levels, to show multi-floor routing works. It is
synthetic and labelled as such.
"""

from __future__ import annotations

from dataclasses import dataclass

from hallpass import layout


@dataclass(frozen=True)
class Venue:
    id: str
    name: str
    floors: tuple[str, ...]
    split_row: int | None = None  # rows above this go to the next floor
    synthetic: bool = False

    def spot(self, board: int) -> layout.Spot | None:
        base = layout.spot_for_board(board)
        if base is None:
            return None
        row = board // 100
        if self.split_row and row > self.split_row:
            return layout.spot(row - self.split_row, board % 100, board, floor=1)
        return base

    def local_row(self, board: int) -> tuple[int, int]:
        """(floor, row on that floor) for drawing."""
        row = board // 100
        if self.split_row and row > self.split_row:
            return 1, row - self.split_row
        return 0, row

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "floors": list(self.floors),
                "split_row": self.split_row, "synthetic": self.synthetic}


VENUES = {
    v.id: v
    for v in (
        Venue("neurips-2025", "NeurIPS 2025 · Exhibit Hall C–E (as held)", ("Exhibit Hall C,D,E",)),
        Venue("demo-two-floors", "Demo: same posters on two floors", ("Level 1", "Level 2"),
              split_row=28, synthetic=True),
    )
}
DEFAULT = "neurips-2025"
