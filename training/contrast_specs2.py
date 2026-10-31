"""Second batch of contrastive pairs: the same situations as contrast_specs.py, with the page facts the extension adds
("[odkaz: host]" after a link, "[odesílatel: domain]" for an e-mail sender) made deliberately unreliable on their own.

A mark must be evidence, not the answer: some scams link only to the real brand's site (the fraud is in what they ask)
or use a generic hosting, and some legitimate messages link through a newsletter tracking domain or come from a
mailing service. A part has no marks at all, as most texts in production (SMS, chats, OCR) do.
"""
import json
import random
import sys

from contrast_specs import FORMS, PAIRS, TONES

FOREIGN = ["moje-banka-overeni.com", "cz-posta-zasilka.top", "office365-cz.info", "mpsv-prispevek.online",
           "kb-cz.sk-support.net", "o2-vyuctovani.eu", "bazos-platba.store", "xn--esk-spoitelna-wyb.com", "rb-klient.app"]
HOSTING = ["sites.google.com", "forms.office.com", "secure-login.web.app", "bit.ly", "docs.google.com", "1drv.ms", "wixsite.com"]
BRAND = ["www.kb.cz", "www.ceskaposta.cz", "www.o2.cz", "www.bazos.cz", "www.mpsv.cz", "www.csas.cz", "www.rb.cz",
         "www.zasilkovna.cz", "www.cez.cz", "www.alza.cz"]
TRACKING = ["click.e-mailing.cz", "t.newsletter-alza.cz", "links.ecomail.cz", "email.mg.ppl.cz", "r.smartemailing.cz", "url.emailprotection.link"]
SCAM_SENDERS = ["klient-kb.cz", "gmail.com", "seznam.cz", "posta-doruceni.com", "o2-info.net", "outlook.com", "mpsv-cr.eu"]
REAL_SENDERS = ["kb.cz", "info.ceskaposta.cz", "o2.cz", "email.alza.cz", "mpsv.cz", "ecomail.cz", "seznam.cz", "gmail.com"]


def marks(rng: random.Random, intended: str, channel: str, scenario: str) -> str:
    mail = "e-mail" in channel
    style = rng.choices(["none", "link", "sender", "both"], weights=[0.3, 0.35, 0.15 if mail else 0, 0.2 if mail else 0])[0]
    if style == "none":
        return "Write no [odkaz: ...] or [odesílatel: ...] marks."
    parts = []
    if style in ("link", "both"):
        if intended == "scam":
            kind = rng.choices(["foreign", "hosting", "brand"], weights=[0.5, 0.25, 0 if "link" in scenario else 0.25])[0]
            host = rng.choice({"foreign": FOREIGN, "hosting": HOSTING, "brand": BRAND}[kind])
            if kind == "brand":
                parts.append(f"Its only link points to the real website {host} (fraudsters add real links to look trustworthy); "
                             "the fraud is in what it asks you to do outside that link (reply, call, send a code or data, pay to an account).")
        else:
            host = rng.choice(BRAND if rng.random() < 0.6 else TRACKING)
        parts.append(f"Write a clickable link as its text followed by [odkaz: {host}], e.g. 'zde [odkaz: {host}]'.")
    if style in ("sender", "both"):
        domain = rng.choice(SCAM_SENDERS if intended == "scam" else REAL_SENDERS)
        parts.append(f"Start with the sender line 'Od: <display name> [odesílatel: {domain}]', no other sender address.")
    return " ".join(parts)


def main(out_path: str, per_side: int, seed: int) -> None:
    rng = random.Random(seed)
    with open(out_path, "w") as f:
        for p, (request, scam, legit, principle) in enumerate(PAIRS):
            for intended, scenario in (("scam", scam), ("ordinary", legit)):
                guide = ("It is a scam: make it realistic and subtle, as real fraudsters write it, not cartoonish."
                         if intended == "scam" else "It is legitimate and harmless; it must look natural, not suspicious. Add nothing the situation does not "
                         "describe: no extra links, no short links, no new phone number, no app to install, no urgency.")
                for k in range(per_side):
                    channel, length = rng.choice(FORMS)
                    row = {"id": f"pair2-{intended}-{p}-{k}", "intended": intended, "scenario": f"{scenario} (the request: {request})",
                           "brand": "a fitting real Czech company or institution", "channel": channel, "length": length,
                           "tone": rng.choice(TONES), "guide": f"{guide} {marks(rng, intended, channel, scenario)}",
                           "principle": principle, "source": "synthetic-contrast", "hint": intended}
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
