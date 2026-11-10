# Mission-study seeds and recreations

See [the recreation report](studies/mission_report_recreations/README.md), [the modified Trident reconstruction](studies/trident_reconstruction/README.md), and [the source timing catalog](departure_seeds/mission_studies.json).

The desktop source app includes eight selectable study presets and nine eligible study timing references. They are numerical starting points, not accepted solutions: every candidate is freshly evaluated against C3, burn, turn-angle, altitude and time requirements. Existing historical references remain available. Continuous-thrust concepts and references without sufficient timing data are excluded from ballistic seeding.

Website **Use in desktop app** downloads the selected dates, Lambert branches, physical DSM controls and appropriate powered-flyby settings. In the source app or the next approved native build, **Import options / website trajectory** reloads that candidate without a new search. The public 0.2.3 executable predates exact-candidate loading. Native builds remain subject to local user trial before publication.

Candidate pages show a repository-added timestamp in UTC. Git history supplies curated cases; the API retains first receipt separately from updates. Legacy server times are explicitly marked as the earliest retained receipt when the original first publication time is unavailable. Solve times are never substituted for publication times.

Every ordered pair of the eight planets now has timing bounds. Missing old-cache/database pairs fall back to a broad 20-year planet-to-planet envelope, or 50 years for other targets. Existing specific bounds and explicit user overrides take precedence. These are search envelopes, not guarantees that a transfer is feasible.
