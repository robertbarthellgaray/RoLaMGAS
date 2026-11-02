# Open RoLaMGAS

Double-click **Launch Mission Search.cmd**. Your browser opens the local GUI.
There is no remote web app or AI backend. Keep this folder and its `cache`
directory together. **Launch Command Line.cmd** preserves the original wizard.

1. Select a planet, or choose **Horizons object**, enter its name and resolve it.
   `2026 ED138` resolves to a trans-Neptunian object; the suggested long final-leg
   range is editable. `X` is the object in custom routes such as `EJX`.
2. Pick launch dates, tick sequences, set fuel/speed limits and CPU workers.
   **Hard cap per DSM** defaults to 700 m/s; **Hard cap per powered flyby**
   defaults to 200 m/s. Both constrain each vector magnitude, independently of
   the total DSM + flyby budget. Zero prohibits that burn type. Over-cap
   solutions cannot pass the search constraints, but remain exportable diagnostic
   candidates. Integrated exports also flag excessive retargeting/patch burns.
   The **Galileo Style** example is a useful quick demonstration.
   **Additional sequences** accepts comma-separated routes such as `EVEJ, EdvEJ`.
   They are added to the checked presets; clear the presets to search only your
   typed sequences. The last planet must match the destination; use terminal
   `X` for the resolved Horizons object.
   The **Refinement objective** menu chooses balanced launch-injection plus DSM
   cost, minimum C3, minimum DSM, or feasibility-only searches. New GUI searches
   default to balanced refinement. It refines selected passing seeds locally;
   the number of cost-refinement seeds per branch is in the advanced controls.
   It does not guarantee a global minimum or optimize launch-vehicle payload mass.
   The arrival-speed cap applies at the selected destination: 5 km/s at Jupiter
   is a different requirement from 5 km/s at Uranus after a Jupiter assist.
   **Allow powered flybys** includes explicit above-floor periapsis burns in the
   DSM budget. It is optional. The inspector also supports powered export of an
   existing candidate; see [POWERED_FLYBYS.md](POWERED_FLYBYS.md).
3. Click **Start search**. Saved trajectory images appear while the solver runs.
   Sort the cards, pin candidates, switch to a table or inspect a trajectory.
   Use **Include yellow** and **Include red** independently to filter diagnostic candidates.
   Yellow indicates over-limit / needs-burn candidates; red indicates an
   unsatisfied periapsis screen or exceeded individual burn cap. Budget warnings remain exportable.
4. Open any candidate, including a near miss, and click **Integrate & export CSV + XYZV**.
   Optionally set **Arrival altitude above target planet**, e.g. 200 km for
   Venus. Export stops at incoming periapsis; the planet-relative JSON/CSV state
   supports further propagation in FreeFlyer. No insertion burn is added.
   Reintegration backs up existing outputs under the run's `export_history`.
   **Integrate after final flyby · months** adds an unpowered outgoing segment
   to CSV, XYZV and Celestia exports. Default 0 preserves the encounter endpoint;
   fractions are allowed. One month is 30.4375 days. The FreeFlyer arrival state
   stays at incoming periapsis even when the exported trajectory continues.
   Both trajectory files, a report and burn/encounter tables are saved together.
   Download links appear when integration completes.
   Exceeding your C3, DSM, arrival-speed or duration limits does not block export.
   The original limits, candidate status and violations remain in the report
   and Celestia package. Speed mismatches can require powered flybys; those burns
   are explicit. Near-miss flybys may fall below your requested altitude floor,
   which is also reported. Unrepresentable geometry can still fail integration.
5. **Export Celestia package (.zip)** includes the trajectory, SSC, spacecraft
   model and reports. If integration is needed, the button runs it first.
   Automatic mode uses **Panels** for Jupiter/inner planetary missions and
   **RTG** for outer-system/dwarf-planet missions. You can override the model.
   Download/extract the ZIP and drag its whole `Trajectory_…` folder into
   `Celestia/extras`, or use **Open addon folder** to find the unpacked folder.

**Check the integrated budget.** Finite flyby patches require retargeted coasts;
their boundary impulses are explicit and can increase the fuel cost. The report
separates numerical reproduction, clearance checks and compliance with the
original maneuver budget. A numerical pass is not a fuel-budget pass.

The CSV has a header; the XYZV has seven numeric columns:

