# Mission-report recreation attempts

These are actual calculations with the same model used by the desktop app, using local JPL Horizons vectors. Reference values were not copied into the results. Only passing, independently audited cases are admitted to the interactive gallery.

Run independently:

```text
python tools/recreate_mission_studies.py --cache PATH_TO_JPL_CACHE --iterations 160
```

The script saves successful and unsuccessful attempts, search settings, full candidate states, and independent audit reports. It does not upload anything. Cited reference schedules and limitations are in [mission_studies.json](../../departure_seeds/mission_studies.json). All eight study schedules also appear as `study_...` presets in the source app. Eligible timing guesses participate in normal searches, subject to user date/C3 constraints.

| Study | Result | Recomputed C3, km²/s² | Cruise burns, m/s | Important differences |
|---|---|---:|---:|---|
| [Mars Life Explorer 2035](https://robertbarthellgaray.github.io/RoLaMGAS/#mission=0fc1f2bcd586) | Pass | 22.967 | 0 | Report C3 23.1; arrival V∞ 3.105 km/s versus report 3.1 |
| [Mars Life Explorer 2037](https://robertbarthellgaray.github.io/RoLaMGAS/#mission=dd67c26fd41f) | Pass | 18.198 | 0 | Report C3 18.4; arrival V∞ 3.634 km/s versus report 3.7 |
| [Mars Life Explorer 2039](https://robertbarthellgaray.github.io/RoLaMGAS/#mission=9ca55df1c55c) | Pass | 37.066 | 0 | Report C3 37.5; arrival V∞ 2.882 km/s differs from report 3.7 |
| [CALYPSO Uranus cruise](https://robertbarthellgaray.github.io/RoLaMGAS/#mission=35bd4d9c6e03) | Pass | 120.704 | 39.496 | Report maximum C3 121; reconstructed powered Jupiter join. Ariel and KBO phases excluded |
| [T-OWS 2030 operations schedule](https://robertbarthellgaray.github.io/RoLaMGAS/#mission=552363ae7812) | Pass | 89.688 | 9.612 | Report design variants differ; this does not reproduce section-3.3 C3 80.4 |
| CORAL chemical Centaur concept | Not admitted | 45.748 | 2523.086 | Fails cruise and powered-flyby budgets; terminal rendezvous burn is separate |
| ADVENTS primary Venus concept | Not admitted | 13.424 | 9047.128 | Current model cannot place the cited DSM at 8.5% of a leg; terminal V∞ and burn budget are not reproduced |
| T-OWS 2031 Mars-assist backup | Not admitted | 89.276 | 2632.046 | Individual dates are analyst estimates from approximate report durations; insufficient for a passing reconstruction |

[Trident](../trident_reconstruction/README.md) is published separately with its added maneuvers explicitly identified. All six admitted cases were independently integrated coast by coast and reloaded through the desktop app's exact-candidate importer. [Website links](website_links.json), [public-library receipt](upload_receipt.json), and individual `validation.json` files retain the evidence.

Enceladus Multiple Flybys and Titan Orbiter/Probe references provide useful broad cruise durations, but no complete dated encounter chain was recovered here, so they are reference-only entries. CROCODILE uses continuous solar electric propulsion and is intentionally excluded from ballistic Lambert seeds. No rejected case is presented as an accepted trajectory.

Finite-radius patched-conic versions of the six named reconstructions are now
available in the [named download index](../../docs/downloads/NAMED_MISSION_TRAJECTORIES.md),
with CSV, XYZV, full integration reports and burn tables. All six pass the
numerical and planet/Sun clearance checks. Trident and T-OWS exceed their original
onboard budgets after patch retargeting; this is explicitly disclosed. The nine
new Decadal references remain initialization data, not additional solved missions.
