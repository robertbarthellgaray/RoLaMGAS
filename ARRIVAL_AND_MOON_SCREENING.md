# Arrival state export and Titan screening

## Arrival altitude / FreeFlyer

Open an existing candidate and set **Arrival altitude above target planet**.
For the saved Venus candidate `f6f8cd0659c3`, enter 200 km and integrate again.
There is no new search requirement: this sets the periapsis of the final finite
planet-centered arrival arc. Lambert screening remains a planet-center
approximation; its arrival V-infinity is not the local periapsis velocity.

By default CSV/XYZV stop at incoming periapsis. Set **Integrate after final flyby**
to continue for the requested number of months (fractions allowed; one month
equals 30.4375 days). No insertion burn, orbit capture or Keplerian orbit is
added. The outgoing hyperbola is numerically integrated under the target planet
until SOI exit, then a Sun-only initial-value integration continues from the same
position/velocity. A shorter duration stops inside the SOI. A custom small-body
target uses its actual incoming spacecraft velocity for a Sun-only continuation.
Later encounters are not automatically retargeted or modeled as new assists.
Required planet ephemerides are read from cache first; missing future coverage
is downloaded in chunks. No extrapolation is used.

`arrival_state.json` continues to record the incoming periapsis state, not the
end of the extended flight. It records both the
heliocentric and planet-relative position/velocity, epoch JD TDB, GM, reference
radius and actual altitude. `arrival_state.csv` contains the relative state in
the same seven-column layout as the full trajectory CSV. The vectors are in
**Ecliptic J2000**, not planet-equatorial, body-fixed or equatorial J2000 axes.
Convert the frame/time scale as required by the external propagator. JSON carries
the detailed metadata; import that with the state rather than assuming defaults.

The old export is copied to `runs/<run>/export_history/<candidate>_<timestamp>`
before reintegration. A changed arrival altitude retargets finite patches, so
review updated junction burns. The search candidate JSON itself is unchanged.

## Saturn → Titan screening

Open a saved search ending at Saturn, expand **Saturn → Titan closest-approach
screening**, choose how many candidates, an assumed Saturn periapsis altitude,
and the number of approach clock angles. Click **Screen & rank Titan approaches**.
Results, distance plots and ranked CSV appear while the independent worker runs.
Stop preserves completed rows. A repeat GUI screen backs up its prior results to
`moon_screen_history`.

Each candidate's Saturn arrival V-infinity and nominal arrival epoch seed a
planet-centered hyperbola. The worker numerically integrates from Saturn SOI
entry through SOI exit. It rotates that solution about its incoming asymptote to
sample B-plane clock angles; a central gravity field makes these rotations exact
for this model, so only one integration is required per candidate.

Hourly **JPL Titan vectors**, relative to the JPL Saturn state, are compared with
the full probe transit. Local distance minima are refined between samples.
Candidates are sorted by their best sampled Titan center distance, with altitude,
relative speed, date/JD, assumed Saturn periapsis and clock angle recorded. The
JSON includes probe/Titan Saturn-relative and probe Titan-relative states at
closest approach, plus ephemeris provenance and integration residuals.

The count selects passing candidates first, then lowest C3 and DSM. It is a
subset of the saved candidates, not another global search. Increase the count
to screen more saved candidates, or clock count for finer orientation sampling.
Changing periapsis is a separate user-controlled screen.

These are **targeting seeds**. The model omits Titan's gravity, solar tides,
Saturn's oblateness/rings, other moons and atmospheric entry. Changing the assumed
B-plane has not been connected back to a retargeted heliocentric coast, and its
upstream correction cost is not established. A predicted small miss or impact
must be refined using the moon's gravity and, for Dragonfly, entry constraints.
Do not interpret these distances as validated flyby/landing altitudes.

Titan reference radius: 2574.76 km, from
[JPL satellite physical parameters](https://ssd.jpl.nasa.gov/sats/phys_par/).

Standalone example, from the explorer directory:

```powershell
python moon_screen.py --run runs\YOUR_SATURN_RUN --cache cache --count 30 --altitude 10000 --clocks 24
```
