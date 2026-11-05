# RoLaMGAS

**Robert's Lambert Multi Gravity Assist Solver**

![RoLaMGAS orbital artwork](docs/images/RoLaMGAS.png)

[Explore the live trajectory gallery](https://robertbarthellgaray.github.io/RoLaMGAS/) · [Desktop downloads & source](https://github.com/robertbarthellgaray/RoLaMGAS/releases/tag/rolamgas-v0.2.3) · [Robert’s portfolio](https://robertbarthellgaray.github.io/)

## Browse before downloading

The live GitHub Pages explorer combines curated mission examples with a shared trajectory library. New shared submissions join the destination filters, playback, mission dates and downloads automatically. Duplicate same-day encounter sequences share one public entry.

Curated Lambert admission independently recomputes flyby speeds and turning geometry: excess-speed mismatch ≤1 m/s, each DSM ≤700 m/s, and inferred periapses above their stated floors. Coast endpoints and event states are cross-checked against the independent JPL cache. Integrated concepts have a separate Sun/eight-planet clearance audit. See [`docs/data/catalog_audit.json`](docs/data/catalog_audit.json).

Shared pass/yellow labels preserve the original submitting limits and are not independent validation. The desktop app recomputes their science before reuse.

The website is static HTML/CSS/JavaScript under `docs/`. It runs no optimizer and requires no Python server, account or API key. Interactive playback interpolates saved points. The desktop application below performs new searches on the user’s hardware.


Explore interplanetary gravity-assist sequences, inspect candidates as they are
found, refine nearby encounter dates, and export propagated trajectories for
Celestia or other tools. All optimization runs on your own CPU; no AI service,
API key or subscription is required.

## Desktop app

Download the v0.2.3 package for your platform: Windows ZIP, Apple Silicon or
Intel Mac DMG, or Debian/Ubuntu x64 DEB. They open the same local browser GUI.
On Windows, extract the ZIP and open RoLaMGAS.exe inside the folder.
The Mac preview is unsigned/not notarized. See [platform instructions](SHARING.md).
Python and the scientific dependencies are bundled. The eight-planet baseline
is included, covering 2027–2100 at one-day cadence, with extra six-hour Mercury
data. The first run installs those tables into your persistent cache.

Searches, exports and extra Horizons downloads are stored in
`%LOCALAPPDATA%/RoLaMGAS`, separate from the executable. Updating the executable
preserves your work. An internet connection is needed for targets or epochs not
already cached. `ROLAMGAS_DATA_DIR` can select another data directory.

## New in v0.2.3

Complete EdvEVEEJ starters now include a solver-built Jupiter route at C3 6.25
with a 493.9 m/s first-leg DSM, plus four higher-C3/lower-DSM tradeoffs. Select
**Juice style low C3** to load a compatible example. Every starter is rechecked
against the current limits; its reference launch is November 2033 and its last
Earth flyby is about 204.5 km high. This is an original Sun-only design, not a
reconstruction or an n-body validation of JUICE. See [seed details](JUICE_DEPARTURE_SEEDS.md).

The results C3/time graph starts folded and supports filtering and candidate
selection. Planet markers and paths have separate preview switches. Selected
candidates get render priority; red trajectories skip rendering. Combined
unresolved flyby speed mismatches count against the DSM screening budget.
Efficiency ratings are removed; destination groups remain. See [preview details](PREVIEW_AND_RESULTS.md).

## New in v0.2.2

Search the shared trajectory database before allocating optimizer workers.
Every compatible candidate is revalidated against the current ephemerides and
all your search constraints. Zero, one or two verified matches start local
optimization automatically. Three or more show a choice: use the database
results, or search locally too. Bundled records work offline; service failures
fall back to the local solver.

The app includes 2,047 sanitized passing trajectories, connects to the live
community API by default, and defaults to showing yellow candidates while
hiding red candidates. Sharing has a visible opt-out control. The public
library excludes C3 above 250 km²/s² and small-body flights of 60 years or more;
local search limits remain configurable. See [community data details](COMMUNITY.md).

## Run from source

Use 64-bit Python 3.12. On Windows, run `Setup Python.cmd`, then
`Launch RoLaMGAS.cmd`. On macOS/Linux, create a virtual environment, install
`requirements.txt`, and run `python rolamgas.py`.

The baseline archive is unpacked into `cache/` at first launch. New custom-body
data are downloaded from JPL Horizons and cached locally; searches then work
offline within that coverage. The source app saves searches next to its code.

## Candidate refinement

Open a candidate and click **I like this one**. Choose an encounter-date variation
(default ±30 days). A separate search retains its assist sequence, starts from
its date/DSM solution and Lambert branches, and minimizes C3 under the saved
mission limits. The parent search is retained. A local search cannot guarantee
an improvement or a global optimum.

## Extend a selected trajectory

Open its inspector and choose **Add a flyby afterwards**. Select a planet,
number of added encounters and timing bounds. The earlier cruise, dates and
launch C3 stay fixed; only the new portion is searched. Optional new-leg DSMs
retain the saved burn limits. Start with one Mercury return and extend a
result again if its resonance is narrow. Yellow results can still be useful
when the requested arrival speed has not been reached.

## Mercury returns

Choose repeated Mercury encounters, for example `EVMeMeMe` or
`EVVMeMeMeMe`. `Me` means Mercury; `M` means Mars. Resonance-informed guesses
favor returns separated by integer Mercury years while testing multi-revolution
Lambert branches. Every result is still checked for speed matching and turn
feasibility above the periapsis floor. **Minimize arrival V∞** is useful when
seeking a less expensive terminal capture. Capture burns are not included in
the interplanetary screening budget. These templates do not reproduce
BepiColombo's continuous electric propulsion.

## Model and exports

JPL geometric heliocentric Ecliptic J2000 vectors, TDB dates, km and km/s.
The search uses solar Lambert/Kepler arcs and asymptotic flyby joins. Optional
DSMs and powered flybys have explicit budgets. A passing screen is an
approximate patched-conic candidate, not a navigation-grade n-body solution.
Finite-radius trajectory validation/export reports patch correction burns and
clearance checks separately. CSV, XYZV and complete Celestia packages are available.

See `GUI_GUIDE.md`, `SHARING.md` and the original JPL response metadata for details.

## Build and verification

`python -m unittest discover -p "test_*.py"`

Install `requirements-build.txt` and run
`python build_release.py --native --version 0.2.3` on the target OS to build
the native EXE, DMG or DEB plus matching GPL source. GitHub Actions can build all
three platforms; see [SHARING.md](SHARING.md).

## License and provenance

Copyright © 2026 Robert Barthell Garay. RoLaMGAS is distributed under
**GNU GPL version 3 (GPL-3.0-only)**; see [LICENSE](LICENSE).
Third-party libraries retain their own copyrights and licenses; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
The source release includes the code, build instructions, pinned dependencies,
model assets and baseline ephemerides corresponding to the Windows preview.
JPL supplies the ephemerides and does not endorse this application.

## Gallery maintenance

GitHub Pages serves `docs/` from `main`, with no build step. The catalog contains
curated numerical results, not user histories or arbitrary cache contents.
`tools/build_public_catalog.py` accepts a private trajectory project and app-data
directory as inputs to regenerate the public field subset. The existing gallery
runs entirely from the committed static data and does not need those private inputs.
