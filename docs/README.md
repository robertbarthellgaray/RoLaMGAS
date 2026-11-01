# Static trajectory gallery

Served at https://robertbarthellgaray.github.io/RoLaMGAS/ through GitHub Pages.

No build step or Python backend is required. Serve this directory with any static HTTP server. All asset URLs are relative so the gallery works at a project subpath.

`data/index.json` contains the small filter catalog. Detailed paths load on selection from `data/cases/`. SVG card plots are generated offline. `downloads/` contains CSV and XYZV states for every candidate, plus individual file notes and checksums. The two original integrated XYZVs are unchanged; their CSVs preserve every numeric source row. The browser never generates or integrates new trajectories.

RoLaMGAS.png is the original artwork supplied by Robert Barthell Garay.

The offline catalog builder is `../tools/build_public_catalog.py`. Its input trajectory project is not part of this public repository. Existing numeric examples are sufficient to run the gallery.

## Catalog admission

The public examples prioritize distinct assist sequences before metric tradeoffs. Small-body destinations are Pluto, Eris and 2026 ED138. P denotes Pluto, Er Eris and X 2026 ED138. Eris uses JPL’s long-term system-barycenter solution; the primary-body table ends in 2030.

`data/catalog_audit.json` records admission rules, independent endpoint errors, route coverage and clearance checks for both original integrated concepts. Individual Lambert JSON files retain recomputed flyby checks and reference-ephemeris errors. The gallery never admits a result solely because its saved status says it passed.

Run `python -m unittest discover -s tools -p "test_*.py"` from the repository root for admission regression tests. Offline regeneration can additionally use `--extra-runs PATH --validation-cache PATH` to include new private searches and cross-check their actual JPL event states. Run `tools/audit_integrated_catalog.py` after rebuilding the catalog to attach the integrated concepts’ clearance audits.

## Downloaded trajectory states

Open a mission and select **Trajectory CSV** or **Trajectory XYZV** under its
itinerary. Both contain JD(TDB), x, y, z, vx, vy, vz, relative to the Sun in
Ecliptic J2000, with km and km/s. File notes identify the model and SHA-256.

Lambert downloads propagate full coast initial states analytically under solar
gravity. Adaptive samples target 10 km position agreement at quarter/midpoint
Hermite checks, with at most 10 days between samples; velocities are propagated,
not estimated by differencing preview curves. Ideal impulses are bracketed one
second apart. These arcs join at **planet centers** and are not physical flyby
close-up files. Use desktop finite-radius exports for those, and include the
exporter's additional junction corrections in the budget.

The Cassini recreation is a separate design, arriving about 479 days later.
Its ideal DSM and finite-radius export cost are both stated in its model note.
The six offline Mars examples reconstruct their known zero-revolution Lambert
arcs from rounded public encounter positions; their file notes record this.

After rebuilding the catalog, run
`python tools/build_trajectory_downloads.py` to regenerate both formats offline
from the public `coasts` initial states. `--runs-root PATH` can instead supply
full-precision original candidate records. No JPL query or mission search is
performed. The portfolio's three selected candidates are retained on catalog
rebuilds while their existing admission records pass.
