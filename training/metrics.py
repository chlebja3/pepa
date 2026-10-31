"""Precision and recall of a verifier from the per-row results of bench_confidence_hf.py / bench_page_verifier.py.

A row counts as flagged when "podvod" is the model's most likely verdict, so no threshold is tuned on the exam.
Rows labelled "insufficient" are left out: the exam asks only scam vs. ordinary. English Phish-IRIS pages are
reported separately from the Czech material, and Czech messages also without the Czech web texts (fineweb), which
only add ordinary rows and so show precision at a more realistic scam rate.
"""
import argparse
import json
from collections import defaultdict

VERDICTS = ("podvod", "bezne", "nevim")


def flagged(row: dict) -> bool:
    return max(VERDICTS, key=row.get) == "podvod"


def scores(rows: list) -> str:
    tp = sum(r["hint"] == "scam" and flagged(r) for r in rows)
    fp = sum(r["hint"] == "ordinary" and flagged(r) for r in rows)
    scams = sum(r["hint"] == "scam" for r in rows)
    ordinary = sum(r["hint"] == "ordinary" for r in rows)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / scams if scams else 0.0
    return (f"precision {precision:.1%} ({tp}/{tp + fp})  recall {recall:.1%} ({tp}/{scams})  "
            f"false alarms {fp}/{ordinary}")


def main(args: argparse.Namespace) -> None:
    for path in args.results:
        rows = [r for r in map(json.loads, open(path)) if r["hint"] in ("scam", "ordinary")]
        parts = defaultdict(list)
        for r in rows:
            parts["english" if r["source"].startswith("phish-iris") else "czech"].append(r)
        if any(r["source"].startswith("fineweb") for r in parts["czech"]):
            parts["czech messages"] = [r for r in parts["czech"] if not r["source"].startswith("fineweb")]
        print(path)
        for name, part in sorted(parts.items()):
            print(f"  {name:15} {scores(part)}")
        by_source = defaultdict(list)
        for r in parts["czech"]:
            by_source[(r["hint"], r["source"])].append(flagged(r))
        print("  czech flagged by source: " + ", ".join(f"{h} {s} {sum(f)}/{len(f)}" for (h, s), f in sorted(by_source.items())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("results", nargs="+", help="per-row result JSONL files")
    main(parser.parse_args())
