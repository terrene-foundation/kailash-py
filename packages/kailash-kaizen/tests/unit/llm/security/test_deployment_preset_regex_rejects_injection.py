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


# --- round-1 redteam MED-2: structured logging on register / reject ---
def test_register_preset_emits_info_log(caplog) -> None:
    """Successful registration emits an INFO log with the preset name."""
    import logging

    from kaizen.llm.presets import _PRESETS, register_preset

    name = "fake_preset_for_log_test"
    # Defensive cleanup in case a prior run registered the name.
    _PRESETS.pop(name, None)
    with caplog.at_level(logging.INFO, logger="kaizen.llm.presets"):
        register_preset(name, _dummy_factory)
    records = [r for r in caplog.records if r.getMessage() == "preset.registered"]
    assert records, "expected 'preset.registered' INFO record"
    assert records[0].levelno == logging.INFO
    assert getattr(records[0], "preset_name", None) == name
    # cleanup
    _PRESETS.pop(name, None)


def test_validation_reject_emits_warning_with_fingerprint(caplog) -> None:
    """A regex-rejected name emits a WARN with fingerprint but NOT the raw name."""
    import logging

    bad = "open\nai"  # CRLF injection payload
    with caplog.at_level(logging.WARNING, logger="kaizen.llm.presets"):
        with pytest.raises(ValueError):
            register_preset(bad, _dummy_factory)
    records = [
        r for r in caplog.records if r.getMessage() == "preset.validation_rejected"
    ]
    assert records, "expected 'preset.validation_rejected' WARN record"
    rec = records[0]
    assert rec.levelno == logging.WARNING
    # Raw bad name MUST NOT appear anywhere in the record.
    for attr, val in rec.__dict__.items():
        assert bad not in str(val), f"raw name leaked in record.{attr}"
    # Fingerprint MUST be present on the record as structured data.
    assert getattr(rec, "name_fingerprint", None) is not None


def test_validation_reject_non_string_emits_warning(caplog) -> None:
    """A non-string input hits the type-reject path with a typed log tag."""
    import logging

    with caplog.at_level(logging.WARNING, logger="kaizen.llm.presets"):
        with pytest.raises(ValueError):
            register_preset(42, _dummy_factory)  # type: ignore[arg-type]
    records = [
        r for r in caplog.records if r.getMessage() == "preset.validation_rejected"
    ]
    assert records
    assert getattr(records[0], "reason", None) == "non_string"
    assert getattr(records[0], "type", None) == "int"
