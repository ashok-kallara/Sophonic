---
name: reminders
description: Create reminders from natural language — parse dates and write Obsidian Tasks lines. Trigger when the user says "remind me" or gives a task with a time expression.
tools:
  - reminder_create
---

# Reminders

One tool for natural-language reminders: `reminder_create`.

## Tool

- `reminder_create(phrase, tags, priority)` — Parse a natural-language reminder phrase, extract the due date, strip the time tokens, and add the task to today's daily note.

## Examples

| User says | What happens |
|---|---|
| "remind me to send the report Friday" | due = next Friday, text = "send the report" |
| "call dentist tomorrow at 3pm" | due = tomorrow, text = "call dentist" (time ignored) |
| "buy milk in 3 days" | due = today + 3, text = "buy milk" |
| "remind me: review PR by end of day" | due = today, text = "review PR" |

## When to use

- Use `reminder_create` when the user says "remind me", "don't let me forget", or provides a task with a natural-language time expression.
- For tasks without a time expression, use `obsidian_add_task` directly.
