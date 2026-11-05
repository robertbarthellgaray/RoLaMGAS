# Results and preview controls

The results page has a C3 versus flight-time scatter plot above the gallery, folded by default. Select its heading to expand or collapse it; Enter/Space also works when the heading has keyboard focus. It stays open or closed while candidates update. Each color represents an assist sequence. Select a dot with the mouse or Enter/Space to open that candidate's inspector, where CSV/XYZV integration and export remain available. The launch-year range filters both the graph and gallery. Route, yellow/red and pin filters also apply. Flight time uses saved TDB Julian epochs when available, with one year =365.25 days.

There are no efficiency ratings or rankings. The destination groups (planets, dwarf planets, asteroids and comets) remain in the public gallery. Pass/yellow/red continue to describe screening against the search limits.

The trajectory inspector has independent switches for planet markers and planet orbit paths, plus per-body switches. These only affect the drawing. They do not change ephemerides, trajectory states or exports. The header uses the supplied square RoLaMGAS logo.

Red candidates keep their scientific records and export controls but skip automatic trajectory sampling and PNG generation. This also suppresses previously cached red pictures. Red diagnostic dots can still appear in the scatter plot when Include red is selected; those points display stored metrics, not propagated paths.

A selected unrendered candidate gets priority in a dedicated preview queue. The next click supersedes the previous selection. Background sampling yields at safe boundaries; the numerical mission search continues independently. Planet ephemerides are reused between previews of the same run.

The unresolved flyby excess-speed mismatches are added across the sequence. If there are unresolved mismatches and their sum plus the already modeled maneuver total exceeds the DSM screening budget, the candidate is red. Explicitly constructed powered flybys are already charged and their excess-speed differences are not added twice. This scalar screening sum is not the actual powered-periapsis burn magnitude; the exporter constructs and budgets physical burns separately. A fully joined trajectory that only exceeds the total modeled budget retains the existing yellow classification unless an individual burn cap or another hard screen fails.

JUICE-based low-energy Earth-return starts are described in [JUICE_DEPARTURE_SEEDS.md](JUICE_DEPARTURE_SEEDS.md). Their spacecraft reference is bundled, so the numerical workers do not need to download it during a search.
