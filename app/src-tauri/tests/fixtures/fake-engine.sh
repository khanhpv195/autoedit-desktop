#!/bin/sh
echo '{"type":"step","label":"a","progress":0.1}'
echo 'not json'
echo "env:$CLAUDE_CODE_OAUTH_TOKEN" >&2
if [ "$1" = "sleep" ]; then sleep 30; fi
echo '{"type":"done","final":"/x.mp4","summary":[],"usage":{"turns":1,"fallback":false},"needs_review":false}'
exit 0
