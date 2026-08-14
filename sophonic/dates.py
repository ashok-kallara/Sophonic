"""Natural-language date parsing: "tomorrow", "next Friday", "in 3 days" → date."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

_WEEKDAY_NAMES = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

# Common relative patterns handled natively (dateparser 1.2 mishandles these
# under freeze_time and some locales).
_PATTERNS: list[tuple[re.Pattern, callable]] = [
    (re.compile(r"\btomorrow\b", re.I), lambda m, base: base + timedelta(days=1)),
    (re.compile(r"\byesterday\b", re.I), lambda m, base: base - timedelta(days=1)),
    (re.compile(r"\bin\s+(\d+)\s+days?\b", re.I),
     lambda m, base: base + timedelta(days=int(m.group(1)))),
    (re.compile(r"\bnext\s+(" + "|".join(_WEEKDAY_NAMES) + r")\b", re.I),
     lambda m, base: _next_weekday(base, _WEEKDAY_NAMES[m.group(1).lower()], strictly_next=True)),
    (re.compile(r"\bthis\s+(" + "|".join(_WEEKDAY_NAMES) + r")\b", re.I),
     lambda m, base: _next_weekday(base, _WEEKDAY_NAMES[m.group(1).lower()], strictly_next=False)),
    (re.compile(r"\b(" + "|".join(_WEEKDAY_NAMES) + r")\b", re.I),
     lambda m, base: _next_weekday(base, _WEEKDAY_NAMES[m.group(1).lower()], strictly_next=False)),
]


def _next_weekday(base: date, weekday: int, strictly_next: bool = False) -> date:
    days_ahead = weekday - base.weekday()
    if days_ahead < 0 or (days_ahead == 0 and strictly_next):
        days_ahead += 7
    if days_ahead == 0 and not strictly_next:
        days_ahead = 7
    return base + timedelta(days=days_ahead)


def parse_date(text: str, relative_to: date | None = None) -> date | None:
    """Return a future-preferring date parsed from natural language, or None.

    Tries native patterns first (robust under test freezing), then falls back
    to dateparser for ISO dates and other formats.
    """
    base = relative_to or date.today()

    for pattern, resolver in _PATTERNS:
        m = pattern.search(text)
        if m:
            return resolver(m, base)

    # Fallback: dateparser for ISO dates, month names, etc.
    import dateparser
    settings = {
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": datetime(base.year, base.month, base.day),
        "RETURN_AS_TIMEZONE_AWARE": False,
    }

    # Try extracting from longer text first, then verbatim
    try:
        from dateparser.search import search_dates
        hits = search_dates(text, settings=settings)
        if hits:
            return hits[0][1].date()
    except Exception:
        pass

    result: datetime | None = dateparser.parse(text, settings=settings)
    return result.date() if result else None


def today() -> date:
    return date.today()


def yesterday() -> date:
    return date.today() - timedelta(days=1)
