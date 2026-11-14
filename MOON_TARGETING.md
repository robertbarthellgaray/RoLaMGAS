# Target a moon from a parent-planet arrival

Type **Europa** (or **Europa (JII)**) under Horizons object and resolve it.
RoLaMGAS recognizes JPL moon ID 502, selects **Jupiter** as the interplanetary
destination, and retains Europa as the desired moon. Known supported moon names
and IDs also resolve offline. A numbered asteroid such as **52 Europa** still
goes through the separate Horizons object resolver.

Click **Find parent-planet arrivals** or **Start search**. The existing
repository-first search queries Jupiter candidates under your launch dates,
C3, flight-time and arrival-speed limits. All offered Jupiter sequences are
initially selected for a moon search; you can narrow them. Returned candidates
are independently re-evaluated. If at least three pass, the app asks whether to
run a CPU search too; otherwise it follows the usual local-search fallback.
These are Jupiter arrival candidates until the separate moon calculation passes.
Their listed arrival V-infinity is relative to Jupiter, not Europa.

Open a candidate and expand **Target a moon**. Europa is preselected when this
search was made for it. You can also select a moon directly from any saved
parent-planet candidate, without first resolving its name.

- **Closest approach altitude** targets a tangent periapsis above the moon's
  mean spherical radius at the candidate's arrival date.
- **Impact** targets an inbound geometric intersection with that spherical
  surface at the same date. It is not a landing or atmospheric-entry simulation.
- Titan retains its separate illustrative entry-interface, inclination and
  body-fixed point options. Those fields are hidden for other moons.

The worker first makes/reuses the finite-radius interplanetary export. It keeps
earlier trajectory states through the new correction, then joins a Sun-only
cruise to a parent-centered arc with parent gravity plus differential target-moon
gravity. It matches both position and velocity at the planet's sphere of
influence; no artificial SOI impulse is inserted. This parent gravity is why
simply aiming a heliocentric Lambert arc at the moon's future location is
insufficient.

Standard effort scans up to five correction epochs over the final solar leg,
then refines the timing near the best feasible result. Times too close to or
inside the SOI are excluded. Quick effort tries one timing. Every retained result
is independently propagated through both arcs. The report describes the minimum
found; it does not establish a global optimum across all encounter geometries.
An impossible geometry or one requiring an expensive correction may still fail
or exceed the user's added-burn limit. The app reports that outcome explicitly.

The full Sun-centered CSV/XYZV, parent-relative approach, moon-relative endpoint
state, added burn vector/date, timing trials and plots are saved as a separate
branch. Existing parent trajectories are preserved. Progress/elapsed time keep
updating during calculations, and Stop requests interrupt numerical steps.
Moon branches are not automatically uploaded to the public trajectory library.

Supported targets in this preview:

| Parent | Moons |
| --- | --- |
| Mars | Phobos, Deimos |
| Jupiter | Europa, Io, Ganymede, Callisto |
| Saturn | Titan, Enceladus, Rhea, Dione, Tethys, Iapetus, Mimas, Hyperion, Phoebe |
| Uranus | Ariel, Umbriel, Titania, Oberon, Miranda |
| Neptune | Triton |

Physical constants and radii are from [JPL's satellite parameters](https://ssd.jpl.nasa.gov/sats/phys_par/).
Geometric Ecliptic J2000 vectors are fetched from Horizons and cached locally.
The local model does not include other moons, rings, oblateness, radiation,
terrain or navigation uncertainty. Surface means the stated mean-radius sphere;
this is not an operational full-system collision or mission-safety audit.

## Export the calculated moon branch

When targeting finishes, click **Use this moon targeting**. The choice is saved for that candidate. CSV, XYZV and Celestia packages now use the saved full launch-to-moon trajectory, its burn list and its moon-relative endpoint. The exporter does not reintegrate it as a planet arrival. **Use original planet trajectory** restores the previous export source. Planet-arrival altitude, inclination, refinement and post-flyby settings are disabled while the saved moon branch is selected; recalculate targeting to change that branch.

The package offers separate **Patch arrival planet with JPL data** and **Patch targeted moon with JPL data** checkboxes. Selecting a moon branch initially checks both. The planet patch is Sun-relative; the moon patch subtracts the parent position AND velocity. The patch retains the exact solver cache tables and their interpolation knots within their original coverage. **JPL patch duration · days (total)** defaults to 14 days and is centered on the encounter, half before and half after. A moon patch is automatically expanded to at least one osculating orbital period, computed from the JPL moon/parent relative state and GMs. If additional time coverage is needed, the exporter downloads and caches JPL tables outside the original interval without replacing its interior knots. Requests up to 3652.5 days are accepted; large windows can take time to download and produce large packages. The generated provenance report records requested/effective duration and the orbital-period calculation. Sub-millisecond Julian-date roundoff is clamped at table edges; real extrapolation is rejected. Original Celestia orbits resume outside this window. Existing textures, shapes and rotation models remain; this is a position/velocity patch, not a surface-orientation or terrain correction. Disable other addons overriding the same bodies.

Packages identify the selected branch and include `moon_report.json`, its burns, the original source report and JPL patch provenance. Moon branches must pass independent propagation and source/parent clearance checks. Deliberate impact at the selected moon endpoint is supported; other moons, rings, atmosphere and surface topography are not screened or simulated. A branch with changed source-candidate or trajectory checksums must be recalculated or explicitly reselected.
