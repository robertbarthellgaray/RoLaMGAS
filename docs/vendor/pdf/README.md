# Browser PDF export dependencies

These assets are served by RoLaMGAS and loaded only when a visitor exports a PDF.
No CDN or external rendering service is required. The report uses jsPDF 4.2.1
(MIT) and Noto Sans (SIL Open Font License). Both license texts are included.
`sources.json` records the upstream download URLs, sizes and SHA-256 digests.

The PDF contains selectable text with embedded, subsetted fonts and a JPEG of
the trajectory rendered at twice the display resolution.
