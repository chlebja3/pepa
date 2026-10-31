"""Build the scam test pages: invented Czech scams and legitimate look-alikes in the layouts seniors meet them in.

Every text here is written for testing only (no real messages, senders or domains; links go to .example) and is
never used for training. Layouts: webmail with the HTML e-mail in an iframe (as Horde/IMP shows it), webmail with
a plain-text body, chat bubbles, an SMS inbox and a plain web page. cases.json lists what each page should do;
tests/scam_pages_e2e.py opens them in Chromium with the extension.
"""
import html
import json
from pathlib import Path

HERE = Path(__file__).parent

# id, layout, expect ("warn" / "quiet"), sender or title, paragraphs (chat/sms: one message each)
CASES = [
    ("bank-phishing", "mail-iframe", "warn", "Bezpečnostní oddělení <podpora@bezpecnost-uctu.example>", [
        "Vážená klientko, vážený kliente,",
        "při pravidelné kontrole jsme zaznamenali neobvyklé přihlášení k Vašemu internetovému bankovnictví z neznámého zařízení. Z bezpečnostních důvodů byl Váš účet dočasně omezen.",
        "Pro obnovení přístupu je nutné do 24 hodin ověřit Vaši totožnost. Klikněte na tlačítko níže a zadejte přihlašovací údaje a číslo platební karty včetně kódu CVV.",
        "Pokud ověření neprovedete, bude účet trvale zablokován.",
        "Oddělení bezpečnosti klientů"]),
    ("energy-refund", "mail-iframe", "warn", "Zákaznické centrum energií <vraceni@preplatky-energie.example>", [
        "Dobrý den,",
        "na základě ročního vyúčtování Vám vznikl přeplatek za elektřinu ve výši 4 860 Kč. Vrácení přeplatku je možné pouze online.",
        "Pro připsání částky vyplňte ve formuláři číslo své platební karty, datum platnosti a bezpečnostní kód. Formulář je platný 48 hodin, poté nárok zaniká.",
        "S pozdravem, oddělení vyúčtování"]),
    ("ceo-invoice", "mail-plain", "warn", "Ing. Pavel Dvořák <reditel.dvorak@firma-mail.example>", [
        "Dobrý den, paní Kovářová,",
        "jsem teď na jednání a nemůžu telefonovat. Potřebuji, abyste ještě dnes uhradila zálohovou fakturu novému dodavateli, jinak přijdeme o zakázku. Částka je 186 400 Kč, číslo účtu 2700418823/2010.",
        "Prosím nikomu dalšímu o tom zatím neříkejte, je to důvěrné. Až to odešlete, pošlete mi potvrzení sem na e-mail.",
        "Díky, Pavel"]),
    ("inheritance", "mail-plain", "warn", "Advokátní kancelář Morris & Partners <legal.office@inherit-claims.example>", [
        "Vážený pane, vážená paní,",
        "kontaktujeme Vás ohledně dědictví po zesnulém klientovi naší kanceláře, který nese stejné příjmení jako Vy. Částka 2 450 000 EUR připadne státu, pokud se do 10 dnů nepřihlásí příbuzný.",
        "Pro zahájení převodu potřebujeme kopii Vašeho občanského průkazu a úhradu administrativního poplatku 390 EUR. Celá věc je zcela legální a diskrétní.",
        "S úctou, JUDr. Morris"]),
    ("parcel-email", "mail-iframe", "warn", "Doručovací služba <info@zasilky-doruceni.example>", [
        "Vaše zásilka č. CZ48219375 nemohla být doručena, protože nebylo uhrazeno poštovné 42 Kč.",
        "Zásilka bude vrácena odesílateli, pokud poplatek neuhradíte do 12 hodin. Pro zaplacení zadejte údaje z platební karty na stránce doručení.",
        "Děkujeme, Vaše doručovací služba"]),
    ("order-confirmation", "mail-iframe", "quiet", "Obchod Zahrada <objednavky@zahrada-obchod.example>", [
        "Dobrý den, děkujeme za Vaši objednávku č. 2026-118734.",
        "Objednané zboží: hrábě na listí, 2× pytel na bioodpad. Celkem 689 Kč, zaplaceno kartou při objednávce.",
        "Zásilku předáme dopravci do dvou pracovních dnů. Stav objednávky najdete po přihlášení ve svém účtu na našem webu.",
        "Tým Obchodu Zahrada"]),
    ("newsletter", "mail-iframe", "quiet", "Knihkupectví U Lípy <novinky@knihy-lipa.example>", [
        "Podzimní novinky z knihkupectví",
        "Tento měsíc jsme pro vás vybrali nové detektivky českých autorů a krásné knihy o houbaření. Ve čtvrtek 6. listopadu proběhne v prodejně autorské čtení s besedou.",
        "Členové věrnostního klubu mají na všechny novinky slevu 10 %. Odhlásit se z odběru můžete odkazem v patičce."]),
    # The same ordinary text; only the attachment's file type differs (checked by the extension, not by the model).
    ("invoice-attachment", "mail-plain", "warn", "Fakturace <fakturace@dodavatel.example>", [
        "Dobrý den,", "v příloze Vám zasíláme fakturu za služby v říjnu 2026. Splatnost je 14 dní od vystavení.", "S pozdravem, účtárna"]),
    ("invoice-pdf", "mail-plain", "quiet", "Fakturace <fakturace@dodavatel.example>", [
        "Dobrý den,", "v příloze Vám zasíláme fakturu za služby v říjnu 2026. Splatnost je 14 dní od vystavení.", "S pozdravem, účtárna"]),
    ("bank-notice", "mail-plain", "quiet", "Vaše banka <info@banka.example>", [
        "Vážený kliente,",
        "od 1. prosince upravujeme sazebník poplatků. Vedení účtu zůstává zdarma, změní se cena výběru z bankomatu jiné banky.",
        "Podrobnosti najdete po přihlášení do internetového bankovnictví nebo na pobočce. Nikdy Vás nebudeme žádat o zadání PINu či hesla e-mailem ani telefonem.",
        "Vaše banka"]),
    ("family-mail", "mail-plain", "quiet", "Jana Nováková <jana.novakova@posta.example>", [
        "Ahoj mami,",
        "v neděli přijedeme na oběd kolem dvanácté, děti se moc těší. Petr veze víno z Moravy a já upeču jablečný štrúdl.",
        "Kdybys něco potřebovala nakoupit, napiš mi to, zastavíme se cestou v obchodě.",
        "Pa, Jana"]),
    ("mami-whatsapp", "chat", "warn", "Neznámé číslo +420 7xx xxx 214", [
        "Ahoj mami, rozbil se mi telefon, tohle je moje nové číslo, starý si smaž.",
        "Potřebuju nutně zaplatit fakturu a z nového mobilu mi ještě nejde bankovnictví. Můžeš to za mě poslat? Je to 18 500 Kč, vrátím ti to zítra.",
        "Pošlu ti číslo účtu, ale prosím rychle, je to dnes splatné."]),
    ("marketplace-buyer", "chat", "warn", "Kupující Tomáš (bazar)", [
        "Dobrý den, mám zájem o vaši sedačku, beru ji za plnou cenu.",
        "Jsem teď v zahraničí, pošlu kurýra. Zaplatím přes bezpečnou platbu, tady máte odkaz, kde si peníze přijmete: platba-bezpecne.example/prijem",
        "Stačí tam vyplnit číslo vaší karty a kód ze zadní strany, aby vám to mohli připsat."]),
    ("fake-police", "chat", "warn", "Policie ČR - kpt. Novák", [
        "Dobrý den, tady kapitán Novák z Policie ČR, oddělení finanční kriminality.",
        "Zjistili jsme, že zaměstnanec vaší banky se pokouší vybrat vaše úspory. Abychom je ochránili, musíte je ještě dnes převést na bezpečný účet, který vám nadiktujeme.",
        "Nikomu v bance o tom neříkejte, jsou zapojení. Jde o utajované vyšetřování."]),
    ("romance", "chat", "warn", "Michael (seznámení)", [
        "Má drahá, každý den myslím jen na tebe. Brzy se konečně uvidíme.",
        "Bohužel mě na letišti zadrželi a chtějí clo za můj zavazadlo se zlatem, 3 200 dolarů. Moje karta tady nefunguje.",
        "Prosím, pošli mi peníze přes Western Union, hned jak přijedu, všechno ti vrátím. Miluju tě."]),
    ("family-chat", "chat", "quiet", "Rodina", [
        "Babi, posílám fotky z výletu, byli jsme na Sněžce!",
        "To jsou krásné fotky, ať se vám daří. Kdy přijedete?",
        "V sobotu odpoledne, vezmeme i psa."]),
    ("marketplace-ok", "chat", "quiet", "Kupující Eva (bazar)", [
        "Dobrý den, je sedačka ještě k dispozici?",
        "Mohla bych se na ni přijet podívat v pátek po páté? Zaplatila bych hotově při převzetí.",
        "Děkuji, adresu mi prosím pošlete."]),
    # Chat apps nest every bubble deeply, so each message is checked alone. Alone the openers are "nevím" and the
    # extension has to read them with the following messages (content.js, widen).
    ("mami-split", "chat-deep", "warn", "Neznámé číslo +420 7xx xxx 377", [
        "Ahoj mami, mám nové číslo",
        "Starý mobil mi spadl do vody.",
        "Můžeš mi dnes pomoct s jednou platbou? Mám zablokované bankovnictví, zítra ti to vrátím. Tátovi to prosím neříkej."]),
    ("bazar-split", "chat-deep", "quiet", "Kupující Jirka (bazar)", [
        "Dobrý den, mám dotaz k inzerátu.",
        "Je ten kočárek ještě k dispozici?",
        "Mohl bych se přijet podívat v sobotu dopoledne, zaplatil bych hotově."]),
    ("family-split", "chat-deep", "quiet", "Petr", [
        "Ahoj, tady Petr, jsem zpátky v Praze.",
        "Nechceš zítra zajít na kafe?",
        "Klidně odpoledne, kolem třetí u nádraží."]),
    ("sms-customs", "sms", "warn", "Celni-sprava", [
        "Vase zasilka ceka na celni odbaveni. Doplatte clo 39 Kc do 24h na celni-odbaveni.example jinak bude zasilka zlikvidovana."]),
    ("sms-toll", "sms", "warn", "DalnicniZnamka", [
        "Upozorneni: Vase vozidlo nema platnou dalnicni znamku. Pokuta 5000 Kc. Uhradte snizenou pokutu 200 Kc dnes na znamka-pokuta.example"]),
    ("sms-housing-aid", "sms", "warn", "MPSV-info", [
        "Mate narok na prispevek na bydleni 6 800 Kc. Pro vyplaceni potvrdte svou identitu prihlasenim do bankovnictvi na prispevek-mpsv.example"]),
    ("sms-doctor", "sms", "quiet", "Ordinace MUDr. Malá", [
        "Pripominame Vasi objednavku na preventivni prohlidku ve ctvrtek 6.11. v 9:30. V pripade zmeny volejte na ordinaci."]),
    ("sms-delivery-ok", "sms", "quiet", "Kuryr", [
        "Vase zasilka z obchodu Zahrada bude dorucena dnes mezi 14 a 16 h. Kuryr Vam pred prijezdem zavola."]),
    ("investment-ad", "web", "warn", "Senzační objev: jak si důchodci přivydělávají", [
        "Známý moderátor prozradil v živém vysílání tajemství, o kterém banky nechtějí, abyste věděli. Díky automatické obchodní platformě s umělou inteligencí vydělává přes 50 000 Kč týdně.",
        "Stačí jednorázový vklad 6 000 Kč a systém obchoduje s kryptoměnami za vás. Zisk je zaručený, riziko nulové.",
        "Registrace je otevřená jen dnes pro prvních 50 zájemců. Po registraci vám zavolá osobní poradce a pomůže nainstalovat aplikaci pro vzdálený přístup."]),
    ("tech-support", "web", "warn", "Systémové varování", [
        "VÁŠ POČÍTAČ BYL ZABLOKOVÁN. Zjistili jsme virus, který odcizuje vaše hesla a bankovní údaje.",
        "Nezavírejte tuto stránku a nevypínejte počítač. Ihned zavolejte technickou podporu na číslo +420 800 xxx xxx, technik se připojí k vašemu počítači a virus odstraní.",
        "Kód chyby: 0x80070570. Pokud nezavoláte do 5 minut, budou data smazána."]),
    ("fake-eshop", "web", "warn", "Výprodej zavíráme – vše za 90 % slevu", [
        "Zavíráme prodejnu, proto doprodáváme veškeré zboží se slevou až 90 %. Robotický vysavač nyní za 499 Kč místo 12 990 Kč.",
        "Platba pouze předem převodem na účet nebo kartou, dobírka není možná. Zbývají poslední 3 kusy, nabídka končí za 09:59 minut.",
        "Kontaktní adresu ani telefon neuvádíme z důvodu ochrany osobních údajů."]),
    ("news-about-scams", "web", "quiet", "Policie varuje před falešnými bankéři", [
        "Policisté v posledních týdnech evidují desítky případů, kdy podvodníci volají seniorům jako zaměstnanci banky nebo policie a přesvědčují je, aby převedli úspory na „bezpečný účet“.",
        "Banka ani policie nikdy nežádá převod peněz na jiný účet ani zadání údajů z karty. Pokud vám někdo takto volá, zavěste a zavolejte do své banky na číslo z její oficiální stránky.",
        "Případy podvodů hlaste na lince 158."]),
    ("municipal", "web", "quiet", "Obecní úřad – úřední hodiny", [
        "Obecní úřad bude ve čtvrtek 30. října uzavřen z důvodu školení zaměstnanců.",
        "Poplatek za svoz odpadu na příští rok je 900 Kč na osobu a lze jej zaplatit v hotovosti na úřadě nebo převodem na účet obce uvedený na úřední desce.",
        "Děkujeme za pochopení."]),
]

