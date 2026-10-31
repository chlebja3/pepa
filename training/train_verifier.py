"""Fine-tune a small verifier LLM (Qwen3.5-2B or Gemma 4 E2B) on teacher-labelled Czech texts, LoRA or full.

Input rows: {"text", "verdict": scam|ordinary|insufficient, "duvod"}. The model learns to answer the system prompt
with {"verdikt": ..., "duvod": ...}; scam rows with a teacher "rada" (what to do now, fitted to the situation) add it
as a third key. Loss is on the answer tokens only. Optional general Czech chat rows
({"messages": [...]}, loss on the last answer) are mixed in so the model does not forget how to write Czech.
Training stops and saves when free RAM drops below a limit (--min-free-gb), so other processes on the machine are
never pushed into OOM.
Text read from screenshots carries OCR errors (lost diacritics, confused letters, broken words); --noise corrupts a
share of the training texts the same way so the model does not rely on clean spelling.
A missed scam costs more than a false alarm, so --scam-repeat shows scam rows more often to move the model towards
recall.
"""
import argparse
import json
import os
import random

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainerCallback, TrainingArguments

from bench_verifier import SYSTEM_EN

VERDIKT = {"scam": "podvod", "ordinary": "bezne", "insufficient": "nevim"}
PLAIN = str.maketrans("áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ", "acdeeinorstuuyzACDEEINORSTUUYZ")
LOOKALIKE = {"o": "0", "l": "1", "i": "l", "e": "c", "a": "s", "m": "rn", "n": "r", "u": "v", "s": "5", "B": "8", "O": "0"}


def ocr_noise(text: str, rng: random.Random) -> str:
    """Corrupt text like a poor OCR pass: drop diacritics, swap look-alike letters, lose or merge characters."""
    if rng.random() < 0.3:
        text = text.translate(PLAIN)
    rate = rng.uniform(0.01, 0.06)
    out = []
    for ch in text:
        roll = rng.random()
        if roll < rate / 3:
            continue
        if roll < 2 * rate / 3:
            out.append(LOOKALIKE.get(ch, ch))
        elif roll < rate and ch.isalpha():
            out.append(ch.translate(PLAIN) + rng.choice(["", " ", "."]))
        else:
            out.append(ch)
    return "".join(out)


def free_gb() -> float:
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable"):
            return int(line.split()[1]) / 1048576
    return 0.0


class MemoryGuard(TrainerCallback):
    def __init__(self, min_free_gb: float):
        self.min_free_gb = min_free_gb

    def on_step_end(self, args, state, control, **kwargs):
        if free_gb() < self.min_free_gb:
            print(f"free RAM {free_gb():.1f} GB < {self.min_free_gb} GB, saving and stopping", flush=True)
            control.should_save = True
            control.should_training_stop = True
        return control


def encode(tokenizer, row: dict, max_len: int) -> dict:
    messages = [{"role": "system", "content": SYSTEM_EN}, {"role": "user", "content": row["text"]}]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    answer = {"verdikt": VERDIKT[row["verdict"]], "duvod": row["duvod"]}
    if row["verdict"] == "scam" and row.get("rada"):
        answer["rada"] = row["rada"]
    answer = json.dumps(answer, ensure_ascii=False)
    prompt_ids = tokenizer(prompt, add_special_tokens=False).input_ids
    answer_ids = tokenizer(answer + tokenizer.eos_token, add_special_tokens=False).input_ids
    prompt_ids = prompt_ids[:max_len - len(answer_ids)]
    return {"input_ids": prompt_ids + answer_ids, "labels": [-100] * len(prompt_ids) + answer_ids}


