# Decadal Survey mission-study seeds

The official [2011 Appendix G](https://nap.nationalacademies.org/reports/13117/appendix_g.html)
and [NASA mission-study index](https://science.nasa.gov/planetary-science/resources/documents/)
provide 56 report links: 31 older mission/option/technology PDFs, 11 completed
2020 studies and 14 completed 2022 studies. These are report files, not 56
independent interplanetary trajectories.

The machine-readable index is [decadal_sources.json](../../departure_seeds/decadal_sources.json).
Nineteen selected reports were downloaded and text-extracted locally. PDFs and
extracted full text remain in the ignored `cache/decadal_reports` folder. The
Orbilander PDF exceeded the downloader's 64 MiB cap and was not inspected.

## New timing guesses

[decadal_missions.json](../../departure_seeds/decadal_missions.json) adds nine
eligible references to the existing historical seed loader. Every entry includes
its primary PDF URL and page/table locator. The two Ganymede entries describe
one study with conflicting dates, not two independent mission designs.

| Study | Sequence | Launch → terminal encounter | Report C3, km²/s² |
|---|---|---|---:|
| Io Observer | EVVEJ | 2021-06-30 → 2027-12-30 | 17–19 |
| Ganymede Orbiter, two date variants | EVEEJ | 2021-05-24 → 2028-07-20 | 12.688 |
| Saturn Atmospheric Entry Probe | EdvES | 2027-08-30 → 2034-06-22 | 49 |
| Enceladus Orbiter | EVEVES | 2023-01-28 → 2031-07-29 | 11.7 |
| Mercury Lander, chemical option | EVVMedvMedvMedvMeMe | 2020-04-06 → 2025-04-22 | 16.5 |
| Neptune Odyssey, direct chemical baseline | EdvN | 2033-05-31 → 2049-06-03 | 148.3 |
| Trojan Tour, Agamemnon chemical baseline | EdvJdvX | 2019-02-21 → 2029-02-18 | 73.15 |
| Titan Lake Probe, Option 3 | EVEVES | January 2023 + 3385 days | 13.5 |

These are proposed-study initial guesses, not accepted gallery candidates or
reproduced mission budgets. Source calendar days are initialized at TDB midnight
when the study does not specify a clock/time scale. The Titan study gives only a
launch month and relative days; January 1 is a search-bound endpoint, not a
claimed launch date. Study epochs do not override a user's launch/arrival windows
or C3 constraints. Timing guesses are clipped to user-selected leg bounds.

Important source limitations are retained in the data:

- Ganymede's second Earth flyby is October 19, 2025 in the table and October 29
  in its plot. It also uses a Callisto assist immediately before JOI, which the
  heliocentric planet-only model does not reproduce.
- Mercury's three DSM dates are provided, but only their combined 1.238 km/s is
  specified. Individual magnitudes are left null. The third DSM is earlier in its
  leg than the current 10% minimum DSM fraction, so initialization clamps it.
- Titan's 250 m/s DSM allocation has no specified epoch. Enceladus's mixed
  statistical/bias maneuver allocation is not treated as a known flyby impulse.
- JOI, Saturn/Neptune insertion, landing, probe/carrier diversion and moon tours
  are excluded from heliocentric cruise DSM accounting.
- Mercury Lander 2020, Persephone, Titan Saturn System Mission and Chiron use
  continuous electric propulsion in their relevant baselines. They are retained
  as architecture references but excluded from ballistic timing initialization.

Four architectures are newly selectable: EVEVES, EVVMedvMedvMedvMeMe, EdvN and
EEJN. EEJN is topology-only; no complete chemical encounter schedule was
recovered. The Agamemnon sequence uses the existing custom-target `X` mechanism,
with confirmed SPK identity 20000911.

## Numerical first-leg check

[departure_checks.json](departure_checks.json) records actual Lambert solutions
from the local JPL cache, including unsuccessful high-energy branches. None is
marked as a full-chain validation. First-leg DSM routes use a zero-offset
ballistic initialization here, so their C3 cannot be compared directly with the
designed DSM trajectory's C3.

The check exposed missing one-revolution Earth–Venus departure options in the
existing EVVEJ and EVEEJ templates. Those options are now included. With them:

| Study | Report C3 | Computed first-leg C3 |
|---|---:|---:|
| Io Observer | 17–19 | 16.958 |
| Ganymede Orbiter | 12.688 | 12.659 |
| Enceladus Orbiter | 11.7 | 11.595 |
| Mercury Lander chemical | 16.5 | 16.564 |

These close departure-energy matches support the initialization geometry; they
do not establish that all subsequent unpowered flybys or DSM budgets match.
The Trojan route's default zero-revolution departure remains a poor initial
guess and needs further branch/DSM design before it could become a useful
reconstruction. It has not been published as a solved trajectory.

## Repeat locally

```powershell
python tools/fetch_decadal_reports.py --inventory
python -m pip install pypdf  # optional, needed only for PDF extraction
python tools/fetch_decadal_reports.py --ids vv2011_14_io_observer --extract
python tools/check_decadal_departures.py --cache "$env:LOCALAPPDATA\RoLaMGAS\cache"
```

The first command refreshes the source index. The second tool caches only the
selected reports, respects the app's certificate configuration, and reports
failed downloads with a nonzero exit status. The departure check is offline:
missing JPL cache coverage is reported rather than extrapolated or downloaded.