ATTACHMENTS = {"invoice-attachment": "faktura_2026_10.pdf.html", "invoice-pdf": "faktura_2026_10.pdf"}

STYLE = """body{font-family:Arial,sans-serif;margin:0;background:#f4f4f4;color:#222}
.top{background:#2d4b73;color:#fff;padding:10px 16px}
.list td{padding:6px 12px;border-bottom:1px solid #ddd}
#msgHeadersTable td{padding:4px 12px}#messageBody{background:#fff;margin:8px;padding:12px}
.chat{max-width:560px;margin:16px auto;background:#e5ddd5;padding:12px}
.bubble{background:#fff;border-radius:8px;padding:8px 12px;margin:8px 0;max-width:80%}
.sms{max-width:420px;margin:16px auto;background:#fff;padding:12px}.sms .msg{background:#e9e9eb;border-radius:14px;padding:10px 14px}
article{max-width:720px;margin:24px auto;background:#fff;padding:24px}"""


def page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="cs"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f'<style>{STYLE}</style></head><body>{body}</body></html>')


def attachment(case_id: str) -> str:
    name = ATTACHMENTS.get(case_id)
    return f'<tr><td>Přílohy:</td><td><a href="download.html?part=2" download="{name}">{name}</a> (14 kB)</td></tr>' if name else ''


