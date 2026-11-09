# HallPass

**950 posters in 3 hours. You can see 15. Which 15?**

HallPass helps attendees of large ML conferences (NeurIPS, ICML, ICLR, CVPR) find the posters
that matter to them and **walk to them**: personalized shortlists, an inferred hall map, and the
shortest route between boards.

Built at the WeMakeDevs Cloud Native Hackathon (Salt Lake City, 2026-11-09).

## Status
Work in progress during the hackathon.

## Data
Uses the public NeurIPS 2025 schedule data (`neurips.cc/static/virtual/data/neurips-2025-orals-posters.json`),
as archived on **2025-12-01**, before the poster sessions began (Dec 3–5), i.e. exactly what an
attendee had on day one. The hall map is **inferred from board numbers** (row × 100 + slot),
not an official floor plan.

## Run locally
```
uv sync
cp .env.example .env          # add your Elastic Cloud URL + API key
uv run python -m hallpass.ingest --recreate
uv run uvicorn hallpass.api:app --reload
```

## Deploy (Kubernetes, via Radar + Argo CD)
Every push to `main` builds an image to GHCR (`.github/workflows/deploy.yaml`) and Argo CD
syncs `deploy/` into namespace `team-hallpass`, served at https://hallpass.cnh.radarhq.io.
Infra scaffolding comes from [skyhook-io/cnh-starter](https://github.com/skyhook-io/cnh-starter).

Elasticsearch credentials live only in a Kubernetes Secret, created by hand:
```
read -rs ES_URL; read -rs ES_API_KEY
kubectl -n team-hallpass create secret generic app-credentials \
  --from-literal=es-url="$ES_URL" --from-literal=es-api-key="$ES_API_KEY"
```

## AI assistance disclosure
This project is built with help from Claude Code (Anthropic) as a coding assistant.
