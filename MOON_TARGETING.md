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

When targeting finishes, click **Use this moon targeting**. The choice is saved for that candidate. CSV, XYZV and Celestia packages use that branch, its burn list and its moon-relative encounter state. **Use original planet trajectory** restores the previous export source. Planet-arrival altitude, inclination and refinement stay disabled; recalculate targeting to change the encounter.

For a **closest-approach** branch, **Integrate after final flyby · months** also works with the selected moon trajectory. It continues the existing terminal state under parent plus differential targeted-moon gravity until the outbound parent SOI crossing, then under Sun-only gravity. No burn is added. The original source file remains unchanged; continuation files are cached separately by source checksum and duration. Zero months restores the original branch. Impact and atmospheric-entry branches stop at their interface and cannot be continued through the surface with this vacuum model. Reports record continuity, a numerical tolerance cross-check and whether the outgoing solar conic escapes or stays bound. Later encounters, other moons and interstellar forces are not included.

The package offers separate **Patch arrival planet with JPL data** and **Patch targeted moon with JPL data** checkboxes. Selecting a moon branch initially checks both. The planet patch is Sun-relative; the moon patch subtracts the parent position AND velocity. The patch retains the exact solver cache tables and their interpolation knots within their original coverage. **JPL patch duration · days (total)** defaults to 14 days and is centered on the encounter, half before and half after. A moon patch is automatically expanded to at least one osculating orbital period, computed from the JPL moon/parent relative state and GMs. If additional time coverage is needed, the exporter downloads and caches JPL tables outside the original interval without replacing its interior knots. Requests up to 3652.5 days are accepted; large windows can take time to download and produce large packages. The generated provenance report records requested/effective duration and the orbital-period calculation. Sub-millisecond Julian-date roundoff is clamped at table edges; real extrapolation is rejected. Original Celestia orbits resume outside this window. Existing textures, shapes and rotation models remain; this is a position/velocity patch, not a surface-orientation or terrain correction. Disable other addons overriding the same bodies.

Packages identify the selected branch and include `moon_report.json`, its burns, the original source report and JPL patch provenance. Moon branches must pass independent propagation and source/parent clearance checks. Deliberate impact at the selected moon endpoint is supported; other moons, rings, atmosphere and surface topography are not screened or simulated. A branch with changed source-candidate or trajectory checksums must be recalculated or explicitly reselected.

Planet/moon XYZV playback patches are now thinned independently of the solver tables. Cubic Hermite interpolation is checked at original source knots and quarter points against 0.05 km position and 0.000001 km/s velocity tolerances; the encounter and patch endpoints are retained. The provenance report records checked errors and retained sample count. This is an interpolation check against the cached JPL solution, not a claim about its absolute observational accuracy.


Local v0.2.8 preview adds Pluto (Horizons 999) with Charon, Nix, Hydra, Kerberos and Styx. Numbered Pluto aliases resolve to the physical center; barycenter 9 remains separate. Pluto/Charon gravity is included for the outer-moon targeting and continuation. Kerberos and Styx use massless-target gravity approximations because JPL lists only upper limits for their GM; their reported mean radii still define geometric approach/impact surfaces. Other moons, atmospheric effects and nonspherical shape/terrain remain omitted. Other dwarf-planet systems require independently sourced parent/moon physical parameters before being added.

Physical parameters: https://ssd.jpl.nasa.gov/sats/phys_par/sep.html (PLU060). The satellite list and mean radii are not a terrain or full-system navigation model.

Celestia exports now have Patch target (major planet or small body) and Patch targeted moon. Small-body patches default to a total 365.25 days, centered on the final encounter; duration can be entered in years or days, up to ten years. The optional maximum playback interval is entered in hours. Small-body automatic intervals are 3 hours for physical Pluto, 1 hour for comets/very small perihelia, and 1 day for slowly moving small bodies. A user-selected coarser small-body interval sacrifices playback fidelity. Planet/moon outputs are checked for interpolation error and may retain additional points. Original orbital definitions resume outside the window.

Legacy Windows-1252 Celestia catalogs and catalogs without SPDX headers are accepted without inventing a source license. Actual out-of-range ephemeris requests remain prohibited; errors identify the body and available dates. Sub-millisecond Julian-date conversion roundoff is clamped to the endpoint.


## Expanded moon catalog (0.2.9 preview)

The offline catalog, dated 2026-11-20, combines JPL's planetary satellite elements,
physical-parameter table and Small-Body Satellites API. After duplicate Pluto
entries are merged, it lists 992 moons/reported satellites across 523 parent
systems. See `celestia_assets/moon_catalog.csv` for every entry and its data status.
The catalog includes unconfirmed reports, identified as unavailable for targeting.

Target a moon is shown for any catalogued parent, including Eris aliases and
numbered small-body names. Current data supports 464 moon targets. A measured
radius permits surface-altitude approaches and vacuum geometric impact. Where a
planetary moon has an ephemeris but no measured radius, the field explicitly
changes to distance from its center and surface impact is disabled. Unknown moon
mass is treated as zero with a massless-target note; it does not provide a
predicted gravity assist. Systems without a usable orbit/identity or parent
physical model remain listed with an explanation instead of inventing parameters.

Eris's current integrated heliocentric orbit and the Eris/Dysnomia precomputed
satellite solution are separate datasets. The former can extend to 2500; the
Dysnomia satellite table currently ends in 2030. The default uses only published
JPL coverage. An unchecked **Allow approximate moon orbit projection outside JPL
coverage** control enables a two-body reference-orbit model for supported small
body systems. It adds the projected relative orbit to the current integrated
system-barycenter motion, retaining the primary's barycentric displacement.
Future moon phase is uncertain. Reports, UI and generated patch comments mark
these outputs approximate. Projected cache tables are excluded from normal
JPL-only queries. Continuation retains the chosen model and provenance.

GMs quoted as a range use its nominal midpoint, explicitly recorded with the JPL
range. This does not replace a spacecraft-grade mass/orbit uncertainty analysis.
Catalog and reference data sources: https://ssd.jpl.nasa.gov/sats/elem/ ,
https://ssd.jpl.nasa.gov/sats/phys_par/ , https://ssd-api.jpl.nasa.gov/doc/sb_sat.html ,
https://ssd.jpl.nasa.gov/horizons/ .

The default correction search now uses one upstream timing (35% of the final coast). The optional scan still tries several timings and refines the best. A completed moon branch can be selected directly by checking **Patch targeted moon**; the separate selection button remains available. Numbered small-body names and their catalog aliases are compared as the same parent during export, with candidate and trajectory checksums still enforced.
