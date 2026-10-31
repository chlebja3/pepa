"""Add synthetic everyday e-mails (synthetic_specs.py --emails, teacher.py generate + blind label) to screener data.

Only messages whose blind label equals the intended verdict are kept. The screener scores a long e-mail chunk by chunk
(screener.py) and keeps the highest chunk, so a footer full of links alone can raise an alarm; every chunk of a
legitimate e-mail is therefore added as an ordinary row too. Scam e-mails are added whole only, because a single
chunk of a scam (a footer, a greeting) need not be a scam.

  train: add_synthetic_mail.py train-explained.jsonl mail-labelled-train.jsonl train-mail.jsonl
  eval:  add_synthetic_mail.py - mail-labelled-eval.jsonl mail-eval.jsonl
"""
import argparse
import json
from collections import Counter

CHUNK, STEP = 1000, 800  # as in screener.py


def kept(path: str) -> list:
    rows = []
    for line in open(path):
        r = json.loads(line)
        if r["teacher"].get("usable", True) and r["teacher"]["verdict"] == r["hint"]:
            rows.append({"id": r["id"], "text": r["text"], "source": "synthetic-mail", "style": None, "hint": r["hint"],
                         "verdict": r["hint"], "category": r["teacher"].get("category"),
                         "flags": r["teacher"].get("flags", []), "enron": False, "teacher": {}})
    return rows


def main(args: argparse.Namespace) -> None:
    mail = kept(args.labelled)
    out = [json.loads(line) for line in open(args.base)] if args.base != "-" else []
    added = Counter()
    for r in mail:
        out.append(r)
        added[r["verdict"]] += 1
        if args.base != "-" and r["verdict"] == "ordinary" and len(r["text"]) > CHUNK:
            for n, i in enumerate(range(0, len(r["text"]) - CHUNK + STEP, STEP)):
                out.append({**r, "id": f"{r['id']}-c{n}", "text": r["text"][i:i + CHUNK]})
                added["ordinary chunk"] += 1
    with open(args.out, "w") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"kept {len(mail)} e-mails; added {dict(added)}; wrote {len(out)} rows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("base", help="existing training rows, or - for an eval file of the e-mails alone")
    parser.add_argument("labelled", help="teacher.py --mode label output on the generated e-mails")
    parser.add_argument("out")
    main(parser.parse_args())
