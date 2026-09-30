"""Benchmark a local typed-decision model (Laya) on the synthetic 120 s meeting.

Spike, not product code (docs/features/rebuild-local-decision-model-spike.md). It measures two
uses of a "System 1" decision model on text only:

  1. classify each turn (decision / action / question / risk / other), the basis of a
     pre-filter that would keep the LLM from reading the whole transcript;
  2. verify a claim against the segment it cites (does the segment support it?), the basis of
     a check on Brain items beyond "the cited id exists".

The reference is the synthetic Catalan / Spanish / English meeting written by
scripts/make_meeting_audio.py (no real data). Only numbers are printed.

Usage (needs the `laya` package, kept out of the backend image):
  python scripts/laya_benchmark.py [--json data/smoke/meeting-120s.json] [--repeat 3]
"""

import argparse
import json
import statistics
import sys
import time
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

# (turn index, claim, is the claim supported by the turn?). Claims are written the way Brain
# would write them (Spanish or English), over turns in any of the three languages.
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


CLASSIFY_B = {
    "kind": {
        "type": "choice",
        "instructions": "Classify this sentence from a business meeting by what the speaker "
        "is doing. A speaker who says they will do something, offers to do it, or is assigned "
        "it is making an action. A speaker who proposes, approves or agrees on a course of "
        "action is making a decision.",
        "criteria": {
            "decision": "proposes, approves, agrees or decides what will be done",
            "action": "says who will do a task, offers to do it, or asks someone to do it",
            "question": "asks a question",
            "risk": "reports a problem, failure, delay or danger",
            "other": "greeting, thanks, status update or summary with no commitment",
        },
    }
}

VERIFY_B = {
    "supported": {
        "type": "noul",
        "instructions": "Read the segment and the claim. Is the claim a correct paraphrase of "
        "what the segment says, with the same person, action, time and numbers? Different "
        "wording is fine; a different detail is not.",
    }
}


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


def choice_of(result: dict, name: str) -> str:
    """Predicted class: Router.predict returns {"answers": {name: {"choice": ...}}}."""
    return str(result["answers"][name]["choice"])


def probability_of(result: dict, name: str) -> float:
    """Probability of a `noul` (yes) question."""
    return float(result["answers"][name]["noul"])


def run(args: argparse.Namespace) -> int:
    from laya import Router

    classify = CLASSIFY_B if args.variant == "b" else CLASSIFY
    print(f"variant {args.variant}")

    turns = load_turns(Path(args.json))
    router = Router()

    print("== 1. classify turns ==")
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_language: dict[str, list[bool]] = defaultdict(list)
    latencies = []
    for index, turn in enumerate(turns):
        expected = LABELS.get(index)
        if expected is None:
            continue
        result, milliseconds = timed(lambda t=turn: router.predict(t["text"], classify), args.repeat)
        latencies.append(milliseconds)
        predicted = choice_of(result, "kind")
        confusion[expected][predicted] += 1
        by_language[turn["language"]].append(predicted == expected)
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
    kept = sum(confusion[c][p] for c in candidates for p in candidates)
    needed = sum(sum(confusion[c].values()) for c in candidates)
    lost = sum(confusion[c][p] for c in candidates for p in CLASSES if p not in candidates)
    print(
        f"pre-filter: recall of decision+action as a candidate = "
        f"{(needed - lost) / needed:.2f} (lost {lost} of {needed}; kept-as-right-class {kept})"
    )
    print(f"latency per question: median {statistics.median(latencies):.0f} ms")

    print("\n== 2. verify claims against the cited turn ==")
    question = VERIFY_B if args.variant == "b" else {
        "supported": {
            "type": "noul",
            "instructions": "Does the segment say what the claim states? Answer yes only if "
            "every detail of the claim (who, what, when) is stated in the segment.",
        }
    }
    scored = []
    latencies = []
    for index, claim, truth in CLAIMS:
        state = f"Segment: {turns[index]['text']}\nClaim: {claim}"
        result, milliseconds = timed(lambda s=state: router.predict(s, question), args.repeat)
        latencies.append(milliseconds)
        scored.append((probability_of(result, "supported"), truth, turns[index]["language"]))
    print(f"latency per question: median {statistics.median(latencies):.0f} ms")
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
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", default=str(ROOT / "data" / "smoke" / "meeting-120s.json"))
    parser.add_argument("--variant", choices=("a", "b"), default="a", help="wording of the questions")
    parser.add_argument("--repeat", type=int, default=3, help="timing repetitions per question")
    return run(parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())
