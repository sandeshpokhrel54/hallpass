from hallpass.boards import parse_board


def test_four_digit_board():
    b = parse_board("#4902")
    assert (b.number, b.row, b.slot, b.wall, b.side) == (4902, 49, 2, 25, "A")


def test_three_digit_board():
    b = parse_board("#100")
    assert (b.row, b.slot, b.wall, b.side) == (1, 0, 1, "A")


def test_paired_rows_share_a_wall():
    assert parse_board("#1305").wall == parse_board("#1405").wall == 7
    assert parse_board("#1305").side != parse_board("#1405").side


def test_plain_number_has_no_row():
    b = parse_board("12")
    assert (b.number, b.row, b.slot, b.wall) == (12, None, 12, None)


def test_missing_board():
    assert parse_board(None) is None
    assert parse_board("") is None
    assert parse_board("TBD") is None
