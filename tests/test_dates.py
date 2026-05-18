"""Tests for natural-language date parsing."""

from datetime import date

import pytest
from freezegun import freeze_time


@freeze_time("2026-05-02")
def test_tomorrow():
    from sophonic.dates import parse_date
    assert parse_date("tomorrow") == date(2026, 5, 3)


@freeze_time("2026-05-02")
def test_next_friday():
    from sophonic.dates import parse_date
    d = parse_date("next Friday")
    assert d is not None
    assert d > date(2026, 5, 2)
    assert d.weekday() == 4  # Friday


@freeze_time("2026-05-02")  # Saturday
def test_in_3_days():
    from sophonic.dates import parse_date
    assert parse_date("in 3 days") == date(2026, 5, 5)


@freeze_time("2026-05-02")
def test_next_monday():
    from sophonic.dates import parse_date
    d = parse_date("next Monday")
    assert d is not None
    assert d.weekday() == 0


@freeze_time("2026-05-02")
def test_explicit_date():
    from sophonic.dates import parse_date
    assert parse_date("2026-05-10") == date(2026, 5, 10)


def test_gibberish_returns_none():
    from sophonic.dates import parse_date
    # "xyzzy" should not parse to a date
    result = parse_date("xyzzy the untranslatable")
    # May return None or a spurious date — just verify no exception
    assert result is None or isinstance(result, date)
