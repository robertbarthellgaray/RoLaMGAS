# Planar Earth-return routes to Uranus

Local study, 2026-11-19. Departure guesses span C3 25–90 in increments of 5; all are initially prograde and close to Earth’s orbital plane. A finite sweep is not proof that other energies or dates are infeasible.

Sequence: **EdvEdvEU**. Both DSMs start at an osculating solar aphelion. Both Earth assists use a minimum altitude of 200 km. These routes do not visit Venus or Jupiter. C3 is launch excess speed squared, not a burn magnitude.

| Candidate | Launch (TDB) | Arrival (TDB) | C3 | Years | DSM total (m/s) | Arrival V∞ (km/s) | Largest speed gap (m/s) |
|---|---|---|---:|---:|---:|---:|---:|
| 58ab019f66dc | 2040-10-14 | 2054-11-02 | 28 | 14.050 | 1399.98 | 11.286 | 0.0511886 |
| cb1fcb54b1a4 | 2036-10-21 | 2051-06-12 | 83 | 14.641 | 950.84 | 9.982 | 0.000624321 |
| 1ba5e287c106 | 2034-09-23 | 2053-03-01 | 30 | 18.434 | 765.60 | 5.833 | 7.46194e-08 |
| b6cd07267ba3 | 2030-08-09 | 2050-05-05 | 55 | 19.737 | 337.45 | 5.744 | 0.406101 |
| 2f35f8e62491 | 2028-08-30 | 2049-01-26 | 30 | 20.409 | 738.43 | 5.151 | 9.98721e-08 |
| 83cdf80e1dcf | 2035-11-27 | 2056-04-26 | 50 | 20.413 | 393.55 | 5.320 | 8.86189e-08 |
| e32bf45fda11 | 2034-10-22 | 2057-03-06 | 55 | 22.370 | 336.56 | 4.932 | 7.89804e-08 |
| 428d144b2bde | 2041-09-26 | 2064-06-02 | 30 | 22.683 | 704.27 | 4.796 | 0.728431 |
| 76beed186c51 | 2038-10-11 | 2062-01-27 | 30 | 23.298 | 666.74 | 4.821 | 6.82121e-09 |
| 3a2c2935b839 | 2040-11-11 | 2064-08-30 | 30 | 23.801 | 657.73 | 4.810 | 7.86198e-08 |
| 8ac45aec6a85 | 2038-10-14 | 2062-12-30 | 30 | 24.212 | 661.76 | 4.848 | 1.14984e-05 |
| cc3afcd4fa57 | 2035-08-26 | 2059-11-18 | 60 | 24.231 | 337.39 | 4.876 | 0.655836 |
| f5991c12e0ab | 2040-10-23 | 2065-01-18 | 30 | 24.239 | 655.63 | 4.822 | 3.11466e-08 |
| e0e61a2c782c | 2041-11-22 | 2067-03-31 | 30 | 25.352 | 648.81 | 4.856 | 0.00203888 |
| 898de074143a | 2036-09-07 | 2062-07-02 | 60 | 25.815 | 352.62 | 4.975 | 0.504861 |

Each `*_handoff.json` imports search settings and the exact saved candidate. The desktop Model re-evaluated every stored chain, recovered its physical DSM controls, and verified the import round trip. Flyby speed gaps are reported separately, not silently called zero.

**Validation scope:** Kepler/Lambert heliocentric arcs and instantaneous, unpowered patched-conic turns. No n-body propagation, finite-SOI matching, atmosphere, radiation, launch vehicle performance, or Uranus capture is included. Extra finite-patch burns must be assessed by Integrate & export before describing these as integrated trajectories.

Regenerate locally:
```powershell
python tools/explore_double_earth_uranus.py --starts 280 --energies 25 30 35 40 45 50 55 60 65 70 75 80 85 90 --output studies/planar_earth_uranus_grid
python tools/finalize_double_earth_uranus.py --hold-duration --input studies/planar_earth_uranus_grid
python tools/build_double_earth_seeds.py
```

Use cached JPL Earth/Uranus vectors covering 2028–2080. Optimization and plotting run locally without AI.
