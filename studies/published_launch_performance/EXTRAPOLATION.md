# Capacity estimates through C3 = 200

Published samples are retained unchanged and take precedence. Beyond their
coverage, the app/site can show explicitly labeled engineering estimates through
C3=200 km²/s². These models are not provider guarantees, flight qualification,
or hard feasibility filters. A displayed `0 (model)` means the adopted model
has reached zero payload; it does not certify that every possible configuration
of the launch vehicle is incapable. Small positive estimates below the rounding
step display as `<100 (estimate)` rather than zero.

`tools/extend_launch_capacity.py` reproduces the attached model parameters and
`extended_capacity_estimates.csv`. JavaScript evaluates the same saved model;
no numerical curve fitting occurs in the user's browser or app.

## Bare launcher extrapolation

For rows with several source samples, fit the highest-energy three to five
points to `m(v) = A exp(-(v-v_ref)/v_e) - D`, where
`v = sqrt(C3 + 2 mu_E / (R_E + 200 km))`. Fit A, D and v_e under positive bounds
and clip negative payloads to zero. The effective exhaust speed is bounded to
2.5–6 km/s. These are effective fit parameters, not identified stage properties.
Fit RMS inside the source domain is recorded; it is not an extrapolation error
or confidence interval. Configuration, declination, reserves, adapters and ascent
optimization retain the source's limitations.

The LVM3 row instead extends its existing NSIL-calibrated effective stage model.

One-point rows cannot identify a unique curve. Their extrapolations are explicitly
assumed-stage scenarios anchored at the published point:

- Ariane 62/64: ESA publishes 30 tonnes of upper-stage propellant. Effective
  inert mass 4.5 tonnes and exhaust speed 4.5 km/s are analyst assumptions.
  https://www.esa.int/articles/about-us/directorates/space-transportation/ariane/ariane-6-what-s-it-made-of
- LM-5: assumed 26.5 tonnes propellant, 3.4 tonnes effective inert mass and
  4.334 km/s exhaust speed, informed by the stage comparison table in
  https://www.scielo.br/j/jatm/a/jg5XF3Ls6mb98g9WXwVK3Zw/

The anchored stage model is `v = v_offset + v_e ln(1 + P/(D+m))`.
The velocity offset is calibrated at the single reference point. No independent
validation or uniqueness is implied for these one-point scenarios.

## Launcher plus STAR 48BV concepts

Seven separate conceptual configurations are shown only at C3≥100. They do not
alter the bare-launcher rows or imply that launch providers offer these services.
They use only interpolation inside the source launcher's tabulated C3 coverage,
not its extrapolation. For each requested final energy, solve for a staging C3
that produces exactly that energy after a full-motor prograde kick, while paying
the mass penalty of the motor and integration hardware.

- Northrop Minotaur IV/V/VI User Guide, PDF p.23: motor wet mass 2,171 kg,
  propellant 2,014 kg, hence inert motor mass 157 kg.
  https://cdn.northropgrumman.com/-/media/Project/Northrop-Grumman/ngc/what-we-do/space/launch-vehicles/minotaur/Minotaur-IV-V-VI-User-Guide.pdf
- NASA 20240015535, Table 1, PDF p.4: effective specific impulse 292.1 s.
  https://ntrs.nasa.gov/api/citations/20240015535/downloads/JANNAF%209871%20Propellants%20for%20Space%20Kibbey.pdf
- Analyst assumptions: extra 100 kg integration allowance, 200 km reference
  periapsis, and 100 m/s kick loss allowance.

The approximately 85-second motor burn is represented as an impulse plus that
assumed loss allowance. Finite-burn steering, gravity losses, structure, attitude
control, separation, thermal compatibility, launch declination and provider
qualification are not simulated. The allowance is not a validated error bound.
NASA's source payload convention and spacecraft interface mass may differ from
mission-specific payload accounting.

Rounded examples: FH Expendable + STAR 48BV ~800 kg at C3=158 and ~400 kg at
C3=200. Vulcan VC6 + STAR 48BV ~700 kg and ~300 kg respectively. These are
concept estimates; New Horizons itself used an Atlas V + STAR 48B configuration,
which is not silently equated with STAR 48BV or added back to the active list.

SilverBird-derived numbers remain excluded.
