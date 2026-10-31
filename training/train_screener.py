"""Fast screener (system 1): a small multilingual encoder classifies every text as scam / ordinary / not enough info.

It only decides what the verifier LLM sees, so it runs at high recall and its precision matters little. Trained on the
same teacher-labelled texts as the verifier (train-explained.jsonl; the shipped screener uses train-web.jsonl, which
adds synthetic e-mails, web pages and SMS, see pipeline.sh); --scam-weight raises the loss on scam rows to move
it towards recall, --noise gives a share of texts OCR-like errors as in train_verifier.py. After training it scores
the dev and test halves (split_exam.py) in the per-row format of tradeoff.py, margin = logit of scam against the other
two. --init starts the encoder from another checkpoint's "encoder.*" weights (e.g. an earlier classifier built on
mmBERT-base), so a previously trained model can be compared on the same data. --ascii strips diacritics from a
share of texts, as many Czech SMS and chat messages are written.
"""
import argparse
import json
import random
import unicodedata
from pathlib import Path

import torch
from safetensors.torch import load_file
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

from train_verifier import ocr_noise

LABELS = ["scam", "ordinary", "insufficient"]
VERDICTS = ["podvod", "bezne", "nevim"]


def strip_diacritics(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def batches(rows: list, size: int) -> list:
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def encode(tokenizer, texts: list, max_len: int) -> dict:
    return tokenizer(texts, truncation=True, max_length=max_len, padding=True, return_tensors="pt").to("cuda")


@torch.no_grad()
def score(model, tokenizer, rows: list, max_len: int) -> list:
    model.eval()
    out = []
    for chunk in batches(rows, 128):
        logits = model(**encode(tokenizer, [r["text"] for r in chunk], max_len)).logits.float()
        probs = logits.softmax(-1)
        margins = logits[:, 0] - torch.logsumexp(logits[:, 1:], dim=-1)
        for r, p, m in zip(chunk, probs.tolist(), margins.tolist()):
            out.append({"id": r["id"], "hint": r["hint"], "source": r["source"], **dict(zip(VERDICTS, p)), "margin": m})
    model.train()
    return out


def main(args: argparse.Namespace) -> None:
    rows = [json.loads(line) for line in open(args.data)]
    rows = [r for r in rows if r["verdict"] in LABELS]
    rng = random.Random(9)
    rows = [{**r, "text": ocr_noise(r["text"], rng)} if rng.random() < args.noise else r for r in rows]
    rng = random.Random(11)
    rows = [{**r, "text": strip_diacritics(r["text"])} if rng.random() < args.ascii else r for r in rows]
    random.Random(7).shuffle(rows)
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSequenceClassification.from_pretrained(args.model, num_labels=3)
    if args.init:
        state = {k.removeprefix("encoder."): v for k, v in load_file(args.init).items() if k.startswith("encoder.")}
        model.base_model.load_state_dict(state, strict=True)
    model = model.cuda()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    steps = args.epochs * len(batches(rows, args.batch))
    schedule = get_linear_schedule_with_warmup(optimizer, int(0.06 * steps), steps)
    weight = torch.tensor([args.scam_weight, 1.0, 1.0], device="cuda")
    print(f"train {len(rows)} steps {steps}", flush=True)
    step = 0
    for epoch in range(args.epochs):
        random.Random(epoch).shuffle(rows)
        for chunk in batches(rows, args.batch):
            labels = torch.tensor([LABELS.index(r["verdict"]) for r in chunk], device="cuda")
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits = model(**encode(tokenizer, [r["text"] for r in chunk], args.max_len)).logits
            loss = torch.nn.functional.cross_entropy(logits.float(), labels, weight=weight)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            schedule.step()
            optimizer.zero_grad()
            step += 1
            if step % 200 == 0:
                print(f"epoch {epoch} step {step} loss {loss.item():.3f}", flush=True)
    out = Path(args.out)
    model.save_pretrained(out / "model")
    tokenizer.save_pretrained(out / "model")
    for split in ("dev", "test"):
        bench = [json.loads(line) for line in open(Path(args.bench) / f"{split}.jsonl")]
        result_dir = Path(args.results) / f"screen-{split}"
        result_dir.mkdir(parents=True, exist_ok=True)
        with open(result_dir / f"{out.name}.jsonl", "w") as f:
            for r in score(model, tokenizer, bench, args.max_len):
                f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data", help="train-explained.jsonl")
    parser.add_argument("out", help="run folder; its name names the result files")
    parser.add_argument("--model", required=True)
    parser.add_argument("--bench", default="devtest", help="folder with dev.jsonl and test.jsonl")
    parser.add_argument("--results", default="../runs")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--lr", type=float, default=5e-5)
    parser.add_argument("--max-len", type=int, default=384)
    parser.add_argument("--scam-weight", type=float, default=1.0, help="loss weight of scam rows (recall)")
    parser.add_argument("--init", help="safetensors whose encoder.* weights replace the --model encoder")
    parser.add_argument("--ascii", type=float, default=0.0, help="share of training texts without diacritics")
    parser.add_argument("--noise", type=float, default=0.0, help="share of training texts given OCR-like errors")
    main(parser.parse_args())