def mail(case_id: str, sender: str, paragraphs: list, iframe: bool) -> str:
    subject = paragraphs[1][:60] + '…' if len(paragraphs) > 1 else paragraphs[0][:60]
    rows = ''.join(f'<tr><td>{s}</td><td>{t}</td></tr>' for s, t in
                   [('Fakturace', 'Faktura za říjen 2026'), ('Jana Nováková', 'Nedělní oběd'), (html.escape(sender.split('<')[0]), html.escape(subject))])
    headers = (f'<table id="msgHeadersTable"><tr><td>Od:</td><td>{html.escape(sender)}</td></tr>'
               f'<tr><td>Předmět:</td><td>{html.escape(subject)}</td></tr>' + attachment(case_id) + '</table>')
    text = ''.join(f'<p>{html.escape(p)}</p>' for p in paragraphs)
    if iframe:
        (HERE / f'{case_id}.part.html').write_text(page(sender, f'<div style="padding:8px">{text}</div>'))
        content = f'<div class="mimePartData"><iframe src="{case_id}.part.html" style="width:100%;height:520px;border:0"></iframe></div>'
    else:
        content = f'<div class="fixed">{text}</div>'
    return page('Mail :: Doručená pošta', f'<div class="top">Pošta</div><table class="list">{rows}</table>{headers}<div id="messageBody">{content}</div>')


