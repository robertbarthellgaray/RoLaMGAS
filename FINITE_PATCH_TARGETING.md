# Finite-SOI export targeting

The desktop export option **Reduce patch burns by jointly targeting legs and
flybys** adjusts the finite flyby geometry and preceding coasts together. It
does not simply remove impulses from the burn table. Every remaining junction
velocity difference is retained as an explicit vector burn.

The **Maximum intermediate flyby date adjustment** setting is 0–365.25 days,
with a two-day default.
Set it to **0** to keep all flyby dates fixed. Launch, final encounter and
existing DSM epochs stay fixed in both modes. Departure energy may change
within the user's C3 limits and within approximately 10.6% of the source C3.
Flyby altitudes remain above their configured floors. The source candidate,
search results and shared record are unchanged: this is a separate export variant.
Exact epoch windows in the search describe the original candidate; the export
date-adjustment control separately bounds changes to intermediate periapsis dates.

The matcher varies periapsis orientation, radius, asymptotic speed, allowed
intermediate dates and the positions of existing DSMs. It adds no DSM epochs.
Solar Lambert coasts target the actual finite patch positions. Bounded local
least squares initializes a constrained sum-of-impulses optimization. Larger
windows start from the same narrow-window fit, retain the best feasible result,
and obey the individual DSM/patch and total cruise caps. A final continuity
polish can reduce patch burns only within the total budget already achieved.
A variant is adopted only when its explicit total cruise impulse cost is lower. This is not a proof
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
clearances; this is not an n-body propagation. The final encounter date and
arrival altitude are retained. An unspecified planetary arrival plane may be
refined, with its capture assessment recomputed. An explicit arrival-inclination
target keeps its original terminal geometry; a minor-body aimpoint stays fixed. Remaining corrections
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

## Expanded-window CLAUDIUS test

The user's app candidate `61a83e8f369c` is a Lambert reconstruction of CLAUDIUS,
separate from the original n-body project. The earlier two-day export had
**177.484 m/s** in patch corrections, a **737.531 m/s** retargeted DSM, and
**915.060 m/s** total cruise impulses. Its DSM exceeded the 700 m/s cap.

A 30-day window with the expanded finite-geometry fit gives **7.479 m/s**
additional patch corrections and **628.365 m/s** total cruise impulses, with
exported C3 **29.03872 km²/s²** and Uranus arrival V-infinity **5.35181 km/s**.
Earth shifts 0.43753 days earlier, Jupiter 5.99558 days earlier. Launch and
December 2045 Uranus arrival remain fixed, and all individual burn limits pass.
The reported local optimizer may stop at its iteration limit; the accepted
variant is independently integrated and budgeted, not claimed to be optimal.
Original CLAUDIUS files and its Uranian moon tour remain separate and unchanged.

The independent batch tool `tools/refresh_finite_downloads.py` reviews curated
downloads, defaults to a 100 m/s total patch-correction publication threshold,
checks burn caps, budgets and serialized interpolation, and preserves original
files. It uses the website's exact desktop handoff builder and refuses to
substitute different JPL coast states when a source cannot be reproduced.

The November 12 refresh reviewed 129 portable candidates and accepted 117
replacement downloads. Twelve retain their prior files; the original CLAUDIUS,
Tianwen-4 and Mercury integrated cases also retain their original models.
The machine-readable results are in `docs/data/finite_download_review.json`.
Each accepted variant links its actual encounter dates, complete burn table,
targeting changes and previous files. Its source preview remains unchanged.
Clearance checks cover bodies with cached data spanning the exported interval,
not an exhaustive search for unplanned encounters.

Desktop handoffs now retain the original Julian dates at microsecond calendar
precision. JavaScript's millisecond date rounding otherwise prevented exact
reproduction of the long eight-planet reconstruction. No source-state acceptance
tolerance was relaxed. With a 30-day search window, that reconstruction's refined
variant has 18.900 m/s of patch corrections and 63.486 m/s total cruise impulses;
it remains a patched-conic reconstruction, not the player's flown n-body solution.

## Command line

```sh
python integrate_export.py --candidate candidate.json --config request.json --output export --refine-patches --patch-epoch-shift-days 0
```

Use `--patch-epoch-shift-days 2` to permit small date adjustments, or
`--no-refine-patches` to inspect the finite export without local matching.

Background: [iterative patched-conic trajectory design](https://doi.org/10.1016/j.actaastro.2021.04.021)
and [JPL's constrained multi-flyby targeting formulation](https://ntrs.nasa.gov/citations/20210003861).
The implementation here uses its own bounded local fit, not those authors' code.
