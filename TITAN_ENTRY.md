# Separate Titan atmospheric entry integrator

`titan_entry.py` accepts the Titan-relative position/velocity saved by moon
targeting, integrates gravity and aerodynamic forces, and exports a local XYZV,
states CSV, atmospheric profile CSV, numerical report and graphs. It runs on the
local CPU and does not need an AI service. The bundled reference atmosphere works
offline. This is a physics-based reference model, **not the operational Dragonfly
EDL simulation or a validated landing prediction**.

From this checkout:

```powershell
.\.venv\Scripts\python.exe -X utf8 titan_entry.py --state runs\dragonfly_titan_site\arrival_state.json --cache cache --output runs\titan_entry\ballistic
```

Default: constant ballistic coefficient 70 kg/m², zero lift, zero winds relative
to rigid corotation. It stops at Mach 1.5, the approximate supersonic-parachute
handoff. It does not silently continue a bare aeroshell to the surface.

For a **separately labeled illustrative parachute continuation** to 800 m:

```powershell
.\.venv\Scripts\python.exe -X utf8 titan_entry.py --state runs\dragonfly_titan_site\arrival_state.json --cache cache --prefix runs\dragonfly_titan_site\trajectory.xyzv --scenario illustrative-descent --output runs\titan_entry\site_reference_descent
```

`--cache` is optional: it adds differential Saturn gravity from existing hourly
JPL Saturn/Titan vectors. It never downloads data during entry integration. If
the requested cached coverage is absent, the error identifies the missing
coverage. Omit it to run spherical-Titan gravity only.

`--prefix` requires the cache and a Sun-centered cruise XYZV ending exactly at
the supplied entry epoch. Titan's JPL states translate the entry states back to
heliocentric coordinates. The exporter refuses a position/velocity mismatch;
it never resets the vehicle state. Both the untouched local entry and the joined
heliocentric `full_trajectory.xyzv` are saved. Keep their coordinate centers
distinct when importing into Celestia.

Other inputs: `--beta`, `--density-scale`, `--zonal-wind-mps` (eastward),
`--meridional-wind-mps` (northward), `--lift-to-drag`, `--bank-deg`, and
`--atmosphere PATH`. Wind flags add to any wind profile in the supplied CSV.
The entry module is also included as a native worker in the next local preview:
`RoLaMGAS.exe --rolamgas-module titan_entry --state ... --output ...`.
Released 0.2.5 does not contain this module.

## Atmosphere and provenance

The shipped CSV uses the original PDS Huygens HASI V1.1 products from 2005:

- [PDS HASI profiles](https://atmos.nmsu.edu/PDS/data/hphasi_0001/DATA/PROFILES/)
- `HASI_L4_ATMO_PROFILE_ENTRY.TAB` and its `.LBL`
- `HASI_L4_ATMO_PROFILE_DESCEN.TAB` and its `.LBL`
- Corrected `HASI_L4_ACCE_DENSITY.TAB` and its `.LBL` in `DATA/ACC`

The descent file supplies **1,816 archived densities**. The entry profile file
supplies 911 pressure/temperature pairs but leaves density empty despite its
label's fifth-column definition. The importer resolves this using the separate
**corrected accelerometer density product**: all 911 profile altitudes have exact
matches in that product. The bundled atmosphere therefore uses archived HASI
density values throughout, without ideal-gas substitution. Upper densities are
the instrument team's accelerometer-based retrievals and inherit their original
retrieval assumptions. Labels, source URLs, row counts and raw-file SHA-256
values are recorded in `model_assets/titan/hasi_reference.json`.

Interpolation uses PCHIP on log density/pressure and on temperature. The
146.797–157.3182 km gap is interpolated. Below the lowest 3 m sample its value
is held to the spherical surface. The altitude convention uses a 2,574.76 km
Titan mean radius, without a geoid or terrain map.

Rebuild/fetch independently:

```powershell
.\.venv\Scripts\python.exe -X utf8 tools\prepare_titan_atmosphere.py
```

Add `--offline` to require existing raw files under `cache/huygens_hasi`.
Replacement CSV columns are `altitude_m,density_kg_m3,temperature_k,pressure_pa`,
with strictly increasing altitude and positive finite values. Optional wind
columns are `zonal_wind_mps,meridional_wind_mps`.

[Titan-GRAM 2026](https://ntrs.nasa.gov/citations/20260007686) is NASA's engineering
model for mean atmosphere and statistical variation. Its C++ implementation is
available by request in the [GRAM Suite](https://software.nasa.gov/software/MFS-33888-1).
An exported GRAM column can replace the reference CSV. No licensed GRAM source
is redistributed here, and this HASI-based module is not Titan-GRAM.

## Dynamics and accuracy limits

Internally, metres and seconds are used. The inertial Titan-centered equations
include spherical gravity, optional differential Saturn gravity, drag and optional
lift. Atmosphere-relative velocity subtracts rigid Titan rotation and supplied
east/north winds. The IAU_TITAN prime meridian and pole are evaluated at each
output epoch for longitude/latitude. Numerical energy change is checked against
integrated aerodynamic and tidal work. Phase changes preserve position and
velocity. Input/output axes are Ecliptic J2000 and epochs are JD TDB.

The NASA 2024 [entry reference](https://ntrs.nasa.gov/citations/20240007259)
lists a 4.5 m aeroshell, reference mass 2,310 kg, ballistic coefficient 70 kg/m²,
7.3 km/s entry and −48° flight-path angle. Our saved arrival is different
(November 2035, about 8.49 km/s inertial); agreement with the reference is not
assumed. The current real mission plans [late 2034](https://science.nasa.gov/mission/dragonfly/).

The illustrative descent mode uses the newer published **8.25 m drogue** and
**16.7 m main**, with **CD=0.7 assumed** for each. During drogue descent it adds
subsonic capsule drag with assumed CD=1.0 and the 4.5 m reference area. At 5 km
main-chute drag replaces that model. Mass stays at the published CBE 2,309 kg;
release speed is computed, not fitted. These are explicit approximations, not
a retrieved parachute database. They stay fixed during density sensitivity runs.
NASA's [2025 modeling overview](https://ntrs.nasa.gov/citations/20240014477)
describes the newer geometry and example roughly 137-minute descent. The older
2024 example used a smaller drogue and roughly 119 minutes; those design cycles
must not be mixed as an exact validation target.

The model omits attitude dynamics, parachute inflation/reefing, mass jettison,
heating/ablation, seasonal weather prediction and powered flight. Mach uses
constant gamma=1.4 and the stated mixture gas constant. Density/wind sweeps are
sensitivity scenarios, not statistical confidence intervals. A single 2005
column cannot establish a 2034/2035 landing ellipse.

The report also compares its predicted aerodynamic load with the **12 Earth-g**
entry-load constraint in NASA's 2025 study. Our faster hypothetical arrival can
exceed that reference in this simplified model. Numerical completion does not
mean the flight vehicle meets its load or thermal requirements.

Targeting an entry subpoint over 4° N, 162.5° E is **not targeting a landing
there**: the descending vehicle follows a ground track while Titan rotates.
For a Selk-area arrival, the next targeting stage must solve for an uptrack entry
state that reaches the desired location through the selected EDL model, then
reconnect that state to the interplanetary approach. An accurate Dragonfly addon
also needs the correct 2034 arrival geometry and better vehicle/wind inputs.
