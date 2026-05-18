# Sophonic

A lightweight, Obsidian-native AI assistant that lives in your terminal and IDE — no web UI, no cloud dashboard. It reads and writes your Obsidian vault directly, pulls live context from Google Calendar, Gmail, Slack, and Zoom, and is available both as a CLI (`sophonic`) and as an MCP server (`sophonic-mcp`) you can register in Claude Code, Cursor, or any IDE that supports MCP.

---

## Table of Contents

- [Capabilities](#capabilities)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Vault settings](#vault-settings)
  - [Feature toggles](#feature-toggles)
  - [Browser engine (Slack & Zoom)](#browser-engine-slack--zoom)
  - [Google OAuth](#google-oauth)
  - [LLM model](#llm-model)
- [Authentication](#authentication)
  - [Google (Calendar + Gmail)](#google-calendar--gmail)
  - [Slack](#slack)
  - [Zoom](#zoom)
- [CLI Reference](#cli-reference)
  - [Daily workflow](#daily-workflow)
  - [Reminders & tasks](#reminders--tasks)
  - [Mail](#mail)
  - [Slack](#slack-1)
  - [Zoom](#zoom-1)
  - [AI assistant (free-form)](#ai-assistant-free-form)
  - [Auth](#auth)
- [MCP Server](#mcp-server)
  - [Registering in Claude Code](#registering-in-claude-code)
  - [Tool reference](#tool-reference)
- [Obsidian Conventions](#obsidian-conventions)
  - [Daily notes](#daily-notes)
  - [Task format](#task-format)
  - [Meeting notes](#meeting-notes)
- [Project Structure](#project-structure)
- [Development](#development)
  - [Running tests](#running-tests)
  - [Adding a new integration](#adding-a-new-integration)

---

## Capabilities

| Integration | What it does |
|---|---|
| **Obsidian** | Creates and reads per-day daily notes (`Daily/DAILY-YYYY-MM-DD.md`). Adds tasks under `## Tasks` in today's note using the [Obsidian Tasks](https://obsidian-tasks-group.github.io/obsidian-tasks/) emoji format. Lists tasks by due date, rolls over incomplete items from the previous day, marks tasks complete. Full-text vault search via ripgrep. |
| **Reminders** | Parses natural-language phrases ("send report next Friday", "call dentist in 3 days") into Tasks-plugin-formatted task lines with `📅 YYYY-MM-DD` due dates, appended to today's daily note. |
| **Google Calendar** | Lists events for today or any date range via read-only OAuth. |
| **Gmail** | Lists unread messages, searches by Gmail query, fetches full threads. Read-only OAuth. |
| **Slack** | Playwright-based web scraper: lists unread channels/DMs, searches Slack. Works when the Slack MCP is not available due to admin restrictions. Supports Chromium, Chrome, and Island browsers. |
| **Zoom** | Playwright-based transcript scraper: lists recordings from the web portal, fetches transcript text, and files transcripts as Obsidian meeting notes under `Work/Meetings/` with a backlink in the day's daily note. |

---

## Architecture

```
                  ┌─────────────────────────────────────────┐
   $ sophonic ...  │   sophonic.cli (Typer)                   │
                  │   Anthropic tool-use loop (sophonic ask) │
                  └──────────────┬──────────────────────────┘
                                 │
                  ┌──────────────▼──────────────────────────┐
                  │   sophonic.tools  (shared core)          │
                  │   obsidian · reminders · gcal · gmail   │
                  │   slack_web · zoom                      │
                  └──────────────▲──────────────────────────┘
                                 │
                  ┌──────────────┴──────────────────────────┐
   Claude Code /  │   sophonic.mcp_server (FastMCP, stdio)   │
   Cursor / IDE   │   22 namespaced tools                   │
                  └─────────────────────────────────────────┘
```

Both entry points share identical tool implementations — no duplicated logic. The MCP server exposes all tools as namespaced names (`obsidian_*`, `gcal_*`, `gmail_*`, `slack_*`, `zoom_*`, `reminder_*`) so `allowedTools` rules in Claude Code can target whole namespaces.

---

## Requirements

- **Python 3.12+** (managed by `uv`)
- **[uv](https://docs.astral.sh/uv/)** — `brew install uv`
- **Anthropic API key** — for `sophonic ask` (CLI AI mode)
- **Obsidian** with the [Tasks plugin](https://obsidian-tasks-group.github.io/obsidian-tasks/) installed (already supported — no config changes needed)
- **Google Cloud project** with Calendar and Gmail APIs enabled — only for `sophonic auth google`
- **Playwright browsers** — installed once with `uv run playwright install chromium`
- **Island browser** (optional) — if your org uses [Island](https://www.island.io/) and you want Slack/Zoom scraped through it

---

## Installation

```bash
# 1. Clone
git clone <repo-url>
cd sophonic

# 2. Install dependencies
uv sync

# 3. Install Playwright's bundled browser (only needed for Slack/Zoom)
uv run playwright install chromium

# 4. Verify
uv run sophonic --help
uv run sophonic-mcp --help
```

Create `~/.sophonic/` and set your API key:

```bash
mkdir -p ~/.sophonic
echo 'ANTHROPIC_API_KEY=sk-ant-...' >> ~/.sophonic/.env
```

Add to your shell profile so `sophonic ask` can find it:

```bash
# ~/.zshrc or ~/.config/fish/config.fish
export ANTHROPIC_API_KEY="sk-ant-..."
export SOPHONIC_VAULT="/Users/you/Documents/Obsidian/your-vault"
```

---

## Configuration

All settings live in `~/.sophonic/config.toml`. Every key has a working default — create the file only for values you want to override.

```toml
[vault]
path        = "/Users/you/Documents/Obsidian/your-vault"
daily_dir   = "Daily"          # daily notes go in Daily/DAILY-YYYY-MM-DD.md
daily_prefix = "DAILY-"
meetings_dir = "Work/Meetings" # Zoom transcripts filed here

# Toggle integrations independently.
# Disabled integrations skip their imports, CLI commands, and MCP tools.
[features]
google = true   # Google Calendar + Gmail
slack  = true
zoom   = true

[google]
client_secret_file = "~/.sophonic/google_client_secret.json"
scopes = [
  "https://www.googleapis.com/auth/calendar.readonly",
  "https://www.googleapis.com/auth/gmail.readonly",
]

# Browser engine per integration.
# Options: "chromium" (default, bundled), "chrome", "island"
[browser.slack]
engine = "chromium"
[browser.zoom]
engine = "chromium"

# Override Island binary path (auto-detected at /Applications/Island.app/... if empty)
[browser.island]
path = ""

[slack]
workspace_url = "https://app.slack.com"   # or "https://yourcompany.slack.com"

[zoom]
recordings_url  = "https://zoom.us/recording"
save_transcripts = true   # auto-file fetched transcripts as meeting notes

[llm]
model = "claude-sonnet-4-6"
```

### Vault settings

- `daily_dir` + `daily_prefix` control the filename pattern. Default produces `Daily/DAILY-2026-05-03.md`.
- `meetings_dir` is where Zoom transcript notes are written. Created automatically on first use.

### Feature toggles

Set any of `google`, `slack`, `zoom` to `false` to completely disable that integration — its Python modules won't be imported, its CLI subcommands won't appear, and its MCP tools won't be registered. Useful during initial setup or when an integration is broken.

### Browser engine (Slack & Zoom)

Each Playwright-backed integration has its own engine setting and its own persistent session directory under `~/.sophonic/playwright-profile/<engine>-<integration>/`. Switching engines does not clobber an existing logged-in session.

| Engine | When to use |
|---|---|
| `chromium` | Default. Uses Playwright's bundled Chromium — no external install. |
| `chrome` | Uses your installed Google Chrome via Playwright. Requires Chrome. Uses a dedicated profile dir — never touches your real Chrome profile. |
| `island` | Uses [Island](https://www.island.io/) enterprise browser. Auto-detected at `/Applications/Island.app/`. Override with `[browser.island] path = "..."`. Useful when your org requires Island for SaaS access. |

### Google OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → enable **Google Calendar API** and **Gmail API**
3. Create an **OAuth 2.0 Client ID** (Desktop app type)
4. Download the JSON file and save it as `~/.sophonic/google_client_secret.json`
5. Run `sophonic auth google` — a browser tab opens for consent; tokens are saved to `~/.sophonic/tokens/google.json` (mode `0600`)

### LLM model

`sophonic ask` uses Anthropic's API with prompt caching enabled. Change the model in `[llm]`:

```toml
[llm]
model = "claude-opus-4-7"   # or claude-haiku-4-5-20251001 for faster/cheaper
```

---

## Authentication

### Google (Calendar + Gmail)

```bash
# One-time OAuth flow — opens a browser tab for Google consent
sophonic auth google
```

Tokens are stored at `~/.sophonic/tokens/google.json`. They refresh automatically on subsequent calls. Re-run the command if you change scopes in `config.toml`.

### Slack

```bash
# Opens your configured browser engine headed so you can log in
sophonic auth slack
```

Log in to your Slack workspace in the browser that opens, then press Enter in the terminal. The session (cookies + local storage) is persisted under `~/.sophonic/playwright-profile/chromium-slack/` (or the engine you configured). Subsequent `sophonic slack` commands run headless against that profile.

If your org uses Island, first set `[browser.slack] engine = "island"` in config, then run `sophonic auth slack`.

### Zoom

```bash
sophonic auth zoom
```

Same flow as Slack — logs in once, saves session, runs headless thereafter. Session stored under `~/.sophonic/playwright-profile/chromium-zoom/`.

---

## CLI Reference

Set `SOPHONIC_VAULT` in your environment or in `~/.sophonic/config.toml` so commands know where your vault is.

### Daily workflow

```bash
# Print today's daily note (creates it from template if it doesn't exist yet)
sophonic daily

# Show today's calendar + due tasks + anything incomplete from yesterday
sophonic today

# Copy yesterday's incomplete tasks into today's daily note (idempotent)
sophonic rollover
```

`sophonic rollover` is safe to run multiple times — it skips lines already present in today's note. Pair it with a cron job for automatic morning roll-over:

```cron
0 8 * * * /path/to/sophonic rollover
```

### Reminders & tasks

```bash
# Add a task to today's daily note with a parsed due date
sophonic remind "send Q2 slides to the team next Friday"
sophonic remind "call dentist tomorrow"
sophonic remind "pay credit card in 5 days"

# List tasks
sophonic tasks --due today
sophonic tasks --due 2026-05-10      # due before this date
sophonic tasks --overdue
sophonic tasks --incomplete-yesterday
```

**Supported natural-language date expressions:**

| Phrase | Resolves to |
|---|---|
| `tomorrow` | today + 1 day |
| `next Friday` | next occurrence of Friday (strictly next week) |
| `this Monday` | next occurrence of Monday (could be today+1 or this week) |
| `in 3 days` | today + 3 days |
| `in 2 weeks` | today + 14 days |
| `2026-05-10` | exact ISO date |
| Month names (`May 15`) | via dateparser fallback |

### Mail

```bash
sophonic mail unread               # 20 most recent unread messages
sophonic mail unread --max 50
```

### Slack

```bash
sophonic slack unread              # unread channels and DMs
sophonic slack search "incident postmortem"
```

If not authenticated, commands print `Not authenticated. Run: sophonic auth slack` and exit cleanly.

### Zoom

```bash
# List recent recordings (default: last 7 days)
sophonic zoom transcripts
sophonic zoom transcripts --since 14d

# Fetch a transcript and file it as an Obsidian meeting note
sophonic zoom save "https://zoom.us/recording/..." --title "Q2 Planning" --date 2026-05-03
```

`sophonic zoom save` writes the transcript to `Work/Meetings/YYYY-MM-DD - <title>.md` and adds a backlink under `## Notes` in today's daily note.

### AI assistant (free-form)

```bash
sophonic ask "what's on my calendar today and are there any unfinished tasks?"
sophonic ask "summarize my unread emails and add action items as tasks due today"
sophonic ask "find the standup transcript from yesterday and summarize blockers"
```

`sophonic ask` runs the full Anthropic tool-use loop — it calls whichever tools it needs (calendar, tasks, search, etc.) and returns a plain-English answer. Uses `claude-sonnet-4-6` with prompt caching by default.

### Auth

```bash
sophonic auth google    # OAuth flow for Calendar + Gmail
sophonic auth slack     # headed browser login for Slack
sophonic auth zoom      # headed browser login for Zoom
```

---

## MCP Server

`sophonic-mcp` runs as an MCP server over stdio. Any IDE that supports the Model Context Protocol can call it — Claude Code, Cursor, VS Code with an MCP extension, etc.

### Registering in Claude Code

Add to `~/.claude.json` (or to a project's `.claude/settings.json`):

```json
{
  "mcpServers": {
    "sophonic": {
      "command": "uv",
      "args": [
        "run",
        "--project", "/Users/you/projects/sophonic",
        "sophonic-mcp"
      ],
      "env": {
        "SOPHONIC_VAULT": "/Users/you/Documents/Obsidian/your-vault",
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

Or via the Claude Code `/mcp` command:

```
/mcp add sophonic uv run --project /Users/you/projects/sophonic sophonic-mcp
```

Once registered, Claude Code can call tools like `obsidian_add_task` directly without you typing anything — just ask it naturally and it will call the right tools.

**Tip:** Use `allowedTools` in `settings.json` to auto-approve safe reads without prompting:

```json
{
  "allowedTools": [
    "mcp__sophonic__obsidian_*",
    "mcp__sophonic__gcal_*",
    "mcp__sophonic__reminder_create"
  ]
}
```

### Tool reference

All 22 tools are available when all features are enabled. Disabled integrations contribute zero tools to the MCP manifest.

| Tool | Description |
|---|---|
| `obsidian_add_task` | Add a task line to today's (or a given) daily note |
| `obsidian_list_tasks` | List tasks matching a filter: `all`, `due_today`, `overdue`, `incomplete_yesterday`, `due_before:YYYY-MM-DD` |
| `obsidian_incomplete_yesterday` | Tasks not completed from yesterday |
| `obsidian_rollover` | Copy yesterday's incomplete tasks into today's daily note |
| `obsidian_complete_task` | Mark a task line as done (`[x]`) with a `✅ YYYY-MM-DD` stamp |
| `obsidian_daily_note` | Return the text of today's (or a given) daily note |
| `obsidian_read_note` | Read any note by vault-relative path |
| `obsidian_write_note` | Write/overwrite a note |
| `obsidian_append_note` | Append content to a note |
| `obsidian_search` | Full-text vault search (ripgrep, Python fallback) |
| `obsidian_save_meeting_note` | Write a meeting transcript note and backlink from today's daily note |
| `reminder_create` | Parse natural-language reminder phrase and add it as a task |
| `gcal_events_today` | Today's Google Calendar events |
| `gcal_events_range` | Calendar events between two dates |
| `gmail_unread` | Most recent unread Gmail messages |
| `gmail_search` | Search Gmail by any query string |
| `gmail_thread` | Full thread with body text |
| `slack_unread` | Unread Slack channels/DMs |
| `slack_search` | Search Slack |
| `zoom_transcripts` | List recent Zoom recordings |
| `zoom_transcript` | Fetch transcript text for a recording URL |
| `zoom_save_transcript` | Fetch transcript and file it as an Obsidian meeting note |

---

## Obsidian Conventions

Sophonic works with the [Obsidian Tasks plugin](https://obsidian-tasks-group.github.io/obsidian-tasks/) emoji format. No changes to your vault configuration are needed — the tools write standard Markdown that the plugin picks up automatically.

### Daily notes

Each day gets its own note at `Daily/DAILY-YYYY-MM-DD.md` (configurable). Created on first write of the day from this template:

```markdown
# DAILY 2026-05-03
#sophonic

## Tasks

## Notes
```

New tasks are inserted under `## Tasks`. Free-form content goes under `## Notes`. Existing vaults with a single rolling daily note (e.g. `Work/DAILY.md`) are left untouched — the new per-day notes live alongside them.

### Task format

Tasks follow the Obsidian Tasks emoji convention:

```
- [ ] Pay rent 📅 2026-05-05 ⏫ #personal/finance
- [ ] Review PR 📅 2026-05-04 🔼
- [x] Send slides ✅ 2026-05-03
```

| Emoji | Meaning |
|---|---|
| `📅 YYYY-MM-DD` | Due date |
| `⏫` | High priority |
| `🔼` | Medium priority |
| `🔽` | Low priority |
| `✅ YYYY-MM-DD` | Completion date (added when task is marked done) |

Your existing `Task Dashboard.md` (or any vault-wide Tasks query) picks up tasks written by Sophonic automatically — no dashboard changes needed.

### Meeting notes

`zoom_save_transcript` (and `sophonic zoom save`) writes notes to `Work/Meetings/YYYY-MM-DD - <title>.md` with this structure:

```markdown
---
source: zoom
recorded_at: 2026-05-03
tags: [sophonic]
---

# Q2 Planning

**Source URL:** https://zoom.us/recording/...

```
Speaker 1: Let's discuss Q2 goals...
Speaker 2: Agreed, here's my proposal...
```
```

A backlink is added to the day's `## Notes` section:

```markdown
## Notes
- [[Work/Meetings/2026-05-03 - Q2 Planning]]
```

All Sophonic-created notes include a `#sophonic` tag, making it easy to build a Dataview query of everything the assistant has written.

---

## Project Structure

```
sophonic/
├── pyproject.toml               # uv project: deps, console scripts, pytest config
├── uv.lock
├── .python-version              # 3.12
├── .env.example                 # copy to ~/.sophonic/.env
├── src/sophonic/
│   ├── config.py                # Pydantic config model, loads ~/.sophonic/config.toml
│   ├── paths.py                 # vault root, daily_note_path(), meetings_dir()
│   ├── dates.py                 # natural-language date parser (native + dateparser fallback)
│   ├── google_auth.py           # shared Google OAuth 2.0 flow
│   ├── browser.py               # Playwright persistent context (chromium/chrome/island)
│   ├── llm.py                   # Anthropic client, prompt caching, tool-use loop
│   ├── cli.py                   # Typer CLI app
│   ├── mcp_server.py            # FastMCP stdio server
│   └── tools/
│       ├── __init__.py          # build_registry() — feature-gated tool registration
│       ├── obsidian.py          # vault read/write, task CRUD, rollover, search
│       ├── reminders.py         # natural-language → Obsidian task line
│       ├── gcal.py              # Google Calendar (events_today, events_range)
│       ├── gmail.py             # Gmail (unread, search, thread)
│       ├── slack_web.py         # Playwright Slack scraper (unread, search)
│       └── zoom.py              # Playwright Zoom scraper (transcripts, save)
└── tests/
    ├── conftest.py              # use_fixture_vault autouse fixture
    ├── fixtures/vault/          # throwaway vault for tests
    ├── test_dates.py
    ├── test_obsidian.py
    ├── test_reminders.py
    ├── test_gcal.py
    ├── test_gmail.py
    ├── test_slack.py
    ├── test_zoom.py
    ├── test_llm_schema.py
    └── test_mcp.py
```

---

## Development

### Running tests

```bash
uv run pytest               # all 47 tests
uv run pytest -v            # verbose
uv run pytest tests/test_obsidian.py   # single file
```

All integration tests (Google, Slack, Zoom) use mocked Playwright and mocked Google API clients — no real network calls, no credentials needed.

### Adding a new integration

1. Create `src/sophonic/tools/<name>.py` with your functions and a `TOOLS` dict:

   ```python
   TOOLS: dict[str, Any] = {
       "myintegration_action": action_fn,
   }
   ```

2. Add a feature flag to `FeaturesConfig` in `config.py`:

   ```python
   class FeaturesConfig(BaseModel):
       myintegration: bool = True
   ```

3. Register it in `tools/__init__.py` inside `build_registry()`:

   ```python
   if cfg.myintegration:
       from sophonic.tools import myintegration
       for name, fn in myintegration.TOOLS.items():
           register(name, fn)
   ```

4. Add CLI subcommands in `cli.py` if needed.
5. Write tests with mocked external calls in `tests/test_<name>.py`.

The MCP server picks up new tools automatically via `build_registry()` — no changes to `mcp_server.py` needed.
