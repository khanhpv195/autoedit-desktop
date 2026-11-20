#!/bin/sh
printf '\033[1mOpen this URL:\033[0m https://claude.ai/oauth/authorize?code=true&x=1\n'
printf 'Paste code here if prompted > '
read code
printf 'Your OAuth token (valid for 1 year):\n\n\033[32msk-ant-oat01-'
printf 'AbCdEfGhIjKlMnOpQrStUvWxYz_0123456789-abcdefghij\033[0m\n\nStore this token securely.\n'
sleep 5
