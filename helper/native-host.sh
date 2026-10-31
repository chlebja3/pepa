#!/usr/bin/env bash
# Started by the browser through native messaging (see install.py); not meant to be run by hand.
ROOT="$(cd -- "$(dirname -- "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
PYTHON="$ROOT/.venv/bin/python"
# Snap Chromium (Ubuntu's default) runs the helper in its core24 sandbox: it has python3.12 but not the /usr/bin/python
# the venv links to, so use the sandbox's interpreter with the venv's packages.
if [ ! -x "$PYTHON" ]; then
  PYTHON=python3.12
  export PYTHONPATH="$ROOT/.venv/lib/python3.12/site-packages"
fi
exec "$PYTHON" "$ROOT/native_host.py" "$@"
