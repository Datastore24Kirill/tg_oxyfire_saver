#!/bin/bash
# Build TG-Oxyfire-Saver-macOS.zip from repo sources + a bundled .app.
# On CI the .app is taken from the previous GitHub release (ad-hoc signed, not notarized).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
STAGE="$ROOT/dist/macos-stage"
WORK="$STAGE/TG-Oxyfire-Saver-macOS"
ZIP="$ROOT/dist/TG-Oxyfire-Saver-macOS.zip"
APP_NAME="TG Oxyfire Saver.app"

rm -rf "$STAGE"
mkdir -p "$WORK/src" "$WORK/scripts" "$WORK/dist" "$ROOT/dist"

APP_SRC=""
if [[ -d "$ROOT/dist/$APP_NAME" ]]; then
  APP_SRC="$ROOT/dist/$APP_NAME"
elif [[ -d "/Applications/$APP_NAME" ]]; then
  APP_SRC="/Applications/$APP_NAME"
else
  PREV="$(mktemp -d)"
  echo "Downloading a previous Mac zip for the .app skeleton…"
  export CURRENT="${GITHUB_REF_NAME:-}"
  ASSET_URL="$(
    curl -fsSL "https://api.github.com/repos/Datastore24Kirill/tg_oxyfire_saver/releases?per_page=20" \
      | python3 -c '
import json, os, sys
cur = os.environ.get("CURRENT", "")
rels = json.load(sys.stdin)
for rel in rels:
    if rel.get("tag_name") == cur:
        continue
    for asset in rel.get("assets") or []:
        if asset.get("name") == "TG-Oxyfire-Saver-macOS.zip":
            print(asset["browser_download_url"])
            raise SystemExit(0)
raise SystemExit(1)
' 
  )" || {
    echo "ERROR: no previous TG-Oxyfire-Saver-macOS.zip found" >&2
    exit 1
  }
  curl -fsSL -o "$PREV/prev.zip" "$ASSET_URL"
  ditto -x -k "$PREV/prev.zip" "$PREV/unz"
  found="$(find "$PREV/unz" -name "$APP_NAME" -type d | head -1)"
  if [[ -z "$found" ]]; then
    echo "ERROR: no $APP_NAME in previous release" >&2
    exit 1
  fi
  APP_SRC="$found"
fi

ditto "$APP_SRC" "$WORK/dist/$APP_NAME"

rsync -a \
  --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude '.env' --exclude '*.session' --exclude '*.session-journal' \
  --exclude 'data/' --exclude 'app.log' --exclude '.api_port' \
  --exclude '.instance.lock' --exclude '.menu.lock' --exclude 'store.db' \
  --exclude 'core/thumbs/' --exclude 'day_markers/' \
  "$ROOT/src/" "$WORK/src/"
mkdir -p "$WORK/src/data" "$WORK/src/core/thumbs"
touch "$WORK/src/data/.gitkeep" "$WORK/src/core/thumbs/.gitkeep"
cp "$ROOT/VERSION" "$WORK/VERSION"
cp "$ROOT/VERSION" "$WORK/src/VERSION"
cp "$ROOT/README.md" "$ROOT/LICENSE" "$ROOT/.env.example" "$ROOT/.gitignore" "$WORK/"
cp "$ROOT/scripts/install_from_source.sh" "$ROOT/scripts/package_macos.sh" "$WORK/scripts/"
cp "$ROOT/Install.command" "$WORK/"
chmod +x "$WORK/Install.command" "$WORK/scripts/"*.sh

# Stamp version into Swift about panel, then rebuild the menu helper if swiftc exists.
SWIFT="$WORK/src/menu_native.swift"
if [[ -f "$SWIFT" ]]; then
  perl -i -pe "s/applicationVersion: \"[^\"]+\"/applicationVersion: \"$VERSION\"/" "$SWIFT"
  perl -i -pe "s/(?<!application)\.version: \"[^\"]+\"/.version: \"$VERSION\"/" "$SWIFT" || true
fi
MENU="$WORK/dist/$APP_NAME/Contents/Helpers/TGOxyfireMenu.app"
if command -v swiftc >/dev/null 2>&1 && [[ -d "$MENU" ]] && [[ -f "$SWIFT" ]]; then
  swiftc -O -framework Cocoa -o "$MENU/Contents/MacOS/TGOxyfireMenu" "$SWIFT"
  codesign --force --sign - "$MENU/Contents/MacOS/TGOxyfireMenu" >/dev/null 2>&1 || true
  codesign --force --deep --sign - "$MENU" >/dev/null 2>&1 || true
fi

for APP in \
  "$WORK/dist/$APP_NAME" \
  "$WORK/dist/$APP_NAME/Contents/Helpers/TGSaverWindow.app" \
  "$WORK/dist/$APP_NAME/Contents/Helpers/TGSaverEngine.app" \
  "$MENU"
do
  if [[ -f "$APP/Contents/Info.plist" ]]; then
    /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$APP/Contents/Info.plist" 2>/dev/null || \
      /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $VERSION" "$APP/Contents/Info.plist" || true
    /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VERSION" "$APP/Contents/Info.plist" 2>/dev/null || \
      /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $VERSION" "$APP/Contents/Info.plist" || true
  fi
done

for H in TGSaverEngine TGSaverWindow TGOxyfireMenu; do
  rm -rf "$WORK/dist/$APP_NAME/Contents/Helpers/${H}.app/Contents/lib" 2>/dev/null || true
done

rm -f "$ZIP"
ditto -c -k --sequesterRsrc --keepParent "$WORK" "$ZIP"
ls -lh "$ZIP"
echo "Wrote $ZIP"
