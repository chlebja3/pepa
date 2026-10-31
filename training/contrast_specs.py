"""Contrastive specs for teacher.py --mode generate: the same request (log in, pay, send a code, give personal data,
open an attachment) once in a context where it is normal and once where it is not.

The verifier missed scams that look exactly like legitimate notices from the same brands. A minimal pair forces it to
decide on the context (who asks, through which channel, where the link leads, what is unusual about the request)
rather than on the topic or the brand. "principle" goes into the explanation, so the reason states the mismatch.
"""
import json
import random
import sys

# (request, scam situation, legitimate situation with the same request, principle for the explanation)
PAIRS = [
    ("log in through a link",
     "an e-mail looking like it comes from the reader's bank says the account will be limited unless the reader verifies their identity today; the 'Ověřit' link leads to a domain that is not the bank's (e.g. a free hosting or a look-alike name)",
     "an e-mail from the reader's bank says a new monthly statement is ready and asks the reader to open the bank's mobile app or internet banking as usual; it contains no login link",
     "a bank never asks to verify identity through a link in an e-mail; the link leads elsewhere than the bank's website"),
    ("read a message by clicking",
     "a short notice 'Obdrželi jste novou zabezpečenou zprávu od své banky. Pro zobrazení klikněte zde' without naming the reader, with a link to an unknown domain",
     "a bank notice that a new document (contract change) is waiting in the internet banking under Zprávy, the reader should log in the usual way; names the reader and the product",
     "a vague 'you have a new message, click here' with an unknown link, instead of telling you to open the bank's app yourself"),
    ("change a password",
     "an e-mail from 'IT podpora' or 'Administrátor pošty' says the Office 365 or mailbox password expires today and must be kept through a link, otherwise the mailbox will be deleted",
     "the company IT department (a named colleague) announces that passwords must be changed by the end of the month through the usual way (Ctrl+Alt+Del or the company portal they already use); no link to log in",
     "the request comes with pressure and a link to an outside page, instead of the usual company way of changing the password"),
    ("open a shared document",
     "a 'document shared with you' (OneDrive, SharePoint, Google Drive) from a stranger or an unknown company, with a vague name like 'Faktura_2026' or 'Smlouva k podpisu', requiring login to view",
     "a colleague the reader works with shares a document they talked about (named project, meeting), through the company's usual shared drive",
     "an unexpected document from an unknown sender that asks for a login before you can see it"),
    ("release blocked e-mails or voicemail",
     "a mail-server notice says several incoming e-mails are held in quarantine or a voicemail is waiting, and they must be released through a link within 24 hours",
     "the company IT announces a planned outage of the e-mail server on Saturday night; nothing needs to be done",
     "an invented problem with the mailbox and a link to 'release' messages, from no identifiable sender"),
    ("fill in device or personal details for the employer",
     "an e-mail signed 'HR oddělení' from an outside address asks every employee to fill in a table with their phone IMEI, birth number and bank account by today, through a link or attachment",
     "the reader's HR colleague (named) reminds to update the bank account for salary in the internal HR system they normally use, before the payroll date",
     "the employer would not collect such data through an outside form under time pressure"),
    ("confirm an order of office equipment",
     "a message about 'leasing of new laptops / office chairs for employees' asks to log in with the company account on a linked page to choose the model",
     "the office manager announces that new office chairs arrive next week and asks who wants a different size to reply to the e-mail",
     "an unusual offer used as a pretext to make you enter the company login on an outside page"),
    ("install a security update",
     "a message says the VPN certificate or disk encryption expires and the employee must download and install a new client from a link today",
     "the IT department says the VPN client will update automatically overnight and the computer should stay on",
     "a request to download and install software from a link, instead of the update coming automatically from the company IT"),
    ("pay an invoice for the boss",
     "the director writes from a private e-mail or chat that they are in a meeting, an urgent payment to a new supplier account must go out today and the reader should not tell anyone",
     "the director asks the accountant in the usual company e-mail to process the supplier invoice through the normal approval system this week",
     "an urgent payment to a new account with a request to keep it quiet, outside the usual approval"),
    ("open an attached invoice",
     "an e-mail 'Kopie platby' or 'Faktura v příloze' from an unknown company with no order number, asking to open the attachment or enable content",
     "a known supplier sends the monthly invoice with the order number, amount and due date that match the earlier order",
     "an unexpected invoice from someone you have no business with, pushing you to open the attachment"),
    ("pay a small customs or delivery fee",
     "an SMS says a parcel is held at customs or the delivery is paused and a fee of a few koruna (e.g. 1,10 Kč or 34 Kč) must be paid through a short link",
     "a carrier SMS says the parcel arrives today between 10 and 12, the cash-on-delivery amount is the price of the order the reader made, track it in the carrier's app",
     "a tiny fee through a link is a typical way to get card details; carriers do not ask for it like this"),
    ("apply for a state benefit",
     "an SMS from 'MPSV' or 'Úřad práce' says the reader is entitled to a housing or energy allowance and should apply through a short link with card details",
     "an Úřad práce letter or SMS reminds the reader of an appointment at the office to bring documents for the housing allowance application",
     "the state does not pay benefits through a link in an SMS and never needs card details for that"),
    ("receive money for a sold item",
     "a message 'Gratulujeme k prodeji, kupující zaplatil, převezměte platbu' with a link where the seller must enter card details to receive the money",
     "a classifieds site notification says a buyer replied to the ad and the seller can read the message in the app; or a buyer asks for the account number to send a normal bank transfer",
     "to receive money you only give your account number; entering card details on a linked page is a trap"),
    ("pay for a reserved item",
     "an SMS says an item is reserved for the reader and must be paid within an hour through a link, otherwise it expires",
     "an e-shop the reader ordered from confirms that the reserved item can be picked up in the store until Friday, paid at the counter",
     "pressure to pay through a link for something you did not order"),
    ("forward an SMS code",
     "a friend's account on WhatsApp or Messenger writes 'I sent you a six-digit code by mistake, please forward it to me'",
     "an SMS from a service contains a login code for the reader's own login and says never to give the code to anyone",
     "nobody else needs the code that came to your phone; whoever has it can take over your account"),
    ("read a code to a caller",
     "a caller from the 'bank's security department' or the mobile operator asks the reader to read out the code that just arrived by SMS to cancel a suspicious payment",
     "the reader calls the bank's hotline themselves and the operator asks them to confirm the change in the bank's mobile app",
     "a code from an SMS is never read to anyone on the phone; the bank never asks for it"),
    ("vote in a contest with a code",
     "an acquaintance asks to vote for their child in a contest; the reader will get a code by SMS and should send it back",
     "an acquaintance shares a link to a public poll on a known news site where anyone can vote with one click, no code",
     "a voting request that needs your SMS code is used to steal accounts"),
    ("move money to a safe account",
     "someone in a chat or on the phone presents as a bank security officer or police, says the account is under attack and the savings must be moved to a 'safe account' or withdrawn and handed over",
     "the reader writes to the bank's chat inside the bank's own app and asks about account fees; the reply explains the fees",
     "no bank or police moves your money to a 'safe account' to protect it"),
    ("send money to a relative",
     "a 'son' or 'daughter' writes from an unknown number that the old phone broke, asks to save the new number and then to pay an urgent invoice today, and not to tell anyone",
     "a daughter writes from the number the reader has saved and asks to send the share of the cottage rent they agreed on last weekend, with the account number of the owner",
     "a new number together with an urgent money request; a real relative can be checked by calling the old number"),
    ("save a relative's new number",
     "a short message 'Ahoj mami, mám nové číslo, ulož si ho' or 'Ahoj tati, tohle je moje nové číslo, to staré už nefunguje' from an unknown number, nothing more yet",
     "a grandchild writes from their usual number that they will come on Sunday for lunch",
     "this is how the 'new number' scam starts; check it by calling the old number before replying"),
    ("give personal data for an update",
     "an e-mail or SMS from 'zdravotní pojišťovna', 'ČSSZ' or a pension office asks to update personal data (birth number, card, ID) through a link, otherwise payments stop",
     "a doctor's office asks the new patient to bring the insurance card and ID to the first appointment",
     "official institutions do not stop payments unless you fill in a link; they do not ask for card data"),
    ("open a court or police document",
     "an e-mail 'Předvolání' or 'Policie ČR – trestní oznámení' says a summons is in the attachment or behind a link and the reader must respond in 48 hours",
     "a news article or police press release explains how fake summons e-mails look",
     "police and courts deliver summons by data box or registered post, not by an e-mail with an attachment"),
    ("view medical results",
     "an SMS says the reader's test results are ready and can be viewed through a short link after entering personal data",
     "a clinic SMS says the results are ready and the doctor will go through them at the appointment on Tuesday",
     "a link from an unknown number asking for personal data in exchange for results"),
    ("take a paid online task",
     "a recruiter on WhatsApp offers easy money for liking YouTube videos or rating hotels, then asks for a small deposit to unlock better-paid tasks",
     "a genuine part-time job offer from a named shop with an hourly wage and an interview in person",
     "a job where you first have to pay to earn more is a scam"),
    ("pay a phone or energy bill",
     "an e-mail 'Vyúčtování O2' or 'ČEZ – nedoplatek' says the bill was not paid and the service will be cut tonight unless the reader pays through the link with a card",
     "the operator's usual monthly e-mail says the bill for the month is ready, the amount is paid automatically by direct debit as usual",
     "a threat to cut the service tonight with a card payment through a link"),
    ("verify a bank account by a small payment",
     "a message says the account must be verified by paying 1 Kč through a linked payment gate with full card details",
     "a new online service asks to verify the account by a 1 Kč transfer from the reader's own banking to an account listed in the service's own app",
     "card details on a linked gate are what the scammer wants; a normal verification is a transfer you make yourself"),
    ("install an app for help",
     "a caller or chat 'technician' says the computer is infected or a bank payment is stuck and asks to install AnyDesk or TeamViewer",
     "the reader's grandson offers to help with the new laptop when he visits on Saturday",
     "someone who asks you to install a remote control app wants control of your computer and bank"),
    ("buy a product on sale",
     "a social media ad of a 'closing down' shop with 80 % discounts and a sad family story, payment only by card on an unknown website",
     "a known e-shop sends its usual newsletter with seasonal discounts of 20 %",
     "unrealistic discounts with an emotional story on an unknown site"),
]

