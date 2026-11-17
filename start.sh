#!/usr/bin/env bash
# ============================================================
#  Trilingual Sentiment Analysis - Launcher (macOS / Linux)
#  With Python 3  : install deps + start web UI (auto browser)
#  Without Python : open the portable HTML (no install, offline)
# ============================================================
cd "$(dirname "$0")"

PY=""
if command -v python3 >/dev/null 2>&1 && python3 -c "import sys" >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1 && python -c "import sys" >/dev/null 2>&1; then
    PY=python
fi

open_portable() {
    echo "[INFO] Python 3 unavailable. Opening the portable version instead."
    echo "       The portable HTML runs offline with no installation."
    for f in ./*.html; do
        [ -e "$f" ] || continue
        if command -v open >/dev/null 2>&1; then open "$f"
        elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$f"
        else echo "Please open manually: $f"; fi
        break
    done
}

if [ -z "$PY" ]; then open_portable; exit 0; fi

echo "[1/2] Checking dependencies..."
if ! "$PY" -m pip install -r requirements.txt --quiet; then
    open_portable
    exit 0
fi

echo "[2/2] Starting server... the browser will open automatically."
echo "      Press Ctrl+C to stop."
exec "$PY" webapp/app.py --open
