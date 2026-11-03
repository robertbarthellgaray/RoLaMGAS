# RoLaMGAS community backend

Cloudflare Worker + D1 source, prepared for local review. See ../COMMUNITY.md for
privacy, free-tier quotas, local tests and the approval-gated deployment steps.

Run tests (Node24): `node --test community_backend/worker.test.mjs` from repo root.
Start local API: `node community_backend/local_server.mjs`.

`POST /v1/candidates` accepts 1–10 sanitized records. `GET /v1/candidates` accepts
`target`, `min_c3`, `max_c3`, `launch_start`, `launch_end`, and `limit` (max100).
`GET /v1/health` reports the schema version. Classifications are user submissions;
this service does not verify orbital dynamics. Desktop clients recompute them.

## Production deployment

API: https://rolamgas-community.corigarayv.workers.dev

Health: `/v1/health`. Deployed 2026-11-03 with the `DB` binding and the
97 public starter records. Worker observability and preview URLs are disabled.
The configured production D1 database is `rolamgas-community`.
