# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""`ResolvedModel.with_extra_header` header allowlist (#498 S1)."""

from __future__ import annotations

import pytest

from kaizen.llm.deployment import ResolvedModel

_FORBIDDEN = [
    "authorization",
    "host",
    "cookie",
    "x-amz-security-token",
    "x-api-key",
    "x-goog-api-key",
    "anthropic-version",
]


@pytest.mark.parametrize("header_name", _FORBIDDEN)
def test_with_extra_header_rejects_forbidden_lowercase(header_name: str) -> None:
    m = ResolvedModel(name="gpt-4")
    with pytest.raises(ValueError):
        m.with_extra_header(header_name, "malicious")


@pytest.mark.parametrize("header_name", _FORBIDDEN)
def test_with_extra_header_rejects_forbidden_titlecase(header_name: str) -> None:
    # Case-insensitive rejection is the whole point.
    m = ResolvedModel(name="gpt-4")
    title = header_name.title()  # e.g. Authorization
    with pytest.raises(ValueError):
        m.with_extra_header(title, "malicious")


@pytest.mark.parametrize("header_name", _FORBIDDEN)
def test_with_extra_header_rejects_forbidden_upper(header_name: str) -> None:
    m = ResolvedModel(name="gpt-4")
    upper = header_name.upper()
    with pytest.raises(ValueError):
        m.with_extra_header(upper, "malicious")


def test_with_extra_header_error_does_not_echo_raw_name() -> None:
    """Log-injection defense: the raw bad header name must not appear in str(err)."""
    m = ResolvedModel(name="gpt-4")
    evil = "Authorization"
    try:
        m.with_extra_header(evil, "malicious")
    except ValueError as exc:
        # The exception message MUST NOT echo the raw user-supplied name verbatim
        # (per deployment.py docstring contract).
        assert evil not in str(exc)
    else:
        pytest.fail("expected ValueError")


def test_with_extra_header_allows_safe_header() -> None:
    m = ResolvedModel(name="gpt-4")
    m2 = m.with_extra_header("x-custom-trace", "abc123")
    assert m2.extra_headers == {"x-custom-trace": "abc123"}


def test_with_extra_header_returns_new_instance() -> None:
    """Functional-style: original ResolvedModel must be unchanged."""
    m = ResolvedModel(name="gpt-4")
    m2 = m.with_extra_header("x-custom", "value")
    assert m.extra_headers == {}
    assert m is not m2
    assert m2.extra_headers == {"x-custom": "value"}


def test_resolved_model_is_frozen() -> None:
    m = ResolvedModel(name="gpt-4")
    with pytest.raises((ValueError, TypeError)):
        m.name = "gpt-5"  # type: ignore[misc]
