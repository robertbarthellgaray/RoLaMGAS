# Shared trajectory library

The public trajectory API is deployed at
https://rolamgas-community.corigarayv.workers.dev. It was initialized with the 97
sanitized public starter candidates on 2026-11-03, then expanded to 2,047 distinct
historical passing trajectories from all recovered solver generations. The website and source defaults
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
The unified interactive explorer checks the shared feed every 30 seconds while
visible. New records enter the same destination filters, viewer and downloads
as the curated examples, without rebuilding GitHub Pages.

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

## Historical passing archive

`community_seed_catalog.json` and `docs/data/community_seed_catalog.json` contain
the full recovered public archive. `docs/data/community_history_index.csv` lists
departure/arrival dates, TDB Julian epochs, flight time and mission metrics.
`docs/data/community_history_report.json` reports conversion totals without local
paths or private run identifiers. The Choose your next world explorer combines this complete archive with curated
examples and live submissions. It starts with 2,056 interactive entries after
shared copies of curated examples are removed. An inclusive received-time cursor
and keyset pagination retrieve every new submission, including new target IDs;
the per-response API limit does not hide older historical passes. Filtering and
sorting apply to the whole library before previews load.

These classifications preserve the original run's limits and solver version;
they are not a new certification under today's defaults. Legacy gallery exports
without optimizer variables recover their DSM controls from saved heliocentric
arcs and their original Lambert branches. Records lacking discovery timestamps
use their file-save time, shown as solved / first saved. The production schema
validator checks every public record and supplies its canonical deduplication ID.
Private records, paths, requests and raw run folders are never copied publicly.

To regenerate an archive independently, with Node.js and the Python requirements
installed, run this from the repository root (repeat --root for older folders):

    python tools/import_passing_history.py --root PATH_TO_RUNS --existing community_seed_catalog.json --output new_catalog.json --report import_report.json --private-report private_errors.json

The importer writes files locally and never uploads automatically. Review any
errors before replacing the public files. Keep private_errors.json private.

The public archive records `received_through` for incremental synchronization and
`curated_aliases` for legacy curated entries; neither contains user/run identities.
Every shared trajectory supports rotation, playback, encounter/DSM dates, and
browser-generated CSV/XYZV samples of its saved Sun-only coasts. These downloads
retain planet-center joins; finite-radius flyby exports still require the desktop
exporter. Curated integrated files remain the original saved exports.

Public library policy: C3 must be at most 250 km²/s². On 2026-11-03,
25 historical trajectories above that ceiling were purged from the public archive
and production database. New submissions and history imports enforce the same ceiling.

## v0.2.2: database-first searches

The desktop checks the live library before allocating optimizer processes.
Queries use C3, launch dates, arrival V-infinity and total duration, follow every
result page, and then independently recompute each compatible mission with the
current JPL data and all current constraints. With three distinct passing library
results, it waits for the user's choice to use the results or search locally too.
With fewer, it searches locally automatically. Bundled records provide an offline
library; failures of the service never turn into a failed numerical search.

Public small-body flights must be shorter than 40 Julian years (365.25 days each).
Trips above C3 170 must take less than 25 years. Actual encounter epochs determine
duration. Eight-planet targets are exempt from those small-body quality limits.

## Automatic planet-ending prefixes (local preview)

New app searches and explicit Share actions also prepare eligible prefixes. For
example, `EVEEJUX` can contribute `EV`, `EVEEJ` and `EVEEJU`. Earth-return stopping
points are skipped. The original candidate stays unchanged.

`trajectory_prefixes.public_records` reruns the same Lambert legs against the
parent's saved JPL event states, using its original screening limits. Each child
gets its own arrival V-infinity, flyby checks and maneuver total. DSMs and powered
flyby burns after its final arrival are removed, including the burn that would
have redirected it onward at its new destination. Only prefixes passing these
checks and normal public-library policies are shared. A target-specific arrival
V-infinity ceiling can reject a prefix even when the parent passes.

Parents and prefixes use the same anonymous field allowlist, opt-out setting,
same-day duplicate slots, server limits and website trimming. There is no extra
JPL request for this step. Previously released binaries do not gain this behavior
until updated. Publication tools can call the same helper; the Jupiter batch
uses it. The raw API still validates individual science records and cannot
reconstruct missing planet velocities from older uploads alone.
