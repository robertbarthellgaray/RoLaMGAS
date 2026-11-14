# Titan lookup and Dragonfly arrivals

The resolver searches the combined JPL Horizons index before fetching SBDB
orbital elements for small bodies. Titan, Titan (SVI), and SPK=606 identify Titan.
Numeric queries can match both a moon ID and an asteroid number; ambiguity is
displayed, with explicit SPK selections. Spacecraft/asteroid name collisions
are also displayed.

Titan resolves as a natural satellite of Saturn. The GUI explains the model
limitation and offers **Search Saturn arrivals instead**, explicitly selecting
Saturn and EES / EdvES routes. This does not claim to target Titan. Moon-target
requests are rejected before starting a search or integration, including old
cached moon descriptors, because the current Sun-only terminal model would
omit the planet's gravitational bending.

## Target a moon from a selected Saturn trajectory

Select a Saturn-arrival candidate, open its route menu, then expand **Target a
moon**. Pick Titan or another supported Saturn moon, and select:

- **Closest approach**: altitude above the mean surface, with zero moon-relative
  radial velocity at the selected arrival epoch. This targets a true periapsis.
- **Impact**: an inbound geometric surface intersection in vacuum. It does not
  model atmospheric entry, surface shape, landing or impact survival.
- **Titan entry interface**: stop at an illustrative inbound altitude (1,270 km
  by default). This does not optimize flight-path angle or landing location.

Optional Titan approach inclination is measured from its IAU equator (0°
prograde equatorial, 90° polar). An extra encounter-clock control and plane-angle
constraint are solved together with the SOI match; the independent endpoint
must agree within 0.001°. The reported plane is an osculating incoming plane,
not a captured orbit. Some inclinations are unreachable for the incoming
asymptote. No free plane-change burn or landing-site claim is inserted. The
Titan pole is from JPL NAIF pck00011.tpc. Other moons currently leave inclination
unconstrained.

Alternatively, choose **Target a point in Titan’s rotating frame** for entry or
vacuum impact. The solver transforms planetocentric latitude and east-positive
longitude into an inertial target at the encounter epoch using NAIF's
IAU_TITAN pole and prime meridian. It uses W=186.5855+22.5769768*d degrees,
with d from J2000 noon, rather than approximating orbital phase as elapsed days
times a fixed true anomaly. The JPL Titan vectors supply its actual location.
The prime meridian is approximately Saturn-facing; eccentricity and the adopted
orientation model permit libration. The endpoint report includes rotating-frame
longitude, latitude and velocity with the rigid rotation subtracted (no winds).

For entry mode, these are **entry-interface subpoint coordinates**, not landing
coordinates. During descent both the ground track and Titan's rotating surface
move; atmospheric drag, winds, lift and parachutes matter. The default 4° N,
162.5° E comes from a published Selk-area study, not an exact current landing
coordinate. An EDL model is required to connect an entry state to a landing
ellipse. A fixed point and a separate inclination constraint are not combined by
this local solver. If the requested point is on an inaccessible side at this
epoch, it reports failure rather than moving the point or inserting a free burn.

The worker first makes or reuses the candidate's finite-radius interplanetary
export. It takes an actual saved state inside the last Sun-only coast, preserving
all earlier legs and flybys. A real cruise DSM changes the final approach.
Inside Saturn's SOI it integrates Saturn gravity and the selected moon's
differential point-mass acceleration, including acceleration of the origin.
The boundary position and epoch are adjusted until all three velocity components
match continuously. **No burn is applied at Saturn SOI entry.**

Quick mode tests one cruise-burn epoch. Standard mode compares three, retaining
the lowest added burn that passes independent propagation. This is a small timing
search, not a global minimum. The arrival epoch stays fixed. Some candidates,
moons or dates cannot be connected by this local search.

The UI reports elapsed time and boundary trials, supports Stop, and saves each
branch separately. Download the full launch-to-moon CSV/XYZV, parent-relative
approach, endpoint state, explicit burns, trial results and numerical report.
Branches above the requested added-burn limit remain downloadable with a warning.
Launcher injection is listed separately and excluded from the onboard cruise sum;
replaced source terminal burns are also excluded.

An independent Sun integration carries its numerical state directly into the
Saturn/moon integration. The source join, SOI velocity match, endpoint, tangent
condition (approach mode) and earlier sampled moon distances are checked. Saturn
and the selected moon have surface events. This is not an all-moon collision,
ring, radiation or operational mission audit. Solar tides inside the SOI, other
moons, J2, atmospheric drag/heating and navigation uncertainty are omitted.

The interplanetary search itself still targets the parent planet. A direct
Sun-only Earth-to-Titan Lambert leg is not accepted as a physical Titan arrival.

At Titan's orbital distance an illustrative Saturn-centered speed is
`sqrt(v_inf_Saturn**2 + 2*mu_Saturn/r_Titan)`. Titan's velocity must then be
subtracted as a vector. Saturn-arrival V-infinity is not Titan entry speed.
Intersecting Titan's heliocentric ephemeris with a Sun-only Lambert leg does
not validate the actual arrival.

Dragonfly uses direct atmospheric entry, descent and landing rather than a
propulsive Titan orbit insertion followed by repeated aerobraking. NASA's 2025
entry study describes entry interface at 1,270 km altitude and atmosphere-relative
speed above 7 km/s. The new Titan entry mode uses this illustrative interface altitude;
its speed and flight-path angle remain computed outputs, not validated EDL constraints.

Sources:

- [JPL Horizons Lookup API](https://ssd-api.jpl.nasa.gov/doc/horizons_lookup.html)
- [NASA: Static Aerodynamics of the Dragonfly Entry Vehicle](https://ntrs.nasa.gov/citations/20250011502)

The old Saturn → Titan screening mode is separate from the new targeted branch.
It ranks nominal close approaches without a Titan terminal constraint; see
[ARRIVAL_AND_MOON_SCREENING.md](ARRIVAL_AND_MOON_SCREENING.md).

The published **Dragonfly-style Titan entry** case retains the earlier EdvES
transfer and targets entry in November 2035. It is an illustrative reconstruction,
not the official operational Dragonfly ephemeris or a landing simulation.

For a separate atmospheric continuation from the saved Titan-relative endpoint,
see [TITAN_ENTRY.md](TITAN_ENTRY.md). Default propagation stops at the Mach-1.5
parachute handoff; its optional full-descent scenario is explicitly illustrative.
