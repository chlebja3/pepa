"""Route (dev recall RECALL, default 95 %; scr-e5-fp uses 0.97) and alarm (at most 1 % of dev ordinary rows above it) thresholds of screener runs."""
import os
import sys
from pathlib import Path

from tradeoff import load, pick_recall

for name in sys.argv[1:]:
    rows = load(Path("../runs/screen-dev") / f"{name}.jsonl")
    ordinary = sorted(r["margin"] for r in rows if r["hint"] == "ordinary")
    alarm = ordinary[int(len(ordinary) * 0.99)]
    print(name, "route", round(pick_recall(rows, float(os.environ.get("RECALL", 0.95))), 3), "alarm", round(alarm, 3), "n_ord", len(ordinary))
