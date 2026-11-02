# Sharing RoLaMGAS

No purchased domain is required. GitHub Pages provides the public precomputed
trajectory gallery; the downloadable solver runs locally on the user's CPU.
The browser opens a loopback-only interface, and new Horizons requests are
saved in that user's cache. Pages cannot execute the Python backend.

## Run from source on Windows, macOS or Linux

The source repository and source ZIP include the solver, browser interface,
spacecraft models, licenses and offline eight-planet baseline. Python 3.12 is
the tested build version. Download the source ZIP from the same release as the
binary, or clone the repository. On macOS/Linux, open a terminal in its folder:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python rolamgas.py
```

On Windows use the supplied `Setup Python.cmd` and `Launch RoLaMGAS.cmd`, or
activate `.venv\Scripts\Activate.ps1` and run the same Python commands.
Dependencies require an internet connection on first installation. Afterwards,
the bundled baseline supports offline planetary searches over its date range;
new objects still require a successful Horizons download. A desktop browser is
required. No AI service or account is needed to run searches.

## Native downloads and local rebuilding

The build script supports the host operating system:

```sh
python -m pip install -r requirements-build.txt
python -m unittest discover -p 'test_*.py'
python build_release.py --native --version 0.2.0
```

Outputs are written under `releases/`:

| Host | Download | Install or launch |
| --- | --- | --- |
| Windows x64 | `RoLaMGAS.exe` | Open the executable; Python is bundled. |
| Apple Silicon Mac | `RoLaMGAS-0.2.0-macos-arm64.dmg` | Open the DMG and drag the app to Applications. |
| Intel Mac | `RoLaMGAS-0.2.0-macos-amd64.dmg` | Use the separate Intel build. |
| Debian/Ubuntu x64 | `rolamgas_0.2.0_amd64.deb` | Open with the software installer, or run `sudo apt install ./rolamgas_0.2.0_amd64.deb`. |

The Linux package installs a menu entry and the `rolamgas` command. It bundles
Python and scientific dependencies, and uses the system browser. Building a
DEB requires `dpkg-deb` (the Debian/Ubuntu `dpkg` package). The CI build uses
Ubuntu 22.04 and requires glibc 2.35 or newer; it is not a universal package for
all Linux distributions. Build on an older target distribution when older
glibc compatibility is required. Source execution remains available elsewhere.

`--exe` builds only the native application (plus source/checksums), without a
DMG/DEB wrapper. macOS and Linux use a directory bundle; Windows retains the
single EXE. All formats include the same baseline, model and interface assets.
Persistent runs and caches are stored outside the frozen app. Set
`ROLAMGAS_DATA_DIR` to choose another writable location.

Native builds must run on the target OS and CPU architecture: PyInstaller is
[not a cross-compiler](https://pyinstaller.org/en/stable/). A Windows computer
cannot produce a usable Mac application just by renaming its executable.
The Mac build is architecture-specific, not universal. The preview is unsigned
and not notarized, so macOS and Windows may require approval to open it. This
workflow does not use signing credentials or claim Apple notarization.

## GitHub native build workflow

In the repository's **Actions → Build native downloads**, select **Run workflow**
and enter a package version. It builds Windows x64, macOS Apple Silicon, macOS
Intel and Linux x64 on separate native runners. Each build runs source tests
and starts its frozen application in self-check mode. The workflow retains
downloadable artifacts for 30 days; manual runs do **not** create a public release.

To publish a version after reviewing those results, push a version tag such as
`v0.2.0` or `rolamgas-v0.2.0`. A tagged run publishes the native files, matching
GPLv3 source ZIP and per-platform SHA-256 manifests to that GitHub Release only
after every native build succeeds. Use the repository's release page for public
one-click downloads rather than committing executables to source control.
The current Windows release remains unchanged until a new build is published.

macOS/Linux packaging is prepared here; successful builds and use on those
platforms must be verified by their native workflow runs. Development on
Windows alone does not establish that the other binaries work.

The build script uses an explicit source-file list and includes only baseline
ephemerides, not working `runs/`, arbitrary cache files, credentials, or resolved
target history. The separate baseline archive contains original JPL response
checksums. Download checksums are recorded in `release_manifest-<platform>.json`
in CI, or `release_manifest.json` for local builds. Public releases include
corresponding source and third-party notices.

Runner platform labels and architecture details follow
[GitHub's hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
DEB packages use the system
[dpkg-deb tool](https://manpages.debian.org/bookworm/dpkg/dpkg-deb.1.en.html).

## Static gallery and other hosting

GitHub Pages serves `docs/` from `main`. It loads precomputed JSON, plots and
trajectory downloads. New examples are curated offline with
`tools/build_public_catalog.py`; only explicit numeric fields are published.
Private working runs, cache histories and local paths are not copied.

A hosted computation service would need isolated jobs, per-user storage and
resource limits; this local server is not configured as a public multi-user
service. A custom domain is optional. A browser-only solver could use WebAssembly
and Web Workers, but the current Numba and process-pool design would need
adaptation and performance testing. These native packages do not implement
that browser port.
