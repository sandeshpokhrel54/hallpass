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
