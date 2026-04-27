"""Tests for the minimal ICS builder (F11)."""

from datetime import datetime, timezone

from app.services.ics import build_calendar


def test_build_calendar_emits_crlf_and_required_properties():
    evt = (
        "abc",
        "Leave",
        datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 5, 1, 17, 0, tzinfo=timezone.utc),
        None,
    )
    out = build_calendar([evt])

    assert out.startswith("BEGIN:VCALENDAR\r\n")
    assert out.endswith("END:VCALENDAR\r\n")
    assert "VERSION:2.0" in out
    assert "BEGIN:VEVENT" in out and "END:VEVENT" in out
    assert "UID:abc" in out
    assert "DTSTART:20260501T090000Z" in out
    assert "DTEND:20260501T170000Z" in out
    assert "SUMMARY:Leave" in out


def test_build_calendar_escapes_commas_and_newlines():
    evt = (
        "u1",
        "Summer break, week 1",
        datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 7, 8, 0, 0, tzinfo=timezone.utc),
        "line1\nline2",
    )
    out = build_calendar([evt])
    assert "SUMMARY:Summer break\\, week 1" in out
    assert "DESCRIPTION:line1\\nline2" in out


def test_build_calendar_empty_events_still_valid():
    out = build_calendar([])
    assert "BEGIN:VCALENDAR" in out and "END:VCALENDAR" in out
    assert "BEGIN:VEVENT" not in out
