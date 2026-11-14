# RoLaMGAS 0.2.6

Select a supported moon, reuse an arrival at its parent planet, and calculate
a separate moon-impact or approach branch. Export the path you selected as
CSV, XYZV or a complete Celestia package.

- Known moon searches select the parent planet's repository arrivals and keep
  the requested moon for the targeting stage. Supported systems: Mars,
  Jupiter, Saturn, Uranus and Neptune.
- The targeting stage scans correction timings and refines the best found
  solution. Its report lists the actual upstream burn, retained cruise burns,
  independent propagation errors and budget checks. The SOI handoff is continuous.
- **Use this moon targeting** selects the saved simulation for all exports.
  Click the selected button again to cancel, or use **Use original planet
  trajectory**. Selecting a branch never deletes the original path.
- Optional Celestia JPL patches cover the parent planet and target moon. The
  planet is Sun-relative; moon position and velocity are parent-relative.
  Existing textures, shapes and rotation models are retained.
- **JPL patch duration · days (total)** sets a centered window, half before
  and half after encounter. Default: 14 days. Moon patches expand to at least
  one osculating orbital period. Missing coverage is downloaded and cached;
  the original targeting-table knots are preserved inside their original span.
- Fixes fractional-Julian-date rounding that caused **Nonfinite JPL patch
  vectors for Ganymede**. Real extrapolation is rejected.
- Moon branches and packages retain provenance, source/trajectory checksums,
  their distinct Celestia object names, burn reports and moon-relative endpoint.

Titan additionally supports an illustrative entry-interface or rotating-frame
point target and an optional approach inclination. These are not atmospheric
descent, landing or captured-orbit simulations. New terminal arcs use the
parent and targeted moon; other moons, rings, J2 and topography are omitted.
Impact mode deliberately ends at the selected moon's modeled mean-radius
surface. Independent propagation is not a full-system collision certification.

Local verification included actual Europa and Ganymede arrival branches,
compiled GUI exports, selectable durations and cancellation, and isolated
Celestia position checks. See [MOON_TARGETING.md](MOON_TARGETING.md).

The public gallery now shows verified JPL names before minor-planet numbers
and refreshes new target identities every six hours. Existing identities are
rechecked every 30 days; old numeric target links continue to work.

Updating the app preserves searches and caches in the existing data directory.
Windows: extract the whole ZIP and keep `_internal` beside `RoLaMGAS.exe`.
Mac packages remain unsigned. Source is included under GPLv3.
