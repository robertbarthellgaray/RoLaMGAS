# Titan entry reference-model checks

Reproduce locally:

```powershell
.\.venv\Scripts\python.exe -X utf8 tools\run_titan_entry_study.py
```

The script needs no network and uses the bundled HASI column. The adjacent
JSON/CSV compare a constant-beta 3-DOF integrator with high-level reference
conditions in [NASA's 2024 Dragonfly aerothermal poster](https://ntrs.nasa.gov/citations/20240007259).
Reference inputs are constructed states, not downloaded official spacecraft
ephemerides. The hypothetical saved arrival remains November 2035, whereas the
real Dragonfly mission currently plans late 2034.

Numerical work/energy balance is checked. Using the paper's entry speed, angle
and beta, this simplified model's peak dynamic pressure is about **29% below**
the Dragonfly reference and **12% below** the Huygens reference. These are
material differences: the model is **not validated as an operational EDL
prediction**. We do not adjust coefficients just to erase those differences.
Vehicle aerodynamics, exact interface/state conventions and the atmosphere used
by each source need further comparison.

Density 0.8/1.0/1.2 and an eastward 50 m/s wind are illustrative sensitivity
cases, not probability distributions. Mach uses a constant ideal-gas mixture;
density itself comes from the corrected archived HASI products.

The separate full-descent examples use published 2025 chute dimensions and assumed drag coefficients.
They stop at 800 m release and do not model powered flight or touchdown. For
the 4° N, 162.5° E **entry subpoint** example, the zero-wind scenario releases
near 18.35° N, 154.22° E. A desired surface site therefore requires an uptrack
entry target and an inverse EDL solve; selecting an entry subpoint above the
site is insufficient.

See [TITAN_ENTRY.md](../../TITAN_ENTRY.md) for reproducible commands, force
model, data provenance, phase assumptions and how to supply a GRAM-derived
column or wind profile. Detailed run files remain under `runs/titan_entry*`.
