# HallPass

**950 posters in 3 hours. You can see 15. Which 15, and how do you get to them?**

At NeurIPS, CVPR or ICLR, a single poster session puts ~1,000 posters in one hall. Attendees
skim a schedule, keyword-search titles, and wander. HallPass is a phone-first guide for the
person standing in the hall:

1. **Describe your work** (or paste your abstract) → the posters most relevant to *you* in this session.
2. **Plan my route** → those posters in walking order, drawn on a hall map, with total metres.
3. **What's near me?** → enter the board in front of you; get relevant posters within a short
   walk, ranked by *walking* distance (around the walls, not through them).
4. **Multi-floor venues** → each floor is its own grid joined by a lift; routes finish a floor
   before changing.

Live: https://hallpass.cnh.radarhq.io · Built at the WeMakeDevs Cloud Native Hackathon, Salt Lake City, 2026-11-09.

## Data

NeurIPS 2025's public schedule (`neurips.cc/static/virtual/data/neurips-2025-orals-posters.json`)
as archived on **2025-12-01**, two days *before* the poster sessions (Dec 3–5): exactly what an
attendee had on day one. 5,846 posters; 5,630 have a board number.

The **hall layout is inferred**, not an official floor plan. Board numbers encode
`row × 100 + slot` (`#4902` = row 49, slot 2). Rows 2k−1 and 2k always hold identical poster
counts, so we treat them as the two faces of one wall; topic areas sit in the same rows in every
session. The **two-floor venue is synthetic**: the same posters split across two levels, to show
multi-floor routing. Both are labelled as such in the UI.

## How it works

```
Browser (map UI, Dash0 Web SDK)
   │  same-origin fetch, trace context propagated
   ▼
FastAPI (OpenTelemetry → Dash0: traces, metrics, logs)
   ├─ /search  ── Elasticsearch: RRF( BM25, ELSER sparse, Jina v5 dense ) [+ optional Jina rerank]
   ├─ /near    ── Elasticsearch geo_distance pre-filter (+ semantic) → re-rank by walking metres
   ├─ /zones   ── Elasticsearch significant_terms per wall → self-labelling map
   ├─ /hall    ── posters with positions for the map
   └─ /route   ── nearest-neighbour + 2-opt over an aisle/lift walking metric (pure Python)
Kubernetes (vcluster) ← Argo CD ← `deploy` branch ← GitHub Action ← merged PR (Gitar-reviewed)
```

### Elasticsearch (Serverless) is the whole data layer

| What | Elasticsearch feature | Why |
|---|---|---|
| Find *your* posters | One `rrf` retriever over **BM25** (title^3, authors^2, abstract, topic), **ELSER** (`semantic_text`, learned sparse) and **Jina embeddings v5** (`semantic_text`, dense, via Elastic Inference Service) | Keywords catch names and acronyms, ELSER catches related terms, Jina catches paraphrases. RRF fuses ranks without tuning incompatible scores. ~200 ms |
| Rerank (optional) | `text_similarity_reranker` with **Jina reranker v3** | We measured it on three queries: reranking abstracts was worse on all; titles helped one and dropped the best match on another. So it's `?rerank=true`, off by default |
| Relevant *and* near | Indoor positions stored as **`geo_point`** (metres mapped onto lat/lon); `geo_distance` filter | Straight-line distance is a *lower bound* on walking distance, so a geo circle of radius R provably contains every poster within R metres on foot. Elasticsearch finds candidates; the API re-ranks by real walking distance |
| Self-labelling map | **`significant_terms`** on `topic`, per wall | Labels each wall with what's *unusually* common there ("Image and Video Generation", "Segmentation"), not just what's common everywhere |
| Sessions, layout | `terms`/`min` aggregations, filters | Session picker and map data |

### Walking model and routes (`hallpass/layout.py`, `hallpass/venues.py`)
- Row `r` faces aisle `r // 2`; slots are ~3 m apart, aisles ~5 m apart.
- Aisles connect only at the wall ends; floors connect only via the lift (a ride counts as 40 m).
- Route: nearest-neighbour from your start (or the front-left-most stop), then **2-opt** with O(1)
  edge-delta checks. Tests compare against brute force: within 15% of optimal on small cases.

