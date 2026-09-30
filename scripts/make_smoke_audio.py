"""Generate synthetic speech for ASR and diarization smoke tests (no real meeting content).

Every smoke set covers Catalan, Spanish and English (spec §7, §25):
- Catalan: Piper TTS voices `ca_ES-upc_ona-medium` and `ca_ES-upc_pau-x_low`, synthesized in a
  throwaway python:3.12-slim container (voices from huggingface.co/rhasspy/piper-voices).
- Spanish / English: Windows SAPI voices (Helena es-ES, Zira en-US), when running on Windows.

Two-speaker files alternate voices so diarization can be checked. Output goes to
data/smoke/ (git-ignored) as 16 kHz mono WAV; host ffmpeg joins and resamples.

Usage: python scripts/make_smoke_audio.py
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "smoke"
PARTS = OUT / "parts"
VOICES = OUT / "voices"

CATALAN = {
    "ona": "ca_ES-upc_ona-medium",
    "pau": "ca_ES-upc_pau-x_low",
}
CA_LINES = [
    (
        "ona",
        "Bon dia a tothom. Aquesta és una gravació sintètica per provar la transcripció definitiva.",
    ),
    (
        "pau",
        "Avui revisem el calendari del projecte i acordem publicar la nova versió dilluns vinent.",
    ),
    ("ona", "Perfecte. Llavors jo preparo el document i el comparteixo divendres."),
    ("pau", "D'acord, i jo revisaré el pressupost abans de la reunió."),
]
SAPI = {"es": "Microsoft Helena Desktop", "en": "Microsoft Zira Desktop"}
ES_TEXT = (
    "Hola a todos. Esta es una grabación sintética para probar la transcripción definitiva. "
    "Hoy revisamos el calendario del proyecto y acordamos publicar la versión nueva el próximo lunes."
)
EN_TEXT = (
    "Good morning everyone. This is a synthetic recording used to test the definitive transcript. "
    "We agreed to ship the new release next Monday and to review the budget on Friday."
)
MIXED_LINES = [
    ("es", "Buenos días. Empezamos la revisión semanal del proyecto."),
    ("en", "Thanks. The release candidate is ready for testing."),
    ("es", "Perfecto, entonces publicamos el lunes."),
    ("en", "Agreed. I will send the notes after the meeting."),
]


def run(command: list[str], **kwargs) -> None:
    subprocess.run(command, check=True, **kwargs)


def docker_path(path: Path) -> str:
    # Docker Desktop on Windows accepts native paths with forward slashes.
    return str(path).replace("\\", "/")


def synthesize_catalan() -> list[Path]:
    PARTS.mkdir(parents=True, exist_ok=True)
    VOICES.mkdir(parents=True, exist_ok=True)
    lines = [{"voice": CATALAN[speaker], "text": text} for speaker, text in CA_LINES]
    (PARTS / "ca_lines.json").write_text(json.dumps(lines, ensure_ascii=False), encoding="utf-8")
    # A helper file avoids nested shell quoting; it runs inside the container.
    helper = f"""import json, subprocess
lines = json.load(open('/out/parts/ca_lines.json', encoding='utf-8'))
voices = {sorted(set(CATALAN.values()))!r}
subprocess.run(['python', '-m', 'piper.download_voices', '--download-dir', '/out/voices',
                *voices], check=True)
for index, line in enumerate(lines):
    model = '/out/voices/' + line['voice'] + '.onnx'
    target = '/out/parts/ca_' + str(index) + '.wav'
    subprocess.run(['python', '-m', 'piper', '-m', model, '-f', target],
                   input=line['text'].encode(), check=True)
"""
    (PARTS / "synth.py").write_text(helper, encoding="utf-8")
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{docker_path(OUT)}:/out",
            "python:3.12-slim",
            "sh",
            "-c",
            "pip install -q piper-tts >/dev/null 2>&1 && python /out/parts/synth.py",
        ],
        env=env,
    )
    return [PARTS / f"ca_{index}.wav" for index in range(len(CA_LINES))]


def synthesize_sapi(language: str, text: str, target: Path) -> None:
    # The text goes through a UTF-8 file: console stdin would use the OEM code page and
    # mangle accented characters.
    text_file = target.with_suffix(".txt")
    text_file.write_text(text, encoding="utf-8")
    command = (
        "Add-Type -AssemblyName System.Speech;"
        "$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,"
        "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,"
        "[System.Speech.AudioFormat.AudioChannel]::Mono);"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"$s.SelectVoice('{SAPI[language]}');"
        f"$s.SetOutputToWaveFile('{target}', $f);"
        f"$s.Speak((Get-Content -Raw -Encoding UTF8 '{text_file}')); $s.Dispose()"
    )
    run(["powershell", "-NoProfile", "-Command", command])
    text_file.unlink()


def join(parts: list[Path], target: Path, gap_seconds: float = 0.6) -> None:
    """Concatenate parts with silence gaps, resampled to 16 kHz mono PCM16."""
    inputs: list[str] = []
    filters = []
    for index, part in enumerate(parts):
        inputs += ["-i", str(part)]
        filters.append(
            f"[{index}:a]aresample=16000,aformat=channel_layouts=mono,"
            f"apad=pad_dur={gap_seconds}[a{index}]"
        )
    labels = "".join(f"[a{index}]" for index in range(len(parts)))
    graph = ";".join(filters) + f";{labels}concat=n={len(parts)}:v=0:a=1[out]"
    run(
        [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            *inputs,
            "-filter_complex",
            graph,
            "-map",
            "[out]",
            "-c:a",
            "pcm_s16le",
            str(target),
        ]
    )


def main() -> int:
    if shutil.which("ffmpeg") is None or shutil.which("docker") is None:
        print("ffmpeg and docker are required", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)

    ca_parts = synthesize_catalan()
    join([ca_parts[0], ca_parts[2]], OUT / "ca-single.wav")  # one voice (ona)
    join(ca_parts, OUT / "ca-two-speakers.wav")

    if sys.platform == "win32":
        synthesize_sapi("es", ES_TEXT, OUT / "es-single.wav")
        synthesize_sapi("en", EN_TEXT, OUT / "en-single.wav")
        mixed = []
        for index, (language, text) in enumerate(MIXED_LINES):
            part = PARTS / f"mixed_{index}.wav"
            synthesize_sapi(language, text, part)
            mixed.append(part)
        join(mixed, OUT / "es-en-two-speakers.wav")
    else:
        print("Spanish/English SAPI voices need Windows; only Catalan was generated")

    for path in sorted(OUT.glob("*.wav")):
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