def build() -> None:
    cases = []
    for case_id, layout, expect, who, paragraphs in CASES:
        if layout.startswith('mail'):
            doc = mail(case_id, who, paragraphs, layout == 'mail-iframe')
        elif layout == 'chat':
            doc = page(who, f'<div class="top">{html.escape(who)}</div><div class="chat">' +
                       ''.join(f'<div class="bubble" data-message>{html.escape(p)}</div>' for p in paragraphs) + '</div>')
        elif layout == 'chat-deep':
            doc = page(who, f'<div class="top">{html.escape(who)}</div><div class="chat">' +
                       ''.join(f'<div class="row"><div class="wrap"><div class="col"><div class="bubble" data-message>{html.escape(p)}</div></div></div></div>'
                               for p in paragraphs) + '</div>')
        elif layout == 'sms':
            doc = page(who, f'<div class="sms"><b>{html.escape(who)}</b>' + ''.join(f'<p class="msg">{html.escape(p)}</p>' for p in paragraphs) + '</div>')
        else:
            doc = page(who, f'<article><h1>{html.escape(who)}</h1>' + ''.join(f'<p>{html.escape(p)}</p>' for p in paragraphs) + '</article>')
        (HERE / f'{case_id}.html').write_text(doc)
        cases.append({'id': case_id, 'layout': layout, 'expect': expect})
    (HERE / 'cases.json').write_text(json.dumps(cases, indent=1))
    links = ''.join(f'<li><a href="{c["id"]}.html">{c["id"]}</a> · {c["layout"]} · {"podvod" if c["expect"] == "warn" else "běžné"}</li>' for c in cases)
    (HERE / 'index.html').write_text(page('Testovací stránky', f'<article><h1>Testovací stránky</h1><ul>{links}</ul></article>'))


if __name__ == '__main__':
    build()
