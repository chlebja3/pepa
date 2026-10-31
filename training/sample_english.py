"""Draw a balanced, deduplicated sample of English corpora for teacher labelling and translation."""
import argparse
import hashlib
import json
import random
import re

# file, text field, label field, {label value: hint}, how many per hint
PLAN = [
    ("ucirvine__sms_spam", "sms", "label", {1: "spam", 0: "ham"}, {"spam": 747, "ham": 1500}),
    ("mshenoda__spam-messages", "text", "label", {"spam": "spam", "ham": "ham"}, {"spam": 6000, "ham": 3500}),
    ("zefang-liu__phishing-email-dataset", "Email Text", "Email Type",
     {"Phishing Email": "phishing", "Safe Email": "ham"}, {"phishing": 4000, "ham": 2000}),
    ("SetFit__enron_spam", "text", "label", {1: "spam", 0: "ham"}, {"spam": 1500, "ham": 1500}),
    ("Deysi__spam-detection-dataset", "text", "label", {"spam": "spam", "not_spam": "ham"}, {"spam": 2000, "ham": 2000}),
    ("cybersectony__PhishingEmailDetectionv2.0", "content", "label", {1: "phishing", 0: "ham"}, {"phishing": 3000, "ham": 1500}),
    ("BothBosu__scam-dialogue", "dialogue", "label", {1: "scam_call", 0: "normal_call"}, {"scam_call": 800, "normal_call": 800}),
    ("BothBosu__multi-agent-scam-conversation", "dialogue", "labels", {1: "scam_call", 0: "normal_call"}, {"scam_call": 800, "normal_call": 800}),
]


def key(text: str) -> str:
    return hashlib.sha1(re.sub(r"\W+", "", text.lower())[:300].encode()).hexdigest()


def main(raw: str, output: str) -> None:
    rng = random.Random(7)
    seen = set()
    out = []
    for name, field, label, hints, quota in PLAN:
        pools = {h: [] for h in quota}
        for line in open(f"{raw}/{name}.jsonl"):
            row = json.loads(line)
            hint = hints.get(row[label])
            text = (row[field] or "").strip()
            if hint is None or not 25 <= len(text) <= 4000 or text.startswith("http") and " " not in text:
                continue
            pools[hint].append(text)
        for hint, texts in pools.items():
            rng.shuffle(texts)
            taken = 0
            for text in texts:
                k = key(text)
                if k in seen:
                    continue
                seen.add(k)
                out.append({"id": f"{name}-{k[:12]}", "text": text, "source": name, "hint": hint})
                taken += 1
                if taken == quota[hint]:
                    break
            print(name, hint, taken, "of", len(texts))
    rng.shuffle(out)
    with open(output, "w") as f:
        for row in out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("total", len(out))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("raw")
    parser.add_argument("output")
    args = parser.parse_args()
    main(args.raw, args.output)
