"""Plays the scammer on examples/podvodnik.html in Chromium with the extension, as a juror would.

For every app (chat, e-mail, bazar, social network) it plays the prepared scam and the prepared ordinary conversation,
and it also types a few new messages that are in no list, the way a juror improvising a scam would. A case passes
when PEPA warns on a scam and stays quiet on an ordinary message.
"""
import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from scam_pages_e2e import INSTALL, PROFILE, ROOT, STATE

URL = 'http://127.0.0.1:8766/podvodnik.html'
# Messages written for this test only, not the page's inspiration: (app, expect, fields to fill)
TYPED = [
    ('chat', 'warn', {'sender': '+420 731 555 210', 'text': 'Babi, to jsem já, Kuba. Ztratil jsem peněženku i s kartou a nutně potřebuju poslat 6 000 Kč na nájem. Pošli to prosím na účet mého kamaráda, vrátím ti to v pátek. A nikomu to neříkej, mamka by se zlobila.'}),
    ('chat', 'quiet', {'sender': '+420 731 555 210', 'text': 'Babi, v sobotu ti přijedu pomoct s oknama. Přivezu i ten žebřík od táty, tak kolem desáté.'}),
    ('mail', 'warn', {'mfrom': 'Finanční správa <info@danove-preplatky.example>', 'msubject': 'Vrácení přeplatku na dani',
                      'text': 'Dobrý den,\n\nna základě Vašeho daňového přiznání Vám vznikl nárok na vrácení přeplatku ve výši 4 870 Kč. Pro vyplacení je nutné do 48 hodin potvrdit číslo Vaší platební karty na stránce https://danove-preplatky.example/vraceni.\n\nPo uplynutí lhůty nárok zaniká.'}),
    ('bazar', 'warn', {'sender': 'Martina P.', 'text': 'Dobrý den, kolo beru, posílám kurýra DPD. Platba proběhne přes ověřenou službu, stačí kliknout sem a zadat údaje karty pro přijetí peněz: overena-platba-dpd.example/prijem'}),
    ('social', 'warn', {'author': 'Investice pro každého', 'sponsored': True,
                        'text': 'Česká vláda spustila tajný program pro občany: vložte 5 000 Kč a umělá inteligence vám každý měsíc vydělá až 80 000 Kč. Garantovaný výnos bez rizika, místa jsou omezená. Zaregistrujte se dnes a náš finanční poradce vám zavolá.'}),
]


def wait_final(page, seconds: float, settle: float) -> tuple[bool, str, float]:
    """Same end condition as scam_pages_e2e: verified cards with their reason, or a quiet check for `settle` seconds."""
    start = time.time()
    state, changed = None, start
    while time.time() - start < seconds:
        now = page.evaluate(STATE)
        if now != state: state, changed = now, time.time()
        cards = state['cards'] if state else []
        if cards and not any(c['pending'] or c['explaining'] for c in cards): break
        if not cards and state and 'zkontrolováno' in state['status'] and time.time() - changed > settle: break
        time.sleep(0.2)
    final = [c for c in (state['cards'] if state else []) if not c['pending']]
    return bool(final), final[0]['why'] if final else (state and state['status'] or ''), time.time() - start


def open_app(page, app: str) -> None:
    page.goto(f'{URL}#{app}')
    page.reload()  # a hash change alone does not reload the page and its PEPA state
    page.wait_for_selector('#app > *')


def type_message(page, fields: dict) -> None:
    for key, value in fields.items():
        if key == 'sponsored': page.check('#sponsored')
        else: page.fill(f'#{key}', value)
    page.click('#sendBtn')


def main(args: argparse.Namespace) -> None:
    server = subprocess.Popen([sys.executable, '-m', 'http.server', '8766', '--bind', '127.0.0.1', '-d', str(ROOT / 'examples')],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results = []
    try:
        shutil.rmtree(PROFILE, ignore_errors=True)
        subprocess.run([sys.executable, INSTALL, '--register', PROFILE / 'NativeMessagingHosts'], check=True, stdout=subprocess.DEVNULL)
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                PROFILE, channel='chromium', headless=not args.show, viewport={'width': 1440, 'height': 900},
                args=[f'--disable-extensions-except={args.extension}', f'--load-extension={args.extension}'])
            worker = context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
            start = time.time()
            while worker.evaluate("engine('status').then(s => s.screener + ' ' + s.verifier, e => 'error ' + e.message)") != 'ready ready':
                assert time.time() - start < 300, 'models did not load'
                time.sleep(1)
            page = context.new_page()
            cases = [(app, expect, 'prepared', None) for app in ('chat', 'mail', 'bazar', 'social') for expect in ('warn', 'quiet')]
            cases += [(app, expect, 'typed', fields) for app, expect, fields in TYPED]
            cases = [c for c in cases if not args.apps or c[0] in args.apps]
            for app, expect, kind, fields in cases:
                open_app(page, app)
                if fields: type_message(page, fields)
                else: page.click('#playScam' if expect == 'warn' else '#playOk')
                warned, why, took = wait_final(page, args.seconds, args.settle)
                ok = warned == (expect == 'warn')
                results.append(ok)
                page.screenshot(path=str(ROOT / '.local' / f'playground-{app}-{kind}-{expect}.png'))
                print(f"{'OK  ' if ok else 'FAIL'} {app:6} {kind:8} expect {expect:5} {took:5.1f}s {why}", flush=True)
            context.close()
    finally:
        server.terminate()
        shutil.rmtree(PROFILE, ignore_errors=True)
    print(f'{sum(results)}/{len(results)} correct')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=float, default=60, help='time limit per case')
    parser.add_argument('--settle', type=float, default=10, help='quiet case: seconds without change after a check')
    parser.add_argument('--extension', type=Path, default=ROOT / 'extension', help='unpacked extension folder')
    parser.add_argument('--apps', nargs='*', help='only these apps (chat, mail, bazar, social)')
    parser.add_argument('--show', action='store_true', help='visible browser window')
    main(parser.parse_args())