```
Julian date (TDB)    x km    y km    z km    vx km/s    vy km/s    vz km/s
```

Coordinates are heliocentric Ecliptic J2000. The Celestia package supplies the
correct `data` and `models` folders and a normalized generic spacecraft mesh.
The originals are `LowPolySatPanels.3ds` and `LowPolySatRTG.3ds` in the parent
mission_designer directory. A bundled fallback copy is retained under
`explorer/model_assets`; the exporter prefers the parent originals if present.

The installed baseline covers **all eight planets, 2027-01-01 through 2100-01-01**,
at one-day cadence, plus six-hour Mercury tables. Public JPL responses and SHA-256
checksums are retained on disk. The cache panel shows their availability and size.
New targets, tighter cadence or dates outside stored coverage require downloading
more data. A cached small-body identity and its vectors work offline.

Each run stores its request, images, candidates and results under `runs/`.
Exports are under `runs/<run>/exports/<candidate>/`. Pins stay in this browser's
local storage. **Stop** saves completed jobs and candidates already received;
**Quit app** requests a stop and closes the local server. Closing the browser tab
alone leaves the solver running; reopen the launcher to reconnect.

The elapsed clock advances independently of new candidates. Plot failures are
shown on their individual cards and do not stop the solver. Fatal search errors
are published immediately, before worker cleanup, rather than leaving a stale
“running” status.

The model is preliminary. The integrated export checks numerically propagated
conic arcs and bracketed planet/Sun minima. It excludes moon perturbations,
planetary rings, atmosphere, thermal constraints and continuous n-body validation.

For Dragonfly seeds, open a Saturn-destination search and expand **Saturn → Titan
closest-approach screening** above the gallery. Choose candidate count, assumed
Saturn periapsis and clock-angle count. Results and plots appear live, sorted
by Titan distance. See [ARRIVAL_AND_MOON_SCREENING.md](ARRIVAL_AND_MOON_SCREENING.md)
for the physical assumptions, state formats and standalone command.

All distinct recorded diagnostic solutions are retained without per-worker or overall caps. Exact duplicates are merged. The advanced retention count applies only to green candidates. Random sampling trials remain the optimizer seed pool; completed candidate solutions are retained. Older summaries can be expanded from saved checkpoints with `python restore_diagnostics.py runs`; previously discarded records cannot be recreated. Expanded archives publish their full candidate list before rendering the additional pictures.

The two individual burn-cap controls are in the expandable **Individual burn limits** menu directly below **Allow powered flybys**.

Candidates with a leg-join excess-speed mismatch or individual DSM above the
DSM cap are retained and displayed in red. **Include red** controls their
visibility. They are not discarded. Gravity-assist direction changes are not
counted as speed mismatches.

Historical results use their saved caps. An older search without individual burn caps is not retroactively subjected to the new 700/200 m/s defaults.


## RoLaMGAS candidate neighborhoods

In the inspector choose **I like this one** and an encounter-date variation
(default ±30 days). This creates a new search using the selected sequence and
its Lambert branches as an explicit starting point. Date and DSM guesses are
preserved under the new parameterization; saved C3, arrival speed, duration,
periapsis and burn limits still apply. The launch window is retained. The new
C3 limit also prevents accepted candidates from exceeding the selected C3.
A selected red/yellow seed may remain infeasible. Improved candidates report
the C3 reduction from their parent. The original search is retained.

For Mercury choose repeated `Me` encounters. **Seed resonant Mercury returns**
biases initial guesses toward integer Mercury orbital periods; broad guesses
are retained too. The final encounter is the destination, earlier `Me` nodes
are flybys. **Minimize arrival V∞** targets a cheaper arrival independently of
C3. Screening still enforces the same flyby physics and floors. No low-thrust
propulsion or automatic Mercury orbit insertion is modeled.


## Add a flyby afterwards

Open a candidate, expand **Add a flyby afterwards**, type/select the next
planet, and click **Search added flyby**. It defaults to the current arrival
planet, so EVVMe becomes EVVMeMe. Choose one to three extra encounters and a
minimum/maximum duration for each added leg. For narrow Mercury returns,
start with one encounter and extend its result again.

The selected earlier encounter dates, solar cruise segments, DSM vectors and
launch C3 are frozen in the screening model. Its existing arrival becomes an
assist. Only the new leg dates and optional new-leg DSM controls are optimized.
The final added encounter remains the arrival endpoint; add another encounter
to design an outgoing assist there. **Allow a DSM on each added leg** applies
only to the appended legs and keeps the saved per-burn and total limits.

