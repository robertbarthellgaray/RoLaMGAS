# Additional published launch-performance references

`samples.json` contains independent primary-source data. The rebuild script
`tools/build_international_launch_performance.py` adds these rows to both the
desktop and website capacity tables. The points do not change solver constraints.

## Ariane 6

Arianespace's February 2021 manual, section 2.4.5 (printed p.2-11, PDF page 37),
lists 2,600 kg for Ariane 62 and 6,900 kg for Ariane 64 at V-infinity 2.5 km/s.
Squaring that speed gives C3 6.25 km2/s2. Section 2.2 includes adapters and carrying
structures in the performance mass convention. These isolated reference points
remain unchanged. Separate assumed-stage estimates extend these rows through
C3 200; see [EXTRAPOLATION.md](EXTRAPOLATION.md). The manual does not provide a public
general-purpose C3 curve in this section. Later booster upgrades are not assumed.

## SLS

NASA NTRS document 20205007434, *NASA's Space Launch System: Capabilities for
Ultra-High C3 Missions* (2020), contains configuration-specific performance graphs.

- Figure 3 (PDF page 4): black Block 1 cargo / 5 m fairing curve, sampled at C3
  0 through 130. Values are payload-system mass.
- Figure 6 (PDF page 6): solid red Block 2 **plus an added Centaur third stage**,
  declination 28.5 degrees, sampled at C3 60 through 280. This is an unflown
  concept studied in 2020, not a claim about today's launch manifest or availability.

Samples were read from the original embedded graph images. Figure 3 calibration:
1094 x 794 image, plot x=103..1063 for C3=-20..140, y=715..18 for mass=0..80 tonnes.
Figure 6 calibration: 1032 x 749 image, plot x=98..1003 for C3=60..300,
y=676..17 for mass=0..20 tonnes. Source traces were checked against the plotted
curves and the paper's approximate 15-tonne example near C3=83 for SLS/Centaur.
Readings are rounded to 100 kg; they are approximate graph digitizations, not
certified performance or statistical uncertainty bounds. The UI rounds interpolated
values to the same precision. Interpolation stays within each row's own coverage.

## Missing data and historical context

Long March 5 remains a **single** approximately 3,000 kg / C3=30 study point from
Wang et al. (2025), section 5.3. No unsupported full LM-5 curve is inferred from it.
"Not tabulated" is distinct from zero payload or inability to launch.

New Horizons demonstrates why configuration matters: it used a dedicated STAR 48B
kick stage in addition to its launch vehicle. A standard launcher-only curve does
not describe that combination. Atlas V is not added to the active comparison.
NASA mission reference: https://science.nasa.gov/mission/new-horizons/
