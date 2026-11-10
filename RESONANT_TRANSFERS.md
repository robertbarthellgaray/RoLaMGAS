# Resonant transfers: Earth, Uranus and Mercury

This review uses geometric JPL Horizons planet-center states, Sun-only Kepler/Lambert coasts and instantaneous asymptotic flyby joins. These are original numerical reconstructions. Finite-radius export retargeting costs and destination capture are separate.

## Why the exact two-year EEJ idea cannot supply a free Jupiter kick

For a circular Earth orbit, a spacecraft leaving prograde at perihelion in a two-year ellipse has:

- semimajor axis 1.587401 AU;
- aphelion 2.174802 AU;
- Earth-relative departure speed 5.077898 km/s;
- C3 25.785052 km²/s².

After one spacecraft orbit it returns with the same velocity. Its incoming excess velocity already points along Earth's motion. An unpowered flyby preserves its magnitude, so rotating it cannot increase heliocentric speed. The maximum-energy exit is the unturned entrance. A minimum-energy 1-to-5.2-AU transfer instead needs about C3 77.282 in the same circular model.

This excludes the exact proposed geometry. It does not exclude every EEJ trajectory: non-perihelion returns, different periods, extra assists and DSMs have different incoming vectors and must be checked separately. The study tool generates the energy-limit plot without solving a degenerate same-point Lambert boundary condition.

## What the UOP report actually specifies

The user's report, PDF page 31 / printed page 25, Exhibit 3-24, gives:

| Departure | Sequence | C3 (km²/s²) | Total DSM (m/s) | Flight time (years) |
|---|---|---:|---:|---:|
| 2033-01-08 | EVEEU | 23.6 | 420 | 15.3 |
| 2034-05-27 | EVEEU | 23.1 | 680 | 15.2 |
| 2036-02-28 | EVEEU | 28.2 | 540 | 15.3 |
| 2038-01-08 | EVEEU | 35.5 | 0 | 14.2 |

Section 3.3.2 describes a patched-conic search allowing excess-speed leveraging and powered flybys. The table does not publish individual flyby dates, DSM epochs, vectors or burn placement for those EVEEU cases. The absence of `dv` in a printed sequence does not mean that row is ballistic. A solver restricted to plain EVEEU is solving a different problem for the first three rows.

