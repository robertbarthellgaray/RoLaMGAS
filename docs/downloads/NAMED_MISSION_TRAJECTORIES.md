# Named mission-study trajectory downloads

Finite-radius patched conics using JPL planet states: Sun-only outside planned
SOIs, encounter-planet-only inside. Includes one month after final encounter.
These are modified concept reconstructions, not official spacecraft ephemerides.

| Name | CSV | Celestia XYZV | Exported cruise Δv | Original search budget |
|---|---|---|---:|---|
| Trident date-match — added maneuvers | [CSV](f53fc65c9329-patched.csv) | [XYZV](f53fc65c9329-patched.xyzv) | 2.080 km/s | Exceeded |
| Mars Life Explorer 2035 | [CSV](0fc1f2bcd586-patched.csv) | [XYZV](0fc1f2bcd586-patched.xyzv) | 0.096 km/s | Within |
| Mars Life Explorer 2037 | [CSV](dd67c26fd41f-patched.csv) | [XYZV](dd67c26fd41f-patched.xyzv) | 0.119 km/s | Within |
| Mars Life Explorer 2039 | [CSV](9ca55df1c55c-patched.csv) | [XYZV](9ca55df1c55c-patched.xyzv) | 0.089 km/s | Within |
| CALYPSO — Uranus cruise | [CSV](35bd4d9c6e03-patched.csv) | [XYZV](35bd4d9c6e03-patched.xyzv) | 0.681 km/s | Within |
| T-OWS 2030 — operations-table schedule | [CSV](552363ae7812-patched.csv) | [XYZV](552363ae7812-patched.xyzv) | 1.319 km/s | Exceeded |

All six passed numerical arc/join continuity and the sampled/refined planet/Sun
clearance screen. This is not continuous n-body or moon/ring validation. The
exported costs include the retargeting/junction impulses needed to join finite
SOI patches; they differ from the original Lambert candidate scores. Launch
injection and target capture are excluded from the cruise totals.

Each file has a matching `-integration.json`, `-burns.csv`, `-encounters.csv` and
`-README.txt`. The named website pages link to these files and reports. Trident
ends at a Neptune encounter; no resolved Triton flyby is claimed. CALYPSO is the
Uranus cruise only, not an Ariel/KBO reconstruction.
