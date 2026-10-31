# Third-party components

| Component | Where | Licence |
| --- | --- | --- |
| llama.cpp b11982 (official builds: Vulkan for Linux and Windows, Metal for macOS) | `helper/runtime/llama.cpp`, downloaded by `install/install.py` | MIT, `helper/runtime/llama.cpp/LICENSE` |
| Qwen3.5-2B (base of the verifier) | `helper/models/verifier` | Apache-2.0 |
| multilingual-e5-small (base of the screener) | `helper/models/screener` | MIT |
| Tesseract `ces.traineddata` (tessdata) | `helper/models/ocr` | Apache-2.0 |
| Atkinson Hyperlegible Next | `extension/fonts` | SIL OFL 1.1, `extension/fonts/OFL.txt` |
| PyTorch, Hugging Face Transformers, Pillow, zxing-cpp (QR codes) | installed by `install/install.py` | BSD-3-Clause, Apache-2.0, MIT-CMU, Apache-2.0 |

## ČOI list of risky e-shops

`helper/data/sources/coi-risky-sites-snapshot.json` is a dated snapshot of the list of
risky e-shops published by the Czech Trade Inspection Authority (Česká obchodní inspekce), from
https://coi.gov.cz/pro-spotrebitele/rizikove-e-shopy/. It is used under the ČOI open-data licence,
https://coi.gov.cz/pro-spotrebitele/otevrena-data/licence-otevrenych-dat/. A match is shown as a reason to check the
shop, not as proof of fraud.
