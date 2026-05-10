# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for the ``_audit_safe_default`` whitelist serializer.

Per issue #876 L-4 — ``WorkflowHistoryStore.record_event`` no longer uses
``json.dumps(payload, default=str)`` because that silently coerces every
unsupported type to its string repr.  The new ``_audit_safe_default``
helper allows ``datetime`` / ``date`` / ``time`` / ``Decimal`` / ``UUID``
via typed conversion and raises ``TypeError`` for every other type.

Spec: ``specs/core-runtime.md`` § audit-log payload supported types.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from kailash.infrastructure.history_store import _audit_safe_default

# ---------------------------------------------------------------------------
# Supported types — typed conversion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        # datetime / date / time → isoformat()
        (
            datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc),
            "2026-05-11T12:00:00+00:00",
        ),
        (datetime(2026, 5, 11, 12, 0, 0), "2026-05-11T12:00:00"),
        (date(2026, 5, 11), "2026-05-11"),
        (time(12, 30, 45), "12:30:45"),
        # Decimal → str(obj) preserves precision
        (Decimal("1.50"), "1.50"),
        (Decimal("-0.001"), "-0.001"),
        (Decimal("0E-10"), "0E-10"),
        # UUID → str(obj) canonical form
        (
            UUID("12345678-1234-5678-1234-567812345678"),
            "12345678-1234-5678-1234-567812345678",
        ),
    ],
)
def test_audit_safe_default_supported_types(value, expected) -> None:
    assert _audit_safe_default(value) == expected


# ---------------------------------------------------------------------------
# Unsupported types — raise TypeError with actionable message
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, type_name",
    [
        ({1, 2, 3}, "set"),
        (frozenset([1, 2]), "frozenset"),
        (b"bytes", "bytes"),
        (bytearray(b"abc"), "bytearray"),
        (memoryview(b"abc"), "memoryview"),
    ],
)
def test_audit_safe_default_raises_on_unsupported_collections(value, type_name) -> None:
    with pytest.raises(TypeError, match=r"unsupported type"):
        _audit_safe_default(value)
    # Confirm error message names the type AND points to the spec.
    try:
        _audit_safe_default(value)
    except TypeError as exc:
        msg = str(exc)
        assert type_name in msg, f"error message missing type name: {msg}"
        assert (
            "specs/core-runtime.md" in msg
        ), f"error message missing spec pointer: {msg}"


def test_audit_safe_default_raises_on_custom_class() -> None:
    """Custom classes MUST raise — the whitelist is the contract."""

    class _Custom:
        pass

    with pytest.raises(TypeError, match=r"unsupported type"):
        _audit_safe_default(_Custom())


def test_audit_safe_default_raises_on_object() -> None:
    """Generic ``object()`` instances are NOT in the whitelist."""
    with pytest.raises(TypeError, match=r"unsupported type"):
        _audit_safe_default(object())


# ---------------------------------------------------------------------------
# Behavioral end-to-end via json.dumps — the wiring site
# ---------------------------------------------------------------------------


def test_json_dumps_with_audit_safe_default_serializes_decimal() -> None:
    """Round-trip via the public path ``json.dumps(payload,
    default=_audit_safe_default)`` — the production write-site shape.
    """
    payload = {"outputs": {"price": Decimal("19.99")}}
    out = json.dumps(payload, default=_audit_safe_default)
    # Decimal is preserved AS a string in the JSON output.  Readers
    # apply ``Decimal(value)`` on the way back per the spec.
    assert '"price": "19.99"' in out


def test_json_dumps_with_audit_safe_default_serializes_datetime() -> None:
    payload = {
        "outputs": {"ended_at": datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)},
    }
    out = json.dumps(payload, default=_audit_safe_default)
    assert "2026-05-11T12:00:00+00:00" in out


def test_json_dumps_with_audit_safe_default_serializes_uuid() -> None:
    payload = {
        "outputs": {
            "request_id": UUID("12345678-1234-5678-1234-567812345678"),
        },
    }
    out = json.dumps(payload, default=_audit_safe_default)
    assert "12345678-1234-5678-1234-567812345678" in out


def test_json_dumps_with_audit_safe_default_raises_on_set() -> None:
    """A node returning a ``set`` previously silently shipped as repr.
    The new contract loudly rejects at audit-write time.
    """
    payload = {"outputs": {"items": {1, 2, 3}}}
    with pytest.raises(TypeError, match=r"unsupported type 'set'"):
        json.dumps(payload, default=_audit_safe_default)


def test_json_dumps_with_audit_safe_default_serializes_native_json() -> None:
    """Native JSON types (dict / list / str / int / float / bool / None)
    pass through unchanged — ``default`` is not invoked.
    """
    payload = {
        "outputs": {
            "nested": {"a": [1, 2.5, True, False, None, "str"]},
        }
    }
    out = json.dumps(payload, default=_audit_safe_default)
    parsed = json.loads(out)
    assert parsed == payload
