"""Precision/recall tradeoff of each verifier: the threshold on the margin (log-odds of "podvod") is chosen on the dev
half for a target precision, then applied unchanged to the test half (split_exam.py). Given only one folder, each
file is split into the halves by the same id hash (page results). English Phish-IRIS pages are left out: the page
verifier trains on other pages of that collection.

Precision counts all Czech ordinary rows, Czech web texts included, so scams are only ~5 % of the rows, closer to a
real inbox than the exam alone. "argmax" is the model's own answer without any threshold.
--recall picks the threshold for a target recall instead (screeners, and verifiers when a missed scam is the worse
error); the false alarms then show how often an ordinary text would be warned about or forwarded.
"""
import argparse
import json
from pathlib import Path

from split_exam import half


def load(path: Path) -> list:
    return [r for r in map(json.loads, open(path))
            if r["hint"] in ("scam", "ordinary") and not r["source"].startswith("phish-iris")]


def at(rows: list, threshold: float) -> tuple:
    tp = sum(r["hint"] == "scam" and r["margin"] > threshold for r in rows)
    fp = sum(r["hint"] == "ordinary" and r["margin"] > threshold for r in rows)
    scams = sum(r["hint"] == "scam" for r in rows)
    return (tp / (tp + fp) if tp + fp else 1.0), tp / scams, fp


def pick(rows: list, precision: float) -> float:
    """Lowest threshold whose dev precision still reaches the target (most recall at that precision)."""
    for threshold in sorted({r["margin"] for r in rows}):
        if at(rows, threshold)[0] >= precision:
            return threshold
    return max(r["margin"] for r in rows)


def pick_recall(rows: list, recall: float) -> float:
    """Highest threshold whose dev recall still reaches the target (fewest false alarms at that recall)."""
    for threshold in sorted({r["margin"] for r in rows}, reverse=True):
        if at(rows, threshold)[1] >= recall:
            return threshold
    return min(r["margin"] for r in rows) - 1


def fmt(result: tuple) -> str:
    precision, recall, fp = result
    return f"P {precision:5.1%} R {recall:5.1%} FA {fp:2}"


def main(args: argparse.Namespace) -> None:
    for dev_path in sorted(Path(args.dev).glob("*.jsonl")):
        if args.test:
            test_path = Path(args.test) / dev_path.name
            if not test_path.exists():
                continue
            dev, test = load(dev_path), load(test_path)
        else:
            rows = load(dev_path)
            dev, test = [r for r in rows if half(r["id"]) == "dev"], [r for r in rows if half(r["id"]) == "test"]
        argmax = [{**r, "margin": 1.0 if max(("podvod", "bezne", "nevim"), key=r.get) == "podvod" else -1.0} for r in test]
        cells = [f"argmax {fmt(at(argmax, 0.0))}"]
        for target in args.precision:
            cells.append(f"@P{target:.0%} {fmt(at(test, pick(dev, target)))}")
        for target in args.recall:
            cells.append(f"@R{target:.0%} {fmt(at(test, pick_recall(dev, target)))}")
        print(f"{dev_path.stem:28} " + " | ".join(cells))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dev", help="folder of per-row dev results (one JSONL per model)")
    parser.add_argument("test", nargs="?", help="folder of test results with the same file names")
    parser.add_argument("--precision", type=float, nargs="+", default=[0.8, 0.9, 0.95])
    parser.add_argument("--recall", type=float, nargs="*", default=[0.8, 0.9])
    main(parser.parse_args())
