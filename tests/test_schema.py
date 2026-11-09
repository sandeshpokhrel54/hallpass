from hallpass.schema import to_doc

REC = {
    "id": 1,
    "name": " A Paper ",
    "abstract": "We study things.",
    "authors": [{"fullname": "Ada L", "institution": "Uni X"}, {"fullname": "Bob", "institution": None}],
    "topic": "Computer Vision->Segmentation",
    "eventtype": "Poster",
    "event_type": "{location} Spotlight Poster",
    "session": "San Diego Poster Session 2",
    "starttime": "2025-12-03T16:30:00-08:00",
    "endtime": "2025-12-03T19:30:00-08:00",
    "room_name": "Exhibit Hall C,D,E",
    "poster_position": "#3407",
    "paper_url": "https://openreview.net/forum?id=x",
    "virtualsite_url": "/virtual/2025/poster/1",
}


def test_poster_maps_to_doc():
    d = to_doc(REC)
    assert d["title"] == "A Paper"
    assert d["semantic_content"].startswith("A Paper\n\nWe study")
    assert d["authors"] == ["Ada L", "Bob"]
    assert d["institutions"] == ["Uni X"]
    assert d["topic_area"] == "Computer Vision"
    assert d["kind"] == "Spotlight Poster"
    assert d["venue"] == "San Diego"
    assert (d["row"], d["slot"], d["wall"]) == (34, 7, 17)
    assert d["virtual_url"] == "https://neurips.cc/virtual/2025/poster/1"


def test_orals_are_skipped():
    assert to_doc({**REC, "eventtype": "Oral"}) is None


def test_unscheduled_posters_are_skipped():
    assert to_doc({**REC, "session": "None"}) is None
