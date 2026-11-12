# RoLaMGAS 0.2.5

The approved 0.2.5-test3 solver is promoted to 0.2.5. Existing searches and
cached ephemerides stay in the user's data directory.

## Finite-radius flyby exports

- Jointly target departure, finite flyby geometry and existing DSMs before
  integrating the patched-conic trajectory. Remaining velocity corrections
  are explicit burns, included in individual and total budget checks.
- Preserve the reference coast's physical winding near resonant returns.
  Moving from planet-center Lambert endpoints to finite SOI endpoints must
  not accidentally select an extra or missing heliocentric revolution.
- Allow intermediate flyby dates to move by up to 365.25 days on either side,
  with a two-day default. Launch and final encounter dates stay fixed.
  Larger windows are distinct variants, not exact historical reconstructions.
- Preserve full Julian-date precision in website-to-desktop handoffs.
- Report exported C3, actual DSMs, periapsis impulses, patch corrections and
  encounter dates separately. Numerical arc checks alone do not certify a
  physically acceptable fuel budget.

The tested CLAUDIUS Lambert recreation reduces additional patch corrections
from 177.484 to 7.479 m/s with a 30-day window. Total cruise impulses fall from
915.060 to 628.365 m/s; exported C3 changes from 28.55236 to 29.03872 km2/s2.
Launch and December 2045 arrival stay fixed. Launch injection and arrival
capture are excluded from these cruise totals. This is a locally refined
candidate, not a proof of a global optimum or an official mission ephemeris.

The force model remains Sun-only outside planned SOIs and encounter-planet-only
inside each SOI. This is not n-body propagation. Clearance checks use available
cached body coverage; unplanned encounters are not automatically patched.

## Website downloads and candidate inspection

117 of 129 portable curated candidates received validated finite-radius
replacement downloads. Original files remain available alongside the new burn
tables, encounter dates and targeting reports. Twelve retain their prior files;
the original integrated CLAUDIUS, Tianwen-4 and Mercury cases are preserved.
Source preview metrics remain distinct from the refined download's metrics.

The release also includes the current proposal/resonance seeds, launch-month
grouping, mobile layout fixes and explicit diagnostics for stored flyby gaps.
See FINITE_PATCH_TARGETING.md and docs/data/finite_download_review.json for the
method and per-candidate review results.

## Downloads

- Windows: extract the entire ZIP and open RoLaMGAS.exe inside its folder.
- macOS: choose the Apple Silicon or Intel DMG. Builds are unsigned.
- Linux: use the Debian/Ubuntu amd64 DEB; glibc 2.35 or newer is required.
- GPLv3 source and SHA-256 checksums accompany the native packages.

Verification includes source and browser regressions, numerical download
integrity checks, and frozen scientific-kernel, saved-seed and full-chain checks.
