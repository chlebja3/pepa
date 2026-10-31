"""Specs for short, realistic fragments (one line of a call, one chat message, an ad snippet) for teacher.py --mode generate.

The verifier missed scams that arrive as such fragments without the full context of a long e-mail. Scams and
look-alike legitimate fragments share the same forms and topics, so the form alone never gives the answer.
"""
import json
import random
import sys

FORMS = [
    ("one or two sentences a caller says on the phone, written as a transcript", "very short (1-2 sentences)"),
    ("a single chat message (WhatsApp, Messenger or a classifieds chat)", "very short (1-2 sentences)"),
    ("a short SMS, possibly with a link", "very short (1-2 sentences)"),
    ("a snippet of a web page, online ad or social media post", "short (3-5 sentences)"),
    ("a short e-mail body with a subject line", "short (3-5 sentences)"),
    ("three or four lines of a chat conversation, only the other side's messages", "short (3-5 sentences)"),
]
SCAMS = [
    "an online ad or fake news article quotes a famous Czech politician or celebrity endorsing an investment platform that pays thousands of Kč a day",
    "a big Czech company or the state supposedly lets every citizen become a shareholder and earn dividends after registering on a platform",
    "a buyer on a classifieds site cannot come in person, will order a courier service and pay in full in advance, and asks the seller to follow a link to receive the money",
    "a fake 'safe delivery' or 'receive payment' page of a classifieds or courier service with a button to get the money",
    "a recruiter offers paid work boosting subscribers, likes or ratings for bloggers or hotels",
    "a soldier on a foreign mission or a doctor met online explains fees for leave, a parcel or a frozen bank account",
    "someone posing as a doctor says a grandchild or child was badly injured and needs paid treatment or a deposit",
    "a fake police or prosecutor e-mail says a summons or criminal case file is in the attachment",
    "a fake e-mail administrator says the mailbox will be shut down and asks to 'repair' it through a link",
    "an SMS from a fake ministry or labour office offers a housing or energy benefit through a short link",
    "an SMS says 'last call: update your details to avoid blocking' without naming a company",
    "a fake police officer on the phone asks how much money is on the account to 'assess the damage'",
    "a fake e-shop 'closing down' or 'family business' page with huge discounts and an emotional story",
    "a fake bank security officer on the phone says someone took a loan in the victim's name and a new safe account is needed",
    "a caller from a fake operator or energy supplier needs the victim to confirm a code from an SMS",
    "a 'relative' writes from an unknown number that the phone broke and asks to pay an urgent invoice for them",
    "a fake parcel service SMS asks to pay a small fee for redelivery through a link",
    "a fake technical support caller asks to install an app so they can check the bank account",
    "a fake bank SMS warns about a suspicious payment and asks to log in through a link to cancel it",
    "a fake tax office e-mail promises a tax refund after entering card details",
]
ORDINARY = [
    "a real buyer on a classifieds site asks about the item and wants to pick it up in person or pay by normal bank transfer",
    "a seller confirms sending the item through a parcel service with a tracking number, paid on pickup",
    "a short news report or police press release describing how fraudsters tricked a senior",
    "a bank's genuine promotional ad for a new account with bonuses for card payments",
    "a genuine job advert with a company name, salary range and a link to its careers page",
    "a hospital or clinic reminds a patient about an appointment or that results are ready",
    "a company IT department announces planned maintenance of the e-mail server, nothing to click",
    "a ministry or office explains who can apply for a housing benefit and where to apply in person or on the official portal",
    "a real e-shop announces a seasonal sale with normal discounts",
    "a grandchild writes from their usual number about a visit next weekend",
    "a genuine bank notice says it will never ask for passwords or PINs by phone",
    "a parcel service SMS says the parcel will be delivered today between 10 and 12, nothing to pay",
    "a colleague asks in chat to check an invoice before the meeting",
    "a forum post where someone asks whether a message they got is a scam and quotes it",
    "a real energy supplier SMS reminds about the yearly bill in the customer account, no link",
    "a news article about a politician announcing a state investment programme, with no offer to the reader",
]
INSUFFICIENT = [
    "a caller only says they are from a company and asks if the person has a minute, nothing else",
    "a one-line chat message asking whether the item is still available",
    "a short message from an unknown number asking to call back",
]
TONES = ["formal", "informal", "pushy", "friendly", "sloppy with typos"]


def main(out_path: str, per_scenario: int, seed: int) -> None:
    rng = random.Random(seed)
    groups = [("scam", SCAMS, "It is a scam: make it realistic and subtle, as real fraudsters write it, not cartoonish."),
              ("ordinary", ORDINARY, "It is legitimate and harmless; it must look natural, not suspicious."),
              ("insufficient", INSUFFICIENT, "Give no further detail about what the sender wants.")]
    with open(out_path, "w") as f:
        for intended, scenarios, guide in groups:
            for s, scenario in enumerate(scenarios):
                for k in range(per_scenario if intended != "insufficient" else per_scenario // 2):
                    channel, length = rng.choice(FORMS)
                    row = {"id": f"frag-{intended}-{s}-{k}", "intended": intended, "scenario": scenario, "brand": "",
                           "channel": channel, "length": length, "tone": rng.choice(TONES), "guide": guide,
                           "source": "synthetic-fragment", "hint": intended}
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
