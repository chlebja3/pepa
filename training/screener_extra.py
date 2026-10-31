"""Screener data of scr-e5-fp: train-web.jsonl plus the fragment and pair rows that are in neither base file.

  screener_extra.py train-web.jsonl train-explained.jsonl train-explained-frag-gram-pair.jsonl train-web-fp.jsonl
"""
import json
import sys
from collections import Counter

web_path, base_path, extended_path, out = sys.argv[1:5]
web = [json.loads(l) for l in open(web_path)]
seen = {r["id"] for r in web} | {json.loads(l)["id"] for l in open(base_path)}
extra = [r for r in map(json.loads, open(extended_path))
         if r["id"] not in seen and r["verdict"] in ("scam", "ordinary", "insufficient")]
with open(out, "w") as f:
    for r in web + extra: f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(len(web), "+", len(extra), dict(Counter(r["verdict"] for r in extra)))
