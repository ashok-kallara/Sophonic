---
description: View or change Sophonic configuration (vault path, feature flags, secrets) without leaving Claude Code.
---

Manage Sophonic configuration by running the plugin's config script with the Bash tool:

```
uv run --project "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/config.py" <args>
```

Supported `<args>`:
- `show` — print effective config (secrets redacted)
- `get <dotted.key>` — read one value (e.g. `get vault.path`)
- `set <dotted.key> <value>` — set a non-secret value (validated), e.g.
  `set vault.path /Users/me/vault`, `set features.gitlab true`
- `unset <dotted.key>` — revert a key to its default
- `set-secret <NAME> --stdin` — store a secret

Interpret my request and run the matching command. **Never put a secret value in a
command yourself** — for `set-secret`, tell me to run it in my own terminal
(`sophonic-config set-secret <NAME> --stdin`, or the `uv run …` form) and paste the value
when prompted, so it never lands in the transcript. Print the resulting JSON.

My request: $ARGUMENTS
