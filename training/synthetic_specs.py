"""Build random specs for synthetic Czech messages: local scam types, look-alike legitimate messages, vague ones.

Each spec is later written into a message by the teacher (teacher.py --mode generate) and then labelled blind by the
second teacher; only messages where the second teacher agrees with the intended verdict are kept. Scams and
legitimate messages draw from the same brands and channels, so the brand or channel alone never gives the answer.
"""
import argparse
import json
import random

SCAMS = [
    "a fake call-centre 'security department' of the bank says the account is under attack and asks to move money to a 'safe account'",
    "a fake bank message asks to log in through a link to 'confirm identity' or 'unblock the account'",
    "a 'buyer' on a second-hand marketplace sends a link to 'receive the payment' or 'arrange courier delivery' that asks for card details",
    "a fake energy supplier threatens disconnection today unless an overdue amount is paid through a link",
    "an investment offer promises high guaranteed returns from shares, crypto or a well-known company, with a 'personal advisor'",
    "fake technical support asks to install a remote-access app to 'fix' the computer or the bank account",
    "'Ahoj mami/tati', a child writes from a new number because the phone broke and urgently needs money sent",
    "a fake police officer or central-bank employee says the savings are in danger and must be withdrawn and handed over",
    "a fake parcel service asks for a small fee for customs or redelivery through a link",
    "a fake tax office or state agency promises a refund or benefit after entering card details",
    "a fake lottery or loyalty prize requires paying a small fee or entering card details",
    "a romance contact met online asks for money for a ticket, hospital or customs",
    "a job offer pays for liking videos or rating hotels, then asks to deposit money to 'unlock' earnings",
    "a fake e-shop or classified ad with a much too low price asks to pay in advance to a private account",
    "an e-mail claims the reader was filmed on adult sites and demands payment in crypto",
    "a fake insurance company or health insurer offers a refund after confirming personal and card data",
    "a fake mobile operator says the SIM card will be blocked unless the user confirms data or pays",
    "a fake e-mail or cloud provider warns the mailbox is full or the password expires, with a login link",
    "an advance-fee message about an inheritance or a large transfer that needs a small fee first",
    "a fake CAPTCHA or security check on a web page instructs to press keys and paste a command",
]
ORDINARY = [
    "a bank's marketing e-mail for a credit card, loan, mortgage or savings account with a normal link to its website",
    "a genuine bank notification about a new device login that says to contact the bank via the official app or the number on the card if it was not you, without asking for any data",
    "a genuine bank notice that the way of confirming payments changed, pointing to the official app, asking for nothing",
    "a genuine parcel notification with a tracking number and delivery time, nothing to pay",
    "a genuine invoice or payment reminder from an energy supplier or operator with the usual account number and due date",
    "an e-shop order confirmation or shipping notice",
    "a newsletter with discounts from a shop, travel agency or supermarket",
    "a bank or police warning ABOUT scams that explains what fraudsters do and says the bank never asks for passwords",
    "a news article or forum post describing a scam that happened to someone",
    "an SMS reminder of a doctor's appointment, school event or service visit",
    "a family or friends chat message about everyday plans, possibly mentioning money in a normal way (splitting a bill, a birthday gift)",
    "a real buyer on a second-hand marketplace asking about the item, meeting in person or paying by normal bank transfer",
    "a genuine one-time login code SMS that says never to share the code",
    "a work e-mail between colleagues about a meeting, document or invoice",
    "a municipality or state office announcement (waste collection, elections, road closure)",
    "a loyalty programme e-mail about collected points with a link to its own website",
    "an insurance company's annual statement or contract renewal reminder",
    "a password reset e-mail the user requested, with a short-lived link",
]
INSUFFICIENT = [
    "a bare greeting or 'are you there?' from an unknown number",
    "a short message asking the reader to call back, with no further detail",
    "'who is this?' or 'I have a new number' with nothing else",
    "a one-line message that only says the reader should check something, without saying what",
]
# Everyday legitimate e-mails that fill a real inbox; the screener saw too few of them and flagged most real mail.
EMAIL_ORDINARY = ORDINARY[:8] + ORDINARY[13:] + [
    "an e-shop order confirmation listing the items, prices, delivery address and payment method already used",
    "a notice that a parcel was handed to the carrier, with a tracking link on the carrier's own website",
    "a request to rate a recent purchase or delivery, with a link to the shop's own review page",
    "a monthly bank account statement or card statement is ready in internet banking, no link to log in",
    "a change of business terms or price list from a bank, operator or energy supplier, effective next month",
    "an electronic invoice for electricity, gas, phone or internet with amount, due date and the usual account",
    "a payment receipt or confirmation that a standing order or direct debit was paid",
    "a subscription renewal notice for a streaming service, magazine or software, paid by the card already on file",
    "a flight or train ticket, booking confirmation or online check-in reminder",
    "a hotel or holiday booking confirmation with dates, price and cancellation conditions",
    "a notice that laboratory results or a prescription (eRecept) are ready, from a clinic or pharmacy",
    "a notification that a new message arrived in the state data box (datová schránka) or citizen portal, to be read there",
    "a school or university e-mail about timetable, enrolment, fees or a parents' meeting",
    "a newsletter from a museum, theatre, library or local club with upcoming events and an unsubscribe link",
    "a charity thanking for a donation and sending the annual confirmation for tax purposes",
    "a confirmation of a newly created account with a link to verify the e-mail address, which the user requested",
    "a genuine security notice that the password was changed or a new device signed in, saying to contact support if it was not you, without a link to log in",
    "an e-mail from a health insurer about a bonus programme or a preventive check-up",
    "a reminder of an upcoming service appointment for a car, boiler or chimney",
    "a pension, tax or social security office letter informing about a decision, with reference numbers",
    "a real-estate or job portal sending new offers matching a saved search",
    "an e-mail from a building manager or housing cooperative about utility billing or maintenance",
    "a long marketing e-mail with many product offers, discount codes and a time-limited sale",
]
EMAIL_SCAMS = [s for s in SCAMS if "CAPTCHA" not in s and "'Ahoj mami/tati'" not in s] + [
    "a fake e-shop order confirmation for an expensive item the reader never ordered, with a link or number to 'cancel'",
    "a fake invoice in the attachment or link from a supplier the reader does not know, asking to pay quickly",
    "a fake notice that a subscription payment failed, asking to update card details through a link",
]
EMAIL_LENGTHS = ["medium (a full e-mail, 6-12 sentences)",
                 "long: the complete e-mail as it lands in the inbox, with sender, subject, greeting, body, signature and "
                 "the usual footer (contact details, company registration, privacy notice, 'please do not reply', "
                 "unsubscribe or settings links)"]