def encode_chat(tokenizer, row: dict, max_len: int) -> dict:
    messages = row["messages"]
    prompt = tokenizer.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True, enable_thinking=False)
    prompt_ids = tokenizer(prompt, add_special_tokens=False).input_ids
    answer_ids = tokenizer(messages[-1]["content"] + tokenizer.eos_token, add_special_tokens=False).input_ids[:max_len // 2]
    prompt_ids = prompt_ids[-(max_len - len(answer_ids)):]
    return {"input_ids": prompt_ids + answer_ids, "labels": [-100] * len(prompt_ids) + answer_ids}


def collate(batch: list, pad_id: int) -> dict:
    width = max(len(b["input_ids"]) for b in batch)
    ids = torch.full((len(batch), width), pad_id)
    labels = torch.full((len(batch), width), -100)
    mask = torch.zeros((len(batch), width), dtype=torch.long)
    for i, b in enumerate(batch):
        n = len(b["input_ids"])
        ids[i, :n] = torch.tensor(b["input_ids"])
        labels[i, :n] = torch.tensor(b["labels"])
        mask[i, :n] = 1
    return {"input_ids": ids, "labels": labels, "attention_mask": mask}


def main(args: argparse.Namespace) -> None:
    assert free_gb() > args.min_free_gb + 15, f"only {free_gb():.0f} GB of RAM free"
    rows = [json.loads(line) for line in open(args.data)]
    # explain mode (teacher.py) stores the reason under "teacher"
    rows = [{**r, "duvod": r.get("duvod") or (r.get("teacher") or {}).get("duvod"),
             "rada": r.get("rada") or (r.get("teacher") or {}).get("rada")} for r in rows]
    rows = [r for r in rows if r["duvod"] and r["source"].split(":")[0] not in args.exclude]
    noise_rng = random.Random(9)
    rows = [{**r, "text": ocr_noise(r["text"], noise_rng)} if noise_rng.random() < args.noise else r for r in rows]
    random.Random(7).shuffle(rows)
    n_val = max(50, len(rows) // 50)
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    extra = [r for r in rows[n_val:] if r["verdict"] == "scam"]
    extra = extra * int(args.scam_repeat - 1) + extra[:int(len(extra) * ((args.scam_repeat - 1) % 1))]
    train = [encode(tokenizer, r, args.max_len) for r in rows[n_val:] + extra]
    val = [encode(tokenizer, r, args.max_len) for r in rows[:n_val]]
    if args.mix:
        general = [json.loads(line) for line in open(args.mix)]
        random.Random(7).shuffle(general)
        n_mix = int(args.mix_share * len(train) / (1 - args.mix_share))
        train += [encode_chat(tokenizer, r, args.max_len) for r in general[:n_mix]]
        random.Random(8).shuffle(train)
    print(f"train {len(train)} val {len(val)}", flush=True)

    # full fine-tuning keeps fp32 master weights (bf16 autocast); LoRA trains adapters on frozen bf16 weights
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.float32 if args.full else torch.bfloat16,
                                                 device_map={"": int(os.environ.get("LOCAL_RANK", 0))})
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    if not args.full:
        lora = LoraConfig(r=args.rank, lora_alpha=2 * args.rank, lora_dropout=0.05, task_type="CAUSAL_LM",
                          target_modules="all-linear", exclude_modules=r".*(vision|audio|visual).*")
        model = get_peft_model(model, lora)
        model.print_trainable_parameters()

    training_args = TrainingArguments(
        output_dir=args.out, per_device_train_batch_size=args.batch, per_device_eval_batch_size=args.batch,
        gradient_accumulation_steps=args.accum, learning_rate=args.lr, num_train_epochs=args.epochs,
        lr_scheduler_type="cosine", warmup_steps=0.03, bf16=True, logging_steps=20, eval_strategy="steps",
        eval_steps=200, save_steps=200, save_total_limit=2, load_best_model_at_end=args.best,
        metric_for_best_model="eval_loss", report_to=[], dataloader_num_workers=0,
        train_sampling_strategy="group_by_length", remove_unused_columns=False, optim=args.optim, ddp_find_unused_parameters=False, weight_decay=0.01 if args.full else 0.0)
    trainer = Trainer(model=model, args=training_args, train_dataset=train, eval_dataset=val,
                      data_collator=lambda batch: collate(batch, tokenizer.pad_token_id),
                      callbacks=[MemoryGuard(args.min_free_gb)])
    trainer.train()
    final = f"{args.out}/{'model' if args.full else 'adapter'}"
    model.save_pretrained(final)
    tokenizer.save_pretrained(final)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data")
    parser.add_argument("out")
    parser.add_argument("--model", required=True)
    parser.add_argument("--full", action="store_true", help="full fine-tuning instead of LoRA (use --lr 1e-5)")
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--mix", help="general Czech chat rows {messages} mixed in against forgetting")
    parser.add_argument("--mix-share", type=float, default=0.15)
    parser.add_argument("--epochs", type=float, default=2)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--accum", type=int, default=2)
    parser.add_argument("--max-len", type=int, default=1024)
    parser.add_argument("--optim", default="adamw_torch_fused", help="adamw_bnb_8bit for full fine-tuning on 40 GB")
    parser.add_argument("--noise", type=float, default=0.0, help="share of training texts given OCR-like errors")
    parser.add_argument("--scam-repeat", type=float, default=1.0, help="how many times each scam row is seen per epoch")
    parser.add_argument("--exclude", nargs="*", default=[], help="training sources to leave out")
    parser.add_argument("--min-free-gb", type=float, default=15)
    parser.add_argument("--best", action="store_true", help="save the checkpoint with the lowest validation loss")
    main(parser.parse_args())
