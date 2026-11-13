# Jupiter library expansion — November 12, 2026

320 new Jupiter-ending candidates, launching in 2027–2055:

| Sequence | Candidates |
|---|---:|
| EdvEJ | 143 |
| EVEEJ | 62 |
| EVVEJ | 8 |
| EJ | 106 |
| EdvJ | 1 |

The batch recomputed Jupiter-ending prefixes of existing outer-system cruises,
retargeted assisted routes to nearby launch weeks, and scanned direct transfers
on a 15-day launch grid with several flight times. A source prefix is a reuse of
an existing cruise, not a newly discovered assist sequence. Same-day encounter
duplicates and already-published Jupiter opportunities were excluded.

All selected candidates passed a fresh Lambert/flyby screen against cached JPL
states and independent DOP853 integration of every solar coast. Maximum numerical
endpoint error: 0.0192 km. Flyby speed mismatch is below 1 m/s, Earth altitude floor
200 km, Venus 300 km, single DSM limit 700 m/s, total modeled cruise burn limit
1 km/s. Assisted non-Venus paths use C3 ≤45, Venus-assisted paths C3 ≤30; direct
Earth–Jupiter transfers allow C3 ≤100. Arrival V∞ is at most 15 km/s and flight
time at most ten years. These ceilings describe screening, not mission optima.

The selected batch spans C3 11.46–99.63 and flight times 1.79–9.63 years. Direct
high-C3 flights provide faster alternatives to the lower-energy assisted routes.
Launch injection and arrival capture are excluded from the modeled cruise budget.
Planet encounters use asymptotic turn screens, not finite-radius/n-body validation.
Finite-patch export may add targeting burns, reported separately by the app.

[Comparison chart](jupiter_opportunities.png), [all metrics](comparison.csv),
[screening report](report.json), [coast audits](coast_audits.json),
[public candidates](public_candidates.json), [sharing summary](sharing_summary.json).
Eligible shorter planet-ending missions were also shared using the same helper
as the app's new automatic-prefix feature.

Reproduce locally, using the existing planet cache:

```powershell
.venv\Scripts\python.exe tools/expand_jupiter_library.py --count 320
```

This writes local results only. Explicitly share an audited saved batch with
`--publish-saved`. A later run can find different new slots because the public
library now includes this batch. The selected full solver states are kept locally
in `selected_candidates.json`; the repository retains the sanitized public states.
