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
2,306 recovered historical passing records. Worker observability and preview URLs are disabled.
The configured production D1 database is `rolamgas-community`.

The unified website uses `target=all`, optional inclusive ISO-UTC `since`, and
the returned opaque `next_cursor` (passed as `cursor`) to fetch the live feed.
Each page contains up to 100 candidates. Existing single-target desktop queries
continue to work. A `(received_at DESC,id)` index supports this incremental feed.
