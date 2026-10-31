"""Checks a text with the same models and steps as the browser extension, without a browser.

usage: helper/.venv/bin/python helper/check.py "text of a message"   (Windows: helper\\.venv\\Scripts\\python helper\\check.py "...")
       helper/.venv/bin/python helper/check.py < message.txt
"""
import sys
import threading

import native_host

LEVELS = {'danger': 'PODVOD (červené varování)', 'caution': 'MOŽNÝ PODVOD (oranžové varování)'}


def main() -> None:
    text = ' '.join(sys.argv[1:]) or sys.stdin.read()
    text = text.strip()[:native_host.MAX_TEXT]
    if not text: sys.exit(__doc__)
    print('Načítám modely...', file=sys.stderr, flush=True)
    engine = native_host.Engine()
    engine.ready.wait()
    if engine.state['verifier'] != 'ready': sys.exit(f'Model se nepodařilo načíst: {engine.state["error"]}')
    result = engine.analyze(text, threading.Lock())
    engine.verifier.close()
    if result['status'] != 'warning':
        print(f'Bez varování ({result["elapsed_ms"] / 1000:.1f} s). PEPA nenašel dost znaků podvodu; to není záruka bezpečnosti.')
        return
    print(f'{LEVELS[result["level"]]} ({result["elapsed_ms"] / 1000:.1f} s)')
    print(f'Proč: {result["message"]}')
    print(f'Co teď udělat: {result["advice"]}')


if __name__ == '__main__':
    main()
