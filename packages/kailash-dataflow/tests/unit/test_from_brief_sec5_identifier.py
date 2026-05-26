# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 regression tests for SEC-5 — DataFlow ``from_brief`` dialect
identifier validation.

Closes the SEC-5 finding at
``workspaces/from-brief-1125/04-validate/round-02-security.md:127-142``.

Pre-SEC-5, ``_validate_model_spec`` and ``_build_annotations`` used
``str.isidentifier()`` which accepts:

  - Unicode identifiers (``Modèl``) — Postgres rejects at DDL time, 30
    frames into the call stack
  - Python keywords (``class``, ``True``) — ditto
  - Identifiers > 63 chars — Postgres truncates silently

SEC-5 layers a strict ASCII regex + 63-char length limit + keyword
denylist BEFORE the realizer reaches ``type(name, bases, ns)``, so
the failure surfaces as ``BriefInterpretationError(unknown_value=...)``
at the validation gate — exactly per ``S1`` invariant 2.

These are structural probes per ``rules/probe-driven-verification.md``
Rule 3 (no LLM judge required).
"""

from __future__ import annotations

import pytest

from dataflow.from_brief import (
    _SQL_IDENTIFIER_RE,
    _build_annotations,
    _validate_model_spec,
)
from kailash._from_brief import BriefInterpretationError


@pytest.mark.regression
def test_model_name_rejects_unicode_identifier() -> None:
    """SEC-5: ``Modèl`` passes Python's ``isidentifier()`` (the prior
    gate) but Postgres rejects unicode unless quoted as a legacy
    identifier; reject loudly at the realizer-input gate."""
    spec = {"name": "Modèl", "fields": [{"name": "id", "type": "int"}]}
    with pytest.raises(BriefInterpretationError):
        _validate_model_spec(spec)


@pytest.mark.regression
def test_model_name_rejects_python_keyword() -> None:
    """SEC-5: ``class`` is a Python keyword AND a SQL reserved word —
    the gate MUST reject."""
    spec = {"name": "class", "fields": [{"name": "id", "type": "int"}]}
    with pytest.raises(BriefInterpretationError):
        _validate_model_spec(spec)


@pytest.mark.regression
def test_model_name_rejects_oversized_identifier() -> None:
    """SEC-5: PostgreSQL identifier limit is 63 chars; the regex caps
    at 63. A 64-char model name MUST be rejected."""
    long_name = "M" + ("a" * 63)  # 64 chars total, ASCII, starts uppercase
    assert len(long_name) == 64
    spec = {"name": long_name, "fields": [{"name": "id", "type": "int"}]}
    with pytest.raises(BriefInterpretationError):
        _validate_model_spec(spec)


@pytest.mark.regression
def test_model_name_accepts_canonical_customer() -> None:
    """Regression guard: legitimate ASCII model names continue to pass
    after the SEC-5 tightening."""
    spec = {
        "name": "Customer",
        "fields": [{"name": "id", "type": "int"}, {"name": "email", "type": "str"}],
    }
    # _validate_model_spec returns a normalized dict — no raise expected.
    out = _validate_model_spec(spec)
    assert out["name"] == "Customer"


@pytest.mark.regression
def test_field_name_rejects_python_keyword() -> None:
    """SEC-5: field-name gate mirrors model-name gate; a Python keyword
    like ``class`` cannot be a column name."""
    allowed = {"str", "int"}
    fields = [{"name": "id", "type": "int"}, {"name": "class", "type": "str"}]
    with pytest.raises(BriefInterpretationError):
        _build_annotations("Customer", fields, allowed)


@pytest.mark.regression
def test_field_name_rejects_unicode() -> None:
    """SEC-5: field-name gate rejects unicode (``classé``)."""
    allowed = {"str", "int"}
    fields = [{"name": "id", "type": "int"}, {"name": "classé", "type": "str"}]
    with pytest.raises(BriefInterpretationError):
        _build_annotations("Customer", fields, allowed)


def test_sql_identifier_regex_directly() -> None:
    """Structural probe: the regex itself enforces the canonical shape."""
    assert _SQL_IDENTIFIER_RE.match("Customer")
    assert _SQL_IDENTIFIER_RE.match("_private")
    assert _SQL_IDENTIFIER_RE.match("a")  # one char OK
    assert not _SQL_IDENTIFIER_RE.match("")  # empty rejected
    assert not _SQL_IDENTIFIER_RE.match("1leading_digit")
    assert not _SQL_IDENTIFIER_RE.match("Modèl")
    assert not _SQL_IDENTIFIER_RE.match("a" * 64)  # length cap
