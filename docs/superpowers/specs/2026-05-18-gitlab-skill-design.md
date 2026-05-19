# GitLab Skill Design

## Goal

Add a `gitlab` capability to Sophonic that proxies a self-hosted GitLab instance's native MCP server (`{instance}/api/v4/mcp`) rather than re-implementing the GitLab REST API in Python. The proxy discovers available tools at startup, wraps them as `gitlab_*` callables in the sophonic registry, and exposes them through both the CLI tool-use loop and the MCP server — with zero per-endpoint Python implementation.

## Architecture

```
build_registry()
  └─ if cfg.features.gitlab:
       gitlab.build_tools(gitlab_cfg)
         ├─ POST {url}/api/v4/mcp  {"method": "tools/list"}
         │    headers: Authorization: Bearer {token}
         │              Accept: application/json
         │
         ├─ for each tool in response:
         │    native_name  = "list_issues"
         │    sophonic_name = "gitlab_list_issues"
         │    wrappers[sophonic_name] = _make_caller(native_name, url, token)
         │
         └─ returns {gitlab_*: fn}  (empty dict + warning on failure)
```

Each wrapper is a plain sync Python function. Tool calls fire one HTTP POST to `{url}/api/v4/mcp` with a JSON-RPC `tools/call` body and return the parsed result. No persistent connection — each call is stateless. `httpx` (available as a transitive dependency of `mcp[cli]`) handles the HTTP layer.

**Session model:** Discovery runs once per `build_registry()` call. Wrappers are cached for the process lifetime. No MCP session handshake is maintained between calls.

**Graceful degradation:** If the GitLab MCP endpoint is unreachable at startup (wrong URL, expired PAT, GitLab < 17.3), `build_tools()` logs a warning and returns `{}`. Sophonic starts normally with zero `gitlab_*` tools registered — identical behavior to `google: false` disabling gcal/gmail.

## Configuration

New section in `~/.sophonic/config.toml`:

```toml
[features]
gitlab = true    # false by default; flip on once [gitlab] section is configured

[gitlab]
url             = "https://gitlab.company.com"
token           = "glpat-xxxxxxxxxxxxxxxxxxxx"   # Personal Access Token, api scope
default_project = "group/project"               # optional; used when not specified in request
```

`token` also reads from the `GITLAB_TOKEN` environment variable — env wins over config. Both `url` and `token` must be non-empty for `build_tools()` to attempt a connection; if either is missing it short-circuits with a clear warning even when `gitlab: true`.

**Feature flags — all tools now gated:** As part of this change, `obsidian` and `reminders` join the existing `google`, `slack`, `zoom` flags in `FeaturesConfig`. All six tool groups are now explicitly toggleable. Defaults preserve current behavior (obsidian and reminders default `true`).

```python
class FeaturesConfig(BaseModel):
    obsidian:  bool = True
    reminders: bool = True
    google:    bool = True
    slack:     bool = True
    zoom:      bool = True
    gitlab:    bool = False
```

## New Pydantic models (`config.py`)

```python
class GitLabConfig(BaseModel):
    url: str = ""
    token: str = ""
    default_project: str = ""
```

`token` resolution in `build_tools()`: `os.environ.get("GITLAB_TOKEN") or cfg.token`.

## `tools/gitlab.py`

```python
def build_tools(cfg: GitLabConfig) -> dict[str, Callable[..., Any]]:
    """
    Discover tools from the GitLab MCP endpoint and return {gitlab_*: fn}.
    Returns {} with a warning if the endpoint is unreachable or config is incomplete.
    """

def _discover(mcp_url: str, token: str) -> list[dict]:
    """POST tools/list, return raw tool descriptors."""

def _make_caller(native_name: str, mcp_url: str, token: str) -> Callable:
    """Return a sync wrapper that POSTs tools/call for native_name."""
```

Key implementation notes:
- Use a closure factory (`_make_caller`) to avoid the late-binding loop variable bug — same pattern used in `mcp_server.py` for MCP prompt registration.
- Set `wrapper.__doc__` from the tool's `description` field so FastMCP picks it up as the MCP tool description.
- Set `wrapper.__name__` to the sophonic name (`gitlab_list_issues`) so introspection and error messages are readable.
- Timeout: 10 s for discovery, 30 s per tool call.
- The `mcp_url` is `{cfg.url.rstrip('/')}/api/v4/mcp`.

