# Static trajectory gallery

Served at https://robertbarthellgaray.github.io/RoLaMGAS/ through GitHub Pages.

No build step or Python backend is required. Serve this directory with any static HTTP server. All asset URLs are relative so the gallery works at a project subpath.

`data/index.json` contains the small filter catalog. Detailed paths load on selection from `data/cases/`. SVG card plots are generated offline. `downloads/` contains the two original integrated XYZV files; the browser never generates or integrates new trajectories.

RoLaMGAS.png is the original artwork supplied by Robert Barthell Garay.

The offline catalog builder is `../tools/build_public_catalog.py`. Its input trajectory project is not part of this public repository. Existing numeric examples are sufficient to run the gallery.

## Catalog admission

The public examples prioritize distinct assist sequences before metric tradeoffs. Small-body destinations are Pluto, Eris and 2026 ED138. P denotes Pluto, Er Eris and X 2026 ED138. Eris uses JPL’s long-term system-barycenter solution; the primary-body table ends in 2030.

`data/catalog_audit.json` records admission rules, independent endpoint errors, route coverage and clearance checks for both original integrated concepts. Individual Lambert JSON files retain recomputed flyby checks and reference-ephemeris errors. The gallery never admits a result solely because its saved status says it passed.

Run `python -m unittest discover -s tools -p "test_*.py"` from the repository root for admission regression tests. Offline regeneration can additionally use `--extra-runs PATH --validation-cache PATH` to include new private searches and cross-check their actual JPL event states. Run `tools/audit_integrated_catalog.py` after rebuilding the catalog to attach the integrated concepts’ clearance audits.
