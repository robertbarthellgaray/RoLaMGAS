# JUICE-informed Earth-return departure guesses

JUICE launched on 14 April 2023. Its real cruise uses the Moon and Earth in August 2024, Venus in August 2025, Earth in September 2026, Earth in January 2029 and Jupiter in July 2031. The first encounter is a lunar-Earth assist, rather than an Earth-only swingby. The current heliocentric Lambert chain omits the Moon, so EEVEEJ is an approximation to that mission. See [ESA's mission overview](https://www.esa.int/Science_Exploration/Space_Science/Juice).

The source download identifies JUICE as Horizons spacecraft **-28**, confirmed by the official lookup API and [NAIF ID list](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/FORTRAN/req/naif_ids.html). Saved geometric state vectors use **Earth center (399), Ecliptic J2000, JD TDB, km and km/s**, with no light-time or aberration corrections. The complete JPL request, response and trajectory-source header are retained in `departure_seeds/juice_geocentric_raw.json`; Earth's reference launch state is in `earth_heliocentric_raw.json`.

At **2023-04-16 12:00:00 TDB**, approximately two days after launch, Horizons gives:

```
r relative to Earth (km) = [-546856.9221353233, -37627.75832836925, -15696.37296502802]
v relative to Earth (km/s) = [-2.756890475009438, -0.3099441307535001, -0.01363964991896692]
```

The distance is **548,374.6 km**. Squaring the finite-distance speed gives **7.6966965 km²/s²**, which includes Earth's gravitational contribution. The Earth-only osculating hyperbolic energy is instead `C3 = v dot v - 2 GM_Earth / |r| = 6.2429442 km²/s²`. The corresponding outgoing asymptotic velocity estimate is **[-2.48229178, -0.28475840, -0.00918429] km/s**, with magnitude about **2.49859 km/s**.

The same calculation three and five days after launch gives C3 **6.27628** and **6.36365 km²/s²**. This drift matters: solar and lunar perturbations make a far-from-Earth osculating estimate epoch-dependent. The selected two-day estimate is a useful initialization, not a definitive reconstruction of the launch vehicle's delivered injection energy. The mission-header launch minute is converted to an approximate TDB reference epoch; it is not claimed to be an exact launch or separation time.

The offline sampler expresses that departure direction in Earth's heliocentric **radial / transverse / normal (RTN)** basis. It rotates the direction into the Earth RTN basis at each trial launch, rather than copying a fixed 2023 inertial vector into a different year. Its magnitude is clipped inside the user's C3 interval. The existing application floor of **6.25 km²/s²** remains authoritative; the small difference from the two-day estimate does not bypass that floor.

For sequences beginning with an Earth departure and Earth return, including EEVEEJ and EdvE variants, a small set of first-leg date guesses is projected toward the reference direction. Projection uses only the first Lambert leg, the selected revolution/path branch, the existing date windows, and hard C3 bounds. Boundary projection first escapes the nearly Earth-following C3≈0 branch basin. At most six starts per branch are added within the existing sample count, and up to one quarter of refinement slots prioritize them. The full chain is still screened and optimized normally; no launch vector, DSM, flyby turn or downstream velocity is silently overridden. Local refinement and appended trajectories keep their original initialization. Advanced JSON settings can disable these seeds with `earth_return_seeds: false`.

A reproducible first-leg benchmark for a **2034–2039** launch window and **C3 6.25–11** is saved as `departure_seeds/benchmark_2034_2039.json`. For the one-revolution high-path branch, 128 ordinary random date trials found no in-range first leg; six informed projections produced six in-range guesses at C3 approximately **6.2500–6.2561**. Projection itself took about 0.06 seconds with compiled kernels and cached JPL ephemerides. This measures improved first-leg initialization only. It does **not** establish that the remaining EEVEEJ flybys can connect, meet burn limits or reproduce JUICE's actual Moon-assisted trajectory.

Regenerate the downloadable JPL reference independently:

```powershell
.\.venv\Scripts\python.exe tools/download_juice_departure.py
```

Recompute the reference offline from the preserved responses:

```powershell
.\.venv\Scripts\python.exe tools/download_juice_departure.py --from-saved
```

Worker searches never download this spacecraft data. The small reference ships with the app. Resume signatures include hashes of both the seed code and selected reference, so a changed empirical initialization cannot silently resume an old engine run.


## Complete EdvEVEEJ starters

The app now also carries a complete solver-built chain in `departure_seeds/eevee_chain.json`. It departs on 22 November 2033, returns to Earth on 19 April 2036, encounters Venus on 10 October 2036, Earth on 25 August 2037 and 7 December 2039, and reaches Jupiter on 9 October 2041. These are TDB dates, not a reconstruction of JUICE's flight. The first Earth-return leg lasts about 2.4 years.

The family lowers the departure energy of an existing passing EEVEEJ solution (C3 12.6824) while fitting an explicit first-leg DSM. The downstream encounter dates stay fixed. Stored tradeoffs are approximately:

| C3 (km²/s²) | First-leg DSM (m/s) |
| --- | --- |
| 6.25 | 493.925 |
| 7 | 428.912 |
| 8 | 346.339 |
| 9 | 267.551 |
| 10 | 191.824 |

All four unpowered flybys match excess speeds within 0.026 m/s; Jupiter arrival excess speed is 8.579 km/s. The lowest flyby is the final Earth encounter, about 204.5 km above the model's reference radius, compatible with the 200 km floor used to generate the family. Higher floor settings must be rechecked and can reject these seeds. Independent DOP853 integration of the C3 6.25 Sun-only arcs reaches every segment endpoint within 0.007 km. This validates those arcs, not a finite-radius planetary passage or an n-body trajectory.

Choose **Juice style low C3** from the examples, or select/type **EdvEVEEJ** with a launch window including November 2033. Before random search, the app maps physical dates and burn controls into the current request, recomputes every maneuver and flyby, and only retains starters that pass all current constraints. This works without community sharing or an Internet connection when planetary ephemerides are cached. A compatible branch is scheduled even with a small branch-family limit. Explicit encounter windows, local refinement, C3 bounds, burn caps and altitude floors remain authoritative. For a narrow C3 interval between stored levels, a bounded local first-leg fit can regenerate a starter. Windows that exclude the reference geometry do not receive a falsely passing trajectory.

Regenerate this family locally from the stored donor dates and your existing cache:

```powershell
.\.venv\Scripts\python.exe tools/build_low_energy_chain_seed.py --cache "$env:LOCALAPPDATA\RoLaMGAS\cache"
```

The tool uses numerical optimization on your CPU, performs no network requests, and requires no AI service. As with the departure-direction reference, the complete-chain seed file is included in resume signatures and native packages.
