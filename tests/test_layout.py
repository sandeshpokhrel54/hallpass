import itertools

from hallpass.layout import (
    AISLE_M, SLOT_M, WALL_LEN_M, geo_point, plan_route, route_length, spot_for_board, walk_m,
)


def S(board):
    return spot_for_board(board)


def test_rows_facing_the_same_aisle():
    # row 2 (back of wall 1) and row 3 (front of wall 2) face aisle 1
    assert S(205).aisle == S(305).aisle == 1
    assert S(105).aisle == 0


def test_same_aisle_walk_is_straight():
    assert walk_m(S(302), S(207)) == 5 * SLOT_M


def test_cross_aisle_walk_goes_round_the_nearer_end():
    # both near the left end: around the left
    assert walk_m(S(101), S(501)) == 2 * AISLE_M + 2 * SLOT_M
    # both near the right end: around the right
    assert walk_m(S(118), S(518)) == 2 * AISLE_M + 2 * (WALL_LEN_M - 18 * SLOT_M)


def test_plain_numbers_have_no_spot():
    assert spot_for_board(12) is None


def test_geo_point_scales_metres():
    p = geo_point(S(4902))
    assert p["lat"] > 0 and p["lon"] > 0 and p["lat"] < 0.01


def test_route_is_optimal_on_small_case():
    stops = [S(b) for b in (4902, 105, 3410, 1218, 2700, 5003)]
    best = min(route_length(list(p)) for p in itertools.permutations(stops))
    got = plan_route(stops)
    assert sorted(s.board for s in got) == sorted(s.board for s in stops)
    assert route_length(got) <= best * 1.15


def test_route_from_start_excludes_start():
    stops = [S(b) for b in (1210, 1215, 4000)]
    got = plan_route(stops, start=S(1205))
    assert [s.board for s in got][:2] == [1210, 1215]


def test_out_of_range_slot_has_no_spot():
    assert spot_for_board(150) is None
    assert spot_for_board(1299) is None
    assert spot_for_board(119) is not None


def test_route_with_start_is_near_optimal():
    start = S(2505)
    stops = [S(b) for b in (4902, 105, 3410, 1218, 2700, 5003, 2510)]
    best = min(route_length([start, *p]) for p in itertools.permutations(stops))
    got = plan_route(stops, start=start)
    assert route_length([start, *got]) <= best * 1.15


def test_route_handles_max_stops_quickly():
    import time
    stops = [S(r * 100 + s) for r in range(1, 56, 4) for s in range(0, 20, 5)][:60]
    t = time.perf_counter()
    got = plan_route(stops)
    assert len(got) == len(stops)
    assert time.perf_counter() - t < 1.0


def test_cross_floor_walk_goes_via_the_lift():
    from hallpass.layout import FLOOR_CHANGE_M, lift, spot
    a, b = spot(2, 10, floor=0), spot(2, 10, floor=1)
    assert walk_m(a, b) == 2 * walk_m(a, lift(0)) + FLOOR_CHANGE_M


def test_route_minimises_floor_changes():
    from hallpass.venues import VENUES
    v = VENUES["demo-two-floors"]
    boards = [305, 3305, 410, 3410, 515, 3515]  # alternate floors
    order = plan_route([v.spot(b) for b in boards])
    floors = [s.floor for s in order]
    changes = sum(1 for x, y in zip(floors, floors[1:]) if x != y)
    assert changes == 1


def test_demo_venue_splits_rows_onto_level_2():
    from hallpass.venues import VENUES
    v = VENUES["demo-two-floors"]
    assert v.spot(2805).floor == 0
    s = v.spot(2905)
    assert s.floor == 1 and s.aisle == 0
    assert v.local_row(2905) == (1, 1)
