# Model files

The models are not part of the source tree because of their size (about 1.7 GB in total). Put them at these paths inside `helper/`;
`MODELS.sha256` lists their checksums (check with `sha256sum -c MODELS.sha256`).

| Path | Used by | Size |
| --- | --- | --- |
| `models/screener/scr-e5-fp/` | native helper: screener (fine-tuned multilingual-e5-small) | 466 MB |
| `models/verifier/qwen-pair-q4_k_m.gguf` | native helper: verifier (fine-tuned Qwen3.5-2B, Q4_K_M) | 1.3 GB |
| `models/ocr/ces.traineddata` | native helper: Czech OCR | 4 MB |

They are published at https://huggingface.co/chlebajz/pepa. `install.py` downloads and checks them (the installer can be restarted after an interruption). Set `PEPA_MODELS` to use another mirror.
