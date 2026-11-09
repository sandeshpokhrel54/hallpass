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

## AI assistance disclosure
This project is built with help from Claude Code (Anthropic) as a coding assistant.
