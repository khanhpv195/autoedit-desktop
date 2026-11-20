#!/usr/bin/env bash
# Build AutoEdit.app and the .dmg (macOS arm64, ad-hoc signed).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
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
