RoLaMGAS ba36e139b812 / EVVMe
Unchanged original integrated XYZV
Original integrated concept. See Model & data for its force model, targeting burns and limitations. CSV preserves every numeric XYZV row, including any repeated impulse epochs.

Columns: JD(TDB), x, y, z, vx, vy, vz
Origin: Sun. Frame: Ecliptic J2000. Position: km. Velocity: km/s.
Time labels are TDB, not UTC.
Rows: 1976
CSV SHA256: 4b1815e65534d9b3b50125de1d5fe7412e876e1effdc841ab89023ee58bb9fa5
XYZV SHA256: 6a023ac4b1996e87002da1cf3531d909d58362d58ecb82eb36714167d064a82e

Featured at Robert’s request: the saved finite-radius patched-conic export, not a passing unpowered Lambert candidate. The raw Venus joins miss excess-speed matching by 55.669 and 48.333 m/s. The export explicitly adds 819.273 m/s of junction corrections and 80.450 m/s of flyby speed-matching burns: 899.724 m/s onboard total. The displayed cruise cost includes all these burns; launch injection and Mercury capture are excluded. Sun-only integrated coasts and translated planet-centered hyperbolas use prescribed JPL planet states. Position joins and sampled/bracketed surface checks passed; this is not a continuous n-body validation. Terminal state is 200 km above Mercury, without capture.
