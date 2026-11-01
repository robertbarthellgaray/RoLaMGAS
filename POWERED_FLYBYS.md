# Powered flybys and warning categories

Individual burn caps default to **700 m/s per DSM** and **200 m/s per powered
flyby**, in addition to the total budget. Search acceptance, least-squares
discovery and cost refinement enforce them. Backend values are km/s:
`max_single_dsm_kms=0.7`, `max_powered_flyby_kms=0.2`. Caps are adjustable;
zero disables nonzero burns of that type. Exceeding either cap prevents an
accepted candidate; diagnostics and explicitly requested exports remain available.
Integration reports separately check the actual retargeted DSM/patch impulses
and actual flyby impulses, retaining all violations.

Yellow candidates exceed a requested budget, arrival-speed, duration or
unpowered excess-speed matching limit. Red marks an unsatisfied periapsis/turn
screen or an exceeded individual DSM/powered-flyby hard cap. These colors do not change the original acceptance tests or claim
continuous n-body validation. Near misses are visible by default and exportable.

Enable **Allow powered flybys** before a new search. The solver includes each
powered-flyby impulse in `total_dsm_kms`, in addition to cruise DSMs. The budget
and local cost optimizer use that combined total. JSON distinguishes
`cruise_dsm_kms` and `powered_flyby_delta_v_kms`.

For an existing candidate, enable **Use powered flybys for this export** in the
inspector. The exporter reevaluates the saved dates/variables with that model,
keeps each flyby above its floor, integrates the incoming and outgoing arcs, and
records the impulse in `burns.csv`. The search candidate is preserved; the
integration report describes the powered variant and its budget violations.
Prior exports are backed up before regeneration.

The construction joins two hyperbolas at the same above-floor periapsis and
matches both asymptotic velocity vectors. A vector impulse changes the periapsis
velocity, including direction when needed. This is a conservative feasible
construction, **not a minimum-fuel powered flyby**. It can involve a costly plane
change; less restrictive maneuver locations or upstream retargeting may be cheaper.

For example, saved EVVEEU candidate `a210b4043487` in run
`20261031_162005_ddac14` can keep its second Earth periapsis at 200 km using this
construction. That Earth burn is 2.36665 km/s; all predicted flyby burns total
2.36782 km/s. The finite-patch integrated variant totals 2.82778 km/s onboard
including its explicit junction corrections. These are demonstrated costs of
this construction, not required minimum costs or an optimized mission.

Independent numerical propagation verified the two hyperbolas, their above-floor
periapses and the incoming/outgoing asymptotes. Geometrically degenerate cases
or a periapsis outside the finite patch remain explicit errors.

Individual cap controls are in the expandable **Individual burn limits** menu immediately below **Allow powered flybys**. Hard-cap violations are red; exceeding only the total maneuver budget remains yellow.
