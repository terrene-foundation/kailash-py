"""Regression tests for issue #446 — DLQ hardcoded DDL identifiers must validate.

Issue: https://github.com/terrene-foundation/kailash-py/issues/446

The original issue framed `workflow/dlq.py`'s use of raw `sqlite3` as a
framework-first violation. Analysis showed the DLQ is a legitimate
resilience primitive that bootstraps before DataFlow, with the
dialect-portable variant already living in `infrastructure/dlq.py`.

Red team review revealed the real gap: the DLQ's hardcoded DDL
identifiers (`dlq`, `idx_dlq_status`, etc.) were interpolated into DDL
strings without routing through `_validate_identifier()`. Per
`dataflow-identifier-safety.md` Rule 5, every identifier in DDL — even
hardcoded ones — MUST route through the validator at the call site.
This is defense-in-depth: hardcoded lists become dynamic lists during
refactors, and the validator marks the intent permanently.

These tests are behavioral (per `rules/testing.md`):

1. ``PersistentDLQ`` initialization with default config succeeds —
   proves the validator passes for all current hardcoded names.
2. Patching the validator to reject the hardcoded name causes
   initialization to fail — proves the validator is actually wired
   into the path, not bypassed.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.mark.regression
def test_persistent_dlq_initializes_with_validated_identifiers(tmp_path: Path) -> None:
    """Issue #446: PersistentDLQ init succeeds — validator passes for hardcoded names."""
    from kailash.workflow.dlq import PersistentDLQ

    dlq_path = tmp_path / "dlq.sqlite"
    dlq = PersistentDLQ(db_path=str(dlq_path))
    try:
        # If initialization completes, the validator accepted every hardcoded
        # identifier (`dlq`, `idx_dlq_status`, `idx_dlq_next_retry`, `idx_dlq_created`).
        stats = dlq.get_stats()
        assert stats["total"] == 0
    finally:
        dlq.close()


@pytest.mark.regression
def test_persistent_dlq_initialization_calls_validator(tmp_path: Path) -> None:
    """Issue #446: PersistentDLQ init MUST route every hardcoded identifier
    through ``_validate_identifier()`` — proves the validator is actually
    wired into the DDL path, not declared and then bypassed.

    This is the load-bearing test: if a refactor accidentally drops the
    validator call, this test fails.
    """
    from kailash.workflow import dlq as dlq_module
    from kailash.db import dialect as dialect_module

    # Capture the REAL validator before patching. Re-importing inside the
    # spy would resolve to the patched object and recurse forever.
    real_validator = dialect_module._validate_identifier

    seen_identifiers: list[str] = []

    def spy(name: str, *, max_length: int = 128) -> None:
        seen_identifiers.append(name)
        # Defer to the real validator so any invalid name still raises.
        real_validator(name, max_length=max_length)

    with patch.object(dialect_module, "_validate_identifier", side_effect=spy):
        dlq_path = tmp_path / "dlq.sqlite"
        dlq = dlq_module.PersistentDLQ(db_path=str(dlq_path))
        dlq.close()

    # The DLQ MUST validate at least the table name and its indices.
    expected = {"dlq", "idx_dlq_status", "idx_dlq_next_retry", "idx_dlq_created"}
    seen = set(seen_identifiers)
    missing = expected - seen
    assert not missing, (
        f"PersistentDLQ initialization did not validate: {missing}. "
        f"Hardcoded DDL identifiers MUST route through _validate_identifier "
        f"per dataflow-identifier-safety.md Rule 5."
    )


@pytest.mark.regression
def test_dlq_identifier_validator_rejects_injection_attempts() -> None:
    """Issue #446: The validator used by the DLQ MUST reject SQL injection
    payloads. Proves the validator is the right defense, not just a no-op.
    """
    from kailash.db.dialect import _validate_identifier

    injection_payloads = [
        'dlq"; DROP TABLE customers; --',
        "dlq WITH DATA",
        "1_starts_with_digit",
        "dlq; SELECT * FROM users",
        "",
        "dlq with space",
    ]
    for payload in injection_payloads:
        with pytest.raises(ValueError):
            _validate_identifier(payload)


@pytest.mark.regression
def test_dlq_identifier_validator_raises_valueerror_on_unhashable_input() -> None:
    """Issue #446 (round 4): unhashable non-string inputs MUST raise
    ``ValueError`` — not ``TypeError``.

    Regression guard: an earlier implementation called ``hash(name)``
    inside the error-message f-string BEFORE the ``ValueError`` was
    raised. For unhashable inputs (``dict``, ``list``, ``set``) the
    ``hash()`` call itself raised ``TypeError: unhashable type``,
    swallowing the typed ValueError contract and surfacing a
    non-actionable error. The fingerprint helper must tolerate
    unhashable inputs and return a fallback marker so the caller sees
    the typed ValueError it expected.
    """
    from kailash.db.dialect import _validate_identifier

    unhashable_payloads = [
        {"a": 1},
        [1, 2, 3],
        {1, 2, 3},
    ]
    for payload in unhashable_payloads:
        with pytest.raises(ValueError, match="must be a string"):
            _validate_identifier(payload)  # type: ignore[arg-type]
