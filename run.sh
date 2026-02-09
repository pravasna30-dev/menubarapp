#!/usr/bin/env bash
# Token Meter — setup & launch script
set -euo pipefail

cd "$(dirname "$0")"

VENV_DIR=".venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install -q -r requirements.txt

echo "Launching Token Meter..."
"$VENV_DIR/bin/python" token_meter.py
