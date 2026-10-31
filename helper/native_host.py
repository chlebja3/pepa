"""Native messaging host: runs the models for the browser extension.

Chrome starts it on demand (chrome.runtime.connectNative) and keeps it while the extension's background worker holds
the port, so every window and tab shares this one process and one copy of the models. No network port is opened.
Frames: 4-byte native-endian length + UTF-8 JSON in both directions. Requests carry an id, replies echo it.
stdout carries only frames; diagnostics go to stderr, which Chrome writes to its own log. Never log message content.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import struct
import sys
import threading

import backend
from categories import ADVICE, category_from_reason
from link_signals import analyze_links
from ocr import OCR
from page_signals import analyze_page
from screener import Screener
from text_signals import with_signals
from verifier import Verifier

if sys.platform == 'win32':
    import msvcrt

ROOT = Path(__file__).resolve().parent
MAX_TEXT = 20000  # the extension sends at most this; the screener reads it all in chunks, the verifier one chunk
MAX_IMAGE_TEXT = 3000
SIGNALS = False  # pattern hints for the verifier; only a verifier trained with them reads them well
LINK_MARKS = False  # "[odkaz: host]" for QR codes, the same switch as LINK_TARGETS in extension/content.js
FORGED_MARK = re.compile(r'\[(odkaz|odes[ií]latel)\s*:', re.I)  # a mark printed in the image itself is the scammer's, not ours
EXPLAINING = {'message': 'Píšu vysvětlení, co přesně je na zprávě podezřelé…', 'explaining': True}
QUIET = {'status': 'no_signal', 'category': 'ordinary', 'title': 'Bez zachyceného signálu', 'message': 'To není potvrzení bezpečnosti zprávy.', 'advice': ''}
PENDING = {'status': 'pending', 'title': 'Možný podvod – ještě ověřuji', 'message': 'Zpráva má některé znaky podvodu. Během několika sekund ji prověřím podrobněji.',
           'advice': 'Zatím na nic neklikejte, nic neplaťte a nesdělujte žádné údaje.'}


class Engine:
    """The screener and verifier stages and their replies, on native llama.cpp and PyTorch."""

    def __init__(self):
        self.state = {'screener': 'loading', 'verifier': 'loading', 'progress': 0, 'error': None, 'native': True}
        self.ready = threading.Event()
        self.screener = self.verifier = self.ocr = None
        self.last = ('', '')  # the latest warned text and what the verifier read, for explain()
        threading.Thread(target=self.load, daemon=True).start()

    def load(self) -> None:
        config = backend.choose(ROOT)
        self.state.update(backend=config['name'], threads=config['threads'])
        try:
            self.screener = Screener(ROOT / 'models/screener/scr-e5-fp', threads=2)
            self.state['screener'] = 'ready'
            try: self.verifier = Verifier(config['server'], config['gguf'], config['threads'], extra=config['args'])
            except RuntimeError:
                if config['name'] == 'cpu': raise
                print(f'{config["name"]} failed, using the CPU', file=sys.stderr, flush=True)  # e.g. video memory taken by a game
                config = backend.cpu(ROOT)
                self.state['backend'] = 'cpu'
                self.verifier = Verifier(config['server'], config['gguf'], config['threads'], extra=config['args'])
            self.state.update(verifier='ready', progress=1)
        except Exception as error:
            self.state.update(error=str(error), **{k: 'error' for k in ('screener', 'verifier') if self.state[k] == 'loading'})
            raise
        finally:
            self.ready.set()

    def screen(self, text: str) -> tuple:
        result = self.screener.analyze(text)
        score, focus = result.pop('score'), result.pop('focus')
        elapsed_ms = result['elapsed_ms']
        if score < self.screener.threshold: return {**QUIET, 'elapsed_ms': elapsed_ms}, None
        # Only confident screener flags warn at once; the rest is verified quietly.
        return {**PENDING, 'category': 'other', 'alarm': score >= self.screener.alarm, 'elapsed_ms': elapsed_ms}, focus

    def analyze(self, text: str, screen_lock: threading.Lock, explain: bool = True) -> dict:
        """With explain False a warning comes back as soon as the verdict is known, with a general reason; explain()
        then writes the reason for this text (the extension shows the warning about 2.5x sooner on a CPU)."""
        with screen_lock: screened, focus = self.screen(text)
        if focus is None: return screened
        verified = with_signals(focus) if SIGNALS else focus
        checked = self.verifier.check(verified, explain)
        elapsed_ms = screened['elapsed_ms'] + checked['elapsed_ms']
        # "unclear": the verifier answered "nevim" (too little to judge); the extension then checks a larger context.
        if not checked['scam']: return {**screened, **QUIET, 'elapsed_ms': elapsed_ms, 'unclear': checked['verdict'] == 'nevim'}
        self.last = (text, verified)
        return {**screened, 'status': 'warning', 'level': 'danger' if checked['danger'] else 'caution', 'elapsed_ms': elapsed_ms,
                **(self.reply(checked['reason'], checked['advice']) if explain else {**self.reply('', ''), **EXPLAINING})}

    def explain(self, text: str, screen_lock: threading.Lock) -> dict:
        if self.last[0] == text: verified = self.last[1]
        else:
            with screen_lock: focus = self.screener.analyze(text)['focus']
            verified = with_signals(focus) if SIGNALS else focus
        return self.reply(*self.verifier.explain(verified))

    @staticmethod
    def reply(reason: str, advice: str) -> dict:
        category = category_from_reason(reason)
        title, message, advice_default = ADVICE[category]
        return {'category': category, 'title': title, 'message': reason or message, 'advice': advice or advice_default}

    def image(self, data: str, screen_lock: threading.Lock) -> dict:
        self.ocr = self.ocr or OCR()
        extracted = self.ocr.read(base64.b64decode(data, validate=True))
        text = FORGED_MARK.sub(r'(\1:', ' '.join(extracted['text'].split()))
        hosts = extracted['links']
        # A QR code's target goes through the same hostname checks as a link on the page.
        checked = analyze_links({'links': [{'hostname': h, 'display_hostname': '', 'userinfo_hostname': ''} for h in hosts]})['results'] if hosts else []
        qr_warning = next((r for r in checked if r['status'] == 'warning'), None)
        if len(text) < 25 or extracted['ocr_confidence'] < 45:
            if qr_warning: return {**qr_warning, 'source': 'local_qr', 'transcript': text}
            return {'status': 'skipped', 'reason': 'Text v obrázku nelze spolehlivě přečíst.', 'source': 'local_ocr'}
        if LINK_MARKS: text += ''.join(f' [odkaz: {h}]' for h in hosts)
        if len(text) > MAX_IMAGE_TEXT: return {'status': 'skipped', 'reason': 'Obrázek obsahuje příliš mnoho textu pro tento prototyp.', 'source': 'local_ocr'}
        result = self.analyze(text, screen_lock)
        if qr_warning and result['status'] != 'warning': result = {**qr_warning, 'elapsed_ms': result.get('elapsed_ms', 0)}
        return {**result, 'source': 'local_ocr', 'transcript': text, 'ocr_confidence': extracted['ocr_confidence']}


def read_frame(stream) -> dict | None:
    raw = stream.read(4)
    if len(raw) < 4: return None
    return json.loads(stream.read(struct.unpack('=I', raw)[0]))


def main() -> None:
    if sys.platform == 'win32':  # frames are binary: no newline translation
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    sys.stdout = sys.stderr  # a stray print must never corrupt the frame stream
    write_lock, screen_lock = threading.Lock(), threading.Lock()
    engine = Engine()
    # Screening never waits for the verifier; one model check at a time across all tabs (they share the CPU cores).
    screen_pool, model_pool = ThreadPoolExecutor(1), ThreadPoolExecutor(1)

    def reply(id_: int, result: dict) -> None:
        raw = json.dumps({'id': id_, **result}, ensure_ascii=False).encode()
        with write_lock:
            stdout.write(struct.pack('=I', len(raw)) + raw)
            stdout.flush()

    def handle(message: dict) -> dict:
        op = message.get('op')
        if op == 'status': return dict(engine.state)
        engine.ready.wait()
        if engine.state['verifier'] != 'ready': raise RuntimeError('Model se nepodařilo načíst.')
        if op == 'links': return analyze_links({'links': message['links']})
        if op == 'page': return analyze_page(message['page'])
        if op == 'prepare': return {'ok': True}
        text = message.get('text')
        if op in ('screen', 'analyze', 'explain') and not (isinstance(text, str) and 1 <= len(text) <= MAX_TEXT): raise ValueError('Neplatný požadavek.')
        if op == 'screen':
            with screen_lock: return engine.screen(text)[0]
        if op == 'analyze': return engine.analyze(text, screen_lock, not message.get('early'))
        if op == 'explain': return engine.explain(text, screen_lock)
        if op == 'image': return engine.image(message['image'], screen_lock)
        raise ValueError('Neplatný požadavek.')

    def run(message: dict) -> None:
        try: reply(message['id'], handle(message))
        except Exception as error:
            print(f'{message.get("op")}: {type(error).__name__}', file=sys.stderr, flush=True)
            reply(message['id'], {'error': str(error) if isinstance(error, (ValueError, RuntimeError)) else 'Lokální model není dostupný.'})

    while (message := read_frame(stdin)) is not None:
        op = message.get('op')
        if op in ('analyze', 'explain', 'image'): model_pool.submit(run, message)
        elif op == 'screen': screen_pool.submit(run, message)
        else: threading.Thread(target=run, args=(message,), daemon=True).start()
    # Chrome closed the port (browser exit or extension reload): stop llama-server with us.
    if engine.verifier: engine.verifier.close()
    os._exit(0)


if __name__ == '__main__':
    main()
