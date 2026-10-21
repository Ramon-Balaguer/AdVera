"""The sound of the AdVera presentation, synthesized from scratch (no samples, no downloads).

    python presentation/audio.py cues.json out.wav [duration]

cues.json is [[seconds, sound, gain], ...], exported by render.mjs from window.CUES in
index.html, so every sound lands on the frame it belongs to. Under the cues runs a quiet pad
of slow chords. Everything goes through a light reverb and a soft limiter.
"""

import json
import sys
import wave

import numpy as np

RATE = 44_100
rng = np.random.default_rng(20261021)


def seconds(n: float) -> np.ndarray:
    return np.arange(int(n * RATE)) / RATE


def lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    spectrum = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / RATE)
    return np.fft.irfft(spectrum / np.sqrt(1 + (freqs / cutoff) ** 4), len(x))


def bandpass(x: np.ndarray, centre: float, width: float) -> np.ndarray:
    spectrum = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / RATE)
    return np.fft.irfft(spectrum * np.exp(-(((freqs - centre) / width) ** 2)), len(x))


def sweep(n: float, start: float, end: float, width: float) -> np.ndarray:
    """Noise through a band-pass whose centre glides from start to end (overlapping windows)."""
    total = int(n * RATE)
    out = np.zeros(total)
    size = 2048
    window = np.hanning(size)
    for begin in range(0, total - size, size // 4):
        x = (begin + size / 2) / total
        centre = start * (end / start) ** x
        out[begin : begin + size] += bandpass(rng.standard_normal(size), centre, width * (centre / 1000) ** 0.5) * window
    return out / (np.abs(out).max() + 1e-9)


def env(n: float, attack: float, release: float, curve: float = 3) -> np.ndarray:
    t = seconds(n)
    rise = np.clip(t / max(attack, 1e-4), 0, 1)
    fall = np.clip((n - t) / max(release, 1e-4), 0, 1) ** curve
    return rise * fall


def whoosh() -> np.ndarray:
    n = 0.7
    return sweep(n, 400, 3200, 900) * env(n, 0.35, 0.35, 2) * 0.9


def riser() -> np.ndarray:
    n = 1.6
    t = seconds(n)
    tone = np.sin(2 * np.pi * (180 * t + 260 * t**2 / n)) * 0.25
    return (sweep(n, 300, 5000, 1200) * 0.6 + tone) * (t / n) ** 2.2


def suck() -> np.ndarray:
    """The last, steepest part of a riser: the brain drawn into one point."""
    return riser()[-int(0.9 * RATE) :]


def hit() -> np.ndarray:
    n = 1.6
    t = seconds(n)
    freq = 42 + 70 * np.exp(-t * 18)
    body = np.sin(2 * np.pi * np.cumsum(freq) / RATE) * np.exp(-t * 3.2)
    crack = lowpass(rng.standard_normal(len(t)), 2400) * np.exp(-t * 40) * 0.6
    return (body + crack) * 0.95


def tick() -> np.ndarray:
    n = 0.09
    t = seconds(n)
    return (np.sin(2 * np.pi * 1800 * t) * 0.5 + rng.standard_normal(len(t)) * 0.08) * np.exp(-t * 70)


def click() -> np.ndarray:
    a = tick() * 0.8
    b = np.sin(2 * np.pi * 2600 * seconds(0.07)) * np.exp(-seconds(0.07) * 80) * 0.5
    out = np.zeros(int(0.16 * RATE))
    out[: len(a)] += a
    out[int(0.06 * RATE) : int(0.06 * RATE) + len(b)] += b
    return out


def bell(freq: float, n: float = 1.8) -> np.ndarray:
    t = seconds(n)
    partials = [(1, 1.0, 2.2), (2.76, 0.35, 3.5), (5.4, 0.15, 6), (8.93, 0.06, 9)]
    return sum(a * np.sin(2 * np.pi * freq * m * t) * np.exp(-t * d) for m, a, d in partials) * env(n, 0.004, 0.2)


def chime() -> np.ndarray:
    out = bell(659.25) * 0.6
    second = bell(987.77) * 0.35
    lag = int(0.09 * RATE)
    out[lag:] += second[: len(out) - lag]
    return out


def sparkle() -> np.ndarray:
    out = np.zeros(int(1.6 * RATE))
    notes = [1318.5, 1567.98, 1975.5, 2349.3, 2637.0, 3135.9]
    for i, f in enumerate(notes):
        b = bell(f, 0.9) * (0.3 - i * 0.03)
        at = int(i * 0.08 * RATE)
        out[at : at + len(b)] += b[: len(out) - at]
    return out


def pulse() -> np.ndarray:
    n = 0.32
    t = seconds(n)
    freq = 48 + 50 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(freq) / RATE) * np.exp(-t * 11) * 0.7


