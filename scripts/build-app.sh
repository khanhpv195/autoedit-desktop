#!/usr/bin/env bash
# Build AutoEdit.app and the .dmg (macOS arm64, ad-hoc signed).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if ! python3 -c 'import json,sys; d=json.load(open("app/src-tauri/license.json")); sys.exit(0 if d.get("url") and d.get("pubkey") else 1)'; then
  echo "app/src-tauri/license.json chưa có url/pubkey. Làm theo license-server/README.md trước khi build bản phát hành." >&2
  exit 1
fi
"$ROOT/scripts/build-engine.sh"
"$ROOT/scripts/fetch-bins-mac.sh"
cd app
npm ci
# Updater artifacts must be signed. Use the env key, else the local key file, else skip them.
EXTRA=()
if [ -z "${TAURI_SIGNING_PRIVATE_KEY:-}" ]; then
  if [ -f "$HOME/.tauri/autoedit-updater.key" ]; then
    export TAURI_SIGNING_PRIVATE_KEY="$HOME/.tauri/autoedit-updater.key"
    export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="${TAURI_SIGNING_PRIVATE_KEY_PASSWORD:-}"
  else
    EXTRA=(--config '{"bundle":{"createUpdaterArtifacts":false}}')
  fi
fi
npm run tauri build -- "${EXTRA[@]+"${EXTRA[@]}"}"
B="$ROOT/app/src-tauri/target/release/bundle"
du -sh "$B/macos/AutoEdit.app" "$B"/dmg/*.dmg
