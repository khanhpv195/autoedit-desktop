#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../engine"
uv run pyinstaller --noconfirm autoedit.spec
./dist/autoedit/autoedit --version
test -f dist/autoedit/_internal/agent/CLAUDE.md
test -f dist/autoedit/_internal/agent/.claude/skills/niche-hooks/SKILL.md
test -f dist/autoedit/_internal/assets/fonts/BeVietnamPro-ExtraBold.ttf
if find dist/autoedit -path "*_bundled*" | grep -q .; then echo "Claude CLI must not be bundled" >&2; exit 1; fi
du -sh dist/autoedit