**JSON-RPC request shapes:**

Discovery (`tools/list`):
```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "method": "tools/list",
  "params": {}
}
```

Tool call (`tools/call`):
```json
{
  "jsonrpc": "2.0",
  "id": "2",
  "method": "tools/call",
  "params": {
    "name": "list_issues",
    "arguments": { "project": "group/project", "state": "opened" }
  }
}
```

Both requests use `Content-Type: application/json` and `Accept: application/json`. The response `result` field contains the tool's return value; the `error` field (if present) is raised as a `RuntimeError` with the error message.

## SKILL.md

```markdown
---
name: gitlab
description: GitLab issues, MRs, pipelines, and wiki for a self-hosted instance. Trigger when the user mentions tickets, MRs, CI failures, or wiki pages.
tools:
  - gitlab_list_projects
  - gitlab_get_project
  - gitlab_list_issues
  - gitlab_get_issue
  - gitlab_create_issue
  - gitlab_update_issue
  - gitlab_create_note
  - gitlab_list_merge_requests
  - gitlab_get_merge_request
  - gitlab_list_pipelines
  - gitlab_get_pipeline
  - gitlab_retry_failed_ci_jobs
  - gitlab_list_wiki_pages
  - gitlab_get_wiki_page
---

# GitLab

Self-hosted GitLab instance. Project references use the format `group/project`
(e.g. `platform/api-service`). When the user doesn't specify a project, use the
default from `[gitlab] default_project` in config, or ask.

## Tools

- `gitlab_list_projects(search?)` — list accessible projects, optionally filtered by name.
- `gitlab_get_project(project)` — get project details (description, default branch, visibility).
- `gitlab_list_issues(project, state?, labels?, assignee?, search?)` — list issues. `state`: `opened`|`closed`|`all`.
- `gitlab_get_issue(project, issue_iid)` — full issue detail including description, labels, assignee.
- `gitlab_create_issue(project, title, description?, labels?, assignee?, milestone?)` — create a new issue. Echo the created issue URL back to the user.
- `gitlab_update_issue(project, issue_iid, title?, description?, labels?, assignee?, state_event?)` — update issue. `state_event`: `close`|`reopen`.
- `gitlab_create_note(project, noteable_type, noteable_iid, body)` — add a comment. `noteable_type`: `issues`|`merge_requests`. Always echo the note body to the user before posting.
- `gitlab_list_merge_requests(project, state?, author?, search?)` — list MRs. `state`: `opened`|`closed`|`merged`|`all`.
- `gitlab_get_merge_request(project, mr_iid)` — full MR detail including description, diff stats, approvals.
- `gitlab_list_pipelines(project, ref?, status?)` — list pipelines. `status`: `running`|`failed`|`success`|`canceled`.
- `gitlab_get_pipeline(project, pipeline_id)` — pipeline detail including job list and failure reasons.
- `gitlab_retry_failed_ci_jobs(project, pipeline_id)` — retry all failed jobs in a pipeline.
- `gitlab_list_wiki_pages(project)` — list wiki page slugs and titles.
- `gitlab_get_wiki_page(project, slug)` — full content of a wiki page in Markdown.

## Conventions

- Reference issues as `#123`, MRs as `!45` when responding to the user.
- After completing an MR review, offer to add follow-up items as tasks in today's
  Obsidian daily note using `obsidian_add_task`.
- After a pipeline failure, offer to create a GitLab issue for the failing job
  using `gitlab_create_issue`.
- Before posting any note or creating any issue, echo the content to the user
  for confirmation.
- Project argument: always use `group/project` form (e.g. `platform/api-service`),
  not a numeric project ID.

## When to use

Always call a gitlab tool before answering questions about issue status, MR state,
pipeline results, or wiki content. Never guess from memory.

## Auth

If a 401 is returned, tell the user to check `[gitlab] token` in
`~/.sophonic/config.toml` or set `GITLAB_TOKEN` in their shell environment.
Requires a GitLab Personal Access Token with `api` scope.

## Minimum GitLab version

