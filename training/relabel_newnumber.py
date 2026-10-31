"""Label synthetic "this is my new number" messages as scams: it is the usual opening of the family impersonation scam,
and a false alarm for a relative who really changed numbers costs less than a missed scam.

Usage: relabel_newnumber.py INPUT OUTPUT
"""
import hashlib
import json
import re
import sys

NEW_NUMBER = re.compile(r"nov[éeý]\w* čísl|nov[éeý] číslo|nové telefonní|nový telefon", re.I)
REASONS = [
    "Zpráva o novém čísle od někoho blízkého je častý začátek podvodu „mami, mám nové číslo“, po kterém brzy přijde žádost o peníze.",
    "Někdo vám píše z neznámého čísla, že má nové číslo. Takto často začínají podvodníci, kteří se vydávají za člena rodiny nebo známého.",
    "Takto začíná známý podvod: neznámé číslo se vydává za někoho blízkého a později žádá o peníze nebo kód.",
]
ADVICE = [
    "Zavolejte dotyčnému na staré číslo, které už máte uložené, a ověřte si, že číslo opravdu změnil. Neposílejte peníze ani kódy.",
    "Ověřte si to jinou cestou, například telefonátem na původní číslo. Dokud si nejste jistí, nic neplaťte a nesdílejte žádné údaje.",
]


def pick(options: list, key: str) -> str:
    return options[int(hashlib.sha1(key.encode()).hexdigest(), 16) % len(options)]


def main(src: str, dst: str) -> None:
    changed = 0
    with open(dst, "w") as out:
        for line in open(src):
            r = json.loads(line)
            if r["source"] == "synthetic" and r["verdict"] == "insufficient" and NEW_NUMBER.search(r["text"]):
                r = {**r, "verdict": "scam", "category": "family", "flags": ["impersonation", "new_contact_number"],
                     "teacher": {**r["teacher"], "duvod": pick(REASONS, r["id"])}, "rada": pick(ADVICE, r["id"] + "r")}
                changed += 1
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(dst, "relabelled", changed)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
