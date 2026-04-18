# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""ApiKey + ApiKeyBearer hygiene tests (#498 S1)."""

from __future__ import annotations

import hmac

import pytest

from kaizen.llm.auth.bearer import ApiKey, ApiKeyBearer, ApiKeyHeaderKind


def test_apikey_has_no_eq_or_hash() -> None:
    """`ApiKey` deliberately lacks __eq__ / __hash__.

    This forces callers to use `constant_time_eq` for credential comparisons,
    closing off a timing side-channel. Per `rules/security.md` + Rust §6.4.
    """
    # ApiKey does not define __eq__ — default object identity is used.
    # Assert the class dict doesn't have them (inheriting from object doesn't
    # add a custom __eq__ / __hash__).
    assert "__eq__" not in ApiKey.__dict__, "ApiKey must not define __eq__"
    assert "__hash__" not in ApiKey.__dict__, "ApiKey must not define __hash__"


def test_apikey_constant_time_eq_true_on_match() -> None:
    a = ApiKey("sk-hunter2")
    b = ApiKey("sk-hunter2")
    assert a.constant_time_eq(b) is True


def test_apikey_constant_time_eq_false_on_mismatch() -> None:
    a = ApiKey("sk-hunter2")
    b = ApiKey("sk-hunter3")
    assert a.constant_time_eq(b) is False


def test_apikey_constant_time_eq_false_on_non_apikey() -> None:
    a = ApiKey("sk-hunter2")
    assert a.constant_time_eq("sk-hunter2") is False  # type: ignore[arg-type]


def test_apikey_constant_time_eq_uses_hmac_compare_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Monkeypatch `hmac.compare_digest` to verify `constant_time_eq` routes through it."""
    call_count = {"n": 0}
    real_compare = hmac.compare_digest

    def spy(a: bytes, b: bytes) -> bool:
        call_count["n"] += 1
        return real_compare(a, b)

    # Patch at the module level where bearer.py imported it.
    import kaizen.llm.auth.bearer as bearer_mod

    monkeypatch.setattr(bearer_mod.hmac, "compare_digest", spy)
    a = ApiKey("abc")
    b = ApiKey("abc")
    a.constant_time_eq(b)
    assert call_count["n"] == 1


def test_apikey_repr_does_not_leak_secret() -> None:
    a = ApiKey("sk-hunter2-super-secret")
    r = repr(a)
    assert "sk-hunter2" not in r
    assert "hunter2" not in r
    assert "super-secret" not in r
    # Must include a fingerprint for correlation.
    assert "fingerprint=" in r


def test_apikeybearer_repr_does_not_leak_key() -> None:
    """`repr(ApiKeyBearer(...))` must not contain any raw key bytes."""
    raw = "sk-hunter2-classified-payload"
    bearer = ApiKeyBearer(
        kind=ApiKeyHeaderKind.Authorization_Bearer,
        key=ApiKey(raw),
    )
    r = repr(bearer)
    assert raw not in r
    assert "hunter2" not in r
    assert "classified" not in r
    assert "payload" not in r
    # Must include fingerprint for correlation.
    assert "fingerprint=" in r


def test_apikeybearer_str_does_not_leak_key() -> None:
    raw = "sk-hunter2-classified-payload"
    bearer = ApiKeyBearer(
        kind=ApiKeyHeaderKind.Authorization_Bearer,
        key=ApiKey(raw),
    )
    s = str(bearer)
    assert raw not in s
    assert "hunter2" not in s
