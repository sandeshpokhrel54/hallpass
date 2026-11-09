# HallPass at the Cloud Native Hackathon

Team `hallpass` · cluster `uUgyd5vGAqo` · namespace `team-hallpass` · live at https://hallpass.cnh.radarhq.io · times in MST (UTC−7), 2026-11-09.

## Before

No morning screenshot of Checks. The first Checks review for `team-hallpass`, at 14:20 on release `a8ec485`:
[Checks, team-hallpass](https://app.radarhq.io/checks?scope=uUgyd5vGAqo&namespace=team-hallpass)

- **Medium (4), all on `Deployment/app`:**
  - Security · `automountServiceAccountToken`: service account token auto-mounted
  - Security · `readOnlyRootFs`: container `app` has a writable root filesystem
  - Reliability · `missingPDB`: 2 replicas, no PodDisruptionBudget
  - Reliability · `missingTopologySpread`: 2 replicas, no topology spread constraints

## After

At 14:31, on release `4bcacc6`: **0 findings** in `team-hallpass`. The cluster's other 36 findings are on the pre-installed platform (Argo CD, Prometheus, Argo Rollouts, Radar, `default/kubeconfig`) and aren't ours to fix.

## The story

- **What we built:** HallPass gets a NeurIPS attendee from "950 posters in 3 hours" to the 15 worth seeing: relevant posters, a walking route on the hall map, and "what's near me" by walking distance, across multi-floor venues (PRs #1, #3–#6).
- **How we shipped:** every merged PR (Gitar-reviewed) built an image to GHCR, which the Action published to the `deploy` branch; Argo CD in our vcluster deployed it, and we synced and verified every step through Radar's MCP. That's 7 releases, from the first deploy at 12:01 (`1046ff2`) to `4bcacc6` at 14:28 (Radar Changes timeline).
- **What broke and how Radar showed it:** after the first deploys, search returned 500s. Radar's workload logs showed `Could not parse URL '…es.us east4…'`, a typo in the hand-made `app-credentials` Secret. We fixed it in Radar's resource editor at 12:49 and restarted through Radar; search came back, and Radar Changes recorded the `es-url` edit.
- **The investigation:** after the 14:28 release, which made the root filesystem read-only and was untested on real pods, Radar's AI SRE investigated `Deployment/app` and found it healthy (confidence 0.9). The only Warning, a readiness-probe "connection refused" at 14:28:57, was the new pods starting; `/readyz` and `/healthz` returned 200 from 14:30 on, with 0 restarts. So we kept the hardening.
- **Checks before and after:** 4 medium findings on our Deployment became 0 with PR #9: no service account token, a read-only root filesystem with an `emptyDir` at `/tmp`, a PodDisruptionBudget (`minAvailable: 1`), and a topology spread across nodes. A server-side dry run validated the change before merge, and Radar's rollout checks confirmed it after.

## Screenshots to take

1. **Timeline**, showing the day's changes, the 7 image bumps and both Secret edits: https://app.radarhq.io/c/uUgyd5vGAqo/timeline
2. **Argo CD Application `app`**, Synced/Healthy on `deploy: 4bcacc6`: https://app.radarhq.io/c/uUgyd5vGAqo/resources/applications?resource=team-hallpass/app&apiGroup=argoproj.io
3. **Checks, whole cluster**, showing what Radar catches on the platform: https://app.radarhq.io/checks?scope=uUgyd5vGAqo
4. **Checks, team-hallpass**, now at 0: https://app.radarhq.io/checks?scope=uUgyd5vGAqo&namespace=team-hallpass
5. **The investigation**, which is private, so only the person who started it can open it: https://app.radarhq.io/c/uUgyd5vGAqo/investigations/chat_7zfb3rvgDK22stcx?org=org_NCJbssDGEBsU
