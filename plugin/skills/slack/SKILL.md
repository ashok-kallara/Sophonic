---
description: Read Slack unread messages and search history via the Slack desktop app's session. Use when the user asks about Slack messages or channels.
---

# Slack

Reads the signed-in **Slack desktop app**'s local session (no browser) and calls the
Slack Web API.

> **How to run these tools:** use the Bash tool —
> `sophonic tool <NAME> --args-json '<JSON kwargs>'`. Prints JSON, no LLM key.

## Tools

- `slack_unread()` — Unread channels, group DMs, and DMs as `{channel, type, mentions, id}`.
- `slack_search(query)` — Search messages. Returns `{text, channel, user, ts, permalink}`.

## Examples

```bash
sophonic tool slack_unread
sophonic tool slack_search --args-json '{"query":"deploy freeze"}'
```

## Auth

If a result contains `{"needs_auth": true}`, the Slack desktop-app session couldn't be
read. Tell the user to (1) make sure the **Slack desktop app** is installed and signed
in, then (2) run `sophonic auth slack` in their terminal and approve the one-time
Keychain prompt for *Slack Safe Storage*. If it still fails, they may need to set
`[slack] workspace_host` or the `SLACK_XOXC_TOKEN` secret.

## When to use

When the user asks "what did I miss on Slack" or mentions a specific Slack message/channel.
