# Public gallery: launch groups and reversible trimming

The website groups candidates by destination, ordered assist sequence (including
DSM markers), and launch month. Each card shows the count and C3 / flight-time
ranges. Expand it to select an exact TDB departure time and inspect its arrival
date, cruise burn cost and arrival V-infinity. The scatter plot still selects
individual trajectories. Featured and historical mission names are retained.

Default trimming removes a candidate from the list and scatter plot only when a
retained alternative:

- has the same target and ordered assist sequence;
- launches within three Julian years;
- has no higher C3, flight time, arrival V-infinity or modeled cruise burn cost;
- has no larger saved maximum flyby-speed gap (allowing 1 m/s numerical tolerance);
- improves C3 by both 20% and 2 km²/s², **or** flight time by both 20% and one year;
- does not replace a submitted pass with a submitted yellow candidate.

Named, featured, research and integrated missions are protected. Original science
records, archive downloads and direct mission links remain intact. There is no
new claim of physical validation and no deletion from the community database.
“Show trimmed alternatives” restores the full matching list and graph.

Filters apply **before** trimming. For example, a useful 2041 launch remains
available when the user excludes the otherwise cheaper 2039 opportunity. The
comparison runs again when new community records arrive, so new uploads get the
same treatment automatically. No efficiency ratings or ranking categories are
introduced.

The public snapshot audit is `docs/data/library_curation_report.json`. Each
trimmed ID maps to a retained comparison ID. Regenerate from the bundled archive:

```sh
node tools/audit_gallery_curation.mjs --output audit.json
```

To include additional downloaded records (a JSON array from the public API):

```sh
node tools/audit_gallery_curation.mjs --snapshot live.json --output audit.json
```

The saved audit includes a snapshot of the live feed and the bundled archive.
Counts vary with filters, subsequent uploads and locally assigned mission names.
Maximum flyby-speed gaps are compared separately from modeled burns; a zero-DSM
candidate with a large gap cannot hide a better-connected alternative.
The website, tests and audit command use the same `docs/library_curation.js` rules.
