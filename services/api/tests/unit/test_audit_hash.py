"""Tests for the audit service's hash chain primitives (pure functions).

These cover the canonicalisation and SHA-256 chaining logic without
exercising the database.
"""

import hashlib
import json
import uuid
from datetime import date, datetime, timezone

from app.services import audit


def test_canonical_is_sorted_and_compact():
    payload = {"b": 1, "a": 2, "nested": {"y": True, "x": [3, 1, 2]}}
    out = audit._canonical(payload)
    assert out == '{"a":2,"b":1,"nested":{"x":[3,1,2],"y":true}}'


def test_canonical_serialises_datetime_and_uuid():
    uid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    ts = datetime(2026, 4, 20, 12, 34, 56, tzinfo=timezone.utc)
    out = audit._canonical({"id": uid, "when": ts, "day": date(2026, 4, 20)})
    parsed = json.loads(out)
    assert parsed["id"] == str(uid)
    assert parsed["when"].startswith("2026-04-20")
    assert parsed["day"] == "2026-04-20"


def test_hash_matches_sha256_of_prev_plus_payload():
    payload = {"action": "leave.approve", "actor_id": "abc"}
    first = audit._hash(None, payload)
    expected = hashlib.sha256(audit._canonical(payload).encode()).hexdigest()
    assert first == expected
    second = audit._hash(first, payload)
    assert second != first
    expected_second = hashlib.sha256((first + audit._canonical(payload)).encode()).hexdigest()
    assert second == expected_second


def test_hash_is_deterministic_regardless_of_key_order():
    a = audit._hash(None, {"x": 1, "y": 2})
    b = audit._hash(None, {"y": 2, "x": 1})
    assert a == b
