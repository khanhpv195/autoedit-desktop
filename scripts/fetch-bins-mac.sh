#!/usr/bin/env bash
# Fetch static arm64 ffmpeg/ffprobe and build whisper-cli into build/bin/. Idempotent.
# ffmpeg source: ffmpeg.martin-riedl.de 9.0.2 (static, GPL, libx264, libass, libzimg; Developer ID signed).
# Chosen because evermeet/osxexperts builds lack zscale or are not arm64-current; verified below.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/build/bin"
FF_BASE="https://ffmpeg.martin-riedl.de/download/macos/arm64/1789931890_9.0.2"
FFMPEG_SHA256="c8ed4c4e6978a03c485edbfe4e0a5dc2380f8a30bba5150531b31b094492d924"
FFPROBE_SHA256="fcbe839537485eaee7a7a8bc5cbc0f90d53617e80943e8a5b2e31cb851197ea6"
WHISPER_TAG="v1.9.5"
WHISPER_SHA256="ff1a9053feb509ff9d7729703355541ae9690073a6b1c40eb692c962e0dc1720"

mkdir -p "$OUT"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fetch_ff() { # name sha
  local name="$1" sha="$2"
  curl -sSfL -o "$TMP/$name.zip" "$FF_BASE/$name.zip"
  echo "$sha  $TMP/$name.zip" | shasum -a 256 -c - >/dev/null || { echo "sha256 mismatch for $name" >&2; exit 1; }
  mkdir -p "$TMP/$name"
  unzip -qo "$TMP/$name.zip" -d "$TMP/$name"
  install -m 755 "$TMP/$name/$name" "$OUT/$name"
}

[ -x "$OUT/ffmpeg" ] || fetch_ff ffmpeg "$FFMPEG_SHA256"
[ -x "$OUT/ffprobe" ] || fetch_ff ffprobe "$FFPROBE_SHA256"

if [ ! -x "$OUT/whisper-cli" ]; then
  command -v cmake >/dev/null || { echo "cmake is required (brew install cmake)" >&2; exit 1; }
  curl -sSfL -o "$TMP/whisper.tgz" "https://codeload.github.com/ggml-org/whisper.cpp/tar.gz/refs/tags/$WHISPER_TAG"
  echo "$WHISPER_SHA256  $TMP/whisper.tgz" | shasum -a 256 -c - >/dev/null || { echo "sha256 mismatch for whisper.cpp" >&2; exit 1; }
  mkdir -p "$TMP/whisper.cpp"
  tar -xzf "$TMP/whisper.tgz" -C "$TMP/whisper.cpp" --strip-components=1
  cmake -S "$TMP/whisper.cpp" -B "$TMP/b" -DBUILD_SHARED_LIBS=OFF -DGGML_METAL=ON \
    -DGGML_METAL_EMBED_LIBRARY=ON -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_EXAMPLES=ON \
    -DCMAKE_BUILD_TYPE=Release >/dev/null
  cmake --build "$TMP/b" -j --target whisper-cli >/dev/null
  install -m 755 "$TMP/b/bin/whisper-cli" "$OUT/whisper-cli"
fi

# --- Verification ---
fail() { echo "FAIL: $*" >&2; exit 1; }
for f in ffmpeg ffprobe whisper-cli; do
  if otool -L "$OUT/$f" | grep -E "/opt/homebrew|/usr/local" >/dev/null; then fail "$f links to a non-system library"; fi
done
FILTERS="$("$OUT/ffmpeg" -hide_banner -filters | awk '{print $2}')"
# Filters the engine uses (engine/autoedit/render, engine/autoedit/prep).
for f in zscale tonemap format scale crop setsar fps split boxblur overlay eq geq gblur bilateral \
         maskedmerge subtitles afade amix aresample volume loudnorm concat blackdetect; do
  grep -qx "$f" <<<"$FILTERS" || fail "ffmpeg lacks filter $f"
done
ENCODERS="$("$OUT/ffmpeg" -hide_banner -encoders | awk '{print $2}')"
for e in libx264 aac pcm_s16le mjpeg; do
  grep -qx "$e" <<<"$ENCODERS" || fail "ffmpeg lacks encoder $e"
done
"$OUT/ffprobe" -hide_banner -version >/dev/null || fail "ffprobe does not run"
"$OUT/whisper-cli" --help >/dev/null 2>&1 || fail "whisper-cli --help failed"
echo "OK: $(ls "$OUT" | tr '\n' ' ')in $OUT"