## Sponsor tools, and what each one caught

**Gitar.** After the initial commit, every change landed through a PR that Gitar reviewed. It found real bugs we then fixed:
deploy commits blocked by branch protection, kustomization-only merges never deploying, `/near`
ranking by straight-line distance through walls, negative distances from off-wall slot numbers,
an O(n³) route optimiser, an XSS path from scraped data into `innerHTML`, a geo pre-filter centred
on the wrong floor's coordinates, and a WCAG contrast regression. Project-aware setup lives in
[`.gitar/review/hallpass.md`](.gitar/review/hallpass.md) and three
[repository rules](.gitar/rules/) (geometry changes need tests; mapping changes get a `reindex`
checklist; no secrets in public paths).

**Radar.** The app runs in the hackathon's vcluster (`team-hallpass`), deployed by Argo CD and
operated through Radar's MCP from Claude Code. Radar's AI investigation showed that early crash
loops were in the platform's CloudNativePG operator (and kube-state-metrics), not our app. The
evidence (API-server timeouts, startup-probe kills) pointed to an overloaded control plane, so we
reported it rather than "fixing" pre-installed components.

**Dash0.** OpenTelemetry traces, metrics and logs from FastAPI, with the Elasticsearch client's
native spans nested inside each request; the Dash0 Web SDK in the page, so browser sessions link
to backend traces. Custom attributes (`hallpass.kind`, `results`, `candidates`, `floor_changes`)
and metrics (`hallpass.searches`, `hallpass.results`, `hallpass.route.length`). Elasticsearch
failures become traced 502s instead of bare 500s.

**Elasticsearch.** See above.

## Accessibility (Merge Forward)
- The ranked, numbered list is the primary content; the map is supplementary (`role="img"` with a
  summary label). Status updates use `aria-live`.
- Keyboard-operable, visible focus rings; light/dark from the system setting; all text and focus
  colours meet WCAG AA contrast.
- Lift-aware multi-floor routing; "Visited" checkboxes so you can pace yourself.

## Run locally
```
uv sync
cp .env.example .env          # Elastic Cloud URL + API key; Dash0 lines optional
uv run python -m hallpass.ingest --recreate     # ~8 min: ELSER + Jina embeddings on 5,846 posters
uv run uvicorn hallpass.api:app --reload        # http://localhost:8000
uv run pytest
```

## Deploy (Kubernetes via Radar + Argo CD)
`main` is PR-only. Each merge builds an image to GHCR (`.github/workflows/deploy.yaml`), which
force-pushes the image-tag bump to the `deploy` branch; Argo CD tracks `deploy` and syncs
`deploy/` into namespace `team-hallpass`. (GitHub can't exempt the Actions bot from a personal
repo's ruleset, so the bot never writes to `main`.) Infra scaffolding from
[skyhook-io/cnh-starter](https://github.com/skyhook-io/cnh-starter).

Credentials live only in Kubernetes Secrets, created by hand: `app-credentials`
(`es-url`, `es-api-key`) and `dash0-credentials` (`otlp-endpoint`, `auth-token`, `rum-token`;
all optional). Nothing secret is in git or the image.

## API
| Endpoint | Purpose |
|---|---|
| `GET /` | Map UI for browsers; `{"app","version"}` JSON otherwise |
| `GET /sessions` | Poster sessions with times and counts |
| `GET /search?q=&session=&size=&rerank=` | Three-way hybrid search |
| `GET /near?board=&session=&q=&venue=` | Within a short walk, by walking distance |
| `POST /route` `{boards, start?, venue?}` | Walking order, metres, legs, floor changes |
| `GET /hall?session=&venue=` · `GET /zones?session=` · `GET /venues` | Map data |

## AI assistance disclosure
Built with **Claude Code** (Anthropic) as a coding assistant, directed and reviewed by the author:
the problem, product decisions (attendee-first, inferred layout, multi-floor, measuring the
reranker before enabling it), and every merge were the author's. Gitar reviewed all PRs.
