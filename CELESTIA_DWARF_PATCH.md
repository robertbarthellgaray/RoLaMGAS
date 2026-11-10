# Optional JPL patch for a Celestia dwarf planet

In a candidate's inspector, the Celestia package section now has **Patch dwarf
planet** and a **Why patch?** popup. Select it before exporting the ZIP.

Celestia's Keplerian approximations can place a dwarf planet millions of km from
its JPL position. The option adds `jpl_dwarf_planet_patch.ssc`, a JPL XYZV file,
and provenance/original orbital fields to the exported addon. It covers the
calendar year(s) of the target encounters; it does not extend across a decades-long
post-flyby coast. Before and after that interval, the source Celestia orbit and
reference frame are restored. There may be a position jump at the interval
boundaries, away from the flyby.

The patch uses `Modify` so existing textures, shape and other appearance fields
remain available. Each timeline phase retains the original body frame and
rotation model. An implicit rotation period is pinned to its old value before
the Keplerian orbit is replaced by an aperiodic sampled trajectory.

The app reads an installed `Celestia/data/dwarfplanets.ssc` on Windows when found;
the popup also accepts another catalog path. A portable, attributed orbit-only
snapshot is bundled for machines without an accessible installation. Objects
that cannot be matched to an original definition are not silently created.

**Identity matters:** a Pluto Barycenter (Horizons 9) target patches the
Pluto–Charon reference point, retaining Pluto's local binary offset. A physical
Pluto target patches Pluto itself. This does not convert a barycenter encounter
distance into a surface altitude, and does not independently correct moon
ephemerides. The target identity and source ephemeris checksums are retained in
`reports/dwarf_planet_patch.json`.

Missing encounter-year vectors are downloaded from JPL with the app's normal
verified TLS and cache handling. Cached data work offline. Physical Pluto uses
3-hour data to resolve its binary motion; other supported targets use daily
data. Existing spacecraft trajectory samples are not moved by this option.

Extract the ZIP and copy the entire addon folder to Celestia `extras`. The app
does not write to Program Files. Do not install overlapping dwarf-planet patches
for the same object and dates. Delete the optional patch SSC from the addon to
undo it. Patched and unpatched packages have separate folder/ZIP names; install
only one version to avoid duplicate spacecraft.
