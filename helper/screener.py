"""Fast screener (system 1) on the laptop CPU: small fine-tuned encoder (multilingual-e5-small).

It never warns alone; it only decides which texts the verifier LLM reads. Score = margin (logit of scam against
ordinary and not enough info). Long texts are scored in overlapping chunks and the highest margin counts, so a scam
paragraph inside a long e-mail is not diluted.
"""
import json
from pathlib import Path
import time

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

CHUNK, STEP, BATCH = 1000, 800, 16


class Screener:
    max_chars = 20000

    def __init__(self, folder: Path, threads: int = 4):
        torch.set_num_threads(threads)
        config = json.loads((folder / 'screener-config.json').read_text())
        self.threshold = config['threshold']
        self.alarm = config['alarm']  # above it the warning shows before the verifier decides
        self.model_id = folder.name
        self.tokenizer = AutoTokenizer.from_pretrained(folder)
        self.model = AutoModelForSequenceClassification.from_pretrained(folder).eval()

    @torch.no_grad()
    def margin(self, text: str) -> tuple[float, str]:
        """Highest chunk margin and that chunk (the passage the verifier reads, which keeps it fast on long e-mails)."""
        chunks = [text[i:i + CHUNK] for i in range(0, max(1, len(text) - CHUNK + STEP), STEP)]
        logits = torch.cat([self.model(**self.tokenizer(chunks[i:i + BATCH], truncation=True, max_length=384, padding=True,
                                                        return_tensors='pt')).logits for i in range(0, len(chunks), BATCH)])
        margins = logits[:, 0] - torch.logsumexp(logits[:, 1:], dim=-1)
        best = int(margins.argmax())
        return margins[best].item(), chunks[best]

    def analyze(self, text: str) -> dict:
        start = time.perf_counter()
        score, focus = self.margin(text)
        return {'status': 'no_signal', 'category': 'ordinary', 'title': 'Bez zachyceného signálu',
                'message': 'To není potvrzení bezpečnosti zprávy.', 'advice': '',
                'elapsed_ms': round((time.perf_counter() - start) * 1000), 'model': self.model_id, 'experimental': True,
                'score': round(score, 3), 'focus': focus}
