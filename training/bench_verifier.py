"""Compare small local LLMs as the verifier: speed, RAM and zero-shot accuracy on real Czech texts.

Starts llama-server for each GGUF in turn, sends every benchmark row, records verdict and timing.
"""
import argparse
import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path

SYSTEM = """Jsi opatrný kontrolor podvodů pro starší lidi. Posoudíš jednu zprávu (e-mail, SMS, chat nebo text z webu).
Podvod = odesílatel se klamem snaží získat peníze, přihlašovací údaje, data karty, osobní údaje nebo přístup k zařízení.
Běžná reklama, newslettery, skutečná oznámení a články O podvodech nejsou podvod.
Když informace nestačí, odpověz "nevim".
Odpověz jen jedním řádkem JSON bez dalšího textu:
{"verdikt": "podvod"|"bezne"|"nevim", "duvod": "<jedna krátká česká věta pro seniora: co konkrétně je podezřelé, nebo proč je zpráva v pořádku>"}"""
SYSTEM_EN = """You check messages for scams on behalf of elderly Czech users. You get one message (e-mail, SMS, chat or web text), usually in Czech.
Scam = the sender uses deception to get money, login details, card data, personal data or access to a device.
Ordinary advertising, newsletters, genuine notifications, personal messages and articles ABOUT scams are not scams.
If the message is too short or vague to judge, answer "nevim".
Answer with JSON only. "duvod" is one short, plain Czech sentence for a senior: what exactly is suspicious, or why the message is fine."""

# Invented examples, not taken from any evaluation set.
SHOTS = [
    ("Dobrý den, Vaše zásilka čeká na doručení. Doplaťte 28 Kč za clo zde: http://posta-cz.doruceni-info.top",
     {"verdikt": "podvod", "duvod": "Pošta nežádá doplatky přes neznámý odkaz; jde o falešnou stránku, která chce data vaší karty."}),
    ("Ahoj, v sobotu jdeme s dětmi do zoo, přidáte se? Sraz v 10 u vchodu.",
     {"verdikt": "bezne", "duvod": "Běžná soukromá zpráva, nikdo po vás nechce peníze ani údaje."}),
    ("Jsi tam?",
     {"verdikt": "nevim", "duvod": "Ze zprávy zatím nejde poznat, co odesílatel chce."}),
]

SCHEMA = {"type": "object", "properties": {"verdikt": {"type": "string", "enum": ["podvod", "bezne", "nevim"]},
                                           "duvod": {"type": "string"}},
          "required": ["verdikt", "duvod"]}

# Sampling recommended on each model card (non-thinking, text tasks).
PRESETS = {
    "qwen3.5": {"temperature": 1.0, "top_p": 1.0, "top_k": 20, "min_p": 0.0, "presence_penalty": 2.0},
    "granite": {"temperature": 1.0, "top_p": 0.95},
    "lfm2.5": {"temperature": 0.1, "top_k": 50, "repeat_penalty": 1.05},
    "gemma": {"temperature": 1.0, "top_p": 0.95, "top_k": 64},
}
PORT = 18951


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=300))


def rss_gb(pid: int) -> float:
    for line in open(f"/proc/{pid}/status"):
        if line.startswith("VmRSS"):
            return int(line.split()[1]) / 1048576
    return 0.0


def request_body(text: str, gguf: Path, fair: bool) -> dict:
    if not fair:
        return {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}],
                "temperature": 0, "max_tokens": 150, "chat_template_kwargs": {"enable_thinking": False}}
    messages = [{"role": "system", "content": SYSTEM_EN}]
    for shot, answer in SHOTS:
        messages += [{"role": "user", "content": shot}, {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)}]
    messages.append({"role": "user", "content": text})
    preset = next(v for k, v in PRESETS.items() if k in gguf.name.lower())
    return {"messages": messages, "max_tokens": 150, "seed": 1, "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema", "json_schema": {"name": "verdict", "schema": SCHEMA}}, **preset}


def run_model(server: str, gguf: Path, rows: list, threads: int, extra: list, fair: bool) -> list:
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
        body = request_body(row["text"][:1500], gguf, fair)
        start = time.perf_counter()
        out = post("/v1/chat/completions", body)
        seconds = time.perf_counter() - start
        text = out["choices"][0]["message"]["content"] or ""
        match = re.search(r'"verdikt"\s*:\s*"(\w+)"', text)
        reason = re.search(r'"duvod"\s*:\s*"([^"]*)', text)
        results.append({"id": row["id"], "hint": row["hint"], "source": row["source"],
                        "verdict": match.group(1) if match else "unparsed", "reason": reason.group(1) if reason else text[:200],
                        "seconds": round(seconds, 2), "out_tokens": out["usage"]["completion_tokens"]})
    rss = rss_gb(proc.pid)
    proc.terminate()
    proc.wait()
    for r in results:
        r["rss_gb"] = round(rss, 2)
    return results


def summary(name: str, results: list) -> str:
    scams = [r for r in results if r["hint"] == "scam"]
    ordinary = [r for r in results if r["hint"] == "ordinary"]
    caught = sum(r["verdict"] == "podvod" for r in scams)
    alarms = sum(r["verdict"] == "podvod" for r in ordinary)
    unparsed = sum(r["verdict"] == "unparsed" for r in results)
    secs = sorted(r["seconds"] for r in results)
    return (f"{name:42s} scams caught {caught}/{len(scams)}  false alarms {alarms}/{len(ordinary)}  "
            f"unparsed {unparsed}  median {secs[len(secs) // 2]:.1f}s  max {secs[-1]:.1f}s  RSS {results[0]['rss_gb']:.1f} GB")


def main(args: argparse.Namespace) -> None:
    rows = [json.loads(line) for line in open(args.bench)]
    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)
    for gguf in args.models:
        gguf = Path(gguf)
        results = run_model(args.server, gguf, rows[:args.limit], args.threads, args.extra.split(), args.fair)
        with open(out_dir / f"{gguf.stem}.jsonl", "w") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(summary(gguf.stem, results), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("bench")
    parser.add_argument("out")
    parser.add_argument("models", nargs="+")
    parser.add_argument("--server", required=True)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--fair", action="store_true",
                        help="vendor sampling, few-shot English instructions, JSON schema output")
    parser.add_argument("--extra", default="", help="extra llama-server flags, e.g. '-np 1 --cache-ram 0'")
    main(parser.parse_args())
