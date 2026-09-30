"""Build a ~120 s synthetic multi-speaker, multi-language meeting (ca, es, en).

Six distinct Piper voices (two per language) take turns. Ground truth (speaker, language,
start/end, text) is written next to the audio so results can be scored. Synthetic speech only;
no real meeting content.

Usage: python scripts/make_meeting_audio.py
Output: data/smoke/meeting-120s.wav and data/smoke/meeting-120s.json
"""

import json
import os
import subprocess
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "smoke"
PARTS = OUT / "parts120"
VOICES = OUT / "voices"

SPEAKERS = {
    "Marta": ("ca", "ca_ES-upc_ona-medium"),
    "Jordi": ("ca", "ca_ES-upc_pau-x_low"),
    "Lucia": ("es", "es_ES-davefx-medium"),
    "Pablo": ("es", "es_ES-carlfm-x_low"),
    "Emma": ("en", "en_US-lessac-medium"),
    "Jack": ("en", "en_US-ryan-medium"),
}

SCRIPT = [
    ("Marta", "Bon dia a tothom. Comencem la reunió de seguiment del projecte."),
    ("Lucia", "Buenos días. Yo puedo resumir el estado de la migración de la base de datos."),
    ("Emma", "Great, thanks. Before that, let me share the results of the latest performance tests."),
    ("Jordi", "Perfecte. Jo he revisat els resultats i el rendiment ha millorat un trenta per cent."),
    ("Pablo", "Eso es una muy buena noticia. Pero todavía tenemos un problema con las copias de seguridad."),
    ("Jack", "Right, the backups are failing every night because the storage volume is almost full."),
    ("Marta", "Podem ampliar el volum aquesta setmana si algú aprova la despesa."),
    ("Lucia", "Yo lo apruebo, pero necesito un presupuesto detallado antes del viernes."),
    ("Emma", "I can prepare that estimate today and send it to everyone by the end of the afternoon."),
    ("Pablo", "Perfecto. Y después tenemos que hablar de la fecha de lanzamiento de la versión nueva."),
    ("Jordi", "Jo proposaria publicar-la el dilluns vinent, quan l'equip de suport estigui disponible."),
    ("Jack", "That works for me, as long as the documentation is finished by Friday morning."),
    ("Marta", "La documentació la tinc pràcticament acabada, només falta revisar la part de seguretat."),
    ("Lucia", "Yo puedo revisar esa parte mañana por la mañana y darte los comentarios."),
    ("Emma", "One more thing, the customer asked whether we support single sign on in this release."),
    ("Pablo", "De momento no, pero podemos incluirlo en la siguiente versión si es prioritario."),
    ("Jordi", "Crec que hauríem de preguntar al client quin és el termini real que necessita."),
    ("Jack", "I will call them tomorrow and confirm the deadline and the exact requirements."),
    ("Pablo", "Yo también puedo ayudar con las pruebas finales, si alguien me pasa el entorno de preproducción."),
    ("Emma", "I will give you access this afternoon, and I will also send the test checklist we used last time."),
    ("Jordi", "Si trobem algun error crític, ho comunicarem immediatament i ajornarem el llançament."),
    ("Marta", "Molt bé. Llavors quedem així: pressupost divendres, documentació revisada, i llançament dilluns."),
    ("Lucia", "De acuerdo. Yo mandaré el resumen de la reunión por correo esta misma tarde."),
    ("Emma", "Thanks everyone. Talk to you all next week."),
    ("Jordi", "Gràcies a tots i que tingueu un bon dia."),
]
GAP_SECONDS = 0.45


def run(command, **kwargs):
    subprocess.run(command, check=True, **kwargs)


def synthesize() -> None:
    PARTS.mkdir(parents=True, exist_ok=True)
    VOICES.mkdir(parents=True, exist_ok=True)
    lines = [{"voice": SPEAKERS[name][1], "text": text} for name, text in SCRIPT]
    (PARTS / "lines.json").write_text(json.dumps(lines, ensure_ascii=False), encoding="utf-8")
    voices = sorted({voice for _, voice in SPEAKERS.values()})
    (PARTS / "synth.py").write_text(
        f"""import json, subprocess
lines = json.load(open('/out/parts120/lines.json', encoding='utf-8'))
subprocess.run(['python', '-m', 'piper.download_voices', '--download-dir', '/out/voices',
                *{voices!r}], check=True)
for index, line in enumerate(lines):
    model = '/out/voices/' + line['voice'] + '.onnx'
    target = '/out/parts120/t_' + str(index).zfill(2) + '.wav'
    subprocess.run(['python', '-m', 'piper', '-m', model, '-f', target],
                   input=line['text'].encode(), check=True)
""",
        encoding="utf-8",
    )
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    run(
        [
            "docker", "run", "--rm", "-v", f"{str(OUT).replace(chr(92), '/')}:/out",
            "python:3.12-slim", "sh", "-c",
            "pip install -q piper-tts >/dev/null 2>&1 && python /out/parts120/synth.py",
        ],
        env=env,
    )


def duration(path: Path) -> float:
    with wave.open(str(path)) as handle:
        return handle.getnframes() / handle.getframerate()


def main() -> None:
    synthesize()
    parts = [PARTS / f"t_{index:02d}.wav" for index in range(len(SCRIPT))]
    truth, cursor = [], 0.0
    for (name, text), part in zip(SCRIPT, parts, strict=True):
        length = duration(part)
        truth.append(
            {
                "speaker": name,
                "language": SPEAKERS[name][0],
                "start": round(cursor, 2),
                "end": round(cursor + length, 2),
                "text": text,
            }
        )
        cursor += length + GAP_SECONDS
    inputs, filters = [], []
    for index, part in enumerate(parts):
        inputs += ["-i", str(part)]
        filters.append(
            f"[{index}:a]aresample=16000,aformat=channel_layouts=mono,"
            f"apad=pad_dur={GAP_SECONDS}[a{index}]"
        )
    labels = "".join(f"[a{index}]" for index in range(len(parts)))
    graph = ";".join(filters) + f";{labels}concat=n={len(parts)}:v=0:a=1[out]"
    target = OUT / "meeting-120s.wav"
    run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", *inputs, "-filter_complex", graph,
         "-map", "[out]", "-c:a", "pcm_s16le", str(target)])
    (OUT / "meeting-120s.json").write_text(
        json.dumps(truth, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"{target.name}: {cursor:.1f} s, {len(SCRIPT)} turns, {len(SPEAKERS)} speakers")


if __name__ == "__main__":
    main()
