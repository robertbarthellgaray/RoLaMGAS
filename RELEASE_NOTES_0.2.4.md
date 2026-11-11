# RoLaMGAS 0.2.4

The approved test8 solver is promoted to 0.2.4. Existing searches and downloaded
ephemerides remain in the user's data directory when the app is updated.

## Search coverage and reliability

- Try all matching historical/proposal references instead of only the first
  three. Every retained reference receives a short feasibility refinement;
  checkpoints record which references were attempted and refined.
- Preserve a reference's first-leg timing when its launch C3 is already within
  the user's limits. Out-of-range departures still require C3 projection.
- Add cited Decadal Survey timing references and selectable study presets, plus
  missing one-revolution departure branches and route timing coverage.
- Fix Start Search being blocked by a hidden fractional custom-target duration.
  Visible validation messages now identify invalid fields.

## Website handoff and Celestia exports

- Open the exact website candidate in the desktop app using its saved dates,
  Lambert branches and maneuver controls, then revalidate it locally.
- Optional dwarf-planet patches include JPL state vectors around the encounter
  year and preserve the original Celestia orbit outside that interval.
- Named mission-study trajectories have separate finite-radius integrated
  downloads, interpolation checks, encounter reports and explicit burn budgets.

The proposal timing catalog contains numerical initial guesses, not verified
reconstructions of every source report. The restricted 2040s Saturn survey
still found no passing C3 <20, flight time <10 year candidate; no such solution
is claimed by this release. See studies/saturn_2040s_seed_audit/README.md.

## Downloads

- Windows: extract the ZIP and open RoLaMGAS.exe inside its folder.
- macOS: use the Apple Silicon or Intel DMG for your hardware. Builds are unsigned.
- Linux: install the Debian/Ubuntu amd64 DEB; glibc 2.35 or newer is required.
- GPLv3 source and SHA-256 checksums accompany the native packages.

The Windows folder package avoids one-file extraction at startup. Managed lab
computers may still require administrator approval of unsigned software; this
release does not claim to resolve the reported CrowdStrike policy block.

Verification includes the Python regression suite, browser/API contract tests,
real-JPL seed coverage checks, and frozen scientific-kernel and search checks.
