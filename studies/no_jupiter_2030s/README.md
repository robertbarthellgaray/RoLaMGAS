# No-Jupiter low-C3 launch-window survey

750 launch/C3 jobs across 125 launch dates. C3 grid: [10.0, 12.0, 14.0, 16.0, 23.1, 28.0] km²/s². Passing candidates: {'Saturn': 256, 'Neptune': 28}.

All shown candidates have zero modeled DSM/powered-flyby delta-v. Excess-speed matching and minimum turn radii are checked at every assist (Earth 200 km, Venus 300 km, Saturn 10,000 km). Saturn flight time is limited to 20 years, Neptune to 30 years, and arrival V-infinity to 12 km/s. Arrival capture and launch injection burns are excluded.

The 16 selected candidates were recomputed and independently propagated with DOP853; maximum solar-coast endpoint error 0.038999 km.

These are Sun-only Lambert arcs joined at planet centers with asymptotic patched-conic flyby screens. Flyby altitudes are inferred from turns, not integrated finite-radius closest approaches. This is not n-body or a collision audit of resolved planet encounters. Zero DSM does not include finite-SOI targeting/TCMs. No Jupiter encounter is used; Jupiter perturbations are also absent.

The launch-date/C3 grid and finite branch/duration search are not exhaustive; absence of a candidate is not proof of impossibility. Sorting ties by sampled energy does not establish a continuous optimum.

## Selected candidates

| ID | Target | Sequence | Launch (TDB) | Arrival (TDB) | Years | C3 km²/s² | Arrival V∞ km/s |
|---|---|---|---|---|---:|---:|---:|
| [70681d42b0d1](70681d42b0d1.png) | Neptune | EVEESN | 2035-09-01 | 2064-12-20 | 29.304 | 23.100 | 11.390 |
| [e961e60bd93c](e961e60bd93c.png) | Neptune | EVEESN | 2036-06-01 | 2065-03-07 | 28.766 | 23.100 | 11.266 |
| [d4baaadbea4a](d4baaadbea4a.png) | Neptune | EVEESN | 2037-09-01 | 2066-08-07 | 28.932 | 16.000 | 9.154 |
| [62c352527281](62c352527281.png) | Neptune | EVEESN | 2039-05-01 | 2068-06-21 | 29.144 | 23.100 | 7.145 |
| [4acf658b80af](4acf658b80af.png) | Neptune | EVEESN | 2039-06-01 | 2066-02-25 | 26.740 | 23.100 | 9.975 |
| [2241b1f7adb1](2241b1f7adb1.png) | Neptune | EVEESN | 2039-06-01 | 2066-01-20 | 26.642 | 28.000 | 10.171 |
| [9eaf36cdf19a](9eaf36cdf19a.png) | Saturn | EVEES | 2031-04-01 | 2043-06-08 | 12.186 | 16.000 | 5.446 |
| [6dbc677175d8](6dbc677175d8.png) | Saturn | EVEES | 2032-09-01 | 2047-10-03 | 15.087 | 14.000 | 5.519 |
| [2ba2eb92e25c](2ba2eb92e25c.png) | Saturn | EVEES | 2033-02-01 | 2047-05-15 | 14.282 | 16.000 | 5.730 |
| [a6f09d41e876](a6f09d41e876.png) | Saturn | EVEES | 2034-05-01 | 2044-11-19 | 10.557 | 14.000 | 7.748 |
| [b48a78c73d33](b48a78c73d33.png) | Saturn | EVEES | 2035-10-01 | 2047-10-05 | 12.014 | 23.100 | 5.260 |
| [d5c0914a9d16](d5c0914a9d16.png) | Saturn | EVEES | 2036-04-01 | 2049-01-18 | 12.801 | 12.000 | 5.272 |
| [624b45daffa2](624b45daffa2.png) | Saturn | EVEES | 2036-04-01 | 2047-05-22 | 11.140 | 14.000 | 5.238 |
| [aec637dc2828](aec637dc2828.png) | Saturn | EVEES | 2037-07-01 | 2050-03-06 | 12.679 | 14.000 | 5.323 |
| [4140da8296cd](4140da8296cd.png) | Saturn | EVEES | 2037-07-01 | 2047-03-12 | 9.696 | 28.000 | 7.327 |
| [89b07562631d](89b07562631d.png) | Saturn | EVEES | 2039-06-01 | 2053-11-20 | 14.474 | 23.100 | 6.382 |

## Files and rerun

- `comparison.png`: C3 versus flight time, colored by launch year.
- `<id>.png`: full path, inner-assist zoom, and heliocentric distance timeline.
- `<id>.json`: exact portable candidate for RoLaMGAS import.
- `<id>.options.json`: settings plus exact candidate.
- `<id>.full.json`: solver states and independent coast audit.
- `all_candidates.csv`, `selected_candidates.csv`, `flyby_dates.tsv`.

From the repository root, using its scientific Python environment:

```powershell
python tools/search_no_jupiter.py --monthly --workers 4 --output releases/testing/no_jupiter_2030s
python tools/report_no_jupiter.py --input releases/testing/no_jupiter_2030s
```

Searches run on the local CPU using the existing daily JPL cache. Completed date/C3 jobs are checkpointed and skipped on rerun. Changing algorithm or constraints requires a fresh output directory.

## Publication

All 284 passing candidates were independently propagated with DOP853 before publication; maximum coast endpoint error was 0.125363 km. All 284 were uploaded to the live shared library and verified by encounter-key readback. See public_candidates.json, all_coast_audits.json, upload_receipt.json and website_links.json. The same records are included in the desktop and website seed archives. Only scientific candidate records are shared; no user paths or identifiers are included.


Interactive examples:

- [Saturn, C3 12, launch 2036-04-01, 12.80 years](https://robertbarthellgaray.github.io/RoLaMGAS/#mission=0bbf3c81dfd099476026cf360c5df2145577dd523b1f4f329cfb868045bc0dca)
- [Saturn, C3 28, launch 2037-07-01, 9.70 years](https://robertbarthellgaray.github.io/RoLaMGAS/#mission=86df7d4cf36e543dd49b27cd644b18eda8670fa7d35a0aff5f38f6aca27f6c02)
- [Neptune via Saturn, C3 16, launch 2037-09-01, 28.93 years](https://robertbarthellgaray.github.io/RoLaMGAS/#mission=03a99296ab1fc2983eb84c27e3cc18d8b72d0f81a3e04833d0ee1a08b825578d)
