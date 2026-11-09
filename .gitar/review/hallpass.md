# HallPass review guide

HallPass helps attendees of big ML conferences find relevant posters and walk to them.
FastAPI + Elasticsearch (Serverless) + a single static page, deployed by Argo CD.

## Data is untrusted
Poster titles, authors, topics, board labels and URLs come from a scraped public JSON
file. In `hallpass/static/index.html`, flag any of these reaching `innerHTML`, an
attribute, or an `href` without going through `textContent` / `setAttribute`, and any
link that isn't checked to be `http(s):`.

## Hall geometry (hallpass/layout.py, hallpass/venues.py)
- Board number = `row * 100 + slot`; slots 0..19. Row `r` faces aisle `r // 2`.
- Aisles connect only at the wall ends; floors connect only via the lift.
- All distances are **metres**; `walk_m` must stay symmetric and non-negative
  (the 2-opt delta in `plan_route` depends on symmetry).
- Straight-line geo distance is a lower bound on walking distance. Any code that
  uses a geo query to *rank* by proximity (rather than to pre-filter candidates)
  is a bug: ranking must use `walk_m`.

## Elasticsearch
- Every attendee-facing query must filter by `session`.
- Never return `semantic_*` fields in `_source` (they carry embeddings).
- A mapping change in `MAPPINGS` needs a new index name (`ES_INDEX`) and the
  manifests (`deploy/deployment.yaml`, `examples/canary/rollout.yaml`) updated,
  because the live app keeps reading the old index until the new one is built.
- Elasticsearch errors must surface as 502 via the exception handler, not 500.

## Deploy and secrets
- `GET /` must keep returning JSON `{"app","version"}` for non-browser clients:
  the deploy checks in `.agents/skills/ship` depend on it.
- No secret values anywhere in git: credentials only via Secrets
  `app-credentials` / `dash0-credentials`. Dash0 env refs stay `optional: true`.
