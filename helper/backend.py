"""Pick the fastest llama.cpp setup for this computer: a dedicated GPU through Vulkan if there is one, else the CPU.

Measured on a laptop with an i7-10850H (6 cores), Intel UHD and a GeForce MX250 (2 GB), Q4_K_M. Medians over 71 real
public texts (verdict, explanation), and over the 17 scam test pages in Chromium (tests/scam_pages_e2e.py: warning shown,
its reason written; the warning shows with the verdict and the reason follows in place):
  CPU, 6 threads              verdict 1.9 s, explanation +2.8 s; pages: warning 2.1 s, reason 6.3 s
  MX250, Vulkan, all layers   verdict 1.4 s, explanation +1.7 s; pages: warning 1.7 s, reason 3.8 s (1.4 GB of video memory)
  Intel UHD, Vulkan           7.7 s per verdict: integrated GPUs are slower than the cores, so they are left alone
The screener takes about 60 ms per text on the CPU. PEPA_CPU=1 keeps the verifier on the CPU.
CPU: prompt reading is compute-bound, so threads = physical cores (4 instead of 6 threads: +20 %). Q4_K_M beats Q4_0 and
Q8_0; flash attention, smaller micro-batches and MTP speculative decoding (the base model's draft head, 29-41 % accepted)
do not help. --cache-ram 0: llama-server's prompt cache in RAM doubles the memory (4.1 -> 2.1 GB) and gains nothing,
because verifier.py keeps its own checkpoint after the system prompt.
install.py puts the official llama.cpp b11982 build for the system into runtime/llama.cpp: Vulkan on Linux and Windows
(it also runs inside the snap Chromium sandbox), Metal on macOS. The CPU uses the same binary with --device none.
"""
import os
from pathlib import Path
import re
import subprocess
import sys

GPU_MIN_FREE_MB = 1700  # the verifier took 1.4 GB on the MX250
DEDICATED = re.compile(r'NVIDIA|Radeon RX|Radeon Pro|Arc\(TM\) [AB]|Arc [AB]|Apple', re.I)  # integrated PC GPUs are slower than the CPU;
# Apple Silicon shares fast memory with its GPU, so Metal wins there
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)  # Windows: no console window pops up next to the browser
COMMON = ['-fa', 'on', '--cache-ram', '0', '-np', '1']


def physical_cores() -> int:
    if sys.platform == 'darwin': return os.cpu_count() or 1  # Apple Silicon has no hyper-threading
    if not Path('/proc/cpuinfo').exists(): return max(1, (os.cpu_count() or 2) // 2)
    cores, current = set(), {}
    for line in Path('/proc/cpuinfo').read_text().splitlines() + ['']:
        key, _, value = line.partition(':')
        if not line.strip():
            if current: cores.add((current.get('physical id'), current.get('core id')))
            current = {}
        else: current[key.strip()] = value.strip()
    return max(1, len(cores))


def dedicated_gpu(server: Path) -> str | None:
    """The GPU with the most free memory among the dedicated ones that fit the verifier, e.g. 'Vulkan1' or 'MTL0'."""
    out = subprocess.run([server, '--list-devices'], capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW).stdout
    devices = re.findall(r'^\s*((?:Vulkan|MTL)\d+): (.+) \((\d+) MiB, (\d+) MiB free\)', out, re.M)
    usable = [(int(free), device) for device, name, _, free in devices if DEDICATED.search(name) and int(free) >= GPU_MIN_FREE_MB]
    return max(usable)[1] if usable else None


def server(root: Path) -> Path:
    for folder in ('runtime/llama.cpp', 'runtime/vulkan'):
        path = root / folder / ('llama-server.exe' if sys.platform == 'win32' else 'llama-server')
        if path.exists(): return path
    return root.parent / 'tools/llama.cpp/build/bin/llama-server'  # development tree


def cpu(root: Path) -> dict:
    return {'name': 'cpu', 'server': server(root), 'gguf': root / 'models/verifier/qwen-pair-q4_k_m.gguf',
            'threads': min(8, physical_cores()), 'args': ['--device', 'none', *COMMON]}


def choose(root: Path) -> dict:
    config = cpu(root)
    if os.environ.get('PEPA_CPU'): return config  # e.g. the GPU is needed by something else
    device = dedicated_gpu(config['server'])
    if device is None: return config
    return {**config, 'name': f'gpu:{device}', 'args': ['--device', device, '-ngl', '99', *COMMON]}
