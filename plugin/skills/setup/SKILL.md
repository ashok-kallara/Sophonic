---
description: Guided setup for Sophonic — check what's configured and fill the gaps. Use when the user wants to set up, configure, or troubleshoot Sophonic (vault, LLM provider, Google, Slack, Zoom, GitLab).
---

# Sophonic setup

You are the setup wizard. Because you run inside Claude Code (no interactive TTY),
drive configuration through the **non-interactive** `sophonic config` commands via the
Bash tool — never `sophonic init` (that needs a real terminal).

## Procedure

1. **Diagnose.** Run `sophonic doctor` (Bash). It returns JSON: `{"ok", "checks":[{name, ok, detail, fix}]}`.
   Summarize which integrations are green and which need attention.

2. **Fix each failing check by interviewing the user.** For every `ok:false` entry, ask
   the user in chat for the value it needs, then persist it:
   - Non-secret settings → `sophonic config set <key> <value>`
     (e.g. `sophonic config set vault.path /Users/me/vault`,
     `sophonic config set features.gitlab true`,
     `sophonic config set llm.provider openai`,
     `sophonic config set gitlab.url https://gitlab.example.com`).
   - Inspect current values with `sophonic config show` (secrets are redacted) or
     `sophonic config get <key>`.

3. **Secrets — never type them into a command yourself.** API keys and tokens must not
   appear in your tool calls or the transcript. Instead, tell the user to run this in
   **their own terminal**:
   ```
   sophonic config set-secret <ENV_NAME> --stdin
   ```
   then paste the secret. The LLM key is `SOPHONIC_LLM_API_KEY` (works for any
   provider); GitLab uses `GITLAB_TOKEN`. The `doctor` `fix` field names the exact
   env var to use.

4. **Browser / OAuth auth — hand off to the user.** You cannot open a browser. For any
   `google.auth`, `slack.auth`, or `zoom.auth` gap, tell the user to run the matching
   command in their terminal: `sophonic auth google`, `sophonic auth slack`, or
   `sophonic auth zoom`. For `google.client_secret`, tell them to download a desktop
   OAuth client JSON from Google Cloud and save it at the path in the check `detail`.

5. **Re-check.** After the user reports back, run `sophonic doctor` again and confirm the
   relevant checks are now green.

## Config keys (dotted)

`vault.path`, `vault.daily_dir`, `vault.daily_prefix`, `vault.meetings_dir` ·
`features.{obsidian,reminders,google,slack,zoom,gitlab}` (bool) ·
`llm.provider` (`anthropic`|`openai`|`litellm`), `llm.model`, `llm.api_base` (the LLM key is the `SOPHONIC_LLM_API_KEY` secret, not a config key) ·
`google.client_secret_file` · `browser.zoom.engine` (`chromium`|`chrome`|`island`) ·
`slack.workspace_host` (optional) · `gitlab.url`, `gitlab.default_project`.

Slack needs no config (reads the desktop-app session; run `sophonic auth slack`). Zoom
needs the `ZOOM_COOKIES` secret (`sophonic config set-secret ZOOM_COOKIES --stdin`).

## Notes

- Config is written to `~/.sophonic/config.toml`; secrets to `~/.sophonic/.env` (0600),
  which Sophonic auto-loads.
- Tool calls (`sophonic tool …`) need no LLM key — only `sophonic ask` and the openai
  provider do. So most of the assistant works before any key is set.
