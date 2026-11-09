---
title: "Index mapping change needs a new index"
description: "Mapping changes must not break the running app"
when: "PRs that change MAPPINGS in hallpass/es.py"
actions: "Add the label 'reindex' and post a checklist comment"
type: automation
---

# Index mapping change needs a new index

When `MAPPINGS` in `hallpass/es.py` changes, add the label `reindex` and comment:

- [ ] New index name in `ES_INDEX` default (don't mutate the live index in place)
- [ ] `deploy/deployment.yaml` and `examples/canary/rollout.yaml` point at it
- [ ] New index fully built (`uv run python -m hallpass.ingest --recreate`) **before** merge
