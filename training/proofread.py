"""Proofread the Czech explanation (teacher.duvod) and advice (rada) sentences of a verifier training file.

Usage: proofread.py INPUT OUTPUT FIXES [--url ...] [--workers N] [--limit N]
Unique sentences are sent once; FIXES is a resumable JSONL cache {"src", "fixed"}. A fix is kept only when it is
a small edit of the original, so the meaning cannot drift. OUTPUT is INPUT with the fixed sentences.
"""
import argparse
import difflib
import json
import os
import re
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

PROMPT = """Jsi korektor češtiny. Oprav v této větě jen gramatické a pravopisné chyby: shodu rodu, čísla a pádu,
vazby sloves a předložek (například "k kliknutí" -> "ke kliknutí", "vás vyhrožuje" -> "vám vyhrožuje",
"je běžná dotaz" -> "je běžný dotaz"), neexistující slova nahraď správnými běžnými slovy. Neměň smysl,
tón ani délku, nepřidávej nové informace, zachovej vykání. Pokud je věta správně, vrať ji beze změny.

Vrať jen JSON: {{"opraveno": "<věta>"}}

VĚTA:
{text}"""


def call(url: str, model: str, prompt: str, think: bool) -> str:
    body = {"model": model, "max_tokens": 4000 if think else 300, "temperature": 0.0,
            "chat_template_kwargs": {"enable_thinking": think}, "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=600))["choices"][0]["message"]["content"]


def parse(raw: str) -> str:
    return json.loads(re.findall(r"\{[^{}]*\}", raw)[-1])["opraveno"].strip()


def sentences(row: dict) -> list[str]:
    return [s for s in (row["teacher"].get("duvod"), row.get("rada")) if isinstance(s, str) and s.strip()]


def main(args: argparse.Namespace) -> None:
    rows = [json.loads(line) for line in open(args.input)]
    fixes = {}
    try:
        with open(args.fixes) as f:
            for line in f:
                r = json.loads(line)
                fixes[r["src"]] = r["fixed"]
    except FileNotFoundError:
        pass
    todo = sorted({s for r in rows for s in sentences(r)} - set(fixes))[:args.limit]
    print(f"{len(fixes)} cached, {len(todo)} to go", flush=True)
    lock = threading.Lock()
    out = open(args.fixes, "a")

    def work(src: str) -> None:
        try:
            fixed = parse(call(args.url, args.model, PROMPT.format(text=src), args.think))
        except Exception as error:  # one bad generation must not stop the run; the sentence stays as is
            print("fail", repr(error)[:120], flush=True)
            return
        with lock:
            fixes[src] = fixed
            out.write(json.dumps({"src": src, "fixed": fixed}, ensure_ascii=False) + "\n")
            out.flush()
            if len(fixes) % 1000 == 0:
                print(len(fixes), flush=True)

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(work, todo))
    out.close()

    def apply(src: str) -> str:
        fixed = fixes.get(src, src)
        return fixed if fixed and difflib.SequenceMatcher(None, src, fixed).ratio() >= args.min_ratio else src

    changed = 0
    with open(args.output, "w") as f:
        for r in rows:
            new = {**r, "teacher": {**r["teacher"]}}
            if isinstance(r["teacher"].get("duvod"), str):
                new["teacher"]["duvod"] = apply(r["teacher"]["duvod"])
            if isinstance(r.get("rada"), str):
                new["rada"] = apply(r["rada"])
            changed += new != r
            f.write(json.dumps(new, ensure_ascii=False) + "\n")
    print(f"rows {len(rows)}, changed {changed}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("fixes")
    parser.add_argument("--url", default=os.environ.get("TEACHER_BASE_URL", "http://localhost:8000/v1") + "/chat/completions")
    parser.add_argument("--model", default=os.environ.get("TEACHER_MODEL", "model"))
    parser.add_argument("--workers", type=int, default=48)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--think", action="store_true", help="let the model reason before answering")
    parser.add_argument("--min-ratio", type=float, default=0.75)
    main(parser.parse_args())
