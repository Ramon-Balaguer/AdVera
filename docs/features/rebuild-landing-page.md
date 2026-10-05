# Feature: Rebuild landing page
Status: in progress
Last updated: 2026-10-06

## Objective

A commercial landing page for AdVera that explains the product and points to the code repository with installation steps. It must be a static site (HTML, CSS and plain JavaScript, no build step) so it can be published on GitHub Pages or any static host.

## Scope

- `landingpage/`: `index.html`, `styles.css`, `brain.js` (animated brain of coloured triangles, canvas, no libraries), `ambient.js` (drifting triangles behind the whole page), `wave.js` (waveform of the Capture section), `transcript.js` (lights the lines of the example transcript), `i18n.js` (English and Spanish), `site.js` (repository link in one place, copy buttons), `favicon.svg`, `.nojekyll`, `README.md`.
- `.github/workflows/landing-page.yml`: publishes the folder on GitHub Pages on pushes to `main`.
- Copy based on the README: "Every meeting, verifiable knowledge", the three ways of capturing (browser, desktop agent, import) with a moving waveform, an example transcript (Ada, Nil, Ferran, Maria, Vera and Alan in Catalan, Spanish and English), what is recorded, cited answers, the Brain, privacy, how it works, installation and requirements.
- Visual reference chosen by the operator: a dark stage with a particle brain (dala.craftedbygc.com), with AdVera's own name, logo and text. Inter (Google Fonts) instead of the reference's commercial typeface.

- English (default, written in the HTML) and Spanish (`i18n.js`): an EN/ES switch remembered in the browser, or `?lang=es`. What the people of the example transcript say is not translated.

Out of scope: other languages, analytics, a licence statement (the repository has no licence yet).

## Acceptance criteria

1. Opens as static files, with no build and no server-side code.
2. Readable without JavaScript; the animation stops off screen and is still with "reduced motion".
3. No horizontal scroll at 390 px; one column on narrow screens.
4. Only verifiable claims about the product.

## Implementation state

Built on branch `feature/landing-page`; checked at 1440x900 and 390x844 with Playwright (no console errors, no horizontal overflow). The repository address is a placeholder until there is a public remote.

## Decisions

- Brand assets in `landingpage/brand/` (README there): a mark made of one outlined triangle (the "A") with a teal bar and an amber spark, the logo for dark and light backgrounds, icons, avatar and social cards in English and Spanish, rendered by `scripts/brand_assets.mjs`. The name is always written AdVera.

- The brain is drawn from the points of a real 3D model, "Brain Areas" by Versal (CC BY 4.0, Sketchfab), sampled by `scripts/brain_points.py` into `landingpage/brain-points.js` (about 90 KB); the model is not stored in the repository and the licence is credited in the footer. Without the points file the canvas falls back to the drawn outline.

- No framework or build: three files and a canvas.
- The repository address lives in `site.js` (`REPO_URL`) and in the `data-repo` links.
- The footer does not say "open source" while the repository has no licence.

## Files changed

- `landingpage/*`, `.github/workflows/landing-page.yml`

## Validation

- Playwright screenshots at desktop and mobile sizes; no page errors.

## Risks

- The placeholder repository address must be replaced before publishing.

## Next action

The operator sets the repository address and enables GitHub Pages.
