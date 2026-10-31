#!/usr/bin/env bash
# PEPA installer for Linux and macOS: fetches uv (a small Python manager) if missing, then runs install.py.
# usage: ./install.sh [--uninstall]
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
# uv, its Python and its download cache stay in this folder: deleting the folder removes everything.
export UV_CACHE_DIR="$PWD/.uv/cache" UV_PYTHON_INSTALL_DIR="$PWD/.uv/python" PATH="$PWD/.uv/bin:$PATH"
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$PWD/.uv/bin" UV_NO_MODIFY_PATH=1 sh
fi
exec uv run --no-project --python 3.12 install.py "$@"
