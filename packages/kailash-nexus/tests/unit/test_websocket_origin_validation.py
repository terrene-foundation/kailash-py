# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-1 unit tests for WebSocket Origin allowlist validation (issue #673).

Covers ``nexus.websocket_origin``:

- :func:`validate_origin_allowlist` — registration-time validation
- :func:`origin_matches_allowlist` — runtime predicate
- :func:`fingerprint_origin` — log fingerprint shape

Per ``rules/testing.md`` §3-Tier Testing, Tier 1 is allowed to
exercise pure-function helpers in isolation. Tier-2 wiring against
real WebSocket clients lives in
``tests/regression/test_issue_673_websocket_origin_allowlist.py``.

Per ``rules/testing.md`` § Serialize Env-Var-Mutating Tests Via
Module Lock, every test that mutates ``KAILASH_NEXUS_ALLOW_WILDCARD_ORIGIN``
takes the ``_env_serialized`` fixture so concurrent xdist workers
do not race over the env var.
"""

from __future__ import annotations

import threading

import pytest

from nexus.websocket_origin import (
    WILDCARD_ORIGIN_ENV_FLAG,
    WildcardOriginRefusedError,
    fingerprint_origin,
    origin_matches_allowlist,
    validate_origin_allowlist,
)

# Module-scope lock — see rules/testing.md § Env-Var Test Isolation.
_ENV_LOCK = threading.Lock()


@pytest.fixture
def _env_serialized():
    with _ENV_LOCK:
        yield


# ---------------------------------------------------------------------------
# validate_origin_allowlist — typed-error / shape contract
# ---------------------------------------------------------------------------


def test_validate_none_passes_through() -> None:
    assert validate_origin_allowlist(None) is None


def test_validate_empty_list_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        validate_origin_allowlist([])


def test_validate_bare_string_rejected() -> None:
    """Common bug: allowed_origins='https://x' instead of [...]."""
    with pytest.raises(ValueError, match="list of strings"):
        validate_origin_allowlist("https://app.example.com")  # type: ignore[arg-type]


def test_validate_non_string_entry_rejected() -> None:
    with pytest.raises(ValueError, match="entries must be str"):
        validate_origin_allowlist(["https://x.com", 42])  # type: ignore[list-item]


def test_validate_empty_string_entry_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty strings"):
        validate_origin_allowlist(["https://x.com", "   "])


def test_validate_missing_scheme_rejected() -> None:
    with pytest.raises(ValueError, match="must start with"):
        validate_origin_allowlist(["app.example.com"])


def test_validate_exact_origin_accepted() -> None:
    assert validate_origin_allowlist(["https://app.example.com"]) == [
        "https://app.example.com"
    ]


def test_validate_http_scheme_accepted() -> None:
    # Some downstream consumers run mixed-mode (http://) for dev.
    assert validate_origin_allowlist(["http://localhost:3000"]) == [
        "http://localhost:3000"
    ]


def test_validate_wildcard_subdomain_accepted() -> None:
    assert validate_origin_allowlist(["https://*.example.com"]) == [
        "https://*.example.com"
    ]


def test_validate_wildcard_must_be_at_subdomain_position() -> None:
    with pytest.raises(ValueError, match="<scheme>://\\*\\.<host>"):
        validate_origin_allowlist(["https://example.*.com"])


def test_validate_multiple_wildcards_rejected() -> None:
    with pytest.raises(ValueError, match="only one '\\*'"):
        validate_origin_allowlist(["https://*.*.example.com"])


def test_validate_literal_wildcard_rejected_without_env(_env_serialized) -> None:
    with pytest.raises(WildcardOriginRefusedError):
        validate_origin_allowlist(["*"])


def test_validate_literal_wildcard_accepted_with_env(
    _env_serialized, monkeypatch
) -> None:
    monkeypatch.setenv(WILDCARD_ORIGIN_ENV_FLAG, "true")
    assert validate_origin_allowlist(["*"]) == ["*"]


def test_validate_literal_wildcard_env_case_insensitive(
    _env_serialized, monkeypatch
) -> None:
    monkeypatch.setenv(WILDCARD_ORIGIN_ENV_FLAG, "TRUE")
    assert validate_origin_allowlist(["*"]) == ["*"]


def test_validate_literal_wildcard_rejected_when_env_is_false(
    _env_serialized, monkeypatch
) -> None:
    monkeypatch.setenv(WILDCARD_ORIGIN_ENV_FLAG, "false")
    with pytest.raises(WildcardOriginRefusedError):
        validate_origin_allowlist(["*"])


def test_validate_literal_wildcard_rejected_when_env_unset(
    _env_serialized, monkeypatch
) -> None:
    monkeypatch.delenv(WILDCARD_ORIGIN_ENV_FLAG, raising=False)
    with pytest.raises(WildcardOriginRefusedError):
        validate_origin_allowlist(["*"])


def test_validate_returns_fresh_list() -> None:
    """The validated list MUST NOT alias the input — caller mutation
    of the input MUST NOT affect the registered allowlist."""
    src = ["https://app.example.com"]
    out = validate_origin_allowlist(src)
    assert out is not src
    src.append("https://evil.com")
    assert out == ["https://app.example.com"]


# ---------------------------------------------------------------------------
# origin_matches_allowlist — runtime predicate
# ---------------------------------------------------------------------------


def test_match_none_origin_returns_false() -> None:
    assert origin_matches_allowlist(None, ["https://app.example.com"]) is False


def test_match_non_string_origin_returns_false() -> None:
    """Shape rejection per rules/ui-backend-defense.md Rule 2."""
    assert origin_matches_allowlist(123, ["https://x.com"]) is False
    assert origin_matches_allowlist([], ["https://x.com"]) is False
    assert origin_matches_allowlist({}, ["https://x.com"]) is False


def test_match_empty_origin_returns_false() -> None:
    assert origin_matches_allowlist("", ["https://x.com"]) is False


def test_match_exact_origin() -> None:
    assert (
        origin_matches_allowlist("https://app.example.com", ["https://app.example.com"])
        is True
    )


def test_match_exact_origin_case_sensitive() -> None:
    """Origins are case-sensitive per RFC 6454; 'HTTPS://' MUST NOT
    match 'https://' — every real client emits the lowercase form."""
    assert (
        origin_matches_allowlist("HTTPS://APP.EXAMPLE.COM", ["https://app.example.com"])
        is False
    )


def test_match_wildcard_subdomain_matches_subdomain() -> None:
    assert (
        origin_matches_allowlist("https://api.example.com", ["https://*.example.com"])
        is True
    )


def test_match_wildcard_subdomain_matches_deep_subdomain() -> None:
    """Deep subdomain (a.b.example.com) matches *.example.com."""
    assert (
        origin_matches_allowlist("https://a.b.example.com", ["https://*.example.com"])
        is True
    )


def test_match_wildcard_subdomain_rejects_bare_host() -> None:
    """https://*.example.com MUST NOT match https://example.com."""
    assert (
        origin_matches_allowlist("https://example.com", ["https://*.example.com"])
        is False
    )


