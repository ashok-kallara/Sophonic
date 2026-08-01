# Sophonic — Claude Code plugin (no MCP)

This plugin exposes Sophonic's capabilities inside Claude Code **without running the
MCP server**. Claude Code is the agent; the plugin's skills instruct Claude to call
the `sophonic` CLI through the Bash tool. Every tool the MCP server exposes is
reachable via a generic dispatcher:

```bash
sophonic tools                                  # list all available tools (JSON)
sophonic tool <name> --args-json '<JSON kwargs>'  # invoke one tool, print JSON
```

Tool calls need **no `ANTHROPIC_API_KEY`** — only Sophonic's config and (for some
integrations) a one-time auth step.

## Setup

1. **Install the CLI** from the project root (the parent of this `plugin/` dir):
   ```bash
   uv sync                        # generates the `sophonic` executable in .venv
   uv run playwright install chromium   # only if you use Slack/Zoom
   ```
   The bundled `bin/sophonic` wrapper runs the CLI via `uv run --project <repo>`,
   so it works as long as `uv` is on your PATH. Alternatively `uv tool install .`
   to put a real `sophonic` on your PATH and skip the wrapper.

2. **Configure.** Two ways:
   - **In your terminal:** `sophonic init` — an interactive wizard that walks every
     integration and writes `~/.sophonic/config.toml` + `~/.sophonic/.env` (0600).
   - **Inside Claude Code:** run `/sophonic:setup`. Claude runs `sophonic doctor`,
     asks you for what's missing, and persists it with `sophonic config set …`
     (see [Guided setup in Claude](#guided-setup-in-claude) below).

3. **Authenticate** the integrations you use (one time, in your own terminal — these
   need a browser):
   ```bash
   sophonic auth google     # Calendar + Gmail
   sophonic auth slack      # opens a browser, saves the session
   sophonic auth zoom
   ```
   GitLab uses `GITLAB_TOKEN` (PAT with `api` scope): `sophonic config set-secret GITLAB_TOKEN --stdin`.

## Enable the plugin

Local development / testing:
```bash
claude --plugin-dir ./plugin
```
Then in Claude Code, the skills appear namespaced (e.g. `/sophonic:obsidian`) and
Claude will invoke them autonomously based on your request. Slash commands
`/sophonic:today` and `/sophonic:rollover` are also available.

Run `/reload-plugins` after editing plugin files.

## Guided setup in Claude

`sophonic init` needs a real terminal, so inside Claude Code use the `/sophonic:setup`
skill instead. Claude becomes the wizard: it runs `sophonic doctor` to find gaps,
interviews you for each missing value, and writes them with the non-interactive
`sophonic config set …` commands. Two things it hands back to you (by design):

- **Secrets** — Claude never types keys into a command. It asks *you* to run
  `sophonic config set-secret <NAME> --stdin` in your terminal and paste the value, so
  the secret stays out of the transcript and `~/.sophonic/.env` (0600).
- **Browser auth** — Claude can't open a browser, so it hands off `sophonic auth
  google|slack|zoom` for you to run.

## What's included

| Component | Contents |
|---|---|
| `skills/` | `setup`, `obsidian`, `reminders`, `gcal`, `gmail`, `slack`, `zoom`, `gitlab` — each describes its tools and how to call them via `sophonic tool …`. |
| `commands/` | `today`, `rollover` — thin slash commands over the friendly CLI subcommands. |
| `bin/sophonic` | Wrapper placed on the Bash tool's PATH while the plugin is enabled. |

## How this differs from the MCP server

| | MCP server (`sophonic-mcp`) | This plugin |
|---|---|---|
| Transport | MCP stdio | Bash → `sophonic` CLI |
| Tool schemas | Typed JSON Schema per tool | JSON args passed as strings |
| Permissions | `allowedTools` per namespace | Bash allow-rules on `sophonic …` |
| Distribution | manual MCP registration | `--plugin-dir`, marketplace, versioned |

Both can coexist. Feature flags in `~/.sophonic/config.toml` gate which tools exist
in both modes; `sophonic tools` always reflects what is currently available.
