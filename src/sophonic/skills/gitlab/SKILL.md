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
(e.g. `platform/api-service`). When the user does not specify a project, use the
default from `[gitlab] default_project` in `~/.sophonic/config.toml`, or ask.

## Tools

- `gitlab_list_projects(search?)` — list accessible projects, optionally filtered by name.
- `gitlab_get_project(project)` — project details: description, default branch, visibility.
- `gitlab_list_issues(project, state?, labels?, assignee?, search?)` — list issues. `state`: `opened` | `closed` | `all`.
- `gitlab_get_issue(project, issue_iid)` — full issue detail: description, labels, assignee, comments.
- `gitlab_create_issue(project, title, description?, labels?, assignee?, milestone?)` — create an issue. Echo the created issue URL back to the user.
- `gitlab_update_issue(project, issue_iid, title?, description?, labels?, assignee?, state_event?)` — update an issue. `state_event`: `close` | `reopen`.
- `gitlab_create_note(project, noteable_type, noteable_iid, body)` — add a comment. `noteable_type`: `issues` | `merge_requests`. Always echo the body to the user before posting.
- `gitlab_list_merge_requests(project, state?, author?, search?)` — list MRs. `state`: `opened` | `closed` | `merged` | `all`.
- `gitlab_get_merge_request(project, mr_iid)` — full MR detail: description, diff stats, approvals, comments.
- `gitlab_list_pipelines(project, ref?, status?)` — list pipelines. `status`: `running` | `failed` | `success` | `canceled`.
- `gitlab_get_pipeline(project, pipeline_id)` — pipeline detail including job list and failure reasons.
- `gitlab_retry_failed_ci_jobs(project, pipeline_id)` — retry all failed jobs in a pipeline.
- `gitlab_list_wiki_pages(project)` — list wiki page slugs and titles.
- `gitlab_get_wiki_page(project, slug)` — full Markdown content of a wiki page.

## Conventions

- Reference issues as `#123` and MRs as `!45` when responding to the user.
- Before posting any note or creating any issue, echo the content to the user for confirmation.
- After completing an MR review, offer to add follow-up items as tasks in today's Obsidian daily note using `obsidian_add_task`.
- After a pipeline failure, offer to create a GitLab issue for the failing job using `gitlab_create_issue`.
- Always use `group/project` form for project arguments (e.g. `platform/api-service`), not a numeric project ID.

## When to use

Always call a gitlab tool before answering questions about issue status, MR state, pipeline results, or wiki content. Never guess from memory.

## Auth

If a 401 is returned, tell the user to check `[gitlab] token` in `~/.sophonic/config.toml`
or set `GITLAB_TOKEN` in their environment. Requires a Personal Access Token with `api` scope.

## Minimum GitLab version

The MCP endpoint (`/api/v4/mcp`) requires GitLab 17.3 or later.
