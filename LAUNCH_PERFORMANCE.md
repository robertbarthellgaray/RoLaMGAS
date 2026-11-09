# NASA launch performance and addon audits

The website and desktop inspector show cached NASA LSP high-energy capacity
samples at the candidate's C3. Values between adjacent samples are linear
estimates. No extrapolation or missing-vehicle inference is performed. Vehicle
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
