# Sophonic

An Obsidian-native personal assistant delivered as a **pure Claude Code plugin** — no
MCP server, no CLI to install, no LLM API key. Claude Code *is* the model and the tool
loop; Sophonic just adds skills that tell it how to run your day, plus a handful of thin
scripts for the things a model can't do by itself.

## How it works

Sophonic splits cleanly along what a Claude subagent can and cannot do natively:

- **Vault work is pure skills.** Daily notes, tasks, idempotent rollover, meeting notes,
  and the "start my day" brief are just markdown edits, so Claude does them directly with
  its Read/Write/Edit/Glob/Grep tools. There is no code and no API for these — see
  `skills/obsidian`, `skills/reminders`, `skills/start-my-day`.
- **Auth-bound sources are thin scripts.** Google, Slack, Zoom, and GitLab need OAuth,
  Keychain decryption, or cookie sessions — things a model can't perform. Each is a small
  `scripts/<name>.py` that fetches data and prints **one JSON object**; the matching skill
  invokes it over Bash and reads the result. The scripts are read-only fetchers — Claude
  writes anything that lands in the vault.

```
.claude-plugin/plugin.json   the plugin manifest
commands/                    slash commands: /sophonic:{today,config}
skills/                      obsidian, reminders, start-my-day, ask (pure) + gcal, gmail,
                             gtasks, gdrive, slack, zoom, meeting-recap, gitlab, raindrop,
                             setup (script-backed) — every skill is also invocable as
                             /sophonic:<name>
scripts/                     gcal, gmail, gtasks, slack, zoom, gitlab, raindrop
                             (fetchers) + auth, doctor, config (terminal utilities)
sophonic/                    slim library the scripts import (auth + API code only)
```

## Install

This repo is its own Claude Code plugin **marketplace** (`.claude-plugin/marketplace.json`),
so installing straight from GitHub is two commands inside Claude Code:

```
/plugin marketplace add ashok-kallara/Sophonic
/plugin install sophonic@sophonic
```

Then run **`/sophonic:setup`** and follow the prompts. That's it — no clone required.
Claude Code caches the plugin under `~/.claude/plugins/`, and every skill invokes its
scripts via `${CLAUDE_PLUGIN_ROOT}`, so nothing depends on where you run Claude from.

Non-interactively: `claude plugin marketplace add ashok-kallara/Sophonic` then
`claude plugin install sophonic@sophonic --scope user`. (`/plugin` opens an interactive
browser for the same thing.)

**Prerequisites:**
1. Install [`uv`](https://docs.astral.sh/uv/) — the scripts run under it. The first
   script call creates the plugin's virtualenv (`uv sync`) automatically, so the first
   run is slow; later ones are instant.
2. *(Recommended)* Install the terminal commands used for the steps Claude can't do for
   you — entering secrets and OAuth/Keychain prompts:
   ```bash
   uv tool install git+https://github.com/ashok-kallara/Sophonic
   ```
   This gives you `sophonic-config`, `sophonic-doctor`, and `sophonic-auth` on your
   `PATH`. Every hint the plugin prints ("run `sophonic-auth google`…") assumes them.
3. For Zoom, install the Playwright browser once. `/sophonic:setup` does this for you; by
   hand, it must run in the plugin's own environment (the browser build is tied to the
   Playwright version in `uv.lock`, which `uv tool install` does not use):
   ```bash
   uv run --project ~/.claude/plugins/cache/sophonic/sophonic/<commit-sha> playwright install chromium
   ```
   (or `uv run playwright install chromium` from a clone).

No `ANTHROPIC_API_KEY` / `SOPHONIC_LLM_API_KEY` is needed — Claude Code provides the model.

**Updating:** `/plugin marketplace update sophonic`, then `/plugin update sophonic@sophonic`
(or enable auto-update for the marketplace in `/plugin`) and `/reload-plugins`. Refresh the
terminal commands with `uv tool upgrade sophonic`. The plugin deliberately sets no `version`,
so Claude Code uses the git commit SHA: every push to `main` is a new version, with nothing
to bump.

**From a local clone (development):**
```bash
git clone https://github.com/ashok-kallara/Sophonic ~/src/sophonic
```
then in Claude Code:
```
/plugin marketplace add ~/src/sophonic
/plugin install sophonic@sophonic
```
and optionally `uv tool install --editable ~/src/sophonic` for the terminal commands.
After edits, `/reload-plugins` picks them up. Enable/disable per session with
`/plugin enable|disable sophonic@sophonic`; the enabled state is stored in
`~/.claude/settings.json` (user scope) or `.claude/settings.json` (project scope).

## Configure

Configuration lives in `~/.sophonic/config.toml` (settings) and `~/.sophonic/.env`
(secrets, `0600`). Three ways to manage it:

**1. Guided (inside Claude Code):** run **`/sophonic:setup`** — Claude probes what's
configured, interviews you for gaps, and applies them.

**2. Direct from inside Claude Code:** **`/sophonic:config`** — e.g.
`/sophonic:config set vault.path /path/to/vault` or `/sophonic:config show`. Claude runs
the change for you (it will hand secret entry back to your terminal).

**3. Terminal commands:** installed by the `uv tool install` step above — thin console
scripts for people who prefer the shell, and the way to enter secrets without them
touching the chat transcript:
```bash
sophonic-config show                       # effective config (secrets redacted)
sophonic-config set vault.path /path/to/vault
sophonic-config set features.gitlab true
sophonic-config set-secret ZOOM_COOKIES --stdin   # paste, then Enter
sophonic-doctor                            # status of every integration
sophonic-auth google | slack | zoom        # authenticate
```
The skills call the same code through `scripts/*.py` (resolved via `${CLAUDE_PLUGIN_ROOT}`),
so the plugin works even if you skip the terminal commands. Set `SOPHONIC_VAULT` in your environment to override the vault path.

