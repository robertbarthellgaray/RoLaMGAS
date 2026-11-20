# RoLaMGAS v0.2.9

Numbered dwarf-planet imports and moon-branch exports now resolve their parent
identities consistently. The moon targeter defaults to one correction timing,
and a completed branch can be selected directly with **Patch targeted moon**.

- Fixed Eris selection and recovery of saved website imports whose Horizons
  identifier was ambiguous. Imported coasts and costs are checked without
  optimizing or silently replacing the saved route.
- Added a JPL satellite catalog covering 523 parent systems and 992 satellite
  or reported entries. There are 464 targetable entries with the available data;
  414 lack measured radii and support center-distance approaches, not impacts.
  Catalogued entries without sufficient physical/orbital data remain unavailable.
- Added models for Dysnomia, Vanth, Weywot and Menoetius. Where the published
  satellite ephemeris cannot cover a future encounter, an unchecked, explicit
  opt-in permits a labeled two-body projection from a JPL reference orbit.
  Approximate future moon phase is not verified JPL coverage or a validated
  encounter prediction. The labels persist in exports and Celestia patches.
- Fixed parent-name checks for all catalogued systems, including numbered Pluto,
  Eris and Orcus names, while retaining candidate/trajectory checksum checks.
- A completed moon simulation enables the moon-patch checkbox before selection;
  checking it selects that simulation. Stale export status cannot reset a newer
  selection. The optional multi-timing scan and refinement remain available.
- Retains the latest shared-trajectory archive and website addon links.

The targeting/patch model remains preliminary: atmosphere, landing, surface
topography and unmodeled bodies are excluded. Physical constants and reference
orbit uncertainties are documented with each supported model.

Windows: extract the whole ZIP and keep `_internal` beside `RoLaMGAS.exe`.
Saved searches and caches stay in the persistent data directory. Apple Silicon
and Intel Mac DMGs are unsigned; Debian/Ubuntu x64 requires glibc 2.35+.
GPLv3 source, SHA-256 checksums and package verification accompany the downloads.
