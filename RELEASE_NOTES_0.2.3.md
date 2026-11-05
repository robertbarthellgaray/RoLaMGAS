# RoLaMGAS 0.2.3

Complete EdvEVEEJ starters now include a solver-built Jupiter route at C3 6.25
with a 493.9 m/s first-leg DSM, plus four higher-C3/lower-DSM tradeoffs. Select
**Juice style low C3** to load a compatible example. Every starter is rechecked
against the current limits; its reference launch is November 2033 and its last
Earth flyby is about 204.5 km high. This is an original Sun-only design, not a
reconstruction or an n-body validation of JUICE. See [seed details](JUICE_DEPARTURE_SEEDS.md).

The results C3/time graph starts folded and supports filtering and candidate
selection. Planet markers and paths have separate preview switches. Selected
candidates get render priority; red trajectories skip rendering. Combined
unresolved flyby speed mismatches count against the DSM screening budget.
Efficiency ratings are removed; destination groups remain. See [preview details](PREVIEW_AND_RESULTS.md).

Windows: extract the complete ZIP, then run RoLaMGAS.exe. Existing searches and caches stay in the application data directory. Mac and Linux packages include the same offline ephemerides and solver.
