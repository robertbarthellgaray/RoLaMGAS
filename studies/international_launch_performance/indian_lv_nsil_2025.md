# NSIL launch-demand brochure — November 2025

Source: NewSpace India Limited, *Launch Service Requisition: Understanding
Launch Demand*, November 2025, eight pages.

Original URL (returned 404 when checked):
https://www.nsilindia.co.in/sites/default/files/NSIL%20Launch%20Requistion%20opportunity.pdf

User-supplied archive URL:
https://web.archive.org/web/20251113162900/https://www.nsilindia.co.in/sites/default/files/NSIL%20Launch%20Requistion%20opportunity.pdf

Reviewed local copy: `C:\Users\stemg\Downloads\NSIL Launch Requistion opportunity.pdf`.
PDF text and rendered page 5 were inspected; the performance plots are raster
images and are absent from text extraction.

## What this adds

Page 5 supplies LVM3 performance plots, rather than only headline capacities:

- LEO payload versus altitude at launch azimuths 107 and 135 degrees.
- Earth elliptical-orbit payload versus apogee altitude, with six curves labeled
  r_p = 170, 200, 400, 600, 800 and 1000 km. Despite the symbol r_p, these values
  are perigee **altitudes**, not geocentric radii.
- The elliptical curves specify launch azimuth 107 degrees and argument of
  perigee 178 degrees. They extend to roughly 400,000 km apogee altitude for
  the lowest-perigee curves. Approximate visual reading there: 2.5–2.7 tonnes;
  this is not a precision digitization or a guaranteed flight performance.
- The brochure advertises about 5 tonnes to GTO and explicitly describes
  positive-C3 and TLI capability. It does not tabulate positive-C3 payloads.

The older ISRO overview's 4-tonne GTO number must not silently be mixed with
this brochure's 5-tonne figure as if they specify an identical configuration.
The brochure does not establish which stage upgrade explains the difference.

## Conversion and possible model

For a bound, two-body Earth orbit, convert each digitized apogee/perigee point
to characteristic energy using

    C3 = -mu_E / a
    a = ((R_E + h_perigee) + (R_E + h_apogee)) / 2

For example, with R_E=6378.137 km and mu_E=398600.4418 km^3/s^2,
h_perigee=200 km and h_apogee=400000 km give C3=-1.9305 km^2/s^2.
Thus this source directly constrains performance close to escape energy;
conversion of its bound-orbit samples is not itself extrapolation.

Positive-C3 capacity remains a model prediction. A sensible next implementation
would digitize one consistent perigee curve, calibrate an effective rocket-
equation model on some samples, and test on held-out samples. Do not fit a
high-order polynomial in apogee altitude or blend the different perigee curves.
Show source samples and positive-energy extrapolation separately. Internal
held-out agreement does not establish positive-energy prediction accuracy.
Specific impulse, stage mass/configuration, ascent losses and adapter accounting
must remain explicit assumptions; do not silently pair 2025 capacity with an
older stage specification.

At 200 km altitude, ideal instantaneous speed increment from this 400,000 km
apogee orbit to C3=12 is approximately 0.620 km/s. This is an energy comparison,
not a claim that the launcher performs a separate burn there, can restart,
or retains that quantity of propellant after nominal injection.

## Active estimated capacity row

`tools/estimate_indian_launch_performance.py --plot` reproduces the calibration,
comparison plot, JSON model artifact and rounded CSV. It uses approximate
readings of the **170 km** perigee curve, with only apogees of at least 60,000 km
used for fitting. The 28-tonne propellant and 4.334 km/s exhaust-speed values
are model assumptions informed by C25/CE20 specifications; the velocity offset
and effective inert mass are fitted. This does not establish the stage version
represented in the NSIL plot. No inference of restart capability is made.

The row is called **LVM3 · NSIL-based estimate**, carries the explicit source
label **Estimated from NSIL curves · 2025**, and is limited to C3 0–30.
Display is rounded to 100 kg. An alternative local exponential fit is retained
in the artifact to show model sensitivity, not a statistical confidence band.
Interpolation checks against held-out bound-orbit samples do not validate the
positive-energy extrapolation. Use this as a mission-design estimate, not a
hard feasibility filter or provider guarantee.
