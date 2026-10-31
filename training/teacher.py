"""Label and translate texts with a local teacher LLM (OpenAI-compatible endpoint, e.g. vLLM).

Input JSONL rows: {"id", "text", "source", "hint"} (generate mode: synthetic_specs.py rows); output rows add the
teacher's JSON.
Resumable: ids already present in the output are skipped.
"""
import argparse
import json
import os
import random
import re
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

CATEGORIES = ["credentials", "bank_transfer", "marketplace", "parcel", "investment", "family",
              "romance", "advance_fee", "remote_access", "extortion", "account_phishing", "other"]
FLAGS = ["urgency", "threat", "impersonation", "credential_request", "personal_data_request",
         "payment_request", "upfront_fee", "unusual_payment", "suspicious_link", "too_good_to_be_true",
         "secrecy", "remote_access_app", "new_contact_number", "move_to_other_channel"]

LABEL_RULES = f"""Decide what the text is for the person who receives or reads it.
verdict:
- "scam": the sender tries to deceive the reader to get money, login details, card data, personal data,
  or control of a device (phishing, fake fees, fake bank or police, advance-fee, fake investment,
  romance or family impersonation, sextortion, fake job tasks, fake prizes).
- "ordinary": anything else, including legitimate notifications, invoices, newsletters, advertising
  and marketing spam (unwanted but not deceptive), personal and work messages, articles or warnings
  ABOUT scams, and discussions.
- "insufficient": too short or too vague to tell, e.g. a bare greeting or "are you there?".
category (only for scam): one of {CATEGORIES}; otherwise null.
flags (only red flags actually present in the text): subset of {FLAGS}.
usable: false if the text is garbled, mostly random words, or mostly non-language (only a URL, code)."""

LABEL_TRANSLATE = LABEL_RULES + """

Then translate the text into Czech. {style}
Keep the structure, line breaks, links, numbers and typos-level tone (formal stays formal, sloppy stays sloppy).
Do not add warnings or comments. Do not translate URLs.

Return only JSON: {{"verdict": ..., "category": ..., "flags": [...], "usable": true|false, "cs": "<Czech text>"}}

TEXT:
{text}"""

LABEL_ONLY = LABEL_RULES + """

Return only JSON: {{"verdict": ..., "category": ..., "flags": [...], "usable": true|false}}

TEXT:
{text}"""

EXPLAIN = """You write the one-sentence explanation shown to an elderly Czech user by a scam warning tool.
The message below was already judged: verdict "{verdict}", red flags {flags}.
Write "duvod": one short, plain Czech sentence (max 25 words) for a senior.
- For "scam": name the concrete suspicious thing in THIS message (what they ask for, the fake sender, the link, the pressure),
  not generic advice. No technical words such as phishing, URL or doména.
- For "ordinary": say briefly why the message is fine (what it is and that it asks for nothing risky).
- For "insufficient": say that the message does not yet show what the sender wants.
Correct Czech with diacritics, polite form (vy), no exclamation marks.

Return only JSON: {{"duvod": "<Czech sentence>"}}

MESSAGE:
{text}"""

ADVISE = """You write the advice line of a scam warning shown to an elderly Czech user.
The message below was judged a scam. Why: "{duvod}"
Write "rada": what THIS person should do now about THIS particular message, in one or two short, plain Czech
sentences (max 30 words). Fit it to the situation, for example:
- someone claiming to be a relative wants money: call that relative on the number you already know;
- a bank, office or shop asks to log in, pay or confirm data: open their app or website yourself, or call the number
  printed on your card or contract;
- a caller or message wants remote access to the computer: do not install anything, end the conversation;
- a parcel needs a small fee: check the parcel in the carrier's app or website that you open yourself;
- an investment or prize promises easy money: do not send anything, nobody gives money away like this;
- if the person may have already given card data or a password: call your bank right away and block the card.
Never invent phone numbers, web addresses or company names. No technical words such as phishing, URL or doména.
Do not repeat the reason. Use simple everyday Czech words and start with a polite imperative verb, for example
Neklikejte, Nic neplaťte, Zavolejte, Ověřte si, Otevřete, Ukončete, Smažte. Check the grammar of every word.
Correct Czech with diacritics, polite form (vy), no exclamation marks.

Return only JSON: {{"rada": "<Czech advice>"}}

MESSAGE:
{text}"""

GENERATE = """Write one realistic Czech message as it would really arrive to an older person in the Czech Republic.
Channel: {channel}. Length: {length}. Tone: {tone}.
Situation: {scenario}.
{guide}
If a company fits the situation, it is {brand}; otherwise ignore the brand.
Make it look like the real thing (sender line, Czech names, dates, amounts in Kč where they fit). Do not say that it
is a scam or an example, and add no comments.

Return only JSON: {{"text": "<the message>"}}"""

