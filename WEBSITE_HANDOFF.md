# Website selections, exports and historical labels

The graph keeps flight time horizontal and switches its vertical axis between
launch C3 and arrival V-infinity. Visible launch-year fields also control the
Mission limits fields and are preserved in shared links.

Select **Use in desktop app** on the website, save the JSON, and choose
**Import options / website trajectory** in a client built from these sources
(local trial: v0.2.4-test3). The document includes portable search settings and,
for Lambert candidates, the selected dates, branch choices, DSM controls and
reference coast states. It contains no executable commands or local paths.

The app resolves nonplanet identities through JPL, prepares any missing vectors,
and re-evaluates the selected trajectory without launching optimization. It
rejects an import if local states do not reproduce the stored coasts within the
stated tolerances. Geometry and recorded C3/arrival speed are checked; the
inspector reports original and recomputed cruise cost because flyby floors or
powered-flyby settings can change the budget. Imported candidates are not
automatically uploaded.

The public v0.2.3 client can read the search settings but does not implement the
selected-candidate import. Existing integrated concepts export settings only;
their original direct trajectory files remain authoritative.

## Finite flybys

Website Lambert CSVs are labeled analysis data. Their coasts meet at planet
centers. The website's **Build flyby XYZV in app** action now downloads the exact
candidate handoff instead of serving those ideal coast samples as a Celestia
flyby file. **Integrate & export** in the app produces finite-radius SOI patches,
the CSV/XYZV files, clearance results and every explicit impulse.

The exporter already targets finite SOI entry/exit positions and times, but
constructs the planet-centered hyperbolas independently from the heliocentric
coasts. It records velocity disagreements at those joins as
finite_patch_junction impulses. These are neither n-body perturbation
corrections nor proven unavoidable mission costs. A continuous matched-conic
solution must jointly adjust B-plane orientation, encounter timing, asymptotic
velocities and neighboring coasts, subject to minimum-altitude and burn limits.
A radius-only shift does not solve the velocity matching problem.

For a planet-centered hyperbola, periapsis radius is
r_p = planet_radius + altitude. Its asymptotic impact parameter is
B = r_p * sqrt(1 + 2*mu/(r_p*v_inf**2)); it is not equal to periapsis radius.
Finite-SOI targeting also needs the hyperbola orientation and time of flight.
A physically incompatible encounter may still require a DSM or powered flyby.

NASA's [multiple-shooting flyby optimization paper](https://ntrs.nasa.gov/archive/nasa/casi.ntrs.nasa.gov/20190028884.pdf)
describes conversion of lower-fidelity flyby designs to continuous trajectories.
No new joint finite-boundary optimizer is claimed by this UI/export patch.

## Labels and previews

The website can suggest historical names only when every ordered encounter
matches its reference calendar day. Planned dates are labeled planned.
Calendar agreement does not establish flown-state or burn-budget validation.
Custom names remain searchable and are stored locally in the browser; desktop
names remain local to their run.

Red diagnostics remain excluded from background rendering. Explicit selection
requests a preview and gives it priority, while preserving its red classification.
Saturn–Titan screening controls and API endpoints have been removed from the GUI;
the old standalone analysis script is retained for existing research files.

## Google verification

Both GitHub Pages projects include the exact HTML-file verification token.
After the files are deployed, use **Verify** in Search Console and submit
https://robertbarthellgaray.github.io/RoLaMGAS/sitemap.xml.
Verification and sitemap submission do not guarantee indexing or ranking.

## Local validation

- 219 Python solver/backend tests and 14 catalog tests passed.
- 72 JavaScript/browser-logic tests passed.
- Real Edge browser: visible years, time-based axes, mobile layout, download then
  import of the selected Jupiter chain, explicit red preview, removed Titan UI.
- That import reproduced the stored coasts within 0.02834 km and
  8.993e-9 km/s using the bundled daily JPL baseline, without optimization.
- New native binaries remain local pending the user's trial under AGENTS.md.
