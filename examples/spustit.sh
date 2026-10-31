#!/usr/bin/env bash
# Opens the PEPA examples and the "play the scammer" page at http://127.0.0.1:8000 (PEPA reads only web pages,
# not files opened from disk). Open the address in the browser where PEPA is installed. Ctrl+C stops it.
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PY="$HERE/../helper/.venv/bin/python"
[ -x "$PY" ] || PY=python3
URL=http://127.0.0.1:8000/index.html
echo "Ukázky PEPA běží na $URL  (otevřete v prohlížeči s PEPA, ukončíte Ctrl+C)"
( sleep 1; if command -v xdg-open >/dev/null; then xdg-open "$URL"; elif command -v open >/dev/null; then open "$URL"; fi ) >/dev/null 2>&1 &
exec "$PY" -m http.server 8000 --bind 127.0.0.1 -d "$HERE"