EMAIL_BRANDS = ["Datart", "CZC.cz", "Notino", "IKEA", "dm drogerie", "Albert", "Tesco", "Regiojet", "České dráhy",
                "Smartwings", "Invia", "Spotify", "Google", "Allianz", "Kooperativa", "Generali Česká pojišťovna",
                "Pražská plynárenská", "Dr.Max", "Benu lékárna", "Sreality", "Jobs.cz", "Univerzita Karlova",
                "Městský úřad", "Národní divadlo", "Člověk v tísni", "Bezrealitky", "Heureka", "Temu", "AliExpress"]
# Web pages and SMS: the screener missed fake e-shops and SMS typed without diacritics, and flagged too much ordinary
# web text. Scams and look-alike legitimate pages come from the same shop types, so the shop alone never decides.
WEB_SCAMS = [
    "the product page of a fake e-shop: a branded appliance, phone or tool at a fraction of the usual price, payment only in advance by bank transfer, no company details",
    "a fake 'closing down sale' web page with 70-90 % discounts on everything, a countdown timer and 'last pieces', prepayment only",
    "a fake e-shop's terms or contact page with no company ID (IČO), only a web form or a foreign mobile number, and returns 'not possible'",
    "a web page selling a miracle health product or pills with fake doctor quotes and a 'today only' price, payment in advance",
    "a fake web shop for firewood, pellets or heating oil with a very low price, delivery 'after payment to a private account'",
    "a page of a fake travel agency or holiday rental asking to pay the full price to a private account to 'hold' the booking",
    "a fake charity or crowdfunding page for a sick child or a disaster that asks for card details or a transfer to a private account",
]
WEB_ORDINARY = [
    "the product page of a well-known Czech e-shop with a normal price, specifications, reviews and delivery options",
    "a real seasonal sale page of a large chain with discounts of 20-50 %, normal payment options and full company details",
    "a 'contact and company details' page of a genuine shop with IČO, address, phone and opening hours",
    "a business terms or returns policy page of a genuine e-shop with the 14-day return period",
    "a news article or blog post about prices, shopping, energy or travel",
    "a recipe, gardening or DIY article with a few affiliate product links",
    "a discussion forum thread where people compare products or shops",
    "a municipal or club web page announcing events, fees and opening hours",
    "a pharmacy or drugstore product page for vitamins or cosmetics with a normal price and the usual legal notes",
    "a genuine charity page describing a collection, with a transparent account and annual reports",
]
WEB_SMS_SCAMS = [s for s in SCAMS if "CAPTCHA" not in s and "e-shop" not in s]
WEB_SMS_ORDINARY = ORDINARY
PLAIN_TONE = "typed without Czech diacritics (no háčky and čárky), as many SMS are"
BRANDS = ["Česká spořitelna", "ČSOB", "Komerční banka", "Raiffeisenbank", "Moneta", "Air Bank", "Fio banka",
          "Česká pošta", "PPL", "Zásilkovna", "DPD", "GLS", "ČEZ", "E.ON", "innogy", "Pražská energetika",
          "O2", "T-Mobile", "Vodafone", "Alza", "Mall", "Rohlik.cz", "Bazoš", "Vinted", "Sbazar", "Seznam",
          "Microsoft", "Apple", "Netflix", "VZP", "Finanční správa", "ČSSZ", "Policie ČR", "Booking.com", "Lidl", "Kaufland"]
