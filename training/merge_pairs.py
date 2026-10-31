"""Merge the contrastive pairs into a verifier training file: train-explained-gram-mami.jsonl + pair-final.jsonl."""
import json
import sys
from collections import Counter

base, pairs, out = sys.argv[1:4]
rows = [json.loads(l) for l in open(base)]
seen = {r["text"] for r in rows}
added = Counter()
with open(out, "w") as f:
    for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for l in open(pairs):
        r = json.loads(l)
        if r["text"] in seen or not r["teacher"].get("duvod") or (r["verdict"] == "scam" and not r["teacher"].get("rada")): continue
        seen.add(r["text"])
        r.pop("principle")
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
        added[r["verdict"]] += 1
print(len(rows), "base +", dict(added))