CHAT = """Below is a Czech web text. Write one {task} that an ordinary Czech person could ask an assistant about it,
then the assistant's helpful answer. Both in natural, correct Czech with diacritics; the question includes the
text or the part of it the task needs. The answer is clear and plain, without English words.

Return only JSON: {{"question": "<user message>", "answer": "<assistant answer>"}}

TEXT:
{text}"""
CHAT_TASKS = ["request to summarise it in a few sentences", "question about a detail in it",
              "request to explain it simply to an older person", "request to write a short reply or e-mail based on it",
              "request to rewrite it more politely or more clearly", "practical question related to its topic"]

STYLES = {
    "natural": "Write natural, fluent Czech.",
    "local": "Write natural Czech and adapt it to the Czech Republic: Czech companies and institutions "
             "instead of foreign ones (e.g. Česká pošta, PPL, Zásilkovna, ČEZ, Česká spořitelna, Finanční úřad), "
             "Kč instead of foreign currency, Czech phone numbers and names.",
    "literal": "Translate literally, word by word, like a cheap machine translator would; slightly unnatural Czech is expected.",
}


def call(url: str, model: str, prompt: str, max_tokens: int, temperature: float) -> str:
    body = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=600))["choices"][0]["message"]["content"]


def parse(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.S)
    return json.loads(match.group(0))


def main(args: argparse.Namespace) -> None:
    done = set()
    try:
        with open(args.output) as f:
            done = {json.loads(line)["id"] for line in f}
    except FileNotFoundError:
        pass
    rows = [json.loads(line) for line in open(args.input)]
    rows = [r for r in rows if r["id"] not in done]
    print(f"{len(done)} done, {len(rows)} to go", flush=True)
    lock = threading.Lock()
    out = open(args.output, "a")
    counter = {"ok": 0, "bad": 0}

    def work(row: dict) -> None:
        rng = random.Random(row["id"])
        style = rng.choices(list(STYLES), weights=[0.35, 0.4, 0.25])[0]
        if args.mode == "translate":
            prompt = LABEL_TRANSLATE.format(style=STYLES[style], text=row["text"][:args.max_chars])
        elif args.mode == "generate":
            prompt = GENERATE.format(**row)
        elif args.mode == "chat":
            prompt = CHAT.format(task=rng.choice(CHAT_TASKS), text=row["text"][:args.max_chars])
        elif args.mode == "advise":
            prompt = ADVISE.format(duvod=row["teacher"]["duvod"], text=row["text"][:args.max_chars])
        elif args.mode == "explain":
            prompt = EXPLAIN.format(verdict=row["verdict"], flags=row["flags"], text=row["text"][:args.max_chars])
            if row.get("principle"):  # contrastive pairs: the reason names the request and why its context is (not) normal
                prompt += ("\n\nThe point to make in the sentence: " + row["principle"] if row["verdict"] == "scam" else
                           "\n\nSay what the message asks and why that is normal here. (A scam version would differ: " + row["principle"] + ".)")
        else:
            prompt = LABEL_ONLY.format(text=row["text"][:args.max_chars])
        try:
            result = parse(call(args.url, args.model, prompt, args.max_tokens, args.temperature))
        except Exception as error:  # one bad generation must not stop a multi-hour run
            with lock:
                counter["bad"] += 1
            print("fail", row["id"], repr(error)[:120], flush=True)
            return
        record = {**row, "teacher": {**row["teacher"], **result} if args.mode == "advise" else result, "style": style if args.mode == "translate" else None}
        with lock:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            counter["ok"] += 1
            if counter["ok"] % 500 == 0:
                print(counter, flush=True)

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(work, rows))
    print("finished", counter, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--mode", choices=["translate", "label", "explain", "generate", "chat", "advise"], default="translate")
    parser.add_argument("--url", default=os.environ.get("TEACHER_BASE_URL", "http://localhost:8000/v1") + "/chat/completions",
                        help="chat completions endpoint of an OpenAI-compatible server (e.g. vLLM)")
    parser.add_argument("--model", default=os.environ.get("TEACHER_MODEL", "model"), help="served model name")
    parser.add_argument("--workers", type=int, default=48)
    parser.add_argument("--max-chars", type=int, default=2500)
    parser.add_argument("--max-tokens", type=int, default=2000)
    parser.add_argument("--temperature", type=float, default=0.2)
    main(parser.parse_args())
