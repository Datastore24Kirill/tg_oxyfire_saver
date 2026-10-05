#!/bin/bash
# Install TG Oxyfire Saver from this repo (sources + optional bundled .app).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SUPPORT="${HOME}/Library/Application Support/TGVideoSaver"
APP_DEST="${TG_OXYFIRE_APP_DEST:-/Applications/TG Oxyfire Saver.app}"
PY_MIN=3.12

echo "=== TG Oxyfire Saver installer ==="
echo "Support dir: $SUPPORT"

mkdir -p "$SUPPORT"
rsync -a \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.env' \
  --exclude '*.session' \
  --exclude '*.session-journal' \
  --exclude 'data/' \
  --exclude 'app.log' \
  --exclude '.api_port' \
  --exclude '.instance.lock' \
  --exclude '.menu.lock' \
  "$ROOT/src/" "$SUPPORT/"

mkdir -p "$SUPPORT/data" "$SUPPORT/core/thumbs"
cp "$ROOT/VERSION" "$SUPPORT/VERSION" 2>/dev/null || true

# Always ensure runtime .env exists (bundled defaults; silent for end users)
if [[ ! -f "$SUPPORT/.env" ]]; then
  cp "$ROOT/.env.example" "$SUPPORT/.env"
fi
# Fill missing keys without overwriting a custom complete .env
if ! grep -q '^API_ID=[0-9]' "$SUPPORT/.env" 2>/dev/null; then
  grep -E '^API_ID=|^API_HASH=' "$ROOT/.env.example" >> "$SUPPORT/.env"
fi

# The shipped native helpers embed Python 3.12. Keep the same interpreter on update.
PYTHON=""
if [[ -x "$SUPPORT/.venv/bin/python" ]]; then
  PYTHON="$("$SUPPORT/.venv/bin/python" -c 'import sys; print(sys._base_executable if sys.version_info[:2] == (3,12) else "")' 2>/dev/null || true)"
fi
if [[ -z "$PYTHON" ]]; then
  for c in python3.12 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info[:2] != (3,12))'; then
      PYTHON="$(command -v "$c")"
      break
    fi
  done
fi
if [[ -z "$PYTHON" || ! -x "$PYTHON" ]]; then
  echo "ERROR: This Mac bundle requires Python 3.12. The existing environment was not changed."
  exit 1
fi

echo "Using $PYTHON"
"$PYTHON" -m venv "$SUPPORT/.venv"
# shellcheck disable=SC1091
source "$SUPPORT/.venv/bin/activate"
pip install -U pip
pip install -r "$SUPPORT/requirements.txt"
# pyobjc for native UI bits
pip install pyobjc-framework-Cocoa pyobjc-framework-Quartz 2>/dev/null || true

# Rebuild menu helper if swift available
MENU_APP=""
if [[ -d "$ROOT/dist/TG Oxyfire Saver.app" ]]; then
  MENU_APP="$ROOT/dist/TG Oxyfire Saver.app/Contents/Helpers/TGOxyfireMenu.app"
elif [[ -d "$APP_DEST" ]]; then
  MENU_APP="$APP_DEST/Contents/Helpers/TGOxyfireMenu.app"
fi
if command -v swiftc >/dev/null 2>&1 && [[ -f "$SUPPORT/menu_native.swift" ]] && [[ -n "$MENU_APP" ]] && [[ -d "$MENU_APP" ]]; then
  echo "Compiling menu bar helper…"
  swiftc -O -framework Cocoa -o "$MENU_APP/Contents/MacOS/TGOxyfireMenu" "$SUPPORT/menu_native.swift" || true
  codesign --force --sign - "$MENU_APP/Contents/MacOS/TGOxyfireMenu" 2>/dev/null || true
  codesign --force --deep --sign - "$MENU_APP" 2>/dev/null || true
fi

# Install .app if present in dist/
if [[ -d "$ROOT/dist/TG Oxyfire Saver.app" ]]; then
  echo "Installing app → $APP_DEST"
  rm -rf "$APP_DEST"
  ditto "$ROOT/dist/TG Oxyfire Saver.app" "$APP_DEST"
  # Point helper libs at Support venv
  for H in TGSaverEngine TGSaverWindow TGOxyfireMenu; do
    HAPP="$APP_DEST/Contents/Helpers/${H}.app"
    if [[ -d "$HAPP/Contents" ]]; then
      rm -f "$HAPP/Contents/lib"
      ln -sfn "$SUPPORT/.venv/lib" "$HAPP/Contents/lib"
      # refresh pyvenv home line if present
      if [[ -f "$HAPP/Contents/pyvenv.cfg" ]]; then
        printf 'home = %s\nimplementation = CPython\nuv = 0\nversion_info = 3.12\ninclude-system-site-packages = false\n' \
          "$(dirname "$PYTHON")" > "$HAPP/Contents/pyvenv.cfg"
      fi
    fi
  done
  codesign --force --deep --sign - "$APP_DEST" 2>/dev/null || true
fi

echo ""
echo "Done."
echo "Open: $APP_DEST  (or: open \"$APP_DEST\")"
echo "Sign in with QR in Telegram → Settings → Devices."
echo "Gatekeeper: right-click → Open if blocked."
