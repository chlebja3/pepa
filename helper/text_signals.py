"""Fast pattern signals (data/text-signals.json) appended to the text the verifier reads.

They are hints, not verdicts: a verifier trained with them (SIGNALS in native_host.py) still decides, so a scam warning quoted in a news
article can match a pattern and stay quiet.
"""
import json
from pathlib import Path
import re
import unicodedata

SIGNALS = [(s['id'], s['label'], re.compile(s['pattern'])) for s in
           json.loads((Path(__file__).parent / 'data/text-signals.json').read_text())['signals']]


def plain(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if not unicodedata.combining(c))


def find(text: str) -> list[tuple[str, str]]:
    flat = plain(text)
    return [(sid, label) for sid, label, pattern in SIGNALS if pattern.search(flat)]


def with_signals(text: str) -> str:
    found = find(text)
    return f"{text}\n\n[Automatické signály: {'; '.join(label for _, label in found)}]" if found else text