SOUNDS = {
    "whoosh": whoosh, "riser": riser, "suck": suck, "hit": hit, "tick": tick,
    "click": click, "chime": chime, "sparkle": sparkle, "pulse": pulse,
}


def pad(duration: float) -> np.ndarray:
    """Slow chords (A minor, F, C, G with added notes), detuned sines, low-passed."""
    chords = [
        [110.0, 164.81, 220.0, 261.63, 329.63, 493.88],
        [87.31, 130.81, 174.61, 220.0, 261.63, 329.63],
        [65.41, 130.81, 196.0, 261.63, 329.63, 392.0],
        [98.0, 146.83, 196.0, 246.94, 293.66, 440.0],
    ]
    t = seconds(duration)
    out = np.zeros(len(t))
    length = 7.5
    for k in range(int(duration / length) + 1):
        start = k * length
        piece = (t >= start - 1.5) & (t < start + length + 1.5)
        local = t[piece] - start
        shape = np.clip((local + 1.5) / 3, 0, 1) * np.clip((length + 1.5 - local) / 3, 0, 1)
        for f in chords[k % len(chords)]:
            for detune in (-0.25, 0.25):
                out[piece] += np.sin(2 * np.pi * (f + detune) * t[piece] + rng.random() * 6) * shape
    out = lowpass(out, 1400)
    return out / np.abs(out).max() * 0.16


def reverb(x: np.ndarray, length: float = 2.2, mix: float = 0.22) -> np.ndarray:
    t = seconds(length)
    ir = rng.standard_normal(len(t)) * np.exp(-t * 3.0)
    ir = lowpass(ir, 5000)
    size = 1 << int(np.ceil(np.log2(len(x) + len(ir))))
    wet = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x)]
    wet /= np.abs(wet).max() + 1e-9
    return x * (1 - mix) + wet * np.abs(x).max() * mix


def main() -> None:
    cues = json.load(open(sys.argv[1], encoding="utf-8"))
    duration = float(sys.argv[3]) if len(sys.argv) > 3 else 60.0
    total = int(duration * RATE)
    fx = np.zeros(total)
    cache: dict[str, np.ndarray] = {}
    for at, name, gain in cues:
        sound = cache.setdefault(name, SOUNDS[name]())
        if name == "pulse":  # no two pulses alike
            sound = sound * (0.9 + 0.2 * rng.random())
        start = int(at * RATE)
        if start >= total:
            continue
        piece = sound[: total - start] * gain
        fx[start : start + len(piece)] += piece
    mix = reverb(fx) + pad(duration)
    fade = np.minimum(np.clip(seconds(duration) / 0.4, 0, 1), np.clip((duration - seconds(duration)) / 1.2, 0, 1))
    mix *= fade
    mix = np.tanh(mix * 1.4) / np.tanh(1.4)  # soft limiter
    mix *= 0.89 / np.abs(mix).max()  # -1 dBFS
    # A touch of width: the reverb tail a little to each side.
    left = mix
    right = np.roll(mix, int(0.012 * RATE))
    stereo = np.stack([left, right], axis=1)
    data = (stereo * 32767).astype("<i2").tobytes()
    with wave.open(sys.argv[2], "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data)


if __name__ == "__main__":
    main()
