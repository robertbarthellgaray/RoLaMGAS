# RoLaMGAS v0.2.8

Numbered Pluto targets now resolve to the physical Pluto ephemeris, and saved
Pluto arrivals support targeting Charon, Nix, Hydra, Kerberos and Styx.

- Unified **Patch target** controls cover planets, dwarf planets, asteroids and
  comets. Choose a centered duration in days or years and an optional maximum
  playback sampling interval. Small-body patches default to one year total,
  centered on the encounter; moon windows cover at least one orbital period.
- Fixed Trident planet/moon package errors caused by missing catalog metadata,
  legacy Windows catalog encodings, and nested trajectory provenance.
- Cache-boundary roundoff no longer causes false ephemeris extrapolation errors.
  Real out-of-range requests still stop with the missing coverage identified.
- Pluto moon targeting includes Charon's perturbations for the smaller moons,
  checked upstream corrections, collision checks and post-encounter continuation.
- Expanded launch C3, arrival excess speed and flight-time help with historical
  mission examples and clearer units.

Model limits: these are preliminary trajectory-design tools. Pluto's smallest
moon masses are uncertain; Kerberos and Styx use documented massless approximations.
Other dwarf-planet moon systems still require separately validated physical models.
Coarser user-selected playback samples can reduce ephemeris interpolation fidelity.

Windows: extract the whole ZIP and keep `_internal` beside `RoLaMGAS.exe`.
Existing searches and caches remain in the persistent data directory.
Apple Silicon and Intel Mac DMGs are unsigned; Debian/Ubuntu x64 requires glibc 2.35+.
GPLv3 source, SHA-256 checksums and package verification accompany the downloads.
