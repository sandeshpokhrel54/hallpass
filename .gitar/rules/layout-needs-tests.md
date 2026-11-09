---
title: "Hall geometry changes need tests"
description: "Walking distances and routes must stay covered by tests"
when: "PRs that modify hallpass/layout.py or hallpass/venues.py"
actions: "Check that tests/test_layout.py or tests/test_api.py also changed; if not, post a comment asking for a test"
type: check
---

# Hall geometry changes need tests

Attendees act on these distances physically. If a PR changes `hallpass/layout.py` or
`hallpass/venues.py` but no test file under `tests/` changes, post a comment asking for
a test that pins the new behaviour (a distance, a route order, or a floor mapping).
