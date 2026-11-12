# International launch payload versus C3

Added 12 November 2026. The data are informative capacity estimates; they do not alter solver feasibility or screen candidate masses.

| Source | What is included | Interpretation |
|---|---|---|
| [Wise, Lafleur & Saleh, IAC-10.D2.P06 (2010), Table 1, p.7](https://repository.gatech.edu/server/api/core/bitstreams/2578ccee-732e-421b-adda-de8458be849a/content) | LM-3A, LM-3B and LM-3C polynomial coefficients and their published C3 domains | Historical baseline configurations; not modern enhanced variants. Rounded printed coefficients reproduce approximate curves. Fit residuals are not uncertainty in the vehicle's true capacity. |
| [Wang et al., Aerospace 2025, 12(4), 271, Section 5.1](https://www.mdpi.com/2226-4310/12/4/271) | LM-5: approximately 3,000 kg at C3=30 km²/s² | A stated mission-study assumption. Kept as one point, without inventing a complete curve or claiming a provider guarantee. |
| [John Schilling / SilverBird calculator](https://silverbirdastronautics.com/LVperform.html), [method](https://silverbirdastronautics.com/LaunchMethodology.pdf) | PSLV with six strap-ons; GSLV Mark II; GSLV Mark III; CZ-5 | Third-party model results. Complete payload system mass includes attachment hardware. Store all reported model confidence intervals. |

SilverBird conditions: direct ascent, 200 km perigee altitude, 0° departure-asymptote declination, mixed calibration, guidance-command shutdown, default disposal option. CZ-5 uses its standard configuration, no Yuanzheng-2, short fairing and Wenchang; Indian models use Satish Dhawan. Other settings are preserved in `silverbird_samples.json`. Raw HTML hashes accompany each sample.

The calculator names its PSLV only “with six strap-on boosters”; it does not establish the strap-on generation or identify PSLV-XL. Its result is therefore labeled variant unspecified. Likewise, GSLV Mark III is a baseline model, not a verified rating for upgraded LVM3/C32. A modeled zero with broad uncertainty is not a certified inability to launch. No current manufacturer C3 curve for the Indian launchers was established in this research.

Concrete SilverBird model examples:

| Model | C3=0 | C3=10 | C3=20 | C3=28 |
|---|---:|---:|---:|---:|
| GSLV Mark II | 750 kg | 448 kg | 178 kg | 0 kg |
| GSLV Mark III | 1,156 kg | 562 kg | 31 kg | 0 kg |
| CZ-5 | 5,027 kg | 4,030 kg | 3,137 kg | 2,491 kg |

For example, at C3=10, the source's model intervals are 0–1,023 kg for Mark II, 0–1,618 kg for Mark III and 2,951–5,306 kg for CZ-5. These are deliberately not interchangeable with NASA NLS-II provider-ground-rule capacities or with the separate 2025 study point.

`international_launch_performance.png` distinguishes published fits, the single published study point and SilverBird models (with interval shading). `capacity_samples.csv` contains the sample values. No extrapolation is performed. Interpolation of capacity does not produce a new confidence interval; the UI shows the original intervals at the bounding samples instead.

C3 alone does not establish launch feasibility: departure declination, launch-window duration, upper-stage restarts/coast limits, adapter mass and reserves differ by source. GTO mass, lunar-transfer mass and spacecraft-assisted escape missions cannot be treated as positive-C3 launcher capacity points without accounting for their spacecraft propulsion.

Rebuild the data and graph after refreshing the NASA samples:

```text
python tools/build_international_launch_performance.py --plot
```

This reads the saved public numerical samples, adds eight source/configuration rows to both app and website datasets, and retains the NASA queries and vehicle rows. Full downloaded source documents and third-party Javascript are local research material and are not redistributed with this dataset.
