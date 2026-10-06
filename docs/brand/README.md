# AdVera brand assets

The mark is one large outlined triangle, like the particles of the brain on the landing page:
it is the "A" of AdVera. Its bar is teal, and the amber spark inside is the moment a citation
points to. A few small triangles drift off it.

| File | Use |
|---|---|
| `mark.svg`, `mark-512.png` | The mark alone, transparent background |
| `logo.svg` / `logo-dark.png` | Mark and name, for dark backgrounds |
| `logo-light.svg` / `logo-light.png` | Mark and name, for light backgrounds |
| `favicon.svg`, `favicon-16/32/48/180/192/512.png` | Browser and app icons (the mark on a black tile, without the small triangles) |
| `apple-touch-icon.png` | iOS home screen |
| `avatar.png` | Profile picture for social networks, 400x400 |
| `og-image.png`, `og-image-es.png` | Link previews (1200x630), English and Spanish |
| `github-social.png` | Repository social preview on GitHub (1280x640) |
| `square-post.png` | Square post (1080x1080) |

**Rules**
- The name is always written **AdVera**: never ADVERA or Advera, also in uppercase labels.
- Colours: black `#000000`, white `#ffffff`, violet `#8052ff` (the mark, the one action), amber `#ffb829` (emphasis), teal `#15846e`.
- Typeface: Inter, regular (400) for headings and the name, extra light (200) for text.
- Keep clear space around the mark of at least half its width; do not recolour, stretch or add effects.
- The SVG logos write the name as text: they need Inter installed. Use the PNGs where it may be missing.

The PNGs are rendered from the SVGs with `node scripts/brand_assets.mjs` (Playwright of the frontend). The landing page is published on its own, so the script also copies the icons and the link preview it uses to `landingpage/assets/`.
