#!/usr/bin/env bash
# Hardened-runtime sign every Mach-O in the bundled engine and bin dir. Run BEFORE `tauri build`.
# Usage: scripts/sign-mac-resources.sh "<signing identity>"
set -euo pipefail
ID="${1:?usage: sign-mac-resources.sh <identity>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENT="$ROOT/app/src-tauri/entitlements.plist"

sign() { codesign --force --options runtime --timestamp --entitlements "$ENT" -s "$ID" "$1"; }
is_macho() { file -b "$1" | grep -q "Mach-O"; }

# Libraries first, the main executable last.
while IFS= read -r f; do
  [ "$(basename "$f")" = "autoedit" ] && [ "$(dirname "$f")" = "$ROOT/engine/dist/autoedit" ] && continue
  is_macho "$f" && sign "$f"
done < <(find "$ROOT/engine/dist/autoedit" -type f \( -name "*.dylib" -o -name "*.so" -o -perm -u+x \))
sign "$ROOT/engine/dist/autoedit/autoedit"

for f in "$ROOT"/build/bin/*; do
  is_macho "$f" && sign "$f"
done
echo "signed bundled binaries with identity: $ID"
