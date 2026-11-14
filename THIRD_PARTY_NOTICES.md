# Third-party notices

The Windows preview bundles Python and scientific libraries. Their license texts are retained under `third_party_licenses/`. Build dependencies are also documented; listing a package does not imply every component is bundled.

- truststore 0.10.5: third_party_licenses/truststore/LICENSE (MIT)
- numpy 2.2.6: third_party_licenses/numpy/LICENSE.txt
- scipy 1.15.1: third_party_licenses/scipy/LICENSE.txt
- numba 0.61.2: third_party_licenses/numba/LICENSE, third_party_licenses/numba/LICENSES.third-party
- llvmlite 0.44.0: third_party_licenses/llvmlite/LICENSE, third_party_licenses/llvmlite/LICENSE.thirdparty
- lamberthub 1.0.0: third_party_licenses/lamberthub/licenses/LICENSE
- matplotlib 3.9.2: third_party_licenses/matplotlib/LICENSE
- pillow 10.4.0: third_party_licenses/pillow/LICENSE
- contourpy 1.3.0: third_party_licenses/contourpy/LICENSE
- cycler 0.12.1: third_party_licenses/cycler/LICENSE
- fonttools 4.53.1: third_party_licenses/fonttools/LICENSE
- kiwisolver 1.4.7: third_party_licenses/kiwisolver/LICENSE
- packaging 24.1: third_party_licenses/packaging/LICENSE, third_party_licenses/packaging/LICENSE.APACHE, third_party_licenses/packaging/LICENSE.BSD
- pyparsing 3.1.4: third_party_licenses/pyparsing/LICENSE
- python-dateutil 2.9.0.post0: third_party_licenses/python-dateutil/LICENSE
- six 1.16.0: third_party_licenses/six/LICENSE
- setuptools 80.9.0: third_party_licenses/setuptools/licenses/LICENSE, third_party_licenses/setuptools/_vendor/autocommand-2.2.2.dist-info/LICENSE, third_party_licenses/setuptools/_vendor/backports.tarfile-1.2.0.dist-info/LICENSE, third_party_licenses/setuptools/_vendor/importlib_metadata-8.0.0.dist-info/LICENSE, third_party_licenses/setuptools/_vendor/inflect-7.3.1.dist-info/LICENSE, third_party_licenses/setuptools/_vendor/jaraco.collections-5.1.0.dist-info/LICENSE, third_party_licenses/setuptools/_vendor/jaraco.context-5.3.0.dist-info/LICENSE, third_party_licenses/setuptools/_vendor/jaraco.functools-4.0.1.dist-info/LICENSE, third_party_licenses/setuptools/_vendor/jaraco.text-3.12.1.dist-info/LICENSE, third_party_licenses/setuptools/_vendor/more_itertools-10.3.0.dist-info/LICENSE, third_party_licenses/setuptools/_vendor/packaging-24.2.dist-info/LICENSE, third_party_licenses/setuptools/_vendor/packaging-24.2.dist-info/LICENSE.APACHE, third_party_licenses/setuptools/_vendor/packaging-24.2.dist-info/LICENSE.BSD, third_party_licenses/setuptools/_vendor/platformdirs-4.2.2.dist-info/licenses/LICENSE, third_party_licenses/setuptools/_vendor/tomli-2.0.1.dist-info/LICENSE, third_party_licenses/setuptools/_vendor/typeguard-4.3.0.dist-info/LICENSE, third_party_licenses/setuptools/_vendor/typing_extensions-4.12.2.dist-info/LICENSE, third_party_licenses/setuptools/_vendor/wheel-0.45.1.dist-info/LICENSE.txt, third_party_licenses/setuptools/_vendor/zipp-3.19.2.dist-info/LICENSE

Ephemerides are geometric vectors from JPL Horizons. JPL and NASA do not endorse this application. Source responses retain their original metadata in the baseline archive.

Build-tool notices: `third_party_licenses/pyinstaller/`,
`third_party_licenses/pyinstaller_hooks_contrib/`, and `third_party_licenses/altgraph/`.
PyInstaller’s bootloader exception is retained in its license text.

`celestia_assets/dwarf_planet_orbits.json` and `celestia_assets/small_body_orbits.json`
contain orbital/frame/rotation fields derived from Celestia's
`data/dwarfplanets.ssc`, `asteroids.ssc`, `comets.ssc`, `interstellar.ssc` and
`outersys.ssc` (GPL-2.0-or-later). Original SPDX copyright notices and source
checksums are retained in the JSON snapshots. No meshes or textures are copied. The
derived snapshot is distributed under GPLv3, permitted by the original
"or later" license grant; the GPLv3 text is included as `LICENSE`.

Titan atmosphere reference data: ESA Huygens HASI team, dataset
HP-SSA-HASI-2-3-4-MISSION-V1.1, served by the PDS Planetary Atmospheres Node:
https://atmos.nmsu.edu/PDS/data/hphasi_0001/DATA/PROFILES/ . The bundled numerical
table retains archived descent densities and matches the corrected accelerometer
density product to the upper pressure/temperature profile at identical altitudes. Raw-file
URLs, SHA-256 checksums and the missing entry-density-column caveat are in
`model_assets/titan/hasi_reference.json`. This is not a NASA Titan-GRAM implementation;
no GRAM source or proprietary aerodynamic database is included.
