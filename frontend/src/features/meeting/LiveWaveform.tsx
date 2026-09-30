import { useEffect, useRef } from "react";

// Live capture waveform (dual-track-playback-live-metrics.md): a scrolling history of RMS
// levels per track. It is a capture visualization only and is hidden once capture ends
// (post-recording-playback-controls-only.md). Levels are telemetry, never transcript evidence.

export const WAVEFORM_HISTORY = 120; // ~12 s at 10 updates per second

export function pushLevel(history: number[], level: number): number[] {
  const next = history.length >= WAVEFORM_HISTORY ? history.slice(1) : history.slice();
  next.push(Math.max(0, Math.min(1, level)));
  return next;
}

export function LiveWaveform({ label, track, levels }: { label: string; track: string; levels: number[] }) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const element = canvas.current;
    const context = element?.getContext("2d");
    if (!element || !context) return;
    const ratio = window.devicePixelRatio || 1;
    const width = element.clientWidth * ratio;
    const height = element.clientHeight * ratio;
    if (element.width !== width || element.height !== height) {
      element.width = width;
      element.height = height;
    }
    context.clearRect(0, 0, width, height);
    const color = getComputedStyle(element).color;
    context.fillStyle = color;
    const barWidth = width / WAVEFORM_HISTORY;
    const middle = height / 2;
    // Newest level on the right; RMS is small, so scale it up for visibility.
    const offset = WAVEFORM_HISTORY - levels.length;
    levels.forEach((level, index) => {
      const amplitude = Math.max(1 * ratio, Math.min(1, level * 4) * middle);
      context.fillRect((offset + index) * barWidth, middle - amplitude, Math.max(1, barWidth - ratio), amplitude * 2);
    });
  }, [levels]);

  return (
    <div className="waveform-row">
      <span>{label}</span>
      <canvas
        ref={canvas}
        className={`waveform waveform-${track}`}
        data-testid={`waveform-${track}`}
        role="img"
        aria-label={`Forma de onda en vivo: ${label}`}
      />
    </div>
  );
}
