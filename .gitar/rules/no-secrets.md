---
title: "No secrets in the repo"
description: "The repo and image are public"
when: "PRs that modify deploy/, examples/, .env.example, Dockerfile or .github/workflows/"
actions: "Check for credential values; if found, post an inline comment and request changes"
type: check
---

# No secrets in the repo

The repository and the container image are public. Flag any API key, token, password,
kubeconfig, or Elasticsearch/Dash0 URL-with-credentials committed in these paths.
Secret *references* (`secretKeyRef`) and commented placeholders in `.env.example` are fine.
