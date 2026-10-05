# AdVera landing page

A static page (HTML, CSS and plain JavaScript, no build step) to publish on GitHub Pages or any
static host. Open `index.html` in a browser to see it.

- `index.html` – the page.
- `styles.css` – the styles.
- `brain.js` – the animated brain (canvas, no libraries; still for "reduced motion").
- `ambient.js` – the drifting triangles behind the whole page.
- `wave.js` – the waveform of a recording in the Capture section.
- `transcript.js` – lights the lines of the example transcript one after another.
- `i18n.js` – English (default, in the HTML) and Spanish (`?lang=es` or the EN/ES switch).
- `site.js` – the repository link and the copy buttons.
- `.nojekyll` – tells GitHub Pages to serve the files as they are.

**Before publishing**, set the repository address in `site.js` (`REPO_URL`) and in the `href`
of the links marked `data-repo` in `index.html` (they are rewritten by `site.js`, but the HTML
value is what works without JavaScript and what search engines see).

**GitHub Pages:** the workflow `.github/workflows/landing-page.yml` publishes this folder on
every push to `main` that touches it. Enable it once in the repository: Settings → Pages →
Source: GitHub Actions. Any other static host works too: upload the folder as it is.
