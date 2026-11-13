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
2,047 recovered historical passing records. Worker observability and preview URLs are disabled.
The configured production D1 database is `rolamgas-community`.

The unified website uses `target=all`, optional inclusive ISO-UTC `since`, and
the returned opaque `next_cursor` (passed as `cursor`) to fetch the live feed.
Each page contains up to 100 candidates. Existing single-target desktop queries
continue to work. A `(received_at DESC,id)` index supports this incremental feed.

Public library policy: C3 must be at most 250 km²/s². On 2026-11-03,
25 historical trajectories above that ceiling were purged from the public archive
and production database. New submissions and history imports enforce the same ceiling.

Venus-assisted routes that also visit Jupiter, Saturn, Uranus or Neptune have
an additional public-example ceiling of C3 30 km²/s². On 2026-11-11, 45 records
above that preference were archived with restoration backups and removed from
D1 and the bundled catalogs. This is a library policy, not a physical limit;
advanced local searches can override `max_venus_c3`. The worker rejects new
above-policy submissions, and the website filters legacy copies. See
`studies/early2030s_low_c3/README.md` for the audit and replacement examples.

Public small-body flights must be shorter than 40 Julian years (365.25 days each).
Flights above C3 170 km²/s² must take less than 25 years. These limits apply to
all minor bodies, physical Pluto and the Pluto barycenter. The live API, website,
client sharing and history imports use these rules. On 2026-11-12, migration
`0003_small_body_quality.sql` removed 3,057 entries, preserving complete rows in
the private `quality_purge_20261112` recovery table. Insert/update triggers
prevent old clients from restoring over-limit entries.

The previous limit was 60 Julian years, measured from actual encounter epochs.
234 historical records at or above that duration were purged on 2026-11-03.
Eight-planet targets are exempt from these small-body limits.

## Same-day encounter deduplication

The library retains one representative for each ordered list of bodies and TDB
encounter calendar days, including launch and arrival. The day key uses
`floor(JD + 0.5)` because Julian days begin at noon. Differences in branches,
DSM notation or sub-day optimizer controls do not create extra public slots.
Submitted pass precedes yellow; within that class the deterministic balanced
selection cost is `C3/100 + cruise_delta_v_km_s + arrival_vinf_km_s/20 + flight_years/100`.
This selects a representative, not a new physical validation or relative rating.
A better subsequent submission atomically replaces its slot. A unique D1 index
prevents concurrent clients, including v0.2.2, from creating duplicate slots.

Existing deployments need the one-time migration
`migrations/0001_same_day_encounters.sql` **before deploying the updated Worker**.
First export the complete remote D1 database to a private backup outside the repo:

```powershell
npx wrangler d1 export rolamgas-community --remote --output "$env:TEMP/rolamgas-before-same-day-dedup.sql" --config community_backend/wrangler.toml
npx wrangler d1 execute rolamgas-community --remote --file community_backend/migrations/0001_same_day_encounters.sql --config community_backend/wrangler.toml
npx wrangler deploy --config community_backend/wrangler.toml
```

Use a new backup filename if one already exists. The migration is intentionally
one-time: it adds columns, removes inferior duplicates with a SQL window rank,
and installs the unique encounter index. A trigger briefly blocks old Worker
writes between migration and deployment, so nullable slots cannot bypass the
index; deploy the updated Worker immediately after the migration. New databases use `schema.sql` directly.
The bundled archives preserve `duplicate_aliases` for historical website links.
Private/full solver histories are untouched.

Production migration applied on 2026-11-04 after verifying a complete private SQL backup.
The live library went from 3,242 records to 2,867 unique encounter schedules (375 duplicates removed).
The post-deployment audit found no duplicate slots, missing keys, C3 violations or 60-year small-body flights.
