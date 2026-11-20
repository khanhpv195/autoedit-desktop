# Spike: `claude setup-token` in a PTY (M2 Task 6)

Date: 2026-11-20. Bounded run, no real login completed, no browser opened, no secrets recorded.

## Method

Ran the bundled CLI (`claude-cli/0.2.186/claude`, which reports itself as "Claude Code v2.1.329")
as `claude setup-token` in a pseudo-terminal sized 40 rows x 1000 columns, with
`DISABLE_AUTOUPDATER=1` and `BROWSER=true` (no-op browser). Killed after 20 seconds.
(`script -q ... &` with stdin detached printed nothing, so a Python `pty.fork()` harness was used.)
Query parameters of the OAuth URL (`client_id`, `code_challenge`, `state`) are replaced by `…` below.

## Observed output (ANSI stripped)

1. Banner "Welcome to Claude Code v2.1.329", then
   "This will guide you through long-lived (1-year) auth token setup for your Claude account. Claude subscription required."
2. "Opening browser to sign in…" with a spinner (many cursor-move and glyph redraws).
3. "Browser didn't open? Use the url below to sign in (c to copy)", then the URL on one line (1000 columns, no wrapping):
   `https://claude.com/cai/oauth/authorize?code=true&client_id=…&response_type=code&redirect_uri=https%3A%2F%2Fplatform.claude.com%2Foauth%2Fcode%2Fcallback&scope=user%3Ainference&code_challenge=…&code_challenge_method=S256&state=…`
4. "Paste code here if prompted" followed by an empty bordered input box.

## Answers

- Prints a URL: yes (`https://claude.com/cai/oauth/authorize?...`), host is `claude.com`, not `claude.ai`. `find_url` must not assume a host.
- Asks to paste a code: yes ("Paste code here if prompted"). With the browser flow the callback page on
  platform.claude.com shows a code the user pastes into this prompt; so the UI needs a code box wired to `login_input`.
- Needs a key press: no key press needed to reach the URL and the prompt. "c to copy" is optional.
- Output is a full-screen TUI: the cursor-forward escape sequences replace spaces (words appear glued
  after naive ANSI stripping, e.g. "Pastecodehereifprompted"). The URL and the token are single
  unbroken strings, so `find_url` and `extract_token` still work; user-facing lines may look glued.
  `strip_ansi` should turn `ESC[nC` (cursor forward) into a space to keep lines readable.
- The spinner redraws produce many near-empty lines; the UI should drop blank or single-glyph lines.

## Conclusion

Flow for the app: spawn in PTY, show the URL (and open it via the opener plugin), show a code input
that calls `login_input` (text + `\r`), then watch output for `sk-ant-oat01-...`.

Phần nhận token: PENDING HUMAN, kiểm khi chạy app (the token output format after a completed login was
not exercised here; the extraction regex and wrapped-line handling are covered by unit tests against
a fake CLI only).