Config keys: `vault.{path,daily_dir,daily_prefix,meetings_dir,wiki_dir}` ·
`features.{obsidian,reminders,google,slack,zoom,gitlab,raindrop}` ·
`google.{client_secret_file,scopes}` · `browser.zoom.engine` (`chromium`|`chrome`|`island`) ·
`slack.workspace_host` · `gitlab.{url,default_project}` ·
`raindrop.default_collection`. Secrets (`.env`): `ZOOM_COOKIES`, `GITLAB_TOKEN`,
`RAINDROP_TOKEN`.

## Authenticate (run these in your own terminal)

These open a browser or read a local session, so you run them — not Claude (they use the
`sophonic-auth` command from `uv tool install` above):

```bash
sophonic-auth google   # OAuth consent (needs a Desktop-app client JSON)
sophonic-auth slack    # reads the signed-in Slack desktop app (Keychain prompt)
sophonic-auth zoom     # prints how to paste your zoom.us cookies
```

- **Google** — download a **Desktop app** OAuth client JSON from Google Cloud and save it
  at the path `doctor` reports (`~/.sophonic/google_client_secret.json` by default).
- **Slack** — macOS only; decrypts the desktop app's session via the Keychain (approve the
  one-time *Slack Safe Storage* prompt).
- **Zoom** — paste the `Cookie:` request header from https://zoom.us into
  `sophonic-config set-secret ZOOM_COOKIES --stdin`.
- **GitLab** — set `gitlab.url` and the `GITLAB_TOKEN` secret (PAT with `api` scope);
  requires GitLab 17.3+ (the `/api/v4/mcp` endpoint).
- **Raindrop.io** — no browser flow: create a permanent "test token" at
  raindrop.io/settings/integrations (+ Create new app → Create test token) and set it as
  the `RAINDROP_TOKEN` secret.

## Use it

Talk to Claude naturally ("what's on my calendar?", "roll over yesterday's tasks",
"remind me to send the deck Friday", "what did I miss on Slack?") — the matching skill
activates. Or use the slash commands:

- `/sophonic:start-my-day` — build today's note and merge Zoom action items, Google Tasks,
  Google Drive comments, and Slack follow-ups, plus a summary of informational Slack
  channels. (Rollover is folded into this and into `/sophonic:obsidian` — there's no
  separate rollover command.)
- `/sophonic:today` — calendar + tasks due today + yesterday's unfinished (read-only).
- `/sophonic:ask` — ad-hoc cross-source search (Obsidian, Tasks, Drive, Gmail, Slack,
  Calendar, Zoom, GitLab) when you don't know which source has the answer.
- `/sophonic:meeting-recap` — pull today's Zoom AI Companion meeting summaries into a
  `## Meeting Recaps` section in today's note (idempotent — skips meetings already
  captured without refetching).
- `/sophonic:raindrop` — turn saved Raindrop.io bookmarks (last 30 days by default) into
  one reference note per article under `<vault>/WIKI/`, with a summary, expanded
  context, key tenets, and takeaways — research papers get a plain-language rewrite.
- `/sophonic:setup` — guided configuration.
- `/sophonic:config` — view or change a config value directly (e.g. `set vault.path …`).

Every skill is also its own slash command (`/sophonic:gcal`, `/sophonic:gdrive`,
`/sophonic:slack`, …) for a fast, single-source lookup instead of `ask`'s full fan-out.

## Vault conventions

- Daily notes: `<vault>/Daily/DAILY-YYYY-MM-DD.md`.
- Tasks (Obsidian Tasks emoji format):
  `- [ ] text ⏫|🔼|🔽 📅 YYYY-MM-DD #tag`; completed `- [x] … ✅ YYYY-MM-DD`.
- Tasks under `## Tasks`, backlinks under `## Notes`, meeting action items under
  `## Meeting Action Items`, meeting transcripts under `Work/Meetings/`.
- Bookmark reference notes (from `/sophonic:raindrop`) under `WIKI/`, one markdown file
  per article, plus a `WIKI/WIKI Index.md` grouped by month.

The full contract lives in `skills/obsidian/SKILL.md`. Because vault edits are skill-driven
(not enforced by code), the conventions there are what keep formatting and idempotent
rollover consistent — Claude always reads a note before writing it.

## Debugging the scripts

Every fetcher prints a single JSON object and needs no LLM key, so you can run any of them
by hand from a clone (or `uv run --project <plugin dir> python <plugin dir>/scripts/…`
against the installed copy under `~/.claude/plugins/cache/`):

```bash
uv run python scripts/doctor.py
uv run python scripts/slack.py followups --days 2
uv run python scripts/zoom.py action-items --days 1
uv run python scripts/gcal.py events-today
uv run python scripts/gitlab.py tools
uv run python scripts/raindrop.py list --days 30
```

On an auth gap a script prints `{"needs_auth": true, "run": "..."}`; run the given
command in your terminal.

## Adding an integration

1. Add the API/auth code to `sophonic/<name>.py` (keep it read-only and return plain data).
2. Add a `scripts/<name>.py` argv → JSON shim (import from `sophonic/`, use `_common.run`).
3. Add `skills/<name>/SKILL.md` documenting when to use it and the invocation contract.
4. If it should participate in the morning brief, reference it from `skills/start-my-day`.

## Requirements

Python ≥ 3.12, `uv`. Slack is macOS-only (Keychain-decrypted desktop session). Tests:
`uv run pytest`.
