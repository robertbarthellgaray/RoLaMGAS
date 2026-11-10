# Trident calendar-date reconstruction

[Open the interactive candidate](https://robertbarthellgaray.github.io/RoLaMGAS/#mission=f53fc65c9329) · [Import the selected trajectory into the source app](selected-trajectory.json) · [Picture](trajectory.png) · [Independent validation](validation.json)

This is a **modified reconstruction**, not the proposed ballistic Trident trajectory. It matches every encounter calendar day in the user-supplied diagram, with additional designed maneuvers. Its terminal target is Neptune's center in the Lambert model; a Triton encounter has not been designed. The [mission paper](https://www.hou.usra.edu/meetings/lpsc2019/pdf/3200.pdf) and [NASA presentation](https://assets.science.nasa.gov/content/dam/science/astro/programs/exep/resources/exoplanet-meetings/exopag22/files/Jun18_1545_Prockter.pdf) provide proposal context, not validation of these reconstructed vectors.

| Encounter | Calendar day, TDB |
|---|---|
| Earth launch | 2025-10-10 |
| Earth | 2026-10-10 |
| Venus | 2027-03-25 |
| Earth | 2028-02-08 |
| Earth | 2031-02-07 |
| Jupiter | 2032-06-28 |
| Neptune | 2038-09-28 |

Launch C3 is **16.6604 km²/s²**. Modeled cruise delta-v is **617.865 m/s**: 402.205 m/s in three DSMs and 215.659 m/s at powered flybys. The largest individual burn is the 290.485 m/s cruise DSM. Launch injection, terminal capture, finite-radius export corrections, and navigation reserves are excluded.

| Maneuver | Date, TDB | Delta-v, m/s |
|---|---|---:|
| DSM | 2026-04-10 12:00 | 71.154 |
| Venus powered flyby | 2027-03-25 | 6.744 |
| DSM | 2029-08-08 12:00 | 40.566 |
| Earth powered flyby | 2031-02-07 | 23.711 |
| Jupiter powered flyby | 2032-06-28 | 185.203 |
| DSM | 2033-02-11 07:12:01 | 290.485 |

Two numerical flyby impulses below 0.002 m/s are retained in the full budget. The Jupiter excess-speed difference is 603.689 m/s; the explicit common-periapsis impulse is 185.203 m/s. Those are different quantities, and the latter is fully charged. Jupiter periapsis altitude is approximately 71,228 km.

The first one-year Earth return and later three-year Earth return were initialized using physical heliocentric resonance conditions, rather than relying on near-singular same-planet Lambert guesses. A post-Jupiter DSM allowed the powered Jupiter impulse to remain below 200 m/s. The reconstruction uses the app's `Model` and is successfully reloaded by its exact-candidate importer without another search or optimization.

Independent DOP853 integration of every Sun-only coast gives a maximum endpoint error of 0.00240 km. A separate vector audit reconstructs the incoming and outgoing hyperbolic asymptotes from each powered periapsis state, checks periapsis floors, tangent velocity, energy, and burn accounting. This is a patched-conic audit, not n-body, moon-clearance, radiation, or navigation validation. Website CSV/XYZV data describe the ideal Lambert coasts; use desktop finite-radius export for flyby renders.
