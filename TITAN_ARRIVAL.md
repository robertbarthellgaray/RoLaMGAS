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

## Physical arrival model still required

1. Search Earth–Earth–Saturn and Earth–DSM–Earth–Saturn opportunities. Arrival
   V-infinity here is relative to Saturn, not Titan.
2. Replace the planet-center approximation with a finite Saturn-system arrival.
   Vary the incoming B-plane, epoch and upstream targeting correction to connect
   the heliocentric approach to a Saturn-centered hyperbola that intercepts Titan
   at the correct orbital phase. No Saturn orbit insertion is inherently needed.
3. Include Titan's gravity near the moon and target atmospheric entry altitude,
   flight-path angle and atmosphere-relative velocity. Preserve state continuity
   and report all corrections.
4. A separate atmosphere/entry model is needed for deceleration, parachute descent
   and landing. A vacuum trajectory should end at entry interface rather than
   artificially stop, pass through Titan or teleport to its surface.

At Titan's orbital distance an illustrative Saturn-centered speed is
`sqrt(v_inf_Saturn**2 + 2*mu_Saturn/r_Titan)`. Titan's velocity must then be
subtracted as a vector. Saturn-arrival V-infinity is not Titan entry speed.
Intersecting Titan's heliocentric ephemeris with a Sun-only Lambert leg does
not validate the actual arrival.

Dragonfly uses direct atmospheric entry, descent and landing rather than a
propulsive Titan orbit insertion followed by repeated aerobraking. NASA's 2025
entry study describes entry interface at 1,270 km altitude and atmosphere-relative
speed above 7 km/s. These are reference parameters, not constraints enforced by
the explorer.

Sources:

- [JPL Horizons Lookup API](https://ssd-api.jpl.nasa.gov/doc/horizons_lookup.html)
- [NASA: Static Aerodynamics of the Dragonfly Entry Vehicle](https://ntrs.nasa.gov/citations/20250011502)

This update implements identification and the explicit model boundary. The
Saturn/Titan arrival and atmospheric propagation stages are not yet implemented.

The later **Saturn → Titan screening** mode now propagates nominal Saturn
approaches and ranks Titan distances as targeting seeds. It is separate from
moon-terminal Lambert searches and does not include Titan gravity or entry.
See [ARRIVAL_AND_MOON_SCREENING.md](ARRIVAL_AND_MOON_SCREENING.md).
