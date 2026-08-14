---
name: setup
description: Guided setup for Sophonic — check what's configured and fill the gaps (vault path, Google, Slack, Zoom, GitLab). Use when the user wants to set up, configure, install, or troubleshoot Sophonic.
---

# Sophonic setup

You are the setup guide. Configuration lives in `~/.sophonic/config.toml` (settings) and
`~/.sophonic/.env` (secrets, 0600), both driven through the plugin's scripts. There is no
interactive wizard — you interview the user in chat and apply changes.

All commands below run with the Bash tool as:
`uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/<x>.py" …`

## Procedure

1. **Diagnose.** Run `scripts/doctor.py`. It prints
   `{"ok", "checks":[{name, ok, detail, fix}]}`. Summarize which integrations are green
   and which need attention.

2. **Fix each failing check by interviewing the user.** For every `ok:false` entry, ask
   for the value it needs, then persist it:
   - Non-secret settings → `scripts/config.py set <key> <value>`
     (e.g. `set vault.path /Users/me/vault`, `set features.gitlab true`,
     `set gitlab.url https://gitlab.example.com`). Inspect with
     `scripts/config.py show` (secrets redacted) or `scripts/config.py get <key>`.

3. **Secrets — never type them into a command yourself.** A secret must not appear in
   your tool calls or the transcript. Tell the user to run this in **their own terminal**
   (from the plugin directory) and paste when prompted:
   ```
   uv run python scripts/config.py set-secret <ENV_NAME> --stdin
   ```
   `ZOOM_COOKIES` for Zoom, `GITLAB_TOKEN` for GitLab. The `doctor` `fix` field names the
   exact command.

4. **Browser / OAuth / Keychain — hand off to the user.** You cannot open a browser or
   read the Keychain. For a `google.auth` gap have them run
   `uv run python scripts/auth.py google` (opens OAuth consent); for `slack` have them run
   `uv run python scripts/auth.py slack` (approves the Keychain prompt). For
   `google.client_secret`, tell them to download a **Desktop app** OAuth client JSON from
   Google Cloud and save it at the path in the check `detail`.

5. **Re-check.** After the user reports back, run `scripts/doctor.py` again and confirm
   the relevant checks are now green.

## Config keys (dotted)

`vault.path`, `vault.daily_dir`, `vault.daily_prefix`, `vault.meetings_dir` ·
`features.{obsidian,reminders,google,slack,zoom,gitlab}` (bool) ·
`google.client_secret_file`, `google.scopes` (comma-separated list) ·
`browser.zoom.engine` (`chromium`|`chrome`|`island`) ·
`slack.workspace_host` (optional) · `gitlab.url`, `gitlab.default_project`.

Slack needs no config beyond signing into the desktop app (`auth.py slack`). Zoom needs
the `ZOOM_COOKIES` secret. No LLM key is required — Claude Code is the model.

## Notes

- The vault work (daily notes, tasks, rollover) is pure skill — it only needs a valid
  `vault.path`. The scripts exist only for the auth-bound sources (Google/Slack/Zoom/GitLab).
- Terminal users who ran `uv sync` can use the shorthand wrappers instead of the
  `uv run python scripts/…` form: `sophonic-config …`, `sophonic-doctor`, `sophonic-auth …`.
  `doctor`'s `fix` fields use those names. When *you* run a command via Bash, use the
  `uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/…"` form,
  which works whether or not the wrappers are installed.
- `uv` must be installed; the first run of any script triggers `uv sync`. Zoom also needs
  Playwright's Chromium — install once with `uv run playwright install chromium`.
