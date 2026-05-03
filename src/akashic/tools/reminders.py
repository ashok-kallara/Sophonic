"""Natural-language reminders → Obsidian Tasks lines."""

from __future__ import annotations

from datetime import date
from typing import Any

from akashic.dates import parse_date
from akashic.tools.obsidian import add_task


def reminder_create(
    phrase: str,
    tags: list[str] | None = None,
    priority: str | None = None,
) -> dict[str, Any]:
    """
    Parse a natural-language reminder and add it to today's daily note.

    Examples:
      "send the report Friday"         → due 2026-05-08
      "call dentist tomorrow at 3pm"   → due 2026-05-04  (time ignored)
      "buy milk in 3 days"             → due 2026-05-06
    """
    due_date = _extract_due(phrase)
    clean_text = _strip_date_tokens(phrase)

    return add_task(
        text=clean_text,
        due=due_date,
        priority=priority,
        tags=tags or [],
    )


def _extract_due(phrase: str) -> date | None:
    """Try to pull a date from the phrase; return None if none found."""
    d = parse_date(phrase)
    return d


_STRIP_PATTERNS = [
    r"\b(remind me to|remind me|reminder:?)\b",
    r"\b(by|on|at)\b\s+\d{1,2}(am|pm)\b",
    r"\b(at\s+)?\d{1,2}:\d{2}\s*(am|pm)?\b",
    r"\b(at\s+)?\d{1,2}\s*(am|pm)\b",
]


def _strip_date_tokens(phrase: str) -> str:
    """Remove reminder preamble from the phrase to get clean task text."""
    import re
    text = phrase
    for pat in _STRIP_PATTERNS:
        text = re.sub(pat, "", text, flags=re.IGNORECASE)
    return " ".join(text.split())


TOOLS: dict[str, Any] = {
    "reminder_create": reminder_create,
}
