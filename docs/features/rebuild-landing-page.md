# Feature: Rebuild landing page
Status: in progress
Last updated: 2026-10-06

## Objective

A commercial landing page for AdVera that explains the product and points to the code repository with installation steps. It must be a static site (HTML, CSS and plain JavaScript, no build step) so it can be published on GitHub Pages or any static host.

## Scope

- `landingpage/`: `index.html`, `styles.css`, `brain.js` (animated brain of coloured triangles, canvas, no libraries), `site.js` (repository link in one place, copy buttons), `favicon.svg`, `.nojekyll`, `README.md`.
- `.github/workflows/landing-page.yml`: publishes the folder on GitHub Pages on pushes to `main`.
- Copy based on the README: "Every meeting, verifiable knowledge", what is recorded, cited answers, the Brain, privacy, how it works, installation and requirements.
- Visual reference chosen by the operator: a dark stage with a particle brain (dala.craftedbygc.com), with AdVera's own name, logo and text. Inter (Google Fonts) instead of the reference's commercial typeface.

Out of scope: translations, analytics, a licence statement (the repository has no licence yet).

## Acceptance criteria

1. Opens as static files, with no build and no server-side code.
2. Readable without JavaScript; the animation stops off screen and is still with "reduced motion".
3. No horizontal scroll at 390 px; one column on narrow screens.
4. Only verifiable claims about the product.

## Implementation state

Built on branch `feature/landing-page`; checked at 1440x900 and 390x844 with Playwright (no console errors, no horizontal overflow). The repository address is a placeholder until there is a public remote.

## Decisions

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
