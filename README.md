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
so installing is two commands inside Claude Code.

**From GitHub:**
```
/plugin marketplace add <owner>/sophonic
/plugin install sophonic@sophonic
```

**From a local clone (development):**
```
git clone <repo> ~/src/sophonic
```
then in Claude Code:
```
/plugin marketplace add ~/src/sophonic
/plugin install sophonic@sophonic
```
(`/plugin` opens an interactive browser for the same thing. Non-interactively:
`claude plugin install sophonic@sophonic --scope user`.) After changes to the plugin
files, `/reload-plugins` picks them up. Enable/disable per session with
`/plugin enable|disable sophonic@sophonic`; the enabled state is stored in
`~/.claude/settings.json` (user scope) or `.claude/settings.json` (project scope).

**Prerequisites:**
1. Install [`uv`](https://docs.astral.sh/uv/) — the scripts run under it. The first
   script call triggers `uv sync` automatically; you can also run it once up front from
   the plugin directory: `uv sync`.
2. For Zoom, install the Playwright browser once: `uv run playwright install chromium`.

No `ANTHROPIC_API_KEY` / `SOPHONIC_LLM_API_KEY` is needed — Claude Code provides the model.

## Configure

Configuration lives in `~/.sophonic/config.toml` (settings) and `~/.sophonic/.env`
(secrets, `0600`). Three ways to manage it:

**1. Guided (inside Claude Code):** run **`/sophonic:setup`** — Claude probes what's
configured, interviews you for gaps, and applies them.

**2. Direct from inside Claude Code:** **`/sophonic:config`** — e.g.
`/sophonic:config set vault.path /path/to/vault` or `/sophonic:config show`. Claude runs
the change for you (it will hand secret entry back to your terminal).

**3. Terminal CLI wrapper (optional):** the plugin ships thin console scripts for people
who prefer the shell. After `uv sync` (or `uv tool install .` for a global command):
```bash
sophonic-config show                       # effective config (secrets redacted)
sophonic-config set vault.path /path/to/vault
sophonic-config set features.gitlab true
sophonic-config set-secret ZOOM_COOKIES --stdin   # paste, then Enter
sophonic-doctor                            # status of every integration
sophonic-auth google | slack | zoom        # authenticate
```
The equivalent no-install form is `uv run python scripts/config.py …` (this is exactly
what the skills call). Set `SOPHONIC_VAULT` in your environment to override the vault path.

Config keys: `vault.{path,daily_dir,daily_prefix,meetings_dir,wiki_dir}` ·
`features.{obsidian,reminders,google,slack,zoom,gitlab,raindrop}` ·
`google.{client_secret_file,scopes}` · `browser.zoom.engine` (`chromium`|`chrome`|`island`) ·
`slack.workspace_host` · `gitlab.{url,default_project}` ·
`raindrop.default_collection`. Secrets (`.env`): `ZOOM_COOKIES`, `GITLAB_TOKEN`,
`RAINDROP_TOKEN`.

## Authenticate (run these in your own terminal)

These open a browser or read a local session, so you run them — not Claude (use the
`sophonic-auth` wrapper after `uv sync`, or the `uv run …` form):

```bash
sophonic-auth google   # OAuth consent (needs a Desktop-app client JSON)
sophonic-auth slack    # reads the signed-in Slack desktop app (Keychain prompt)
sophonic-auth zoom     # prints how to paste your zoom.us cookies
# no-install form: uv run python scripts/auth.py <service>
```

- **Google** — download a **Desktop app** OAuth client JSON from Google Cloud and save it
  at the path `doctor` reports (`~/.sophonic/google_client_secret.json` by default).
- **Slack** — macOS only; decrypts the desktop app's session via the Keychain (approve the
  one-time *Slack Safe Storage* prompt).
- **Zoom** — paste the `Cookie:` request header from https://zoom.us into
  `scripts/config.py set-secret ZOOM_COOKIES --stdin`.
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
by hand:

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
