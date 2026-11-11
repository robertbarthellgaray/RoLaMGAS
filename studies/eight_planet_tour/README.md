# All eight planets, 1970–1988

The verified result is in [verified_source_recreation](verified_source_recreation/README.md).
It includes a RoLaMGAS desktop-import file, the full candidate, encounter comparison,
plots, JPL provenance, and independent numerical coast checks.

Original RSS/Principia trajectory design: **ReachStar on Bilibili**. This project
recreates the route using JPL data; the original route is credited to ReachStar.

The user supplied the trajectory and then a detailed encounter table.
The table corrected the first Venus encounter to **1970-12-23**, rather than
1970-12-13 in the initial date list. Its 14 TCM entries total **4.54 m/s**.

The result is a **date-adjusted solar patched-conic recreation**, with C3
13.43529 km²/s², a 3.81853 km/s injection from 200 km LEO, and 17.66663 years to
Neptune. It has two modeled midpoint corrections totaling 0.02727 m/s. That value
is a cost in the solar model, not a reproduction of the source's n-body budget.

The research orbit uses unusually low passes near Earth and Venus. The app and
public gallery's default altitude floors remain unchanged. This research case
is published on the website as a separately labeled, attributed research
recreation. It is not a standard-altitude public-library seed or a new executable release.

Run `tools/recreate_eight_planet_tour.py --help` from the repository root for local
reconstruction and audit options. Ephemeris data stays in the local cache.
