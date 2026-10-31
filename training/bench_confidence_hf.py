"""Confidence benchmark for verifier candidates with transformers on a GPU.

Same prompt as bench_confidence.py (few-shot, answer prefilled up to the verdict), but runs the original HF
checkpoints, so the numbers are the baseline for the LoRA fine-tunes of the same weights. A model given as
"name=adapter_dir" (LoRA) or a local model folder (full fine-tune) is a fine-tune: it gets the training prompt of
train_verifier.py, without the examples.
"""
import argparse
import json
import time
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from bench_confidence import PREFIX, summary
from bench_verifier import SHOTS, SYSTEM_EN

VERDICTS = ["podvod", "bezne", "nevim"]
MIN_FREE_GB = 20


def free_gb() -> float:
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable"):
            return int(line.split()[1]) / 1048576
    return 0.0


def prompt_for(tokenizer, text: str, shots: bool = True) -> str:
    messages = [{"role": "system", "content": SYSTEM_EN}]
    for shot, answer in SHOTS if shots else []:
        messages += [{"role": "user", "content": shot}, {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)}]
    messages.append({"role": "user", "content": text})
    rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    return rendered + PREFIX


def verdict_token_ids(tokenizer, shots: bool) -> list:
    """First token of each verdict when it follows the prefilled prefix."""
    prompt = prompt_for(tokenizer, "x", shots)
    base = tokenizer(prompt, add_special_tokens=False).input_ids
    ids = []
    for verdict in VERDICTS:
        full = tokenizer(prompt + verdict, add_special_tokens=False).input_ids
        assert full[:len(base)] == base, "prefix tokenisation changed"
        ids.append(full[len(base)])
    assert len(set(ids)) == 3, ids
    return ids


def run_model(spec: str, rows: list) -> list:
    assert free_gb() > MIN_FREE_GB, f"only {free_gb():.0f} GB of RAM free"
    name, _, adapter = spec.partition("=")
    tokenizer = AutoTokenizer.from_pretrained(name)
    model = AutoModelForCausalLM.from_pretrained(name, dtype=torch.bfloat16, device_map="cuda")
    if adapter:
        model = PeftModel.from_pretrained(model, adapter)
    model.eval()
    shots = not adapter and not Path(name).is_dir()
    ids = verdict_token_ids(tokenizer, shots)
    results = []
    for row in rows:
        inputs = tokenizer(prompt_for(tokenizer, row["text"][:1500], shots), add_special_tokens=False, return_tensors="pt").to("cuda")
        start = time.perf_counter()
        with torch.no_grad():
            logits = model(**inputs, logits_to_keep=1).logits[0, -1].float()
        probs = torch.softmax(logits[ids], dim=0).tolist()
        # log-odds of "podvod" against the other two; unlike the probability it does not saturate at 1.0
        margin = (logits[ids[0]] - torch.logsumexp(logits[ids[1:]], dim=0)).item()
        results.append({"id": row["id"], "hint": row["hint"], "source": row["source"], **dict(zip(VERDICTS, probs)), "margin": margin,
                        "mass": torch.softmax(logits, dim=0)[ids].sum().item(),
                        "seconds": round(time.perf_counter() - start, 3), "rss_gb": 0.0})
    del model
    torch.cuda.empty_cache()
    return results


def main(args: argparse.Namespace) -> None:
    rows = [json.loads(line) for path in args.bench for line in open(path)]
    rows = list({r["id"]: r for r in rows}.values())
    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)
    for name in args.models:
        results = run_model(name, rows)
        base, _, adapter = name.partition("=")
        stem = Path(adapter or base).parent.name if adapter or Path(base).is_dir() else base.replace("/", "--")
        with open(out_dir / f"{stem}.jsonl", "w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
        mass = sorted(r["mass"] for r in results)[len(results) // 2]
        print(summary(name, results, "margin"), f"\n  median probability mass on the three verdicts {mass:.2f}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--bench", nargs="+", required=True)
    parser.add_argument("--models", nargs="+", required=True)
    main(parser.parse_args())
