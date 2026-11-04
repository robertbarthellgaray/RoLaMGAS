# Arrival inclination and a possible capture orbit

The finite-radius exporter can target an arrival orbit inclination relative to the destination planet’s equator. This is an export option; the Lambert search does not yet constrain arrival inclination. It supports the eight planets, whose pole and gravitational parameter are available.

Set **Arrival inclination (degrees)** when exporting, or pass `--arrival-inclination-deg 90` to `integrate_export.py`. Leave it blank to retain the existing arrival plane. A value of 90° gives a polar incoming hyperbola; a coplanar capture burn retains that inclination.

The exporter rotates the terminal hyperbola’s B-plane orientation while keeping the incoming asymptotic velocity, encounter date, and requested periapsis altitude. Two orientations normally satisfy the inclination; it chooses the one closest to the original arrival plane. The heliocentric coast is then retargeted to the finite SOI boundary. Any resulting velocity corrections are listed and charged in `burns.csv` and `integration_report.json`.

For an incoming asymptote unit vector S and planet pole k, the smallest reachable inclination is `asin(abs(S dot k))`; the largest is 180° minus that angle. A fixed arrival direction therefore cannot reach every inclination. An unavailable request produces an error with the reachable range, rather than inventing a free plane change. A polar plane is always geometrically available, but ordinary impact and budget checks still apply.

`arrival_state.json` includes `capture_assessment`: achieved inclination, allowed interval, B-plane vector, pole source, and a hypothetical instantaneous circular-capture burn at arrival periapsis. The hypothetical circular state is also included for use elsewhere. **The exporter does not execute that capture or add its cost to the cruise budget.** The trajectory still ends at incoming periapsis, or continues along the unpowered hyperbola if post-flyby months are requested.

Pole directions use the eight-planet orientation coefficients, including nonzero periodic terms, from [JPL NAIF PCK00011](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/pck00011.tpc). They are evaluated at the TDB encounter epoch in J2000 equatorial axes, then rotated into the same Ecliptic J2000 axes as Horizons states. Inclination 0° aligns the orbit normal with the IAU north pole; the retrograde spins of Venus and Uranus do not reverse this definition. Earth uses the approximate text-PCK orientation, rather than high precision Earth orientation measurements.

The capture estimate assumes two-body gravity and a circular orbit at periapsis. It omits atmosphere, oblateness, moons, rings and long-term orbit stability. The [NAIF PCK reference](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/req/pck.html) describes the orientation convention, and [STK’s B-plane equations](https://help.agi.com/stk/12.9.0/Content/gator/eq-bplane.htm) describe the encounter-plane construction.
