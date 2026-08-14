---
name: gitlab
description: Work with a self-hosted GitLab instance — issues, merge requests, pipelines, wiki, and notes — via the instance's own MCP endpoint. Use when the user mentions GitLab issues (#123), merge requests (!45), pipelines, or their GitLab project.
---

# GitLab

Proxies to the GitLab instance's own MCP endpoint (`/api/v4/mcp`, GitLab 17.3+) via a
thin fetch-script. The available tools are discovered from the instance, so the exact
set depends on your GitLab version.

## Run

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gitlab.py" tools
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gitlab.py" call --tool gitlab_get_issue --args-json '{"id":"123"}'
```

- `tools` — list the available `gitlab_*` tools (name + one-line description). Run this
  first to see what the instance exposes and what arguments each takes.
- `call --tool <name> --args-json '<json>'` — invoke one tool; prints its JSON result.

## Conventions

- Reference issues as `#123` and merge requests as `!45`.
- Use `group/project` refs; the default comes from `gitlab.default_project` in config.
- Echo an issue/note back to the user before creating or posting it.
- After reviewing an MR, offer to add follow-up tasks to the vault ([[obsidian]]); on a
  failed pipeline, offer to open an issue.

## Auth

Needs `gitlab.url` + a personal access token with `api` scope (`gitlab.token` in config
or the `GITLAB_TOKEN` secret), and `features.gitlab true`. Setup: [[setup]].
