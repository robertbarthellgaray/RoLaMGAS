# Optional JPL patch for a Celestia small body

In a candidate's inspector, select **Patch small body with JPL data** before
exporting its Celestia package. The **Why patch?** popup explains the option.
It supports existing Keplerian definitions for asteroids, comets, centaurs,
trans-Neptunian objects and dwarf planets.

Celestia's Keplerian approximations can place a small body millions of km from
its JPL position. The option adds a patch SSC, a JPL XYZV file,
and provenance/original orbital fields to the exported addon. It covers the
calendar year(s) of the target encounters; it does not extend across a decades-long
post-flyby coast. Before and after that interval, the source Celestia orbit and
reference frame are restored. There may be a position jump at the interval
boundaries, away from the flyby.

The patch uses `Modify` so existing textures, meshes, rings and other appearance fields
remain available. Each timeline phase retains the original body frame and
rotation model. An implicit rotation period is pinned to its old value before
the Keplerian orbit is replaced by an aperiodic sampled trajectory.

On Windows the app searches `dwarfplanets.ssc`, `asteroids.ssc`, `comets.ssc`,
`interstellar.ssc`, `outersys.ssc` and `solarsys.ssc` in installed `Celestia/data`.
Chariklo, for example, is defined in `outersys.ssc`. The popup accepts another
addon's original `.ssc` path. A portable, attributed snapshot of 107 orbit
definitions is bundled for machines without an accessible installation. Source
hashes and attribution accompany the copied fields. Missing or ambiguous
objects are not silently created or substituted. Conflicting comet designations
cannot be overridden by shared names such as ATLAS; the selected Horizons
apparition is retained when downloading vectors.

**Identity matters:** a Pluto Barycenter (Horizons 9) target patches the
Pluto–Charon reference point, retaining Pluto's local binary offset. A physical
Pluto target patches Pluto itself. This does not convert a barycenter encounter
distance into a surface altitude, and does not independently correct moon
ephemerides. The exact target identity, original fields, source catalogs,
ephemeris provenance and XYZV checksum are retained in a JSON report.

Asteroid/comet exports use `jpl_small_body_patch.ssc` and
`reports/small_body_patch.json`. Dwarf-planet exports retain the older
`jpl_dwarf_planet_patch.ssc` and `reports/dwarf_planet_patch.json` filenames.
Package manifests provide both `small_body_patch` and the legacy
`dwarf_planet_patch` key for compatibility.

Missing encounter-year vectors are downloaded from JPL with the app's normal
verified TLS and cache handling. Cached data work offline. Comets use hourly
samples; physical Pluto and other targets with perihelion below 0.5 AU use
3-hour samples; other supported targets use daily samples. Exact encounter
epochs are included. This visualization patch does not replace mission-specific
accuracy checks near exceptionally rapid perihelion motion. Existing spacecraft
trajectory samples are not moved by this option.

Extract the ZIP and copy the entire addon folder to Celestia `extras`. The app
does not write to Program Files. Do not install overlapping small-body patches
for the same object and dates. Delete the optional patch SSC from the addon to
undo it. Patched and unpatched packages have separate folder/ZIP names; install
only one version to avoid duplicate spacecraft.