FORMS = [
    ("a short SMS, possibly with a link", "very short (1-2 sentences)"),
    ("a single chat message (WhatsApp, Messenger)", "very short (1-2 sentences)"),
    ("three or four chat messages from the other side, one per line", "short (3-5 sentences)"),
    ("a short e-mail with a subject line", "short (3-6 sentences)"),
    ("an e-mail with a subject line, sender and signature", "medium (6-10 sentences)"),
    ("one or two sentences a caller says on the phone, written as a transcript", "very short (1-2 sentences)"),
]
TONES = ["formal", "informal", "pushy", "friendly", "sloppy with typos", "machine-translated, slightly unnatural"]
LINKS = ("If the message contains a clickable link, write it right after the link text in the form "
         "[odkaz: hostname], e.g. 'Přihlaste se zde [odkaz: {host}]'; a link written out in full (as in an SMS) needs no [odkaz].")
SCAM_HOSTS = ["moje-banka-overeni.com", "secure-login.web.app", "cz-posta-zasilka.top", "bit.ly", "office365-cz.info",
              "mpsv-prispevek.online", "kb-cz.sk-support.net", "o2-vyuctovani.eu", "bazos-platba.store", "sites.google.com"]
REAL_HOSTS = ["www.kb.cz", "www.ceskaposta.cz", "www.o2.cz", "www.bazos.cz", "portal.office.com", "www.mpsv.cz",
              "www.csas.cz", "www.rb.cz", "www.zasilkovna.cz", "www.cez.cz"]


def main(out_path: str, per_side: int, seed: int) -> None:
    rng = random.Random(seed)
    with open(out_path, "w") as f:
        for p, (request, scam, legit, principle) in enumerate(PAIRS):
            for intended, scenario, hosts in (("scam", scam, SCAM_HOSTS), ("ordinary", legit, REAL_HOSTS)):
                guide = ("It is a scam: make it realistic and subtle, as real fraudsters write it, not cartoonish."
                         if intended == "scam" else "It is legitimate and harmless; it must look natural, not suspicious. Add nothing the situation does not "
                         "describe: no extra links, no short links, no new phone number, no app to install, no urgency.")
                for k in range(per_side):
                    channel, length = rng.choice(FORMS)
                    row = {"id": f"pair-{intended}-{p}-{k}", "intended": intended, "scenario": f"{scenario} (the request: {request})",
                           "brand": "a fitting real Czech company or institution", "channel": channel, "length": length,
                           "tone": rng.choice(TONES), "guide": f"{guide} {LINKS.format(host=rng.choice(hosts))}",
                           "principle": principle, "source": "synthetic-contrast", "hint": intended}
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
