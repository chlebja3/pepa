"""Score held-out e-mails (add_synthetic_mail.py eval output) the way the extension does: highest chunk margin.

Prints, for each screener run, the share of legitimate e-mails flagged and of scam e-mails caught at the given
thresholds. Thresholds come from the dev half (tradeoff.py), never from these e-mails.

  score_mail.py mail-eval.jsonl ../runs/scr-e5-w3/model:-6.936:-2.93 ../runs/scr-e5-mail/model:<route>:<alarm>
"""
import argparse
import json

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

CHUNK, STEP = 1000, 800  # as in screener.py


@torch.no_grad()
def margin(model, tokenizer, text: str) -> float:
    chunks = [text[i:i + CHUNK] for i in range(0, max(1, len(text) - CHUNK + STEP), STEP)]
    batch = tokenizer(chunks, truncation=True, max_length=384, padding=True, return_tensors="pt").to("cuda")
    logits = model(**batch).logits.float()
    return (logits[:, 0] - torch.logsumexp(logits[:, 1:], dim=-1)).max().item()


def main(args: argparse.Namespace) -> None:
    rows = [json.loads(line) for line in open(args.data)]
    for spec in args.runs:
        path, route, alarm = spec.rsplit(":", 2)
        tokenizer = AutoTokenizer.from_pretrained(path)
        model = AutoModelForSequenceClassification.from_pretrained(path).cuda().eval()
        scores = [(r["verdict"], margin(model, tokenizer, r["text"])) for r in rows]
        line = [path]
        for verdict in ("ordinary", "scam"):
            s = [m for v, m in scores if v == verdict]
            line.append(f"{verdict} n={len(s)} routed {sum(m >= float(route) for m in s) / len(s):.1%}"
                        f" alarm {sum(m >= float(alarm) for m in s) / len(s):.1%}")
        print(" | ".join(line), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data")
    parser.add_argument("runs", nargs="+", help="model_folder:route_threshold:alarm_threshold")
    main(parser.parse_args())
