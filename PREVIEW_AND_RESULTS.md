# Results and preview controls

The results page has a C3 versus flight-time scatter plot above the gallery, folded by default. Select its heading to expand or collapse it; Enter/Space also works when the heading has keyboard focus. It stays open or closed while candidates update. Each color represents an assist sequence. Select a dot with the mouse or Enter/Space to open that candidate's inspector, where CSV/XYZV integration and export remain available. The launch-year range filters both the graph and gallery. Route, yellow/red and pin filters also apply. Flight time uses saved TDB Julian epochs when available, with one year =365.25 days.

There are no efficiency ratings or rankings. The destination groups (planets, dwarf planets, asteroids and comets) remain in the public gallery. Pass/yellow/red continue to describe screening against the search limits.

The trajectory inspector has independent switches for planet markers and planet orbit paths, plus per-body switches. These only affect the drawing. They do not change ephemerides, trajectory states or exports. The header uses the supplied square RoLaMGAS logo.

Red candidates keep their scientific records and export controls but skip automatic trajectory sampling and PNG generation. This also suppresses previously cached red pictures. Red diagnostic dots can still appear in the scatter plot when Include red is selected; those points display stored metrics, not propagated paths.

A selected unrendered candidate gets priority in a dedicated preview queue. The next click supersedes the previous selection. Background sampling yields at safe boundaries; the numerical mission search continues independently. Planet ephemerides are reused between previews of the same run.

The unresolved flyby excess-speed mismatches are added across the sequence. If there are unresolved mismatches and their sum plus the already modeled maneuver total exceeds the DSM screening budget, the candidate is red. Explicitly constructed powered flybys are already charged and their excess-speed differences are not added twice. This scalar screening sum is not the actual powered-periapsis burn magnitude; the exporter constructs and budgets physical burns separately. A fully joined trajectory that only exceeds the total modeled budget retains the existing yellow classification unless an individual burn cap or another hard screen fails.

JUICE-based low-energy Earth-return starts are described in [JUICE_DEPARTURE_SEEDS.md](JUICE_DEPARTURE_SEEDS.md). Their spacecraft reference is bundled, so the numerical workers do not need to download it during a search.


The graph's selector switches its vertical axis between flight time and arrival V∞. The C3 axis, sequence colors, gallery filters and click-to-inspect behavior stay the same. The public site's Mission limits now contains the launch-year range and maximum flight time; links preserve these values and the graph mode.

Both inspectors estimate the ideal impulsive departure Δv from a chosen positive circular parking altitude: sqrt(C3 + 2μ/r) − sqrt(μ/r). The departure planet supplies μ and reference equatorial radius. This is a separate display calculation, not an integrated parking orbit or a cruise burn. It excludes finite-burn losses and plane changes. At C3 6.25 and 200 km Earth altitude it is about 3.5046 km/s.

The optional same-sequence comparison shows C3, flight time and arrival V∞ against the mean, median and population standard deviation of saved pass/yellow candidates for that target and sequence. The desktop scope is the current run; the website scope is the available library before filters. Percentiles use mid-ranks for tied values. No efficiency labels are assigned. A minimum of two matching records is required; these are biased search samples, not population estimates of all feasible missions.

The website's Animate planets button lazily loads a compact JPL-backed playback table. Filled moving dots use the spacecraft timeline's TDB date; encounter markers stay fixed. The camera includes the participating planet orbit context so moving planets remain in view. Cubic Hermite interpolation is display-only. Missing dates and cache gaps are never extrapolated. The table is reproducible from the verified local cache with `tools/build_planet_playback.py` and records its sampled interpolation errors. The static name registry is refreshed by `tools/refresh_body_names.py --live`, using exact JPL IDs rather than fuzzy names.

Mission names and historical-day validation presets are described in [HISTORICAL_SEEDS.md](HISTORICAL_SEEDS.md). Custom desktop labels stay in the saved run, and website labels stay in that browser; anonymous submissions contain no names.
