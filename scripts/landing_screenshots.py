"""Make the landing page's copies of the README screenshots.

The README uses the full-size PNGs in docs/screenshots/ (made by
`npx playwright test -c playwright.screenshots.config.ts` in frontend/). The landing page is
published on its own (only landingpage/ goes to GitHub Pages), so it gets lighter WebP copies:

    .venv/Scripts/python scripts/landing_screenshots.py
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "screenshots"
TARGET = ROOT / "landingpage" / "assets" / "screenshots"
NAMES = ["meeting", "recording", "brain-answer", "concept-graph", "timeline", "facts", "system"]
WIDTH = 1600


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        with Image.open(SOURCE / f"{name}.png") as image:
            height = round(image.height * WIDTH / image.width)
            small = image.convert("RGB").resize((WIDTH, height), Image.Resampling.LANCZOS)
            out = TARGET / f"{name}.webp"
            small.save(out, "WEBP", quality=84, method=6)
            print(f"{out.relative_to(ROOT)}  {WIDTH}x{height}  {out.stat().st_size // 1024} KiB")


if __name__ == "__main__":
    main()
