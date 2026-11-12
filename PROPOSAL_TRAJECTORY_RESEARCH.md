# Camilla and NASA proposal trajectory references

The new timing library is `departure_seeds/new_frontiers_missions.json`.
Five entries feed the app's historical initialization and have selectable presets
under `examples/proposal_*.json`. Timing references are guesses; every candidate
still undergoes the current launch-energy, burn-budget and flyby checks.

| Study | Sequence from launch | Reported C3 (km²/s²) | Use in RoLaMGAS |
|---|---|---:|---|
| Camilla 2026, Jupiter cruise | EVdvEEJ | 11.9 | Timing seed and independently solved candidate |
| NASA Common Probe Venus 2024 | EV | 7.3 | Timing seed |
| NASA Common Probe Jupiter 2029 | EVEdvJ | 17.0 | Research reference: DSM occurs too early for the present parameterization |
| NASA Common Probe Saturn 2024 | EVEEdvS | 18.7 | Research reference: DSM occurs five days after Earth |
| NASA Common Probe Uranus 2030 | EVEdvEJU | 13.0 | Timing seed; the explicit study preset accommodates its reported 757 m/s DSM |
| NASA Common Probe Neptune 2031 | EJN | 81.8 | Timing seed |
| Europa Clipper 2012 nominal study | EVEEJ | 12.8 | Timing seed, with Jupiter arrival rather than a resolved Ganymede encounter |

Primary sources:

- [Howell et al., Camilla, 2018](https://doi.org/10.1016/j.pss.2018.07.008)
  and [Caltech/JPL article record](https://authors.library.caltech.edu/records/4ep13-y2e40).
  The paper explicitly describes a July 2027 DSM; its September launch option
  has an approximately 0.4 km/s maneuver budget. The supplied presentation chart
  supplies the planetary calendar days used here. Its Chariklo date differs from
  dates stated in the journal text, so this reproduction stops at Jupiter.
- [NASA Common Probe interplanetary trajectory poster](https://ntrs.nasa.gov/api/citations/20180004128/downloads/20180004128.pdf),
  the five planet-specific event tables. These distinguish cruise DSMs from
  carrier-divert burns near atmospheric entry.
- [Europa Mission Concept Study Update, 24 September 2012](https://sites.nationalacademies.org/cs/groups/ssbsite/documents/webpage/ssb_073049.pdf),
  printed page 25. Its annual opportunity table includes reported C3 values from
  10.2 to 16.4. Only the nominal 2020 sequence supplies every planetary encounter
  day on that page; the other launch dates are not invented into complete seeds.
- [NASA planetary mission concept report index](https://science.nasa.gov/planetary-science/resources/documents/)
  and [NASA/JPL summer-seminar study background](https://www.hou.usra.edu/meetings/lpsc2018/pdf/2736.pdf).
  Camilla is a NASA/JPL summer-seminar concept designed against New Frontiers
  constraints; the table also includes studies from other NASA mission classes.

## Independently reconstructed Camilla Jupiter cruise

Candidate **2c8de26a2f93** retains all five planetary calendar days from the supplied
chart. Times within those days and the July burn were solved locally from cached
JPL Horizons vectors. The second Earth encounter is near a two-year resonance;
rounding both encounters to midnight selects a very different Lambert coast.

| Event | TDB calendar epoch |
|---|---|
| Earth launch | 2026-09-09 12:00:00 |
| Venus | 2027-02-25 12:00:00 |
| Modeled DSM | 2027-07-01 00:00:00 |
| Earth 1 | 2027-12-29 12:00:00 |
| Earth 2 | 2029-12-29 approximately 00:24:54 |
| Jupiter | 2031-10-25 12:00:00 |

Computed C3 is **11.91503 km²/s²**; the explicit DSM is **313.751 m/s**.
The largest remaining flyby-speed difference is **0.000221 m/s**. Inferred
flyby altitudes are approximately **10,670 km at Venus, 4,553 km at Earth 1,
and 429 km at Earth 2**, above the ordinary 300/200 km floors.

The stored-vector audit, independent solar coast integrations, desktop exact
import and sampled CSV/XYZV checks pass. These ideal coasts join at planet centers;
the desktop finite-radius exporter remains necessary for close-up Celestia flybys.

Reproduce with local Python and an existing JPL cache:

```sh
python tools/reconstruct_camilla.py --cache PATH_TO_CACHE --output studies/camilla_2026
```

`studies/camilla_2026/selected-trajectory.json` loads the solved candidate into the
current desktop app without another search. The new source timing seeds and
presets become bundled in the next locally tested app build.

## Existing shared candidate with unmodeled flyby gaps

Candidate `4f2144477cd43baf526df67b7f62a966ddcfa557ff67f5012bb9033afc54130c`
already stores `metrics.max_vinf_mismatch_mps = 450.51030810996906`, classification
`yellow`, and zero modeled cruise burns. The maximum alone was not displayed on
the website and does not describe the sum across encounters.

Recomputing from its saved coasts and cached JPL planetary velocities gives:

| Encounter | Speed gap (m/s) | One conservative periapsis impulse (m/s) |
|---|---:|---:|
| Venus | 253.506 | 196.119 |
| Earth 1 | 443.196 | 346.839 |
| Earth 2 | 450.510 | 333.536 |
| Sum | 1,147.212 | 876.493 |

The two columns are different quantities. The right column uses the desktop
solver's common-periapsis powered-flyby construction, preserves the saved incoming
and outgoing asymptotes, and respects the configured altitude floors. It is a
feasible analytic construction, not a minimum-fuel solution or a finite-radius
integration. Nominal encounter times are not resolved periapsis times. Changing
the trajectory and using a DSM can produce a different budget, as the Camilla
reconstruction demonstrates.

The website now displays the saved maximum and provides an estimate button for
each encounter. Its estimates use the existing interpolated JPL context and are
checked against the Python calculation. Source trajectories and modeled burns are
not altered. The archive's existing API schema already preserves the maximum, so
old uploads receive the display improvement too.

For a full-precision offline audit:

```sh
python tools/audit_shared_flybys.py --record candidate.json --cache PATH_TO_CACHE --output audit.json
```

The worked record, independent audit and exact-JPL numerical fixture are saved in
`studies/flyby_audits/4f2144477cd4/`.
