// Renders presentation/index.html to an MP4 with sound, frame by frame (1920×1080, 30 fps).
//   node presentation/render.mjs [out.mp4] [from-seconds] [to-seconds]
// Needs the frontend's Playwright (cd frontend && npm ci), ffmpeg on the PATH and Python with
// numpy for the sound (the repository's .venv, or PYTHON=...).
import { spawn, spawnSync } from "node:child_process";
import { existsSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(here, "../frontend/package.json"));
const { chromium } = require("@playwright/test");

const FPS = 30;
const out = path.resolve(process.argv[2] ?? path.join(here, "advera.mp4"));
const from = Number(process.argv[3] ?? 0);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
// VIDEO_LANG=es renders the Spanish version.
await page.goto(`${pathToFileURL(path.join(here, "index.html")).href}?lang=${process.env.VIDEO_LANG ?? "en"}`);
await page.evaluate(() => window.ready);
const to = Number(process.argv[4] ?? (await page.evaluate(() => window.DURATION)));

// The sound first: the cues of the stretch being rendered, shifted to start at 0.
const cues = (await page.evaluate(() => window.CUES))
  .filter(([t]) => t >= from - 2 && t < to)
  .map(([t, name, gain]) => [t - from, name, gain])
  .filter(([t]) => t >= 0);
const base = out.replace(/\.mp4$/, "");
writeFileSync(`${base}.cues.json`, JSON.stringify(cues));
const venv = path.join(here, "../.venv/Scripts/python.exe");
const python = process.env.PYTHON ?? (existsSync(venv) ? venv : "python");
const sound = spawnSync(python, [path.join(here, "audio.py"), `${base}.cues.json`, `${base}.wav`, String(to - from)], { stdio: "inherit" });
if (sound.status !== 0) throw new Error("audio.py failed");

const ffmpeg = spawn(
  "ffmpeg",
  ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-i", "-", "-i", `${base}.wav`,
    "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out],
  { stdio: ["pipe", "inherit", "inherit"] },
);

const frames = Math.round((to - from) * FPS);
for (let i = 0; i < frames; i++) {
  await page.evaluate((t) => window.render(t), from + i / FPS);
  const png = await page.screenshot({ type: "png" });
  if (!ffmpeg.stdin.write(png)) await new Promise((r) => ffmpeg.stdin.once("drain", r));
  if (i % FPS === 0) process.stdout.write(`\r${(from + i / FPS).toFixed(0)} s / ${to} s`);
}
ffmpeg.stdin.end();
await new Promise((resolve, reject) => ffmpeg.on("close", (code) => (code ? reject(new Error(`ffmpeg ${code}`)) : resolve())));
await browser.close();
rmSync(`${base}.cues.json`);
rmSync(`${base}.wav`);
console.log(`\n${out}`);