CHANNELS = ["SMS", "e-mail", "WhatsApp message", "Facebook Messenger message", "text of a web page", "chat on a marketplace"]
LENGTHS = ["very short (1-2 sentences)", "short (3-5 sentences)", "medium (a full e-mail, 6-12 sentences)"]
GUIDES = {
    "scam": "It is a scam: make the deception realistic and subtle, as real fraudsters write it, not cartoonish. "
            "Links go to plausible look-alike domains.",
    "ordinary": "It is completely legitimate. It must not ask for passwords, PINs, card numbers or codes, must not threaten, "
                "and must not ask to pay anywhere unusual. Any link goes to the company's real official domain. "
                "It may still look commercial, formal or urgent the way genuine companies write.",
    "insufficient": "It is only the vague message itself: no link, no company, no amount, no request for data. "
                    "Nobody could tell from it what the sender wants.",
}
TONES = ["formal", "friendly", "casual with a few typos", "slightly broken Czech as if machine-translated",
         "urgent", "neutral and matter-of-fact"]


def main(args: argparse.Namespace) -> None:
    rng = random.Random(args.seed)
    if args.emails:
        kinds, weights = [("scam", EMAIL_SCAMS), ("ordinary", EMAIL_ORDINARY)], [0.3, 0.7]
    elif args.web:
        kinds, weights = [("scam", WEB_SCAMS), ("ordinary", WEB_ORDINARY), ("scam", WEB_SMS_SCAMS),
                          ("ordinary", WEB_SMS_ORDINARY)], [0.2, 0.4, 0.2, 0.2]
    else:
        kinds, weights = [("scam", SCAMS), ("ordinary", ORDINARY), ("insufficient", INSUFFICIENT)], [0.42, 0.45, 0.13]
    prefix = "synthmail" if args.emails else "synthweb" if args.web else "synth"
    with open(args.out, "w") as f:
        for i in range(args.n):
            verdict, pool = rng.choices(kinds, weights=weights)[0]
            tone = rng.choice(TONES)
            if args.emails:
                channel, length, brand = "e-mail", rng.choice(EMAIL_LENGTHS), rng.choice(BRANDS + EMAIL_BRANDS)
            elif args.web and pool in (WEB_SCAMS, WEB_ORDINARY):
                channel, length, brand = "text of a web page", rng.choice(LENGTHS[1:]), rng.choice(BRANDS + EMAIL_BRANDS)
            elif args.web:
                channel, length, brand = "SMS", rng.choice(LENGTHS[:2]), rng.choice(BRANDS)
                tone = PLAIN_TONE if rng.random() < 0.6 else tone
            else:
                channel, brand = rng.choice(CHANNELS), rng.choice(BRANDS)
                length = LENGTHS[0] if verdict == "insufficient" else rng.choice(LENGTHS)
            spec = {"id": f"{prefix}-{args.seed}-{i}", "intended": verdict, "scenario": rng.choice(pool),
                    "brand": brand, "channel": channel, "length": length,
                    "tone": tone, "guide": GUIDES[verdict], "source": "synthetic", "hint": verdict}
            f.write(json.dumps(spec, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--n", type=int, default=8000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--emails", action="store_true", help="complete e-mails only, mostly everyday legitimate mail")
    parser.add_argument("--web", action="store_true", help="web pages (fake and genuine shops, articles) and SMS")
    main(parser.parse_args())
