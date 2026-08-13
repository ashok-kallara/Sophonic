---
name: reminders
description: Turn a natural-language reminder ("remind me to send the report Friday") into a dated task in today's daily note. Use when the user says "remind me" or asks to be reminded about something with a time expression.
---

# Reminders

Convert a spoken reminder into one Obsidian task line in today's daily note. This is a
pure skill — you parse the phrase and edit the note yourself; follow the vault contract
in [[obsidian]].

## Procedure

1. **Parse the due date** from the phrase using today's date as the base. Handle
   relative expressions ("tomorrow", "Friday", "next Monday", "in 3 days") and explicit
   ISO dates. If there is no date expression, there is no due date — still add the task.
2. **Clean the task text.** Strip the reminder preamble and time-of-day tokens, keeping
   the actionable verb phrase:
   - Drop leading "remind me to", "remind me", "reminder:".
   - Drop clock times ("at 3pm", "at 15:00", "by 9am") — the daily note tracks days,
     not times.
3. **Add the task** under `## Tasks` in today's note, formatted per [[obsidian]]:
   `- [ ] <clean text> 📅 YYYY-MM-DD` (omit `📅 …` if no date was found). Apply a
   priority marker or `#tag`s only if the user asked for them.

## Examples

| Phrase | Task line (today = 2026-08-13) |
|---|---|
| "remind me to send the report Friday" | `- [ ] send the report 📅 2026-08-15` |
| "call the dentist tomorrow at 3pm" | `- [ ] call the dentist 📅 2026-08-14` |
| "buy milk in 3 days" | `- [ ] buy milk 📅 2026-08-16` |
| "follow up with Sam" (no date) | `- [ ] follow up with Sam` |

Read the note before writing, and don't duplicate a task that's already there.
For tasks without any time expression, this is the same as a plain "add a task" via
[[obsidian]].
