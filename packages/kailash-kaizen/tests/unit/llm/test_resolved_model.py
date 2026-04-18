# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""`ResolvedModel.with_extra_header` header allowlist (#498 S1)."""

from __future__ import annotations

import pytest

from kaizen.llm.deployment import ResolvedModel

_FORBIDDEN = [
    # Original D1 set
    "authorization",
    "host",
    "cookie",
    "x-amz-security-token",
    "x-api-key",
    "x-goog-api-key",
    "anthropic-version",
    # Round-1 redteam H2 additions (request-smuggling, proxy-auth,
    # upstream-trust, method-override).
    "transfer-encoding",
    "content-length",
    "proxy-authorization",
    "proxy-authenticate",
    "x-forwarded-for",
    "x-real-ip",
    "forwarded",
    "x-http-method-override",
    "x-http-method",
    "x-method-override",
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


# --- round-1 redteam H2: whitespace-strip bypass ---
@pytest.mark.parametrize(
    "name",
    [
        " Authorization",  # leading space
        "Authorization ",  # trailing space
        "Authorization\t",  # trailing tab
        "\tAuthorization",  # leading tab
        " authorization ",  # both, lowercase
        " X-Forwarded-For ",  # non-Authorization forbidden
    ],
)
def test_with_extra_header_strips_whitespace_before_compare(name: str) -> None:
    """Whitespace around a forbidden name MUST NOT bypass the allowlist."""
    m = ResolvedModel(name="gpt-4")
    with pytest.raises(ValueError):
        m.with_extra_header(name, "malicious")


def test_with_extra_header_rejects_empty_whitespace_only() -> None:
    """A name of only whitespace is itself an invalid request."""
    m = ResolvedModel(name="gpt-4")
    with pytest.raises(ValueError):
        m.with_extra_header("   ", "value")
    with pytest.raises(ValueError):
        m.with_extra_header("", "value")


# --- round-1 redteam M2: non-ASCII hostname rejected at raw layer ---
def test_rejects_non_ascii_hostname() -> None:
    """IDN homograph defense — raw Unicode host MUST NOT reach check_url."""
    from kaizen.llm.deployment import Endpoint
    from kaizen.llm.errors import InvalidEndpoint

    # Cyrillic 'е' (U+0435) in place of Latin 'e' — visually identical,
    # semantically a different host. Pydantic's HttpUrl would punycode it
    # and defeat the downstream SSRF guard.
    cyrillic_url = "https://api.op\u0435nai.com/v1"
    with pytest.raises(InvalidEndpoint) as exc:
        Endpoint(base_url=cyrillic_url)
    assert exc.value.reason == "malformed_url"


def test_rejects_obvious_non_ascii_tld() -> None:
    """Unambiguously non-ASCII hostname (Cyrillic .рф TLD) also rejects."""
    from kaizen.llm.deployment import Endpoint
    from kaizen.llm.errors import InvalidEndpoint

    with pytest.raises(InvalidEndpoint):
        Endpoint(base_url="https://\u043f\u0440\u0438\u043c\u0435\u0440.\u0440\u0444/v1")


def test_accepts_plain_ascii_hostname() -> None:
    """Regression guard: the ASCII check MUST NOT false-positive on valid URLs."""
    from kaizen.llm.deployment import Endpoint

    ep = Endpoint(base_url="https://api.openai.com/v1")
    assert "api.openai.com" in str(ep.base_url)
