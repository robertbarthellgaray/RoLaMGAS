# Finite-SOI export targeting

The desktop export option **Reduce patch burns by jointly targeting legs and
flybys** adjusts the finite flyby geometry and preceding coasts together. It
does not simply remove impulses from the burn table. Every remaining junction
velocity difference is retained as an explicit vector burn.

The **Maximum intermediate flyby date adjustment** setting is 0–2 days.
Set it to **0** to keep all flyby dates fixed. Launch, final encounter and
existing DSM epochs stay fixed in both modes. Departure energy may change
within the user's C3 limits and within approximately 10.6% of the source C3.
Flyby altitudes remain above their configured floors. The source candidate,
search results and shared record are unchanged: this is a separate export variant.
Exact epoch windows in the search describe the original candidate; the export
date-adjustment control separately bounds changes to intermediate periapsis dates.

The matcher varies periapsis orientation, radius, asymptotic speed, allowed
intermediate dates and the positions of existing DSMs. It adds no DSM epochs.
Solar Lambert coasts target the actual finite patch positions. A bounded local
least-squares fit reduces velocity discontinuities, and a variant is adopted
only when its explicit total cruise impulse cost is lower. This is not a proof
of minimum fuel or of a feasible optimized solution for every candidate.
Intermediate zero-gravity body turnarounds are retained without local refinement.

Reports include:

- `exported_launch_c3_km2_s2`: departure energy of the exported variant.
- `finite_targeting.json`: before/after dates, altitudes and analytic burn totals.
- `encounters.csv`: actual exported periapsis epochs and altitudes.
- `burns.csv`: all remaining DSM, periapsis and SOI-junction impulses.
- `integration_report.json`: numerical errors, burn limits and available clearance checks.

The force model remains Sun-only outside planned SOIs and encounter-planet-only
inside each planned SOI. Planet ephemerides translate frames and check
clearances; this is not an n-body propagation. The final target's flyby aimpoint,
arrival altitude and requested inclination are retained. Remaining corrections
are not claimed to be optimal and can include SOI-entry impulses.

## Resonant-coast regression

Near a full heliocentric revolution, replacing planet-center endpoints with
finite SOI points can move the endpoint angle across 0/360 degrees. The Lambert
integer `M` must then change even though the physical orbit stays the same.
The exporter now matches the reference coast's swept angle to the finite
endpoint angle instead of carrying over the old integer blindly. It retains
prograde/retrograde motion and compares the velocities of both Lambert paths.

Candidate `8458adb53518` exposed this: the old Earth–Earth export inserted
**5.0060 and 5.0498 km/s** junction burns. Correcting the winding removes that
branch error. With a maximum two-day intermediate-date adjustment, the tested
local refinement reduced additional patch burns from **11.60327 km/s** to
**0.04944 km/s**, and total cruise impulses from **11.91934 km/s** to
**0.27898 km/s**. The DSM becomes **0.22836 km/s**, small periapsis corrections
total **0.00118 km/s**, and C3 changes from **11.91503** to **10.93285 km²/s²**.
Intermediate dates move by at most **1.55165 days** in that particular variant.
Launch and Chariklo arrival stay fixed. The available Sun/Earth/Venus/Jupiter
clearance checks pass; other planets lack full-span cached clearance coverage.
This example is not a guarantee that every candidate can be repaired cheaply.
With all intermediate flyby dates fixed, the separate test gives **0.84971 km/s**
of patch corrections and **1.13203 km/s** total cruise impulses, at exported
C3 **11.40267 km²/s²**. Both examples pass their individual burn limits.

## Command line

```sh
python integrate_export.py --candidate candidate.json --config request.json --output export --refine-patches --patch-epoch-shift-days 0
```

Use `--patch-epoch-shift-days 2` to permit small date adjustments, or
`--no-refine-patches` to inspect the finite export without local matching.

Background: [iterative patched-conic trajectory design](https://doi.org/10.1016/j.actaastro.2021.04.021)
and [JPL's constrained multi-flyby targeting formulation](https://ntrs.nasa.gov/citations/20210003861).
The implementation here uses its own bounded local fit, not those authors' code.
