---
description: Create reminders from natural language — parse the date and write an Obsidian Tasks line. Use when the user says "remind me" or gives a task with a time expression.
---

# Reminders

> **How to run this tool:** use the Bash tool —
> `sophonic tool reminder_create --args-json '<JSON kwargs>'`. Prints JSON, no API key.

## Tool

- `reminder_create(phrase, tags, priority)` — Parse a natural-language reminder, extract the due date, strip time tokens, and add the task to today's daily note.

## Examples

```bash
sophonic tool reminder_create --args-json '{"phrase":"send the report Friday"}'
sophonic tool reminder_create --args-json '{"phrase":"review PR by end of day","priority":"high"}'
```

| User says | Result |
|---|---|
| "remind me to send the report Friday" | due = next Friday, text = "send the report" |
| "call dentist tomorrow at 3pm" | due = tomorrow, text = "call dentist" (time ignored) |
| "buy milk in 3 days" | due = today + 3, text = "buy milk" |

## When to use

Use `reminder_create` when the user says "remind me", "don't let me forget", or gives a task with a time expression. For tasks with no time expression, use `obsidian_add_task` directly.
