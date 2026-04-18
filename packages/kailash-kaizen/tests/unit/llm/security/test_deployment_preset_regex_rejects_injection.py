# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""MED-3 amendment 6.M2: preset name regex rejects log-injection payloads.

The preset registry validates names against `^[a-z][a-z0-9_]{0,31}$`. Anything
that would log-inject (CRLF, spaces, unicode confusables, null-byte) or evade
the length cap MUST be rejected, and the error message MUST NOT echo the raw
bad name verbatim (log-injection defense).
"""

from __future__ import annotations

import pytest

from kaizen.llm.presets import register_preset


def _dummy_factory(*args, **kwargs):  # pragma: no cover - never invoked
    raise RuntimeError("factory should not be called on rejected name")


@pytest.mark.parametrize(
    "bad_name",
    [
        "open\nai",  # LF injection
        "open\rai",  # CR injection
        "open\r\nai",  # CRLF
        "open ai",  # space
        "OpenAi",  # uppercase
        "openаi",  # Cyrillic 'а' (U+0430), not Latin 'a'
        "open\x00ai",  # null byte
        "1openai",  # leading digit
        "_openai",  # leading underscore
        "",  # empty
        "a" * 33,  # too long (> 32 chars)
        "openai-v2",  # hyphen not allowed
        "openai.v2",  # dot not allowed
        "openai;v2",  # semicolon
        "openai'--",  # SQL-ish
        "openai/../..",  # path traversal-ish
    ],
)
def test_rejects_injection_payload(bad_name: str) -> None:
    with pytest.raises(ValueError):
        register_preset(bad_name, _dummy_factory)


@pytest.mark.parametrize(
    "bad_name",
    [
        "open\nai",
        "open\rai",
        "open\x00ai",
        "openаi",  # cyrillic
    ],
)
def test_error_message_does_not_echo_bad_name(bad_name: str) -> None:
    """Log-injection defense: the raw bad name must not appear in str(err)."""
    try:
        register_preset(bad_name, _dummy_factory)
    except ValueError as exc:
        s = str(exc)
        assert bad_name not in s
        # CRLF / null bytes / cyrillic specifically must not leak
        assert "\n" not in s
        assert "\r" not in s
        assert "\x00" not in s
        # Fingerprint must be present for correlation.
        assert "fingerprint=" in s
    else:
        pytest.fail("expected ValueError")


def test_rejects_non_string_input() -> None:
    with pytest.raises(ValueError):
        register_preset(42, _dummy_factory)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        register_preset(None, _dummy_factory)  # type: ignore[arg-type]


def test_accepts_valid_snake_case() -> None:
    """Sanity: valid names work. Uses a fresh name to avoid conflict with openai."""
    valid = "fake_preset_for_test_xyz"
    # If already registered from a previous test run, that's fine — register
    # would raise for duplicate; we just want to assert regex accepts the shape.
    from kaizen.llm.presets import _PRESET_NAME_RE

    assert _PRESET_NAME_RE.match(valid) is not None
