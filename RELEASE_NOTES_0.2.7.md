# RoLaMGAS v0.2.7

This release fixes searches that stopped with **No feasible solution, try lower M!**:
infeasible Lambert trials are skipped while valid seeds and other branches continue.

- Cancel a running integration from the export controls and retry with new settings.
  Failed frozen workers exit cleanly instead of keeping the integration slot busy.
- Continue a selected moon-approach trajectory for a user-selected number of months
  after closest approach. Impact and atmospheric-entry branches stop at their interface.
- Celestia planet/moon patch files use fewer playback samples with checked Hermite
  interpolation error; the solver's source ephemerides retain their original accuracy.
- Share checked propagated trajectories, CSV/XYZV files, burn tables and validation
  summaries with the public library when sharing is enabled. Sharing can be disabled
  in the app. A failed upload does not prevent local exports.
- Background update notifications and a manual Check updates button link to releases;
  the app does not install updates automatically.
- Additional historical/proposal seeds and planar Earth-return guesses, including
  EdvEdvEU, help initialize new searches. Feasibility still depends on the selected
  date windows, launch energy and maneuver limits.
- Updated launch-capacity estimates, energy advisories, customizable comparison
  graphs and website handoffs are included in the desktop download.

Windows: extract the whole ZIP and keep `_internal` beside `RoLaMGAS.exe`.
Existing searches and caches remain in the persistent data directory.
Apple Silicon and Intel Mac DMGs are unsigned; Debian/Ubuntu x64 requires glibc 2.35+.
GPLv3 source and SHA-256 checksums accompany the native packages.

Numerical arc checks and submitted pass/yellow labels are not full mission certification.
The export report states the force model, actual burns and validation limits.
