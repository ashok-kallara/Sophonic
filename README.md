# Sophonic

A lightweight, Obsidian-native AI assistant for your terminal and IDE — no web UI, no cloud dashboard. It reads and writes your Obsidian vault directly, pulls live context from Google Calendar, Gmail, Slack, and Zoom, and runs both as a CLI (`sophonic`) and as an MCP server (`sophonic-mcp`) you can register in Claude Code, Cursor, or any MCP-aware IDE.

## Contents

- [Capabilities](#capabilities)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Authentication](#authentication)
- [CLI Reference](#cli-reference)
- [MCP Server](#mcp-server)
- [Skills System](#skills-system)
- [Obsidian Conventions](#obsidian-conventions)
- [Project Structure](#project-structure)
- [Development](#development)

---

## Capabilities

| Integration | What it does |
|---|---|
| **Obsidian** | Per-day daily notes (`Daily/DAILY-YYYY-MM-DD.md`). Adds/lists/completes tasks in [Obsidian Tasks](https://obsidian-tasks-group.github.io/obsidian-tasks/) emoji format, rolls over incomplete items, full-text search via ripgrep. |
| **Reminders** | Parses natural language ("send report next Friday") into task lines with `📅 YYYY-MM-DD` due dates. |
| **Google Calendar** | Lists events for today or any date range (read-only OAuth). |
| **Gmail** | Lists unread, searches, fetches full threads (read-only OAuth). |
| **Slack** | Reads the Slack **desktop app** session locally (decrypts its `d` cookie) and calls the Slack Web API — unread channels/DMs and search. No browser, no admin app/token. |
| **Zoom** | Reads Zoom's **AI Companion meeting notes** (auto-generated per meeting, via Zoom Docs) from your pasted `zoom.us` session — lists them and files them as Obsidian meeting notes. No cloud recording needed. |
| **GitLab** | MCP proxy to a self-hosted GitLab (17.3+): issues, MRs, pipelines, wiki. Auth via Personal Access Token. |

---

## Architecture

```
                  ┌─────────────────────────────────────────┐
   $ sophonic ...  │   sophonic.cli (Typer)                   │
                  │   Anthropic/OpenAI tool-use loop (ask)   │
                  └──────────────┬──────────────────────────┘
                  ┌──────────────▼──────────────────────────┐
                  │   sophonic.skills  (behavior layer)      │
                  │   SKILL.md per namespace · skill_load   │
                  └──────────────┬──────────────────────────┘
                  ┌──────────────▼──────────────────────────┐
                  │   sophonic.tools  (mechanism layer)      │
                  │   obsidian · reminders · gcal · gmail   │
                  │   slack_local · zoom · gitlab (MCP proxy)│
                  └──────────────▲──────────────────────────┘
                  ┌──────────────┴──────────────────────────┐
   Claude Code /  │   sophonic.mcp_server (FastMCP, stdio)   │
   Cursor / IDE   │   tools + skills as MCP Prompts         │
                  └─────────────────────────────────────────┘
```

Both entry points share identical tool and skill implementations. The MCP server exposes tools as namespaced names (`obsidian_*`, `gcal_*`, …) so `allowedTools` rules can target whole namespaces. Skills are also exposed as MCP Prompts.

---

## Requirements

- **Python 3.12+** and **[uv](https://docs.astral.sh/uv/)** (`brew install uv`)
- **Anthropic API key** — for `sophonic ask`
- **Obsidian** with the [Tasks plugin](https://obsidian-tasks-group.github.io/obsidian-tasks/)
- **Google Cloud project** with Calendar + Gmail APIs — only for `sophonic auth google`
- **Playwright browser** — only for Zoom; installed for you by `sophonic init` (or run `playwright install chromium` manually)

---

## Installation

```bash
git clone <repo-url> && cd sophonic
uv sync                                  # installs deps + generates the executables
```

Then run `sophonic init` (below) — it installs the Playwright browser and walks you
through configuration. (Or install the browser manually: `uv run playwright install chromium`.)

### How the `sophonic` executable is generated

`sophonic` and `sophonic-mcp` are **Python console scripts**, not compiled binaries. They're declared in `pyproject.toml`:

```toml
[project.scripts]
sophonic     = "sophonic.cli:app"           # → runs sophonic/cli.py:app
sophonic-mcp = "sophonic.mcp_server:main"   # → runs sophonic/mcp_server.py:main
```

`uv sync` installs the package into `.venv/` and generates wrapper scripts at `.venv/bin/sophonic` and `.venv/bin/sophonic-mcp`. You can run them three ways:

```bash
uv run sophonic --help          # run inside the project venv (no activation needed)
source .venv/bin/activate        # then bare `sophonic` works in this shell
uv tool install .                # install `sophonic` onto your PATH globally
```

The rest of this README uses bare `sophonic ...` — that assumes the venv is active or you've run `uv tool install .`. Otherwise prefix commands with `uv run`.

### First-run setup

The fastest path is the interactive wizard. It first installs third-party runtime
dependencies (the Playwright browser used by Zoom), then writes `~/.sophonic/config.toml`
and `~/.sophonic/.env` (0600), and can launch the auth flows at the end:

```bash
sophonic init
```

Check what's configured or still missing at any time:

```bash
sophonic doctor          # JSON status per integration, with a fix command for each gap
```

Prefer to do it by hand? Secrets live in `~/.sophonic/.env` and are **loaded
automatically** (no shell-profile exports needed):

```bash
mkdir -p ~/.sophonic
printf 'sk-ant-...\n' | sophonic config set-secret ANTHROPIC_API_KEY --stdin   # keeps the key out of shell history
sophonic config set vault.path "/Users/you/Documents/Obsidian/your-vault"
```

`SOPHONIC_VAULT` / `GITLAB_TOKEN` environment variables still work and take
precedence over `.env` if set.

---

## Configuration

All settings live in `~/.sophonic/config.toml`. Every key has a working default — create the file only to override.

```toml
[vault]
path         = "/Users/you/Documents/Obsidian/your-vault"
daily_dir    = "Daily"            # → Daily/DAILY-YYYY-MM-DD.md
daily_prefix = "DAILY-"
meetings_dir = "Work/Meetings"    # Zoom transcripts filed here

[features]                        # disabled features skip imports, CLI cmds, and MCP tools
obsidian = true
reminders = true
google = true                     # Calendar + Gmail
slack = true
zoom = true
gitlab = false                    # enable once [gitlab] is configured

[google]
client_secret_file = "~/.sophonic/google_client_secret.json"
scopes = [
  "https://www.googleapis.com/auth/calendar.readonly",
  "https://www.googleapis.com/auth/gmail.readonly",
]

[browser.zoom]                    # engine: "chromium" (default) | "chrome" | "island"
engine = "chromium"               # Zoom is the only browser-driven integration
[browser.island]
path = ""                         # auto-detected at /Applications/Island.app if empty

[slack]
# workspace_host = "acme.enterprise.slack.com"   # optional; only if token auto-detect fails

[llm]
model = "claude-sonnet-4-6"

[gitlab]
url             = "https://gitlab.company.com"
token           = "glpat-..."     # PAT with api scope; or set GITLAB_TOKEN
default_project = "group/project"
```

### Browser engine (Zoom)

Zoom is the only browser-driven integration (Slack and Google use APIs). It runs headless
with your pasted `zoom.us` cookies via `[browser.zoom] engine`, defaulting to Playwright's
bundled Chromium.

| Engine | When to use |
|---|---|
| `chromium` | Default. Playwright's bundled browser — no external install. |
| `chrome` | Your installed Chrome, via a dedicated profile (never touches your real one). |
| `island` | [Island](https://www.island.io/) enterprise browser. Note: managed Island builds often disallow automation, so `chromium` is recommended. |

### Google OAuth setup

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project and enable the **Calendar** and **Gmail** APIs.
2. Create an **OAuth 2.0 Client ID** (Desktop app), download the JSON, save it as `~/.sophonic/google_client_secret.json`.
3. Run `sophonic auth google` — consent in the browser; tokens are saved to `~/.sophonic/tokens/google.json`.

### LLM provider

`sophonic ask` uses Anthropic by default (prompt caching enabled). It also talks to **any OpenAI-compatible endpoint** (OpenAI, Azure, Ollama, OpenRouter, Groq, vLLM, LM Studio, LiteLLM) — the OpenAI client ships by default, no extra install:

```toml
[llm]
provider = "openai"
model = "gpt-4o"
# api_base = "http://localhost:11434/v1"   # e.g. local Ollama
# max_tokens = 4096
```

Use `provider = "litellm"` for a [LiteLLM proxy](https://docs.litellm.ai/docs/simple_proxy) — it behaves like `openai` (same OpenAI-compatible client) but `api_base` is required (`sophonic doctor` flags it if missing):

```toml
[llm]
provider = "litellm"
model    = "bedrock/us.anthropic.claude-opus-4-8"   # a proxy alias
api_base = "https://litellm.example.com"            # proxy root, required
```

| Setting | Purpose | Default |
|---|---|---|
| `provider` | `"anthropic"`, `"openai"`, or `"litellm"` | `"anthropic"` |
| `model` | Model name | `"claude-sonnet-4-6"` |
| `api_base` | OpenAI-compatible base URL (required for `litellm`) | provider default |
| `max_tokens` | Max output tokens per turn | `4096` |

**API key — one variable for any provider.** Set `SOPHONIC_LLM_API_KEY` and it's used
whatever the provider (`sophonic config set-secret SOPHONIC_LLM_API_KEY --stdin`). As a
convenience the standard native vars are also honored as a fallback: `ANTHROPIC_API_KEY`
for `anthropic`, `OPENAI_API_KEY` for `openai`. (`litellm` uses only `SOPHONIC_LLM_API_KEY`.)

`provider` and `model` can be overridden per-run via `SOPHONIC_LLM_PROVIDER` / `SOPHONIC_LLM_MODEL`. Prompt caching applies only on the native Anthropic path.

---

## Authentication

```bash
sophonic auth google    # OAuth flow → ~/.sophonic/tokens/google.json (auto-refreshes)
sophonic auth slack     # verifies the Slack desktop-app session (no browser)
sophonic auth zoom      # prints how to paste your zoom.us cookies (no browser)
```

**Slack** reads the signed-in **Slack desktop app**'s session directly — no browser
login. `sophonic auth slack` decrypts the app's `d` cookie (approve the one-time
Keychain prompt for *Slack Safe Storage*), obtains the workspace token, and verifies
via `auth.test`. If the token can't be auto-detected, set `[slack] workspace_host`
(e.g. `your-org.enterprise.slack.com`) or the `SLACK_XOXC_TOKEN` secret.

**Zoom** reads your **AI Companion meeting notes** (Zoom Docs) using your `zoom.us` web
session cookies (browser automation is blocked in managed browsers like Island). Grab
them straight from the request header:

1. Log in to `zoom.us`, then open your browser's **DevTools → Network** tab.
2. Click any request to `zoom.us`, find **Request Headers**, and copy the entire
   **`Cookie:`** value (the `name=value; name2=value2` string). A leading `Cookie:`
   label is accepted and stripped, so copying the whole line is fine.
3. Store it (paste on one line, then press **Return** — it reads a single line, so no Ctrl-D):

```bash
sophonic config set-secret ZOOM_COOKIES --stdin
# ...or pipe it directly:
pbpaste | sophonic config set-secret ZOOM_COOKIES --stdin
```

Then `sophonic zoom notes` lists recent AI notes and `sophonic zoom save <id>` files one
as an Obsidian meeting note (via Playwright's bundled Chromium, headless). Cookies
expire faster than Slack's, so re-paste when `zoom` commands report `needs_auth`.

> The legacy Playwright browser-scraping path (and `[browser.*] engine`, incl. Island)
> is retained only for environments where a browser *can* be automated; the flows above
> are the supported default.

---

## CLI Reference

Set `SOPHONIC_VAULT` (env or config) so commands know where your vault is.

```bash
# Daily workflow
sophonic daily              # print today's note (creates from template if missing)
sophonic today             # calendar + due tasks + yesterday's incomplete
sophonic rollover          # copy yesterday's incomplete tasks into today (idempotent)

# Reminders & tasks
sophonic remind "send Q2 slides next Friday"
sophonic tasks --due today
sophonic tasks --due 2026-05-10        # due before this date
sophonic tasks --overdue
sophonic tasks --incomplete-yesterday

# Mail
sophonic mail unread --max 50

# Slack
sophonic slack unread
sophonic slack search "incident postmortem"

# Zoom (AI Companion meeting notes)
sophonic zoom notes --limit 20
sophonic zoom save PUB4Gms1RyKnVL_rSUuUBw --title "Data Leads Weekly"

# AI assistant (full tool-use loop)
sophonic ask "what's on my calendar and are there unfinished tasks?"
```

`rollover` is cron-safe:

```cron
0 8 * * * /path/to/sophonic rollover
```

**Natural-language dates:** `tomorrow`, `next Friday`, `this Monday`, `in 3 days`, `in 2 weeks`, ISO dates (`2026-05-10`), and month names (`May 15`, via dateparser).

If a Slack/Zoom command isn't authenticated, it prints `Not authenticated. Run: sophonic auth <name>` and exits cleanly.

---

## MCP Server

`sophonic-mcp` runs over stdio. There are two ways to connect it to Claude Code.

> **Environment:** Sophonic auto-loads `~/.sophonic/.env`, so the MCP server picks up `SOPHONIC_LLM_API_KEY`, `ANTHROPIC_API_KEY`, `SOPHONIC_VAULT`, etc. from there even when Claude Code spawns it without your shell profile. You can also set the vault path in `~/.sophonic/config.toml`.

### Option A — as a Claude Code plugin (recommended)

The repo ships a plugin: `.claude-plugin/plugin.json` (manifest) plus a bundled `.mcp.json` that launches the server via `uv run --project ${CLAUDE_PLUGIN_ROOT} sophonic-mcp` and forwards `SOPHONIC_VAULT` / `ANTHROPIC_API_KEY` from your environment. Point Claude Code at your clone:

```bash
claude --plugin-dir /Users/you/projects/sophonic
```

In that session the `sophonic` MCP server is live — run `/mcp` to confirm the tools and `/plugin` to see it listed. Iterate with `/reload-plugins` after edits.

To load it every session without the flag, distribute it through a [plugin marketplace](https://code.claude.com/docs/en/plugin-marketplaces) (or reference the repo from a team `.claude/settings.json`).

### Option B — as a plain MCP server

Register it manually in `~/.claude.json` (or a project's `.claude/settings.json`):

```json
{
  "mcpServers": {
    "sophonic": {
      "command": "uv",
      "args": ["run", "--project", "/Users/you/projects/sophonic", "sophonic-mcp"],
      "env": {
        "SOPHONIC_VAULT": "/Users/you/Documents/Obsidian/your-vault",
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

Or: `/mcp add sophonic uv run --project /Users/you/projects/sophonic sophonic-mcp`

### Auto-approve safe reads

Use `allowedTools`:

```json
{ "allowedTools": ["mcp__sophonic__obsidian_*", "mcp__sophonic__gcal_*", "mcp__sophonic__reminder_create"] }
```

### Tools

Disabled features contribute zero tools. GitLab registers `gitlab_*` tools dynamically based on what your instance exposes.

| Namespace | Tools |
|---|---|
| **obsidian** | `add_task`, `list_tasks`, `incomplete_yesterday`, `rollover`, `complete_task`, `daily_note`, `read_note`, `write_note`, `append_note`, `search`, `save_meeting_note` |
| **reminder** | `create` |
| **gcal** | `events_today`, `events_range` |
| **gmail** | `unread`, `search`, `thread` |
| **slack** | `unread`, `search` |
| **zoom** | `notes`, `note`, `save_note` |
| **gitlab** | `list_projects`, `get_project`, `list_issues`, `get_issue`, `create_issue`, `update_issue`, `create_note`, `list_merge_requests`, `get_merge_request`, `list_pipelines`, `get_pipeline`, `retry_failed_ci_jobs`, `list_wiki_pages`, `get_wiki_page` |
| **(meta)** | `skill_load` — load full instructions for a namespace before using unfamiliar tools |

---

## Skills System

Sophonic separates **mechanism** (Python: OAuth, Playwright, filesystem) from **behavior** (prompts, conventions). Behavior lives in `SKILL.md` files (YAML frontmatter + Markdown), one per namespace under `src/sophonic/skills/`.

The system prompt carries only a compact **index** of skill names/descriptions (~30 tokens each). When the model needs a capability in depth, it calls `skill_load("obsidian")` to fetch the full body on demand.

```markdown
---
name: obsidian
description: Obsidian vault operations — daily notes, tasks, search. Trigger on tasks/notes/vault.
tools: [obsidian_add_task, obsidian_list_tasks, obsidian_daily_note]
---

# Obsidian
- `obsidian_add_task(text, due?, priority?, tags?)` — appends under ## Tasks in today's note.
...
```

The `tools:` list is validated at startup — Sophonic errors on boot if any listed tool isn't registered, keeping skills in sync with the code.

**User overrides:** drop a replacement at `~/.sophonic/skills/<name>/SKILL.md` to fully replace a bundled skill (no merging). Templates (`*.md.j2`) override the same way.

In Claude Code, skills are also first-class **MCP Prompts** — visible in `/prompts` and fetchable by any MCP client without calling `skill_load`.

---

## Obsidian Conventions

Works with the [Obsidian Tasks plugin](https://obsidian-tasks-group.github.io/obsidian-tasks/) — no vault config changes needed.

### Daily notes

Each day gets `Daily/DAILY-YYYY-MM-DD.md` (configurable), created from this template on first write:

```markdown
# DAILY 2026-05-03
#sophonic

## Tasks

## Notes
```

Tasks go under `## Tasks`, free-form content under `## Notes`. Existing single-file daily notes are left untouched.

### Task format

```
- [ ] Pay rent 📅 2026-05-05 ⏫ #personal/finance
- [x] Send slides ✅ 2026-05-03
```

| Emoji | Meaning |
|---|---|
| `📅 YYYY-MM-DD` | Due date |
| `⏫` / `🔼` / `🔽` | High / Medium / Low priority |
| `✅ YYYY-MM-DD` | Completion date |

### Meeting notes

`zoom_save_note` writes `Work/Meetings/YYYY-MM-DD - <title>.md` with source metadata and the AI note content, then adds a backlink under `## Notes` in today's daily note:

```markdown
## Notes
- [[Work/Meetings/2026-05-03 - Q2 Planning]]
```

All Sophonic-created notes carry a `#sophonic` tag for easy Dataview queries.

---

## Project Structure

```
sophonic/
├── pyproject.toml               # deps, console scripts, pytest config
├── .claude-plugin/plugin.json   # Claude Code plugin manifest
├── .mcp.json                    # bundled MCP server config (used by the plugin)
├── src/sophonic/
│   ├── config.py                # Pydantic config, loads ~/.sophonic/config.toml
│   ├── paths.py · dates.py      # vault paths · natural-language date parser
│   ├── google_auth.py           # shared Google OAuth 2.0 flow
│   ├── browser.py               # Playwright persistent context (chromium/chrome/island)
│   ├── llm.py                   # Anthropic/OpenAI client, prompt caching, tool-use loop
│   ├── cli.py · mcp_server.py   # Typer CLI · FastMCP stdio server (the two entry points)
│   ├── skills.py                # skill discovery, index, skill_load, template renderer
│   ├── skills/<name>/SKILL.md   # one skill per namespace (+ obsidian templates/*.md.j2)
│   └── tools/
│       ├── __init__.py          # build_registry() — feature-gated tool registration
│       ├── obsidian.py · reminders.py · gcal.py · gmail.py
│       └── slack_local.py · zoom.py · gitlab.py
└── tests/                       # mocked Playwright + Google clients; no network/creds needed
```

---

## Development

```bash
uv run -- python -m pytest                      # all tests
uv run -- python -m pytest tests/test_obsidian.py -v
```

### Adding a new integration

1. Create `src/sophonic/tools/<name>.py` exporting a `TOOLS: dict[str, Any]` mapping tool names to functions.
2. Create `src/sophonic/skills/<name>/SKILL.md` with frontmatter listing those exact tool names (validated at startup).
3. Add a flag to `FeaturesConfig` in `config.py`.
4. Register it in `build_registry()` in `tools/__init__.py`:

   ```python
   if cfg.myintegration:
       from sophonic.tools import myintegration
       for name, fn in myintegration.TOOLS.items():
           register(name, fn)
   ```

5. Add CLI subcommands in `cli.py` if needed, and tests in `tests/test_<name>.py`.

The MCP server and skill index pick up new tools automatically — no changes to `mcp_server.py` or `llm.py` needed.
