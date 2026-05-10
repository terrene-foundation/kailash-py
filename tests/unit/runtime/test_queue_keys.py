# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for the canonical queue-key helper module.

Pins:

* ``make_queue_key("default")`` → exact legacy byte string
  ``"kailash:tasks:pending"`` (no suffix). Issue #911 failure-point #2
  (default-queue back-compat).
* Non-default names → ``"kailash:tasks:pending:<name>"``.
* ``validate_queue_name`` rejects every documented bad input class
  (failure-point #8): empty, > 64 chars, control chars, colons,
  slashes, whitespace, null bytes, non-str types.
"""

from __future__ import annotations

import pytest

from kailash.runtime._queue_keys import (
    DEFAULT_QUEUE_NAME,
    make_queue_key,
    validate_queue_name,
)


class TestMakeQueueKey:
    """Byte-vector pins for the queue-key helper."""

    def test_default_queue_byte_compat(self) -> None:
        # Load-bearing: existing single-queue producers + workers share
        # this exact Redis list key.
        assert make_queue_key("default") == "kailash:tasks:pending"

    def test_default_queue_via_constant(self) -> None:
        # Same value via the public constant — guards against the
        # constant drifting from the helper.
        assert make_queue_key(DEFAULT_QUEUE_NAME) == "kailash:tasks:pending"

    def test_default_queue_via_implicit_default(self) -> None:
        # The function's own default-arg path resolves to the same key.
        assert make_queue_key() == "kailash:tasks:pending"

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("fast", "kailash:tasks:pending:fast"),
            ("slow", "kailash:tasks:pending:slow"),
            ("slow_queue", "kailash:tasks:pending:slow_queue"),
            ("a-b-c", "kailash:tasks:pending:a-b-c"),
            ("Q1", "kailash:tasks:pending:Q1"),
            ("x" * 64, "kailash:tasks:pending:" + "x" * 64),
        ],
    )
    def test_non_default_queue_keys(self, name: str, expected: str) -> None:
        assert make_queue_key(name) == expected


class TestValidateQueueName:
    """Negative-input pins for ``validate_queue_name``."""

    @pytest.mark.parametrize(
        "name",
        [
            "default",
            "fast",
            "slow_queue",
            "a-b-c",
            "Q1",
            "x" * 64,
        ],
    )
    def test_accepts_valid_names(self, name: str) -> None:
        # No exception — return value is None per Python convention for
        # validators.
        assert validate_queue_name(name) is None

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            validate_queue_name("")

    def test_rejects_too_long(self) -> None:
        with pytest.raises(ValueError, match="too long"):
            validate_queue_name("x" * 65)

    @pytest.mark.parametrize(
        "name",
        [
            "with:colon",
            "with/slash",
            "with space",
            "with\nnewline",
            "with\ttab",
            "with\x00nullbyte",
            "with\x01control",
            "with.dot",
            "with#hash",
            "unicode-ñ",
        ],
    )
    def test_rejects_unsafe_chars(self, name: str) -> None:
        with pytest.raises(ValueError, match=r"\[A-Za-z0-9_-\]"):
            validate_queue_name(name)

    @pytest.mark.parametrize(
        "name",
        [
            None,
            123,
            ["fast"],
            {"queue": "fast"},
            b"fast",
        ],
    )
    def test_rejects_non_str_types(self, name: object) -> None:
        with pytest.raises(ValueError, match="must be str"):
            validate_queue_name(name)  # type: ignore[arg-type]