def test_match_wildcard_subdomain_rejects_suffix_attack() -> None:
    """Defense against https://example.com.evil.com."""
    assert (
        origin_matches_allowlist(
            "https://example.com.evil.com", ["https://*.example.com"]
        )
        is False
    )


def test_match_wildcard_subdomain_rejects_scheme_mismatch() -> None:
    """https://*.example.com MUST NOT match http://api.example.com."""
    assert (
        origin_matches_allowlist("http://api.example.com", ["https://*.example.com"])
        is False
    )


def test_match_wildcard_with_port_match() -> None:
    """Port is stripped from the candidate host before matching."""
    assert (
        origin_matches_allowlist(
            "https://api.example.com:8443", ["https://*.example.com"]
        )
        is True
    )


def test_match_literal_wildcard_matches_anything(_env_serialized, monkeypatch) -> None:
    monkeypatch.setenv(WILDCARD_ORIGIN_ENV_FLAG, "true")
    allow = validate_origin_allowlist(["*"])
    assert allow is not None
    assert origin_matches_allowlist("https://anything.example", allow) is True
    assert origin_matches_allowlist("http://x.io", allow) is True


def test_match_literal_wildcard_rejects_empty(_env_serialized, monkeypatch) -> None:
    monkeypatch.setenv(WILDCARD_ORIGIN_ENV_FLAG, "true")
    allow = validate_origin_allowlist(["*"])
    assert allow is not None
    assert origin_matches_allowlist("", allow) is False
    assert origin_matches_allowlist(None, allow) is False


def test_match_multiple_entries_first_match_wins() -> None:
    allow = ["https://app.example.com", "https://*.staging.example.com"]
    assert origin_matches_allowlist("https://app.example.com", allow) is True
    assert origin_matches_allowlist("https://x.staging.example.com", allow) is True
    assert origin_matches_allowlist("https://other.com", allow) is False


def test_match_origin_with_path_in_allowlist_does_not_match_path() -> None:
    """Origin headers from real browsers do not include paths.
    A defensive test: an attacker-controlled origin with a path
    suffix MUST NOT match the bare-host entry."""
    allow = ["https://app.example.com"]
    assert origin_matches_allowlist("https://app.example.com/evil", allow) is False


# ---------------------------------------------------------------------------
# fingerprint_origin — log shape
# ---------------------------------------------------------------------------


def test_fingerprint_is_8_hex_chars_for_string() -> None:
    fp = fingerprint_origin("https://app.example.com")
    assert len(fp) == 8
    assert all(c in "0123456789abcdef" for c in fp)


def test_fingerprint_is_deterministic() -> None:
    """Two calls with the same input MUST produce the same fingerprint."""
    a = fingerprint_origin("https://app.example.com")
    b = fingerprint_origin("https://app.example.com")
    assert a == b


def test_fingerprint_differs_per_input() -> None:
    a = fingerprint_origin("https://app.example.com")
    b = fingerprint_origin("https://evil.com")
    assert a != b


def test_fingerprint_none_is_sentinel() -> None:
    assert fingerprint_origin(None) == "00000000"


def test_fingerprint_empty_is_sentinel() -> None:
    assert fingerprint_origin("") == "00000000"


def test_fingerprint_does_not_echo_origin() -> None:
    """The fingerprint MUST NOT contain any substring of the origin —
    rules/observability.md Rule 6 + 8 (no schema-revealing identifiers
    at WARN level)."""
    origin = "https://app.example.com"
    fp = fingerprint_origin(origin)
    assert "example" not in fp
    assert "app" not in fp
    assert "https" not in fp


def test_fingerprint_non_string_returns_hash_of_type() -> None:
    """Non-string inputs hash the type name — provides some signal
    without leaking the underlying object."""
    fp = fingerprint_origin(123)
    assert len(fp) == 8
    assert fp != fingerprint_origin([])  # different types → different fp
