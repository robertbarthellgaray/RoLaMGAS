# Sharing RoLaMGAS

No purchased domain is required. A repository can use GitHub's URL, and GitHub
Pages can provide `username.github.io/RoLaMGAS` for documentation or a download
page. Pages is static hosting and cannot execute this Python backend:
https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site

The downloadable app uses each user's CPU and saves new Horizons data in their
own cache. The Windows executable contains Python, NumPy, SciPy, Numba,
lamberthub, Matplotlib, UI assets and the eight-planet baseline. It opens the
existing loopback-only browser interface. Source ZIPs support other platforms.

A hosted computation service needs a backend with isolated jobs, per-user
storage and resource limits. This local server is not configured as a public
multi-user service. Hosting providers can offer a supplied subdomain; a custom
domain is optional.

A browser-only version could use WebAssembly and Web Workers so calculations
run on the visitor's CPU. Pyodide supports NumPy and SciPy, but the current Numba
and Python process-pool design needs replacement or adaptation, performance
testing and persistent browser storage. Horizons requests also need their
browser access behavior tested; a data proxy or downloadable ephemeris bundles
may be necessary. This release does not claim to implement that browser port.
https://pyodide.org/en/stable/

The build script uses an explicit source-file list and includes only baseline
ephemerides, not the working `runs/`, arbitrary cache files, credentials, or
resolved-target history. The build script does not create a remote repository or website. Public
releases include the corresponding source and third-party notices.

Use GitHub Releases for the executable rather than committing it to source.
The baseline archive is a separate, replaceable resource and includes original
JPL response checksums. Build output checksums are in `release_manifest.json`.

## Static gallery

GitHub Pages serves `docs/` from `main`. It loads only precomputed JSON and
SVG plots. New examples are curated offline with `tools/build_public_catalog.py`;
that script accepts private input directories as arguments and publishes only
an explicit set of numeric fields. Working runs, cache histories and local paths
are not copied. Original integrated files include SHA-256 provenance.
