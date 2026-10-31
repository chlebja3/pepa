"""Merge the two teachers' labels into verifier training candidates.

Keeps only rows where Gemma (translator + labeller) and Qwen (second opinion) agree on the verdict and both find
the text usable. The training text is Gemma's Czech translation. Enron-era mail and any single source are capped so
that one corpus does not dominate. Disagreements are written separately for inspection; they are not training data.
Optional extras: Czech FineWeb web texts the teacher found ordinary, and synthetic messages kept only when the blind
second teacher's label matches the intended one. Any row that overlaps the frozen evaluation set is dropped.
"""
import argparse
import json
import random
import re
from collections import Counter

ENRON = re.compile(r"enron|\bect\b|houston", re.I)


def load(path: str) -> dict:
    rows = {}
    for line in open(path):
        row = json.loads(line)
        rows[row["id"]] = row
    return rows


def shingles(text: str) -> set:
    words = re.findall(r"\w+", text.lower())
    return {" ".join(words[i:i + 5]) for i in range(max(1, len(words) - 4))}


def extras(args: argparse.Namespace) -> list:
    rows = []
    if args.fineweb:
        web = [r for r in load(args.fineweb).values()
               if r["teacher"]["usable"] and r["teacher"]["verdict"] in ("ordinary", "insufficient")]
        random.Random(7).shuffle(web)
        rows += [{"id": r["id"], "text": r["text"][:args.max_chars], "source": "fineweb", "style": None,
                  "verdict": r["teacher"]["verdict"], "category": None, "flags": r["teacher"]["flags"]}
                 for r in web[:args.fineweb_max]]
    if args.synthetic:
        rows += [{"id": r["id"], "text": r["text"], "source": "synthetic", "style": None,
                  "verdict": r["teacher"]["verdict"], "category": r["teacher"]["category"], "flags": r["teacher"]["flags"]}
                 for r in load(args.synthetic).values()
                 if r["teacher"]["usable"] and r["teacher"]["verdict"] == r["hint"]]
    return rows


def main(args: argparse.Namespace) -> None:
    gemma, qwen = load(args.gemma), load(args.qwen)
    rng = random.Random(7)
    agreed, disagreed, seen = [], [], set()
    reasons = Counter()
    for row_id, g in gemma.items():
        q = qwen.get(row_id)
        if q is None:
            reasons["no second opinion yet"] += 1
            continue
        gt, qt = g["teacher"], q["teacher"]
        if not (gt["usable"] and qt["usable"]):
            reasons["unusable"] += 1
            continue
        if gt["verdict"] != qt["verdict"]:
            reasons["disagree"] += 1
            disagreed.append({**g, "qwen": qt})
            continue
        cs = (gt.get("cs") or "").strip()
        if len(cs) < 0.4 * min(len(g["text"]), args.max_chars) or len(cs) < 2:
            reasons["short translation"] += 1
            continue
        key = re.sub(r"\W+", " ", cs.lower()).strip()
        if key in seen:
            reasons["duplicate"] += 1
            continue
        seen.add(key)
        agreed.append({"id": row_id, "text": cs, "source": g["source"], "style": g["style"],
                       "verdict": gt["verdict"], "category": gt["category"], "flags": gt["flags"],
                       "enron": bool(ENRON.search(g["text"]))})
    for row in extras(args):
        key = re.sub(r"\W+", " ", row["text"].lower()).strip()
        if key not in seen:
            seen.add(key)
            agreed.append({**row, "enron": False})
    exam = set()
    for path in args.exclude:
        for line in open(path):
            exam |= shingles(json.loads(line)["text"])
    clean = []
    for row in agreed:
        own = shingles(row["text"])
        if len(own & exam) > 0.2 * len(own):
            reasons["overlaps evaluation set"] += 1
        else:
            clean.append(row)
    agreed = clean
    rng.shuffle(agreed)

    per_source, kept = Counter(), []
    for row in agreed:
        if per_source[row["source"]] >= args.per_source:
            reasons["source cap"] += 1
            continue
        per_source[row["source"]] += 1
        kept.append(row)
    max_enron = int(args.enron_share * sum(not r["enron"] for r in kept) / (1 - args.enron_share))
    enron_rows = [r for r in kept if r["enron"]]
    drop = {r["id"] for r in enron_rows[max_enron:]}
    reasons["enron cap"] += len(drop)
    kept = [r for r in kept if r["id"] not in drop]

    with open(args.out, "w") as f:
        for row in kept:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with open(args.disagreements, "w") as f:
        for row in disagreed:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("kept", len(kept), dict(Counter(r["verdict"] for r in kept)))
    print("dropped", dict(reasons))
    print("styles", dict(Counter(r["style"] for r in kept)))
    print("enron", sum(r["enron"] for r in kept), "sources", per_source.most_common(8))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("gemma")
    parser.add_argument("qwen")
    parser.add_argument("out")
    parser.add_argument("--disagreements", default="teacher-disagreements.jsonl")
    parser.add_argument("--per-source", type=int, default=4000)
    parser.add_argument("--enron-share", type=float, default=0.15)
    parser.add_argument("--max-chars", type=int, default=1800)
    parser.add_argument("--fineweb", help="FineWeb rows labelled by the teacher")
    parser.add_argument("--fineweb-max", type=int, default=4000)
    parser.add_argument("--synthetic", help="synthetic messages labelled blind by the second teacher")
    parser.add_argument("--exclude", nargs="*", default=[], help="frozen evaluation files; overlapping rows are dropped")
    main(parser.parse_args())
