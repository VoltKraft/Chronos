"""Tests for the pure helpers in app.services.shift."""

from datetime import date

from app.services.shift import _is_working_day


def test_weekdays_are_working_days():
    assert _is_working_day(date(2026, 5, 4), holidays=set())  # Monday
    assert _is_working_day(date(2026, 5, 5), holidays=set())  # Tuesday
    assert _is_working_day(date(2026, 5, 8), holidays=set())  # Friday


def test_weekends_are_not_working_days():
    assert not _is_working_day(date(2026, 5, 2), holidays=set())  # Saturday
    assert not _is_working_day(date(2026, 5, 3), holidays=set())  # Sunday


def test_holiday_excluded_even_if_weekday():
    holiday = date(2026, 5, 1)  # Friday
    assert _is_working_day(holiday, holidays=set()) is True
    assert _is_working_day(holiday, holidays={holiday}) is False
