"""Benchmark a typed-decision model served by Ollama (`/v1/systemone`) on the synthetic meeting.

Spike, not product code (docs/features/rebuild-local-decision-model-spike.md). It measures two
uses of a "System 1" decision model on text only:

  1. classify each turn (decision / action / question / risk / other), the basis of a
     pre-filter that would keep the LLM from reading the whole transcript;
  2. verify a claim against the segment it cites (does the segment support it?), the basis of
     a check on Summary items beyond "the cited id exists";
  3. optionally (`--summary-meeting ID`), check the items Summary really produced for a meeting
     against the transcribed segments they cite, and classify the transcribed text.

The reference is the synthetic Catalan / Spanish / English meeting written by
scripts/make_meeting_audio.py (no real data). Only numbers are printed. The server address is
read from $OLLAMA_URL (never stored in the repository).

Usage:
  OLLAMA_URL=http://host:11434 python scripts/decision_model_benchmark.py --model tev1:0.8b
"""

import argparse
import http.client
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLASSES = ("decision", "action", "question", "risk", "other")

# Turn index (in meeting-120s.json) -> label; None = ambiguous, excluded from the metrics.
LABELS: dict[int, str | None] = {
    0: "other", 1: "other", 2: "other", 3: "other", 4: "risk", 5: "risk",
    6: "decision", 7: "decision", 8: "action", 9: "other", 10: "decision", 11: "decision",
    12: "other", 13: "action", 14: "question", 15: None, 16: "action", 17: "action",
    18: "action", 19: "action", 20: None, 21: "decision", 22: "action", 23: "other", 24: "other",
}

# (turn index, claim, is the claim supported by the turn?). Claims are written the way Summary
# would write them (Spanish), over turns in any of the three languages.
CLAIMS: list[tuple[int, str, bool]] = [
    (10, "Se propone publicar la versión el lunes.", True),
    (10, "Se propone publicar la versión el viernes.", False),
    (8, "Emma prepara la estimación de presupuesto hoy.", True),
    (8, "Emma prepara la estimación de presupuesto el viernes.", False),
    (17, "Jack llamará al cliente mañana para confirmar el plazo.", True),
    (17, "Pablo llamará al cliente mañana para confirmar el plazo.", False),
    (12, "La documentación está casi terminada; falta revisar la parte de seguridad.", True),
    (12, "La documentación aún no se ha empezado.", False),
    (5, "Las copias de seguridad fallan porque el volumen de almacenamiento está casi lleno.", True),
    (5, "Las copias de seguridad fallan por un error de red.", False),
    (21, "Se decide publicar el lunes, con el presupuesto el viernes.", True),
    (21, "Se decide aplazar el lanzamiento un mes.", False),
    (14, "El cliente preguntó si se admite inicio de sesión único en esta versión.", True),
    (14, "El cliente pidió un descuento en esta versión.", False),
    (6, "Se propone ampliar el volumen de almacenamiento esta semana.", True),
    (6, "Se propone reducir el volumen de almacenamiento esta semana.", False),
    (16, "Hay que preguntar al cliente cuál es el plazo real que necesita.", True),
    (16, "Hay que preguntar al cliente cuál es su presupuesto.", False),
    (13, "Lucia revisará la parte de seguridad mañana por la mañana.", True),
    (13, "Lucia revisará la parte de seguridad el lunes.", False),
    (22, "Lucia enviará el resumen de la reunión por correo esta tarde.", True),
    (22, "Lucia enviará el resumen de la reunión por correo mañana.", False),
    (19, "Emma dará acceso al entorno esta tarde y enviará la lista de pruebas.", True),
    (19, "Emma no dará acceso al entorno hasta la semana que viene.", False),
]

CLASSIFY = {
    "kind": {
        "type": "choice",
        "instructions": "What kind of statement is this meeting turn?",
        "criteria": {
            "decision": "a decision, proposal or agreement about what to do",
            "action": "a task someone commits to or is asked to do",
            "question": "a question asked to someone",
            "risk": "a problem, failure or risk",
            "other": "greeting, status report or anything else",
        },
    }
}

VERIFY = {
    "supported": {
        "type": "noul",
        "instructions": "Does the segment say what the claim states? Answer yes only if "
        "every detail of the claim (who, what, when) is stated in the segment.",
    }
}


