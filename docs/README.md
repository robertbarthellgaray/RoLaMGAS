# Static trajectory gallery

Served at https://robertbarthellgaray.github.io/RoLaMGAS/ through GitHub Pages.

No build step or Python backend is required. Serve this directory with any static HTTP server. All asset URLs are relative so the gallery works at a project subpath.

`data/index.json` contains the small filter catalog. Detailed paths load on selection from `data/cases/`. SVG card plots are generated offline. `downloads/` contains the two original integrated XYZV files; the browser never generates or integrates new trajectories.

RoLaMGAS.png is the original artwork supplied by Robert Barthell Garay.

The offline catalog builder is `../tools/build_public_catalog.py`. Its input trajectory project is not part of this public repository. Existing numeric examples are sufficient to run the gallery.
