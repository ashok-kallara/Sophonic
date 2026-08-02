---
description: GitLab issues, MRs, pipelines, and wiki for a self-hosted instance. Use when the user mentions tickets, MRs, CI failures, or wiki pages.
---

# GitLab

Self-hosted GitLab. Project references use `group/project` (e.g. `platform/api-service`).
When the user does not name a project, use `[gitlab] default_project` from
`~/.sophonic/config.toml`, or ask.

> **How to run these tools:** use the Bash tool —
> `sophonic tool <NAME> --args-json '<JSON kwargs>'`. GitLab tools are **discovered
> dynamically** from the instance and only exist when `[features] gitlab = true`
> and `[gitlab]` is configured — **run `sophonic tools` to see the exact
> `gitlab_*` names available** before calling one.

## Typical tools

- `gitlab_list_projects(search?)`, `gitlab_get_project(project)`
- `gitlab_list_issues(project, state?, labels?, assignee?, search?)`, `gitlab_get_issue(project, issue_iid)`
- `gitlab_create_issue(project, title, description?, labels?, assignee?, milestone?)`, `gitlab_update_issue(project, issue_iid, …, state_event?)`
- `gitlab_create_note(project, noteable_type, noteable_iid, body)` — `noteable_type`: `issues` | `merge_requests`
- `gitlab_list_merge_requests(project, state?, …)`, `gitlab_get_merge_request(project, mr_iid)`
- `gitlab_list_pipelines(project, ref?, status?)`, `gitlab_get_pipeline(project, pipeline_id)`, `gitlab_retry_failed_ci_jobs(project, pipeline_id)`
- `gitlab_list_wiki_pages(project)`, `gitlab_get_wiki_page(project, slug)`

## Examples

```bash
sophonic tools | grep gitlab_        # discover exact names first
sophonic tool gitlab_list_issues --args-json '{"project":"platform/api-service","state":"opened"}'
sophonic tool gitlab_get_pipeline --args-json '{"project":"platform/api-service","pipeline_id":98765}'
```

## Conventions

- Reference issues as `#123` and MRs as `!45`.
- Echo any note/issue body to the user for confirmation before posting or creating.
- After an MR review, offer to add follow-ups via `obsidian_add_task`.
- After a pipeline failure, offer to open an issue via `gitlab_create_issue`.
- Use `group/project` form, not a numeric ID.

## Auth

On 401, tell the user to check `[gitlab] token` in `~/.sophonic/config.toml` or set
`GITLAB_TOKEN` (PAT with `api` scope). The MCP endpoint requires GitLab 17.3+.