The search minimizes arrival V-infinity. Physically matched extensions above
the requested arrival-speed limit remain yellow and exportable. A speed
mismatch or excessive turn remains a failure. Do not interpret an attractive
arrival speed on a red candidate as a usable reduction. One-leg Mercury
returns receive a bracketed root scan about integer Mercury years because
valid solutions can lie in extremely narrow date intervals. More encounters
do not guarantee a smaller arrival speed or a cheaper capture.

The original run is retained. New cards report whether the original dates and
segments stayed fixed, C3 change, and the arrival-speed reduction. Existing
finite-radius export/patching may still introduce explicit junction burns;
inspect their separate report rather than assuming an unpowered point-conic
screen is already an exact finite-radius solution.


## Search profiles, energy ranges and historical dates

**Mission profile** offers editable starting values. Orbiter uses C3 0–60,
3 km/s total maneuver budget, arrival V∞ ≤8 km/s and a 30-year flight cap.
Flyby probe uses C3 0–200, 1.5 km/s total maneuver budget, arrival V∞ ≤70 km/s
and a 15-year cap. These are starting suggestions, not vehicle limits or
capture designs. Every control remains editable. Custom retains your values.

**Minimum C3** and **Maximum C3** constrain Earth-relative departure energy,
C3 = |v_departure − v_Earth|², in km²/s². A small plotted difference does not
mean equal departure velocity, encounter times or revolution count. The
inspector lists the departure vector, speed and Lambert branches. Very small
nonzero values use scientific notation instead of rounding to zero. Zero
designed DSM does not account for an unsatisfied flyby mismatch; diagnostic
red chains still require repair. Integrated patch burns are recorded separately.
The expandable C3 explanation includes the supplied Uranus-study launch-mass
chart; it is a reference image, not a current launch-performance database.

**Minimize flight time within limits** is now a refinement objective. An
energy-minimizing search will prefer low C3 unless you set a floor or constrain
the arrival date. **Target arrival date** fixes 00:00 TDB with tolerance 0;
a positive tolerance searches that many days either side. It replaces the final
leg's duration range. Other duration, speed and flyby constraints still apply.

For exact historical schedules, select one sequence and fill **Encounter date
windows**, one line per body including launch and arrival. Each line is either
one ISO date/time or two values separated by a comma. For your proposed
Pluto–Kuiper Express study, resolve Pluto, select EJX only, set C3 160–170 and
enter for example:

```text
2004-12-01, 2004-12-31
2006-03-01, 2006-03-31
2012-12-01, 2012-12-31
```

Clear the separate arrival-date box when using the whole December window, or
set a day within it to narrow further. This is a search setup, not a claim that
those dates and energy limits admit an unpowered Jupiter solution. No burn is
invented to force a mismatch to pass. **I like this one** retains date bounds;
**Add a flyby afterwards** starts a later arrival search with the earlier cruise
locked and clears the old terminal date.

**Transfer direction** can search prograde, retrograde, or both senses. This
matters for high-inclination targets such as Halley. It does not imply a
retrograde comet must be approached on a retrograde cruise: a prograde flyby
may have high relative speed. Both directions share the selected branch budget.
Halley's Horizons command now pins an apparition appropriate to the launch
epoch instead of interpreting a list of historical apparitions as vector data.

## Minor-body encounter distance

In the export inspector, **Distance from target center at encounter** accepts
positive fractional kilometers, e.g. 0.1 km. Blank preserves the old 10,000 km
geometric distance. For major supported planets the same control remains an
altitude above the reference surface. Small-body distances are from the center;
there is no modeled surface radius, shape, target gravity or impact clearance.
The actual target-relative encounter state is saved in arrival_state.json/CSV.

## HTTPS certificate problems

RoLaMGAS uses the operating system's certificate trust through truststore.
A school/company proxy or antivirus may present its own certificate. If it is
not trusted, the error explains how to install the administrator-provided root
or set ROLAMGAS_CA_BUNDLE to a trusted PEM CA bundle before restarting. SSL_CERT_FILE
is also accepted. Certificate verification stays enabled. The eight-planet
baseline remains usable offline; new objects and historical epochs outside
its coverage need a verified JPL connection. See SHARING.md for native builds.
