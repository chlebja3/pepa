"""Installs PEPA's local helper on Linux, Windows or macOS (Apple Silicon), for the current user and without admin rights.

1. Python runtime in .venv (PyTorch for the CPU, Transformers, Pillow, zxing-cpp for QR codes), made by uv.
2. Model files from MODELS_URL, checked against MODELS.sha256; an interrupted download simply resumes.
3. The official llama.cpp build for this system into runtime/llama.cpp, checked against its published checksum.
4. Registration of the helper with Chrome, Edge, Brave, Chromium and Vivaldi (native messaging).
The browser extension itself is then loaded once by hand; the installer says how.

usage: install.py                     everything above
       install.py --register DIR...   only write the helper manifest into these NativeMessagingHosts directories
       install.py --uninstall         remove the registration from all browsers
Run it through install.sh (Linux, macOS) or install.cmd (Windows), which also fetch uv when it is missing.
"""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

if sys.platform == 'win32':
    import winreg

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / 'helper'  # the helper; its Python, models and llama.cpp are installed next to it
MODELS_URL = os.environ.get('PEPA_MODELS', 'https://huggingface.co/chlebajz/pepa/resolve/main')
NAME = 'cz.aihlidac.helper'
EXTENSION_ID = 'gbmpchndeobcdpmhipldpnklobjbangj'  # fixed by the "key" in extension/manifest.json
PACKAGES = ['torch==2.7.1', 'transformers==5.16.1', 'pillow==13.0.0', 'zxing-cpp==3.1.1']
LLAMA = 'https://github.com/ggml-org/llama.cpp/releases/download/b11982/'
RUNTIMES = {  # official llama.cpp b11982 builds and their published sha256
    ('linux', 'x86_64'): ('llama-b11982-bin-ubuntu-vulkan-x64.tar.gz', '76a959124127f90555469285621c8d9099514724715d652a997f92841755efbb'),
    ('linux', 'aarch64'): ('llama-b11982-bin-ubuntu-vulkan-arm64.tar.gz', 'b01bc1de4b7fdc47097a741c763d71a5c138e3df8ce1cbdfc029a2e9a48d47cc'),
    ('win32', 'amd64'): ('llama-b11982-bin-win-vulkan-x64.zip', '455c401e3a599ea08b5b1263bd994bf035880b8b558454d44a6cd0c3af480bfc'),
    ('darwin', 'arm64'): ('llama-b11982-bin-macos-arm64.tar.gz', 'a826c186f464594de3ff3dccec3676dfb35c78643f66e99df6b372feadf84ae6'),
}
# Where each browser looks for native messaging hosts of the current user
LINUX_BROWSERS = ['google-chrome', 'google-chrome-beta', 'chromium', 'BraveSoftware/Brave-Browser', 'microsoft-edge', 'vivaldi']
MAC_BROWSERS = ['Google/Chrome', 'Google/Chrome Beta', 'Chromium', 'BraveSoftware/Brave-Browser', 'Microsoft Edge', 'Vivaldi']
WINDOWS_KEYS = ['Google\\Chrome', 'Chromium', 'BraveSoftware\\Brave-Browser', 'Microsoft\\Edge', 'Vivaldi']


def step(text: str) -> None:
    print(f'\n== {text}', flush=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''): digest.update(chunk)
    return digest.hexdigest()


def download(url: str, path: Path, expected: str) -> None:
    """Fetch url to path, resuming a partial download, and fail if the checksum differs."""
    if path.exists() and sha256(path) == expected: return
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + '.part')
    done = part.stat().st_size if part.exists() else 0
    request = urllib.request.Request(url, headers={'Range': f'bytes={done}-'} if done else {})
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 206: done = 0  # the server ignored the range: start over
        total = done + int(response.headers.get('Content-Length', 0))
        with open(part, 'ab' if done else 'wb') as out:
            while chunk := response.read(1 << 20):
                out.write(chunk)
                done += len(chunk)
                if total: print(f'\r   {path.name}: {done * 100 // total} %', end='', flush=True)
    if total: print()
    if sha256(part) != expected:
        part.unlink()
        sys.exit(f'Soubor {path.name} je poškozený (nesedí kontrolní součet). Spusťte instalaci znovu.')
    part.replace(path)


def python_path() -> Path:
    return ROOT / ('.venv/Scripts/python.exe' if sys.platform == 'win32' else '.venv/bin/python')


def install_python() -> None:
    step('Prostředí Pythonu (.venv)')
    uv = shutil.which('uv')
    if not uv: sys.exit('Chybí uv. Spusťte instalaci přes install.sh nebo install.cmd.')
    subprocess.run([uv, 'venv', '--allow-existing', '--python', '3.12', str(ROOT / '.venv')], check=True)
    python = str(python_path())
    # macOS has no separate CPU build of PyTorch; elsewhere the CPU build saves about 2 GB of CUDA libraries.
    index = [] if sys.platform == 'darwin' else ['--index-url', 'https://download.pytorch.org/whl/cpu']
    subprocess.run([uv, 'pip', 'install', '--python', python, PACKAGES[0], *index], check=True)
    subprocess.run([uv, 'pip', 'install', '--python', python, *PACKAGES[1:]], check=True)


def install_models() -> None:
    step('Modely (asi 1,7 GB)')
    for line in (Path(__file__).resolve().parent / 'MODELS.sha256').read_text(encoding='utf-8').splitlines():
        expected, path = line.split(maxsplit=1)
        download(f'{MODELS_URL}/{path}', ROOT / path, expected)
    print('   Modely jsou na místě a kontrolní součty sedí.')


