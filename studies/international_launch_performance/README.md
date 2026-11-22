# Published international launch payload versus C3

The active dataset distinguishes published examples from modeled estimates:

- Wise, Lafleur & Saleh, IAC-10.D2.P06 (2010), Table 1, p.7: historical
  LM-3A, LM-3B and LM-3C polynomial fits, restricted to their published C3 domains.
  Source: https://repository.gatech.edu/server/api/core/bitstreams/2578ccee-732e-421b-adda-de8458be849a/content
- Wang et al., Aerospace 2025, 12(4), 271, Section 5.3: approximately 3,000 kg
  at C3=30 for LM-5, kept as one mission-study point without inventing a curve.
  Source: https://www.mdpi.com/2226-4310/12/4/271

The project owner confirmed permission on 2026-11-21 to run scenarios with
[John Schilling’s SilverBird Astronautics calculator](https://silverbirdastronautics.com/LVperform.html).
The underlying engineering database is not redistributed. With the project owner’s
explicit scraping permission, `silverbird_scenarios.json` now records computed
outputs for 17 configurations. See [collection instructions](../../LAUNCH_PERFORMANCE.md#silverbird-country-selector-and-repeatable-collection). The public form choices are
validated before each query; third-party JavaScript and source HTML stay local.
The historical references below remain separately labeled.

The [2012 ISRO/PLANEX source review](indian_lv_planex_2012.md) records historical
PSLV, GSLV and LVM3 planetary mission mass ranges. The source does not specify
their C3, so these ranges are retained as research rather than numerical
capacity-curve samples.

The [November 2025 NSIL brochure review](indian_lv_nsil_2025.md) identifies
elliptical-orbit performance curves approaching escape energy. These provide
calibration data for the explicitly modeled LVM3 positive-C3 estimate now included
at C3 0–30, with configuration and extrapolation limitations recorded.
Reproduce its model artifact with `python tools/estimate_indian_launch_performance.py --plot`
before rebuilding the combined data.

These historical fits and a mission-study assumption are not certified current
vehicle ratings. Configuration, declination, adapters, reserves, upper-stage
constraints and launch-window width matter. No extrapolation is performed.

Rebuild the published examples after refreshing NASA's rows:

```text
python tools/build_international_launch_performance.py --plot
```

`international_launch_performance.png` and `capacity_samples.csv` contain these
four published source/configuration rows and a fifth, explicitly estimated LVM3
row. Existing NASA provider-ground-rule
rows are retained separately in the combined capacity dataset.
