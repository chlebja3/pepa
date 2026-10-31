"""Local LLM verifier (fine-tuned Qwen3.5-2B, GGUF) behind the screener. Runs llama.cpp's server on loopback.

The screener routes a text here; the verifier decides and writes a short Czech reason for the senior. Confidence is
the margin used when evaluating the model and picking its thresholds: log-odds of the first "podvod" token against "bezne" and
"nevim", right after the prefilled answer start. Both thresholds are below zero: the model warns orange also when "podvod"
is only a strong runner-up, which is what lets it catch 9 of 10 scams.
"""
import json
import math
import re
from pathlib import Path
import socket
import subprocess
import time
import urllib.request

PREFIX = '{"verdikt": "'
SCAM = 'podvod", "duvod": "'  # continues PREFIX
# Margins picked on the dev half (training/tradeoff.py pick_recall), end to end behind the screener. Above WARN the text
# gets an orange warning: 90 % of dev scams; on the test exam 91.8 % of scams and 3.3 % of ordinary texts. Above DANGER
# it is red, a near-certain scam: 80 % of dev scams; on the test exam 81.1 % of scams and 1.9 % of ordinary texts.
WARN = -4.0
DANGER = -1.375
SYSTEM = """You check messages for scams on behalf of elderly Czech users. You get one message (e-mail, SMS, chat or web text), usually in Czech.
Scam = the sender uses deception to get money, login details, card data, personal data or access to a device.
Ordinary advertising, newsletters, genuine notifications, personal messages and articles ABOUT scams are not scams.
If the message is too short or vague to judge, answer "nevim".
Answer with JSON only. "duvod" is one short, plain Czech sentence for a senior: what exactly is suspicious, or why the message is fine."""


def free_port() -> int:
    """A free loopback port for llama-server (a fixed one could be taken, e.g. by a second browser profile)."""
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def post(port: int, path: str, body: dict, timeout: float = 60) -> dict:
    request = urllib.request.Request(f'http://127.0.0.1:{port}{path}', json.dumps(body).encode(), {'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def field(content: str, key: str) -> str:
    match = re.search(rf'"{key}": "((?:[^"\\]|\\.)*)', content)
    return match.group(1).strip() if match else ''


class Verifier:
    def __init__(self, server: Path, gguf: Path, threads: int = 4, threshold: float = WARN, extra: list = ()):
        self.threshold = threshold
        self.model_id = gguf.stem
        self.port = free_port()
        self.proc = subprocess.Popen([str(server), '-m', str(gguf), '-c', '4096', '-t', str(threads), '--host', '127.0.0.1',
                                      '--port', str(self.port), '--no-webui', '--log-disable', *extra],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))  # no console window on Windows
        for _ in range(240):
            try:
                if json.loads(urllib.request.urlopen(f'http://127.0.0.1:{self.port}/health', timeout=2).read()).get('status') == 'ok': break
            except OSError: pass
            if self.proc.poll() is not None: raise RuntimeError('llama-server exited')
            time.sleep(0.5)
        self.first = {v: post(self.port, '/tokenize', {'content': PREFIX + v})['tokens'][len(post(self.port, '/tokenize', {'content': PREFIX})['tokens'])] for v in ('podvod', 'bezne', 'nevim')}
        assert len(set(self.first.values())) == 3, self.first
        self.head = f'<|im_start|>system\n{SYSTEM}<|im_end|>\n<|im_start|>user\n'
        self.head_n = len(post(self.port, '/tokenize', {'content': self.head})['tokens'])
        self.rewarm = False
        self.warm()

    def warm(self) -> None:
        """Evaluate the shared system prompt alone, so llama-server keeps a context checkpoint at its end.

        Qwen3.5 has recurrent layers, whose state cannot be cut back to a common prefix; without this checkpoint every
        text re-reads the 135-token system prompt (about 3x the prompt time of a short message)."""
        post(self.port, '/completion', {'prompt': self.head, 'n_predict': 1, 'temperature': 0, 'cache_prompt': True})

    def prompt(self, text: str) -> str:
        return f'{self.head}{text}<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n{PREFIX}'

    def check(self, text: str, explain: bool = True) -> dict:
        """The verdict, and for a warning also its explanation unless explain is False (then explain() writes it later)."""
        start = time.perf_counter()
        # The verdict is the first token: decide on it alone and write the explanation only for scams (about half the
        # CPU time). The explanation reuses the cached prompt, so it only adds the generation.
        out = post(self.port, '/completion', {'prompt': self.prompt(text), 'n_predict': 1, 'temperature': 0, 'n_probs': 20, 'cache_prompt': True})
        top = {t['id']: t['logprob'] for t in out['completion_probabilities'][0]['top_logprobs']}
        lp = {v: top.get(i, -30.0) for v, i in self.first.items()}
        margin = lp['podvod'] - math.log(math.exp(lp['bezne']) + math.exp(lp['nevim']))
        verdict = max(lp, key=lp.get)
        evicted = out['timings']['cache_n'] < self.head_n - 8
        reason = advice = ''
        self.rewarm = evicted  # after the explanation, which reuses this prompt
        if margin > self.threshold and explain: reason, advice = self.explain(text)
        elif not (margin > self.threshold) and evicted: self.warm()
        return {'verdict': verdict, 'margin': round(margin, 2), 'scam': margin > self.threshold, 'danger': margin > DANGER,
                'reason': reason, 'advice': advice, 'elapsed_ms': round((time.perf_counter() - start) * 1000)}

    def explain(self, text: str) -> tuple:
        """Reason and advice for a warning. Below zero the model's own first choice may be "bezne"; the verdict is fixed
        to "podvod" so that the reason says what is suspicious instead of why the message is fine. Newer models also
        write "rada": what to do now, fitted to this message."""
        out = post(self.port, '/completion', {'prompt': self.prompt(text) + SCAM, 'n_predict': 200, 'temperature': 0, 'cache_prompt': True,
                                              'stop': ['"}', '<|im_end|>']})
        if self.rewarm: self.warm()
        self.rewarm = False
        return tuple(field(SCAM + out['content'], key) for key in ('duvod', 'rada'))

    def close(self) -> None:
        # Nothing to save; a terminated Vulkan llama-server took over 6 s to exit and kept its video memory meanwhile.
        self.proc.kill()
        self.proc.wait()