Source: [NASA UOP final report](https://smd-cms.nasa.gov/wp-content/uploads/2023/10/uranus-orbiter-and-probe.pdf).

## A reconstructed 2034 family now works

These retain the report's departure day and C3. They are independently solved nearby trajectories, not recovered report navigation states.

| Starter ID | Flight time (years) | DSM (m/s) | Uranus arrival V∞ (km/s) |
|---|---:|---:|---:|
| `56b116f12c78` | 15.2 | 694.087 | 6.2204 |
| `eb95953df9dd` | 15.3 | 637.850 | 6.1554 |
| `d4c6f546cde6` | 15.5 | 527.747 | 6.0326 |
| `8a215745de8d` | 15.7 | 452.333 | 5.9202 |

The 15.2-year case has these TDB events:

| Event | Calendar date | JD TDB |
|---|---|---:|
| Earth departure | 2034-05-27 00:00:00 | 2464109.500000000 |
| Venus flyby | 2035-04-29 01:17:22 | 2464446.553734988 |
| Earth flyby | 2036-06-28 08:36:25 | 2464872.858627718 |
| DSM, 694.087 m/s | 2038-06-10 14:36:19 | 2465585.108554110 |
| Earth flyby | 2039-10-21 15:55:10 | 2466083.163321258 |
| Uranus arrival | 2049-08-07 19:11:59 | 2469661.299999873 |

Its inferred flyby altitudes are 1,667.2 km at Venus, 1,375.9 km at the first Earth encounter and 206.8 km at the second Earth encounter. These are asymptotic turn-derived altitudes, not finite-radius closest approaches. Independent DOP853 integration of the Sun-only coasts misses their declared endpoints by at most 0.023 km.

The search needed a one-revolution Earth-to-Venus branch and an approximately 1,210-day Earth-return leg. The old custom route omitted that first branch and capped Earth returns at 1,200 days. The new UOP templates include both, and label the explicit burn placement as `EVEdvEU` or `EVEEdvU` rather than silently adding a burn to plain `EVEEU`.

## What Mercury missions teach us

MESSENGER combined successive spacecraft/Mercury revolution-count ratios of approximately 2/3, 3/4 and 5/6 with burns near aphelion. The corresponding spacecraft periods were approximately 3/2, 4/3 and 6/5 Mercury years. Its five reconstructed DSM magnitudes were 315.6, 227.4, 72.2, 246.7 and 177.8 m/s. Resonance supplied repeated encounters; the flybys and burns together changed orbital shape, apsidal alignment and encounter phase.

Source: [McAdams et al., MESSENGER mission design team, AAS 11-546](https://messenger.jhuapl.edu/Resources/Publications/McAdams.et.al.2011.pdf), particularly Table 5 and the Mercury-flyby discussion. These numbers exclude orbit insertion and smaller corrections.

BepiColombo combines flybys with sustained solar-electric propulsion. It cannot be faithfully represented by assuming all its legs are unpowered Lambert arcs. An earlier ESA design study used Mercury resonance transitions and several low-thrust arcs; it illustrates the strategy, not the final flown schedule.

Sources: [ESA journey description](https://www.esa.int/articles/about-us/directorates/science/bepicolombo/journey-to-mercury), [Jehn and Schoenmaekers, ESA/ESOC trajectory study](https://www.issfd.org/ISSFD_2014/ISSFD24_Paper_S6-5_jehn.pdf).

RoLaMGAS now offers up to eight complete Lambert revolutions on Mercury-return legs, including custom and appended sequences. It schedules coordinated resonance ladders before random combinations and seeds their durations together. Neighboring revolution counts and both Lambert paths remain available; guessed resonances never bypass speed, altitude, C3 or maneuver limits.

Original Mercury starters at C3 43.24852 demonstrate the trade:

| Starter | Additional Mercury returns | Cruise DSM (m/s) | Arrival V∞ (km/s) | Flight time (years) |
|---|---:|---:|---:|---:|
| `51bc33113cf9` | 0 | 0 | 7.2984 | 2.372 |
| `77f8d650c03a` | 1 | 350 | 6.9502 | 4.058 |
| `045a6f706494` | 2 | 700 | 6.5252 | 5.265 |
| `7b9193f015ab` | 4 | 1400 | 5.3544 | 7.685 |

These improve the available arrival-speed choices, but are not yet MESSENGER-quality orbiter approaches. Capture is excluded. The extension search is greedy, so spending more on additional returns does not guarantee a better total mission. Mercury's eccentricity makes encounter phase important; an exactly repeated same-phase flyby does not automatically lower V∞.

The current DSM parameterization uses a zero-revolution Lambert subarc after the burn. Some historical early-in-leg, multi-revolution thrust histories require a more general parameterization; the stored examples obey the existing model with later burn epochs.

## Run independently

From the repository root with its scientific Python environment:

```powershell
.\.venv\Scripts\python.exe tools/study_resonant_transfers.py --output runs/resonance_review
```

This uses cached JPL data only, rebuilds all eight starters under current limits, independently integrates every solar coast, saves candidate and importable options JSON, and produces three PNGs plus `comparison.csv`. No AI or community API is called.

To search for another Mercury return while keeping a saved cruise fixed:

```powershell
.\.venv\Scripts\python.exe tools/study_resonant_transfers.py --extend-candidate runs/resonance_review/51bc33113cf9.json --dsm-per-return-mps 350 --output runs/mercury_return_review
```

Use `--parent-config` with the original configuration when extending a trajectory produced with nondefault DSM velocity scaling or constraints. The forward flyby variables preserve excess speed and enforce periapsis before optimization; every result is rebuilt in the full-chain model and checked for changes to earlier coasts.

For broader searches in the normal application or CLI, import `examples/uop_2034_resonant.options.json` or `examples/mercury_resonant_orbiter.options.json` in the application. The matching plain `.json` files are CLI configurations. CLI example:

```powershell
.\.venv\Scripts\python.exe mission_search.py run --config examples/uop_2034_resonant.json --output runs/uop_2034 --local-search
```

The bundled starters are re-evaluated under the user's current dates, branch restrictions, C3, V∞, maneuver and altitude bounds. They never override them. Local executable previews include the new data; public released binaries remain unchanged until the user has tried and approved a new build.