class Client:
    """Minimal client for Ollama's decision endpoint."""

    def __init__(self, base_url: str, model: str) -> None:
        self.url = base_url.rstrip("/") + "/v1/systemone"
        self.model = model

    def predict(self, state: dict, questions: dict) -> dict:
        body = json.dumps({"model": self.model, "state": state, "questions": questions}).encode()
        request = urllib.request.Request(
            self.url, data=body, headers={"Content-Type": "application/json"}
        )
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    return json.load(response)["answers"]
            except (http.client.HTTPException, urllib.error.URLError, TimeoutError) as error:
                # A large model can make the server drop a connection while it swaps in.
                last_error = error
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"server kept closing the connection: {type(last_error).__name__}")


def choice_of(answers: dict, name: str) -> str:
    return str(answers[name]["choice"])


def probability_of(answers: dict, name: str) -> float:
    return float(answers[name]["noul"])


def load_turns(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def timed(function, repeat: int):
    values = []
    result = None
    for _ in range(repeat):
        started = time.perf_counter()
        result = function()
        values.append((time.perf_counter() - started) * 1000)
    return result, statistics.median(values)


def report_classification(confusion, by_language, latencies) -> None:
    correct = sum(confusion[c][c] for c in CLASSES)
    total = sum(sum(row.values()) for row in confusion.values())
    print(f"accuracy {correct}/{total}")
    for language, hits in sorted(by_language.items()):
        print(f"  {language}: {sum(hits)}/{len(hits)}")
    for cls in CLASSES:
        tp = confusion[cls][cls]
        support = sum(confusion[cls].values())
        predicted_total = sum(confusion[other][cls] for other in CLASSES)
        recall = tp / support if support else float("nan")
        precision = tp / predicted_total if predicted_total else float("nan")
        print(f"  {cls:9} recall {recall:5.2f} precision {precision:5.2f} (n={support})")
    candidates = ("decision", "action")
    needed = sum(sum(confusion[c].values()) for c in candidates)
    lost = sum(confusion[c][p] for c in candidates for p in CLASSES if p not in candidates)
    print(
        f"pre-filter: recall of decision+action as a candidate = "
        f"{(needed - lost) / needed:.2f} (lost {lost} of {needed})"
    )
    if latencies:
        print(f"latency per question (client side): median {statistics.median(latencies):.0f} ms")


def classify_section(client: Client, turns: list[dict], repeat: int) -> None:
    print("== 1. classify turns ==")
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_language: dict[str, list[bool]] = defaultdict(list)
    latencies = []
    for index, turn in enumerate(turns):
        expected = LABELS.get(index)
        if expected is None:
            continue
        answers, milliseconds = timed(
            lambda t=turn: client.predict({"turn": t["text"]}, CLASSIFY), repeat
        )
        latencies.append(milliseconds)
        predicted = choice_of(answers, "kind")
        confusion[expected][predicted] += 1
        by_language[turn["language"]].append(predicted == expected)
    report_classification(confusion, by_language, latencies)


def verify_section(client: Client, turns: list[dict], repeat: int) -> None:
    print("\n== 2. verify claims against the cited turn ==")
    scored = []
    latencies = []
    for index, claim, truth in CLAIMS:
        answers, milliseconds = timed(
            lambda i=index, c=claim: client.predict(
                {"segment": turns[i]["text"], "claim": c}, VERIFY
            ),
            repeat,
        )
        latencies.append(milliseconds)
        scored.append((probability_of(answers, "supported"), truth, turns[index]["language"]))
    print(f"latency per question (client side): median {statistics.median(latencies):.0f} ms")
    positives = [p for p, t, _ in scored if t]
    negatives = [p for p, t, _ in scored if not t]
    print(
        f"mean p(supported): true claims {statistics.mean(positives):.2f}, "
        f"false claims {statistics.mean(negatives):.2f}"
    )
    print("threshold  false-caught  true-kept   F1(false)")
    for threshold in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
        caught = sum(1 for p in negatives if p < threshold)
        kept_true = sum(1 for p in positives if p >= threshold)
        precision = caught / max(1, caught + (len(positives) - kept_true))
        recall = caught / len(negatives)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        print(
            f"  {threshold:.1f}      {caught:2}/{len(negatives)}        "
            f"{kept_true:2}/{len(positives)}      {f1:.2f}"
        )
    for language in sorted({lang for _, _, lang in scored}):
        subset = [(p, t) for p, t, lang in scored if lang == language]
        right = sum(1 for p, t in subset if (p >= 0.5) == t)
        print(f"  segment language {language}: {right}/{len(subset)} right at 0.5")


def api_get(api: str, path: str):
    with urllib.request.urlopen(api.rstrip("/") + path, timeout=30) as response:
        return json.load(response)


def pipeline_section(client: Client, api: str, meeting_id: str, reference: list[dict]) -> None:
    """What the running pipeline really produced: Summary's items and Whisper's text."""
    print("\n== 3. real pipeline output ==")
    summary = api_get(api, f"/api/meetings/{meeting_id}/summary")["result"]
    transcript = api_get(api, f"/api/meetings/{meeting_id}/transcript")
    segments = {s["id"]: s for s in transcript["segments"]}
    accepted = checked = 0
    for category in ("decisions", "actions", "topics", "open_questions", "risks"):
        for item in summary.get(category, []):
            cited = " ".join(
                segments[e["segment_id"]]["text"]
                for e in item["evidence"]
                if e["segment_id"] in segments
            )
            if not cited:
                continue
            answers = client.predict({"segment": cited, "claim": item["text"]}, VERIFY)
            p = probability_of(answers, "supported")
            checked += 1
            accepted += p >= 0.5
            print(f"  {category:14} p(supported)={p:.2f}")
    print(f"real Summary items accepted at 0.5: {accepted}/{checked} (all are supposed to pass)")
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_language: dict[str, list[bool]] = defaultdict(list)
    for index, turn in enumerate(reference):
        expected = LABELS.get(index)
        best, overlap = None, 0.0
        for segment in transcript["segments"]:
            shared = min(turn["end"], segment["end"]) - max(turn["start"], segment["start"])
            if shared > overlap:
                best, overlap = segment, shared
        if expected is None or best is None:
            continue
        answers = client.predict({"turn": best["text"]}, CLASSIFY)
        predicted = choice_of(answers, "kind")
        confusion[expected][predicted] += 1
        by_language[turn["language"]].append(predicted == expected)
    print("classification of the transcribed (Whisper) text:")
    report_classification(confusion, by_language, [])


def prefilter_rule_section(client: Client, reference: list[dict], transcript: dict | None) -> None:
    """Pre-filter by probability instead of argmax: keep a turn unless p(other) >= T."""
    print()
    print("== 4. pre-filter rule: keep a turn unless p(other) >= T ==")
    sources = {"reference text": [t["text"] for t in reference]}
    if transcript is not None:
        texts = []
        for turn in reference:
            best, overlap = None, 0.0
            for segment in transcript["segments"]:
                shared = min(turn["end"], segment["end"]) - max(turn["start"], segment["start"])
                if shared > overlap:
                    best, overlap = segment, shared
            texts.append(best["text"] if best else "")
        sources["Whisper text"] = texts
    for name, texts in sources.items():
        scored = []
        for index, text in enumerate(texts):
            label = LABELS.get(index)
            if label is None or not text:
                continue
            probabilities = client.predict({"turn": text}, CLASSIFY)["kind"]["probabilities"]
            scored.append((label, probabilities.get("other", 0.0)))
        needed = [p for label, p in scored if label in ("decision", "action")]
        print(f"{name} (n={len(scored)}):")
        for threshold in (0.5, 0.7, 0.8, 0.9, 0.95):
            recall = sum(1 for p in needed if p < threshold)
            kept = sum(1 for _, p in scored if p < threshold)
            print(
                f"  T={threshold:.2f}  decision+action kept {recall}/{len(needed)}, "
                f"turns kept {kept}/{len(scored)}"
            )


def run(args: argparse.Namespace) -> int:
    base_url = os.environ.get("OLLAMA_URL")
    if not base_url:
        print("set OLLAMA_URL to the Ollama server address", file=sys.stderr)
        return 2
    client = Client(base_url, args.model)
    print(f"model {args.model}")
    turns = load_turns(Path(args.json))
    classify_section(client, turns, args.repeat)
    verify_section(client, turns, args.repeat)
    transcript = None
    if args.summary_meeting:
        pipeline_section(client, args.api, args.summary_meeting, turns)
        transcript = api_get(args.api, f"/api/meetings/{args.summary_meeting}/transcript")
    prefilter_rule_section(client, turns, transcript)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", default=str(ROOT / "data" / "smoke" / "meeting-120s.json"))
    parser.add_argument("--model", default="tev1:0.8b", help="Ollama decision model")
    parser.add_argument("--api", default="http://localhost:18000", help="AdVera API")
    parser.add_argument("--summary-meeting", help="meeting id whose Summary items to verify")
    parser.add_argument("--repeat", type=int, default=2, help="timing repetitions per question")
    return run(parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())
