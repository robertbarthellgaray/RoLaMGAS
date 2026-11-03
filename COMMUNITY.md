# Shared trajectory library

The public trajectory API is deployed at
https://rolamgas-community.corigarayv.workers.dev. It was initialized with the 97
sanitized public starter candidates on 2026-11-03. The website and source defaults
point at this API. Existing v0.2.1 executables can connect without a rebuild by
setting this URL in their community API connection field.

## What is shared

Sharing defaults to on, with a visible checkbox and a confirmation when turning
it off. The message explains the community benefit and leaves searches/downloads
available. The separate library-use checkbox controls bundled/online seeds.

Only an allowlist is sent: planet/Horizons numeric IDs, assist sequence, TDB
encounter dates, Lambert branches, physical DSM controls, heliocentric arc states,
reported merit values, classification, engine version and solve time in UTC.
No names, email, account/device identifiers, local paths, query text, request
files, run IDs, pins or private logs are sent. The provider receives normal
network metadata such as an IP address; this is not a promise of transport
anonymity. Our database has no IP or visitor-identifier columns and Worker
observability logs are disabled. Shared trajectories become public; disabling
sharing stops future uploads but does not remove already published records.

## Local science validation

The starter catalog contains sanitized, revalidated passing history. It works
offline. Online candidates are filtered by target, launch dates and C3; the app
maps their physical dates/DSM controls into the current search, recomputes C3
before later legs, and rechecks geometry, burns, arrival and time constraints.
Submitted pass/yellow labels are unverified. Revalidated seeds can initialize
extra refinements without replacing the normal random-search budget. Frozen
cruise searches are not automatically transplanted into a different mission.

Uploads run in a bounded background queue during searches. They are best-effort:
a disconnected client or a full queue can drop submissions without stopping the
solver. Already reused/downloaded solutions are not blindly rebroadcast. The
server deduplicates identical trajectories and retains the first solve/receive
times. The curated website catalog remains separate from this submitted library.
The community section refreshes every 30 seconds (HTTP cache can add up to 60s).

## Hosting and cost

Start on Cloudflare Workers Free + D1 Free. As checked 2026-11-02, Workers Free
includes 100,000 requests/day. D1 Free includes 5 million rows read/day, 100,000
rows written/day and 5 GB total storage, with additional per-database limits.
D1 rejects queries at free-tier limits rather than charging free-tier overages.
The template adds an application cap of 5,000 candidate submissions/day. Index
writes also count toward D1 usage; submissions and HTTP requests are not the same
billing unit. No trajectory optimization runs on the server. Paid Workers starts
at $5/month plus usage beyond its included allowances; do not enable a paid plan
without reviewing it separately.

Official sources:
- https://developers.cloudflare.com/workers/platform/pricing/
- https://developers.cloudflare.com/d1/platform/pricing/
- https://developers.cloudflare.com/d1/platform/limits/

## Review locally before publishing

The user must try this build before an upload/deployment. Do not run the remote
commands below until the trial is approved. No embedded API secret is used.

Local API preview with Node 24:

    node community_backend/local_server.mjs

This binds only 127.0.0.1:31311 and uses an in-memory SQLite database. Set DATABASE
to a local SQLite filename for persistence. The Worker module uses the same SQL
through D1 in production; deployment still needs your Cloudflare account.

After the local trial is approved, in community_backend:

    npx wrangler login
    npx wrangler d1 create rolamgas-community

Put the returned database ID into wrangler.toml. Then, after approval:

    npx wrangler d1 execute rolamgas-community --remote --file schema.sql
    npx wrangler deploy

Use a Free account/plan. Wrangler CLI metrics can be disabled with
WRANGLER_SEND_METRICS=false. Keep Worker observability disabled if preserving
this deployment's logging policy. The database cap is global, without a visitor
identifier; it protects quotas but is not a full anti-spam system. Monitor the
free-tier quotas and review abuse controls before a large public rollout.

Set the resulting HTTPS workers.dev URL as endpoint in community_config.json
and docs/community_config.json, rebuild for another local trial, and publish only
after approval. No domain purchase is required. The app's API connection field
can point at a local test server without rebuilding. Keep it blank to use the
starter history and local searches without uploads.

Regenerate the starter catalog explicitly from reviewed local history:

    python tools/build_community_seed_catalog.py --history PATH_TO_RUNS --cache PATH_TO_CACHE --output community_seed_catalog.json

Copy that sanitized file to docs/data/community_seed_catalog.json for the website
fallback. The script never uploads raw requests or copies entire private run
folders into the public catalog.
