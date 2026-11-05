# Historical mission initialization and validation

The app adds initial guesses based on Europa Clipper (EMEJ), Galileo (EVEEJ), Mariner 10 (EVMeMeMe), Cassini (EVdvVEJS), and Juno (EdvEJ). These are offline timing/direction references, not trained AI weights or accepted recreations. First-leg initialization inspects only first-leg states and obeys hard C3 bounds before completing any candidate. All downstream turns, burns, speed joins, date windows and caps are still solved and screened normally.

Four JPL spacecraft departure references ship in `departure_seeds/historical_missions.json`. Saved geometric vectors are Earth-centered Ecliptic J2000, JD TDB, km and km/s. C3 is reconstructed as v² − 2μ/r; the outgoing asymptote is rotated through the Earth RTN frame at each trial launch. The two-day osculating estimates are approximately 40.65 (Europa Clipper), 15.42 (Galileo), 16.60 (Cassini), and 31.10 (Juno) km²/s². They are initialization references, not definitive launch-vehicle injection performance. Samples at three and five days document perturbation sensitivity. Raw responses and exact request parameters are preserved in `departure_seeds/historical_raw/`.

Mariner 10 uses NASA's published flyby timing and Mercury return spacing. Horizons Lookup returned no matching spacecraft; no measured departure vector is invented. Sources are attached to every mission record. Europa Clipper's future encounters remain planned, not flown data.

Choose one of the **Historical ...** examples to constrain launch and every encounter to the corresponding published calendar day. These are one-day TDB windows; NASA's UTC calendar days differ at their boundaries by roughly a minute. Narrowing to an exact epoch requires an explicit UTC-to-TDB conversion. These examples are requests for the solver, not claims that a passing reproduction has already been found. The real spacecraft include navigation corrections and finite planetary passages that a center-joined Lambert chain does not exactly model. Use departure/arrival vectors, C3, DSMs and finite-radius validation as well as calendar dates when assessing a reproduction.

To name a candidate, open its inspector, enter a **Mission name / label**, and select **Save name**. Desktop labels persist in the run's `candidate_names.json`; website labels persist in that browser. The search field matches the name, sequence and stable candidate ID. Names never alter scientific state, imply validation or get sent through anonymous sharing.

Regenerate the JPL initialization independently:

```powershell
.\.venv\Scripts\python.exe tools/download_historical_seeds.py
# Or recompute entirely offline from saved JPL responses:
.\.venv\Scripts\python.exe tools/download_historical_seeds.py --from-saved
```

Advanced settings can disable these references with `historical_mission_seeds: false`. Appended cruises and local candidate refinements do not receive unrelated historical starts. Their original trajectory stays authoritative.
