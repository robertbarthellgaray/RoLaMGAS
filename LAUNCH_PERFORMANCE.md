# NASA launch performance and addon audits

The local source and website datasets include independently published international references: three historical Long March polynomial fits and one LM-5 study point. A separate, explicitly labeled LVM3 estimate extrapolates the November 2025 NSIL elliptical-orbit curves to C3 0–30; it is not a provider rating. Permission to run the hosted [SilverBird Astronautics calculator](https://silverbirdastronautics.com/LVperform.html), by John Schilling, was confirmed by the project owner on 2026-11-21. Its underlying engineering database is not redistributed. The country selector now includes separately credited SilverBird scenario outputs collected with that permission. The 2012 Indian planetary mission mass ranges remain research because their C3 values are unspecified. See [international launch performance research](studies/international_launch_performance/README.md). Reattach the supported capacity rows after a NASA refresh with `python tools/build_international_launch_performance.py --plot`.

The website and desktop inspector show cached NASA LSP high-energy capacity
samples at the candidate's C3. Values between adjacent samples are linear
estimates. Explicitly labeled engineering models extend coverage through C3 200;
see [model assumptions](studies/published_launch_performance/EXTRAPOLATION.md).
Published samples take precedence over those estimates. Vehicle
configurations remain separate: recovery and expendable versions have different
capacities. The expanders retain NASA's adapter, margin and ground rules.

In the local desktop preview, **Query NASA at this exact C3** queries the public
NASA form or reuses an exact query cached within the last 30 days. The UI remains
responsive. NASA's form is not a published API; format changes and outages cause
a visible failure, never a made-up capacity. A successful query with no vehicles
is explicitly distinguished from an estimate of zero payload.

From the source folder, run:
    python launch_performance.py --c3 28
    python launch_performance.py --c3 55 --refresh --output performance.json

Refresh static samples manually:
    python launch_performance.py --curve-grid 0 6.25 10 20 28 40 55 70 100 150 200 250 --output gui_assets/launch_performance_curves.json
Copy the resulting JSON to docs/data/launch_performance_curves.json before
publishing the website. Requests contain only C3; no mission name or personal
information is sent. NASA source: https://elvperf.ksc.nasa.gov/Pages/Query.aspx

Audit a Sun-centered addon without changing its files:
    python tools/audit_addon_trajectory.py addon.zip --output releases/testing/addon_audit

The audit checks all recorded solar coasts, then tests the supplied outgoing
continuation against an independent Kepler propagation. It saves numeric
diagnostics and a plot. A planetary flyby and a solar escape are separate
properties: a perfectly continuous flyby trajectory can remain Sun-bound.

New package manifests and integration reports record engine_version. The Ixion
ZIP supplied for this task lacked version metadata. Its Neptune–Ixion leg
already had an inward prograde Lambert loop: the export reaches 0.48037 AU in
January 2063, then Ixion in August 2078. Its 24-month extension is outbound
through August 2080, agreeing with an independent two-body solution within
0.00227 km. The subsequent Sun-only conic reaches 57.93 AU in December 2141;
later planetary encounters are outside this extrapolation.

The original user-supplied ZIP was not modified, and its contents were not
published to the shared trajectory library.


## SilverBird country selector and repeatable collection

The website and desktop candidate inspector include **Country / region** above
the launch-capacity table. All is the default; selecting a country filters both
the capacity rows and their ground rules. Electron is listed for USA and
New Zealand. Country refers to the launcher, not the launch-site location.
NASA rows, published references and SilverBird models retain separate sources.

`silverbird_performance.py` submits public calculator scenarios to
[John Schilling’s hosted calculator](https://silverbirdastronautics.com/LVperform.html).
The table works offline from cached curves; browsing the website does not submit
calculator requests. To refresh these output samples from the source folder:

```text
python silverbird_performance.py
python silverbird_performance.py --countries India China --refresh
python silverbird_performance.py --countries Europe --grid 0 5 10 15 20 30 40 60 100 158 200
```

The initial collection covers 17 explicit launcher configurations from USA,
China, India, Europe, Russia, Japan and New Zealand. Every scenario uses escape
C3, a 200 km Earth perigee, 0-degree departure declination, mixed calibration,
GCS shutdown and no end-of-life disposal burn. Trajectory mode follows the
source form's supported optimal/direct/two-burn options. Configuration choices,
launch site, timestamps and response hashes are recorded per sample in
`studies/international_launch_performance/silverbird_scenarios.json`.

The calculator's payload includes adapters/attachment fittings. These generic
declination-zero models are not mission-specific capacities or provider
guarantees. The table retains source 95% model intervals; an interpolated mass
shows the intervals at its bracketing samples, not a fabricated interpolated
confidence interval. Positive results are linearly interpolated only between
adjacent successful samples. Missing samples remain unavailable; SilverBird
curves are never extrapolated or used to synthesize kick-stage combinations.

Requests are sequential, at least one second apart. Per-scenario responses are
cached locally; `--refresh` refreshes the public form catalog and selected
outputs. The form catalog otherwise expires after 30 days. No engineering
database, third-party JavaScript or saved source HTML is published or bundled.
The two app/site data files are updated together after collection succeeds.
