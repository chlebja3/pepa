"""Stream Czech FineWeb-2 and cut documents into blocks the size the extension checks."""
import argparse
import hashlib
import json
import re

from datasets import load_dataset


def blocks(text: str, size: int) -> list:
    parts, current = [], ""
    for para in re.split(r"\n\s*\n|\n", text):
        para = para.strip()
        if not para:
            continue
        if current and len(current) + len(para) > size:
            parts.append(current)
            current = ""
        current = (current + "\n" + para).strip()
    if current:
        parts.append(current)
    return [p for p in parts if len(p) >= 80]


def main(args: argparse.Namespace) -> None:
    stream = load_dataset("HuggingFaceFW/fineweb-2", "ces_Latn", split=args.split, streaming=True)
    seen, n = set(), 0
    hard = re.compile(r"podvod|phishing|podvodn|hoax|scam|vydír|falešn", re.I)
    with open(args.output, "w") as f:
        for doc in stream:
            for block in blocks(doc["text"], args.size):
                k = hashlib.sha1(block.encode()).hexdigest()[:16]
                if k in seen:
                    continue
                seen.add(k)
                f.write(json.dumps({"id": f"fw-{k}", "text": block, "source": "fineweb-2-ces",
                                    "url": doc.get("url"), "hint": "scam_topic" if hard.search(block) else "web"},
                                   ensure_ascii=False) + "\n")
                n += 1
            if n >= args.limit:
                break
    print("blocks", n)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument("--split", default="train")
    parser.add_argument("--limit", type=int, default=60000)
    parser.add_argument("--size", type=int, default=700)
    main(parser.parse_args())
