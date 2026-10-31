"""Split the evaluation material into a dev half (for choosing training settings and thresholds) and a test half
(reported once at the end), so the real Czech exam is not used to pick the winner it is scored on.

Input: eval-labels.jsonl = the 385 real Czech exam texts plus Czech web texts (fineweb). Web texts are ordinary
material that measures false alarms at a realistic scam rate; the few the teacher called a scam are dropped as
ambiguous. The split is by a hash of the id, stratified by source and label.
Output: <out>/dev.jsonl and <out>/test.jsonl in the bench format {id, text, source, hint}.
"""
import argparse
import hashlib
import json
from pathlib import Path


def half(row_id: str) -> str:
    return "dev" if int(hashlib.sha1(row_id.encode()).hexdigest(), 16) % 2 == 0 else "test"


def main(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(exist_ok=True)
    files = {name: open(out / f"{name}.jsonl", "w") for name in ("dev", "test")}
    counts = {}
    for row in map(json.loads, open(args.labels)):
        hint, source = row["hint"], row["source"]
        if source.startswith("fineweb"):
            if (row.get("teacher") or {}).get("verdict") != "ordinary":
                continue
            source, hint = f"fineweb:{hint}", "ordinary"
        if hint not in ("scam", "ordinary"):
            continue
        split = half(row["id"])
        files[split].write(json.dumps({"id": row["id"], "text": row["text"], "source": source, "hint": hint},
                                      ensure_ascii=False) + "\n")
        key = (split, source, hint)
        counts[key] = counts.get(key, 0) + 1
    for key, n in sorted(counts.items()):
        print(*key, n)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("labels", help="eval-labels.jsonl")
    parser.add_argument("out")
    main(parser.parse_args())
