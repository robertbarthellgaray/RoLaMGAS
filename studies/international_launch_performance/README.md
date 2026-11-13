# Published international launch payload versus C3

The active dataset contains only independently published examples:

- Wise, Lafleur & Saleh, IAC-10.D2.P06 (2010), Table 1, p.7: historical
  LM-3A, LM-3B and LM-3C polynomial fits, restricted to their published C3 domains.
  Source: https://repository.gatech.edu/server/api/core/bitstreams/2578ccee-732e-421b-adda-de8458be849a/content
- Wang et al., Aerospace 2025, 12(4), 271, Section 5.1: approximately 3,000 kg
  at C3=30 for LM-5, kept as one mission-study point without inventing a curve.
  Source: https://www.mdpi.com/2226-4310/12/4/271

SilverBird-derived outputs are withheld pending permission. They are absent
from the active app/site JSON, charts, numerical downloads and source packages.
The rebuild script does not read or restore those model outputs.

These historical fits and a mission-study assumption are not certified current
vehicle ratings. Configuration, declination, adapters, reserves, upper-stage
constraints and launch-window width matter. No extrapolation is performed.

Rebuild the published examples after refreshing NASA's rows:

```text
python tools/build_international_launch_performance.py --plot
```

`international_launch_performance.png` and `capacity_samples.csv` contain these
four published source/configuration rows. Existing NASA provider-ground-rule
rows are retained separately in the combined capacity dataset.