def install_runtime() -> None:
    step('llama.cpp')
    target = ROOT / 'runtime/llama.cpp'
    server = target / ('llama-server.exe' if sys.platform == 'win32' else 'llama-server')
    if server.exists():
        print('   Už je nainstalovaná.')
        return
    key = (sys.platform, platform.machine().lower())
    if key not in RUNTIMES: sys.exit(f'Pro tento systém ({key[0]}, {key[1]}) zatím nemáme sestavení llama.cpp.')
    name, expected = RUNTIMES[key]
    archive = ROOT / 'runtime' / name
    download(LLAMA + name, archive, expected)
    unpacked = ROOT / 'runtime/unpacked'
    shutil.rmtree(unpacked, ignore_errors=True)
    if name.endswith('.zip'):
        with zipfile.ZipFile(archive) as z: z.extractall(unpacked)
    else:
        with tarfile.open(archive) as t: t.extractall(unpacked, filter='tar')
    # The archives keep llama-server and its libraries in one folder (at the top or in a subfolder).
    found = next(p for p in unpacked.rglob(server.name) if p.is_file())
    shutil.rmtree(target, ignore_errors=True)
    found.parent.replace(target)
    shutil.rmtree(unpacked, ignore_errors=True)
    archive.unlink()
    print(f'   {name} je v {target}')


def launcher() -> Path:
    if sys.platform != 'win32': return ROOT / 'native-host.sh'
    path = ROOT / 'native-host.cmd'
    path.write_text('@echo off\r\nrem Started by the browser through native messaging (see install.py); not meant to be run by hand.\r\n'
                    'set HF_HUB_OFFLINE=1\r\nset TRANSFORMERS_OFFLINE=1\r\nset PYTHONUTF8=1\r\n'
                    '"%~dp0.venv\\Scripts\\python.exe" "%~dp0native_host.py" %*\r\n', encoding='ascii')
    return path


def manifest(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{NAME}.json'
    path.write_text(json.dumps({'name': NAME, 'description': 'PEPA – rychlé místní modely', 'path': str(launcher()),
                                'type': 'stdio', 'allowed_origins': [f'chrome-extension://{EXTENSION_ID}/']}, indent=2, ensure_ascii=False),
                    encoding='utf-8')
    return path


def browser_dirs() -> list:
    """NativeMessagingHosts directories of the browsers this user has (Linux and macOS)."""
    if sys.platform == 'darwin':
        base = Path.home() / 'Library/Application Support'
        return [base / b / 'NativeMessagingHosts' for b in MAC_BROWSERS if (base / b).is_dir()]
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    dirs = [config / b / 'NativeMessagingHosts' for b in LINUX_BROWSERS if (config / b).is_dir()]
    snap = Path.home() / 'snap/chromium/common/chromium'  # Ubuntu's snap Chromium keeps its profile here
    return dirs + ([snap / 'NativeMessagingHosts'] if snap.is_dir() else [])


def register(dirs: list) -> None:
    step('Registrace pomocníka v prohlížečích')
    os.chmod(ROOT / 'native-host.sh', 0o755)
    if dirs:
        for d in dirs: print(f'   {manifest(Path(d))}')
    elif sys.platform == 'win32':
        path = manifest(ROOT)
        for key in WINDOWS_KEYS:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f'Software\\{key}\\NativeMessagingHosts\\{NAME}') as k:
                winreg.SetValueEx(k, '', 0, winreg.REG_SZ, str(path))
        print('   Chrome, Edge, Brave, Chromium a Vivaldi')
    else:
        found = browser_dirs()
        if not found: sys.exit('Nenašli jsme Chrome, Edge, Brave, Chromium ani Vivaldi. Nainstalujte prohlížeč a spusťte instalaci znovu.')
        for d in found: print(f'   {manifest(d)}')


def uninstall() -> None:
    if sys.platform == 'win32':
        for key in WINDOWS_KEYS:
            try: winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f'Software\\{key}\\NativeMessagingHosts\\{NAME}')
            except FileNotFoundError: pass
    else:
        for d in browser_dirs(): (d / f'{NAME}.json').unlink(missing_ok=True)
    print('Pomocník je z prohlížečů odebraný. Rozšíření odeberte na stránce rozšíření a složku PEPA pak můžete smazat.')


def main() -> None:
    parser = argparse.ArgumentParser(description='Instalace pomocníka PEPA')
    parser.add_argument('--register', nargs='+', metavar='DIR', help='only write the helper manifest into these directories')
    parser.add_argument('--uninstall', action='store_true')
    args = parser.parse_args()
    if args.uninstall: return uninstall()
    if args.register: return register(args.register)
    install_python()
    install_models()
    install_runtime()
    register([])
    print(f'''
Hotovo. Zbývá jednou načíst rozšíření:
  1. V prohlížeči otevřete stránku chrome://extensions (v Edgi edge://extensions, v Brave brave://extensions).
  2. Zapněte „Režim pro vývojáře“.
  3. Klikněte na „Načíst rozbalené“ a vyberte složku:
     {REPO / 'extension'}
  4. Restartujte prohlížeč. Ikonu PEPA si připněte na lištu; ukáže, že ochrana běží.
''')


if __name__ == '__main__':
    main()
