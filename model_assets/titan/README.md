# Titan reference atmosphere

Prepared from the Huygens HASI PDS V1.1 entry/descent products by
`tools/prepare_titan_atmosphere.py`. Instrument/data credit: HASI team,
ESA Huygens/Cassini-Huygens, PDS Planetary Atmospheres Node.

The 1,816 descent densities are archived values. The 911 upper entry densities
come from the corrected `HASI_L4_ACCE_DENSITY` product at exactly matching
altitudes. This resolves the empty density column in the entry profile file;
the bundled atmosphere requires no ideal-gas replacement of density.
Read the adjacent JSON for raw-data URLs, checksums and processing limitations.

These data are a 2005 reference column, not a 2030s atmosphere prediction.
See `TITAN_ENTRY.md` for dynamics, optional GRAM inputs and vehicle assumptions.
