"""Score the verifier by its probability of "podvod" instead of a generated verdict.

The prompt ends with the start of the JSON answer, so one forward pass gives the probabilities of the
three verdicts. Reports recall at fixed false-alarm rates so models are compared at the same threshold.
"""
import argparse
import json
import math
import subprocess
import time
import urllib.request
from pathlib import Path

from bench_verifier import PORT, SHOTS, SYSTEM_EN, rss_gb

PREFIX = '{"verdikt": "'
VERDICTS = {"p": "podvod", "b": "bezne", "n": "nevim"}


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=300))


def prompt_for(text: str) -> str:
    messages = [{"role": "system", "content": SYSTEM_EN}]
    for shot, answer in SHOTS:
        messages += [{"role": "user", "content": shot}, {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)}]
    messages.append({"role": "user", "content": text})
    rendered = post("/apply-template", {"messages": messages, "chat_template_kwargs": {"enable_thinking": False}})["prompt"]
    return rendered + PREFIX


def verdict_probs(prompt: str) -> dict:
    out = post("/completion", {"prompt": prompt, "n_predict": 1, "n_probs": 20, "temperature": 0, "cache_prompt": True})
    probs = {v: 0.0 for v in VERDICTS.values()}
    candidates = out["completion_probabilities"][0]["top_logprobs"]
    for cand in candidates:
        token = cand["token"].strip().lower()
        if token and token[0] in VERDICTS and VERDICTS[token[0]].startswith(token):
            probs[VERDICTS[token[0]]] += math.exp(cand["logprob"])
    # a verdict missing from the top list is at most as likely as the last listed token
    floor = math.exp(min(c["logprob"] for c in candidates))
    raw = {k: max(v, floor) for k, v in probs.items()}
    margin = math.log(raw["podvod"]) - math.log(raw["bezne"] + raw["nevim"])
    total = sum(probs.values()) or 1.0
    return {**{k: v / total for k, v in probs.items()}, "margin": margin}


def run_model(server: str, gguf: Path, rows: list, threads: int, extra: list) -> list:
    proc = subprocess.Popen([server, "-m", str(gguf), "-c", "4096", "-t", str(threads), "--port", str(PORT),
                             "--no-webui", *extra], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    while True:
        try:
            if urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health").status == 200:
                break
        except OSError:
            time.sleep(0.5)
    results = []
    for row in rows:
        prompt = prompt_for(row["text"][:1500])
        start = time.perf_counter()
        probs = verdict_probs(prompt)
        results.append({"id": row["id"], "hint": row["hint"], "source": row["source"], **probs,
                        "seconds": round(time.perf_counter() - start, 2)})
    rss = rss_gb(proc.pid)
    proc.terminate()
    proc.wait()
    for r in results:
        r["rss_gb"] = round(rss, 2)
    return results


def summary(name: str, results: list, key: str = "podvod") -> str:
    scams = sorted((r[key] for r in results if r["hint"] == "scam"), reverse=True)
    ordinary = sorted((r[key] for r in results if r["hint"] == "ordinary"), reverse=True)
    lines = [f"{name}: median {sorted(r['seconds'] for r in results)[len(results) // 2]:.1f}s  RSS {results[0]['rss_gb']:.1f} GB"]
    for alarms in (0, 2, 5, 10):
        threshold = ordinary[alarms] if alarms < len(ordinary) else 0.0
        caught = sum(s > threshold for s in scams)
        lines.append(f"  false alarms {alarms}/{len(ordinary)} -> scams caught {caught}/{len(scams)} (threshold {threshold:.3f})")
    return "\n".join(lines)


def main(args: argparse.Namespace) -> None:
    rows = [json.loads(line) for line in open(args.bench)]
    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)
    for gguf in map(Path, args.models):
        results = run_model(args.server, gguf, rows[:args.limit], args.threads, args.extra.split())
        with open(out_dir / f"{gguf.stem}.jsonl", "w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
        print(summary(gguf.stem, results, "margin"), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("bench")
    parser.add_argument("out")
    parser.add_argument("models", nargs="+")
    parser.add_argument("--server", required=True)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--extra", default="-np 1 --cache-ram 0")
    main(parser.parse_args())
