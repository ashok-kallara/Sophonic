---
description: Carry unfinished tasks from the most recent prior daily note into today's note.
---

Use the `obsidian` skill to roll over unfinished tasks into today's daily note: find the
most recent daily note before today, copy its incomplete (`- [ ]`) tasks into today's
`## Tasks`, and add only the ones not already present (idempotent — safe to run twice).
Report how many were carried over and from which date.
