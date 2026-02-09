#!/usr/bin/env bash
# Token Meter — build macOS .app bundle
set -euo pipefail

cd "$(dirname "$0")"

VENV_DIR=".venv"

# ── Create / reuse virtual environment ─────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install -q -r requirements.txt pyinstaller Pillow

# ── Generate app icon ──────────────────────────────────────────────
if [ ! -f "icon.icns" ]; then
    echo "Generating app icon..."
    "$VENV_DIR/bin/python" generate_icon.py
fi

# ── Clean previous builds ─────────────────────────────────────────
rm -rf build dist

# ── Build the .app bundle ─────────────────────────────────────────
echo "Building Token Meter.app..."
"$VENV_DIR/bin/pyinstaller" \
    --name "Token Meter" \
    --windowed \
    --icon icon.icns \
    --osx-bundle-identifier com.tokenmeter.app \
    --noconfirm \
    --clean \
    token_meter.py 2>&1

echo ""
echo "✓ Build complete!"
echo ""
echo "Your app is at:  dist/Token Meter.app"
echo ""
echo "To install, run:"
echo "  cp -r \"dist/Token Meter.app\" /Applications/"
echo ""
echo "Then launch Token Meter from Spotlight or /Applications."
