"""Open every test page (tests/pages, see build.py) in Chromium with the extension.

The extension uses the native messaging helper (native_host.py), registered for the test profile only. A page passes when
the extension warns on a scam ("warn") or stays quiet on a legitimate page ("quiet") within the time limit. Prints
the time to the first (provisional, screener) flag, the time to the verified warning, the time until its reason is
written (the final state) and the reason shown, and saves a screenshot of each page to tests/pages/shots.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / 'tests/pages'
# One reused profile, wiped at each start: the browser copies the 1.3 GB model into it, and a temporary profile per run
# would be left behind whenever a run is killed.
PROFILE = ROOT / '.local/e2e-profile'
INSTALL = ROOT / 'install/install.py'
STATE = """() => { const h=document.querySelector('ai-hlidac-panel'); if(!h) return null; const r=h.shadowRoot;
  return {status:r.getElementById('status').textContent,
          cards:[...r.querySelectorAll('#warnings section')].map(c=>({why:c.querySelector('.why').textContent, pending:c.classList.contains('pending'), explaining:!c.classList.contains('pending') && Boolean(c.querySelector('.progress')), danger:c.classList.contains('danger')}))}; }"""


def run_case(page, case: dict, seconds: float, settle: float) -> dict:
    """Waits for the final state: verified cards (none pending) or, on a quiet page, no change for `settle` seconds."""
    start = time.time()
    page.goto(f'http://127.0.0.1:8765/{case["id"]}.html')
    state, changed, first_flag, verified = None, start, None, None
    while time.time() - start < seconds:
        now = page.evaluate(STATE)
        if now != state: state, changed = now, time.time()
        cards = state['cards'] if state else []
        if cards and first_flag is None: first_flag = time.time() - start
        if cards and verified is None and not any(c['pending'] for c in cards): verified = time.time() - start
        if cards and not any(c['pending'] or c['explaining'] for c in cards): break
        if not cards and state and 'zkontrolováno' in state['status'] and time.time() - changed > settle: break
        time.sleep(0.2)
    page.screenshot(path=str(PAGES / 'shots' / f'{case["id"]}.png'))
    final = [c for c in (state['cards'] if state else []) if not c['pending']]
    warned = bool(final)
    return {**case, 'warned': warned, 'ok': warned == (case['expect'] == 'warn'), 'seconds': round(time.time() - start, 1),
            'flag': first_flag and round(first_flag, 1), 'verified': verified and round(verified, 1), 'status': state and state['status'], 'reason': final[0]['why'] if warned else '',
            'level': ('red' if any(c['danger'] for c in final) else 'orange') if warned else ''}


def main(args: argparse.Namespace) -> None:
    cases = json.loads((PAGES / 'cases.json').read_text())
    if args.only: cases = [c for c in cases if c['id'] in args.only]
    (PAGES / 'shots').mkdir(exist_ok=True)
    server = subprocess.Popen([sys.executable, '-m', 'http.server', '8765', '--bind', '127.0.0.1', '-d', str(PAGES)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results = []
    try:
        shutil.rmtree(PROFILE, ignore_errors=True)
        subprocess.run([sys.executable, INSTALL, '--register', PROFILE / 'NativeMessagingHosts'], check=True, stdout=subprocess.DEVNULL)
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                PROFILE, channel='chromium', headless=not args.show, viewport={'width': 1280, 'height': 900},
                args=[f'--disable-extensions-except={args.extension}', f'--load-extension={args.extension}'])
            worker = context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
            # Times are for a running browser with the models loaded.
            start = time.time()
            while worker.evaluate("engine('status').then(s => s.screener + ' ' + s.verifier, e => 'error ' + e.message)") != 'ready ready':
                assert time.time() - start < 300, 'models did not load'
                time.sleep(1)
            engine = worker.evaluate("engine('status')")
            print(f'models ready after {time.time() - start:.1f}s, backend: {engine.get("backend", "")}', flush=True)
            page = context.new_page()
            for case in cases:
                r = run_case(page, case, args.seconds, args.settle)
                results.append(r)
                print(f"{'OK  ' if r['ok'] else 'FAIL'} {r['id']:20} {r['layout']:11} expect {r['expect']:5} flag {str(r['flag'] or '-'):>4}s warn {str(r['verified'] or '-'):>4}s final {r['seconds']:5.1f}s {r['level']:6} {r['reason'] or r['status']}", flush=True)
            context.close()
    finally:
        server.terminate()
        shutil.rmtree(PROFILE, ignore_errors=True)
    for expect in ('warn', 'quiet'):
        group = [r for r in results if r['expect'] == expect]
        flags = sorted(r['flag'] for r in group if r['flag'])
        verified = sorted(r['verified'] for r in group if r['warned'] and r['verified'])
        finals = sorted(r['seconds'] for r in group if r['warned'])
        print(f"{expect}: {sum(r['ok'] for r in group)}/{len(group)} correct, provisionally flagged {len(flags)}"
              + (f", median time to flag {flags[len(flags) // 2]}s" if flags else '')
              + (f", median time to the warning {verified[len(verified) // 2]}s, to its reason {finals[len(finals) // 2]}s" if verified else ''))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', nargs='*', help='case ids')
    parser.add_argument('--seconds', type=float, default=40, help='time limit per page')
    parser.add_argument('--settle', type=float, default=10, help='quiet page: seconds without change after a check')
    parser.add_argument('--extension', type=Path, default=ROOT / 'extension', help='unpacked extension folder')
    parser.add_argument('--show', action='store_true', help='visible browser window')
    parser.add_argument('--pages', type=Path, default=PAGES, help='folder with the pages and their cases.json (e.g. examples)')
    args = parser.parse_args()
    PAGES = args.pages.resolve()
    main(args)