The MCP endpoint (`/api/v4/mcp`) requires GitLab 17.3 or later.
```

**Tool name note:** The `tools:` frontmatter list reflects GitLab's published MCP tool surface. The existing `skills.validate()` logic handles drift: if discovery fails entirely (0 tools registered), validation is silent — treated as the feature being disabled. If some tools appear but others don't, validation raises a `ValueError` naming the gap, which is the correct signal that the GitLab version or config is partially broken.

## `tools/__init__.py` changes

```python
def build_registry() -> dict[str, Callable[..., Any]]:
    _REGISTRY.clear()
    cfg = load_config()
    feat = cfg.features

    if feat.obsidian:
        from sophonic.tools import obsidian
        for name, fn in obsidian.TOOLS.items():
            register(name, fn)

    if feat.reminders:
        from sophonic.tools import reminders
        for name, fn in reminders.TOOLS.items():
            register(name, fn)

    if feat.google:
        try:
            from sophonic.tools import gcal, gmail
            for name, fn in {**gcal.TOOLS, **gmail.TOOLS}.items():
                register(name, fn)
        except ImportError:
            pass

    if feat.slack:
        try:
            from sophonic.tools import slack_web
            for name, fn in slack_web.TOOLS.items():
                register(name, fn)
        except ImportError:
            pass

    if feat.zoom:
        try:
            from sophonic.tools import zoom
            for name, fn in zoom.TOOLS.items():
                register(name, fn)
        except ImportError:
            pass

    if feat.gitlab:
        from sophonic.tools.gitlab import build_tools as _build_gitlab
        for name, fn in _build_gitlab(cfg.gitlab).items():
            register(name, fn)

    registry = get_registry()
    from sophonic import skills
    skills.validate(registry)
    return registry
```

Note: `cfg = load_config()` replaces `cfg = load_config().features` so both `feat` and `cfg.gitlab` are accessible without a second `load_config()` call.

## Testing strategy

`tests/test_gitlab.py` mocks `httpx.post` (via `unittest.mock.patch`):

- **Discovery success**: mock returns a `tools/list` response with 3 tool descriptors → assert 3 `gitlab_*` functions registered, names prefixed correctly, `__doc__` set from description.
- **Tool call round-trip**: call one wrapper with kwargs → assert `httpx.post` called with correct JSON-RPC body and Bearer header → assert return value is the `result` field from the mocked response.
- **Graceful degradation — connection error**: mock raises `httpx.ConnectError` → assert `build_tools()` returns `{}` and logs a warning (capture with `pytest.warns` or log capture).
- **Graceful degradation — 401**: mock returns HTTP 401 → assert `build_tools()` returns `{}` with warning.
- **Missing config**: `url = ""` → assert short-circuits before HTTP call, returns `{}`.
- **GITLAB_TOKEN env var**: set `GITLAB_TOKEN` in env, empty config token → assert Bearer header uses env var value.
- **`build_registry()` integration**: with `features.gitlab = true` and a mocked `build_tools`, assert `gitlab_*` names appear in the registry.

`tests/test_config.py` additions:
- `FeaturesConfig` defaults: obsidian=True, reminders=True, gitlab=False.
- `GitLabConfig` defaults: url="", token="", default_project="".

## Files changed

| File | Change |
|---|---|
| `src/sophonic/config.py` | Add `GitLabConfig`; add `obsidian`, `reminders`, `gitlab` to `FeaturesConfig`; add `gitlab: GitLabConfig` to `Config` |
| `src/sophonic/tools/__init__.py` | Gate obsidian + reminders under feature flags; add gitlab block; fix `load_config()` call |
| `src/sophonic/tools/gitlab.py` | **NEW** — `build_tools`, `_discover`, `_make_caller` |
| `src/sophonic/skills/gitlab/SKILL.md` | **NEW** — frontmatter + guidance body |
| `tests/test_gitlab.py` | **NEW** — 7 test cases (see above) |
| `tests/test_config.py` | Add default-value assertions for new fields |
| `README.md` | Add GitLab to Capabilities table; add `[gitlab]` config example; add `GITLAB_TOKEN` to env var docs |

No changes to `mcp_server.py`, `llm.py`, or `skills.py`.
