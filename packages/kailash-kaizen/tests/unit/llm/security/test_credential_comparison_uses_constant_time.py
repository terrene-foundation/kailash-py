# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""§6.4 -- Timing side-channel (credential validation).

Asserts that credential equality comparisons route through
`hmac.compare_digest`, not Python's `==`. The test monkeypatches
`hmac.compare_digest` with a spy, performs an `ApiKey.constant_time_eq`
call, and verifies the spy was invoked.

Rust spec §6.4 parity: `kailash-rs` uses `subtle::ConstantTimeEq`;
Python uses `hmac.compare_digest`. Both close the same timing leak at
their respective language level.
"""

from __future__ import annotations

import hmac

import pytest
from pydantic import SecretStr

from kaizen.llm.auth.bearer import ApiKey


def test_apikey_constant_time_eq_calls_hmac_compare_digest(monkeypatch) -> None:
    """The primary credential comparison routes through `hmac.compare_digest`."""
    calls: list[tuple[bytes, bytes]] = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)

    k1 = ApiKey("sk-secret-alpha-123456")
    k2 = ApiKey("sk-secret-alpha-123456")
    k3 = ApiKey("sk-secret-BETA-9999999")

    # Equal keys -- True, one spy call
    assert k1.constant_time_eq(k2) is True
    # Different keys -- False, another spy call
    assert k1.constant_time_eq(k3) is False

    assert len(calls) == 2, (
        "expected exactly 2 calls to hmac.compare_digest from ApiKey."
        f"constant_time_eq; got {len(calls)}"
    )
    # Bytes form matches what we passed in
    assert calls[0] == (
        b"sk-secret-alpha-123456",
        b"sk-secret-alpha-123456",
    )
    assert calls[1] == (
        b"sk-secret-alpha-123456",
        b"sk-secret-BETA-9999999",
    )


def test_apikey_has_no_dunder_eq() -> None:
    """`ApiKey.__eq__` MUST NOT be defined at the class level -- its
    absence is load-bearing. The `==` operator on ApiKey falls back to
    identity, forcing callers to route through `constant_time_eq`.
    """
    # Not in the class's own __dict__; identity fallback comes from object.
    assert "__eq__" not in ApiKey.__dict__
    assert "__hash__" not in ApiKey.__dict__


def test_apikey_non_apikey_other_returns_false_without_spy_call(monkeypatch) -> None:
    """Passing a non-ApiKey short-circuits to False without calling the
    compare_digest helper -- a type-check gate before the HMAC call.
    """
    calls = []

    def spy(a, b):
        calls.append((a, b))
        return hmac.compare_digest(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)

    k = ApiKey("sk-some-value")
    assert k.constant_time_eq("not-an-apikey") is False  # type: ignore[arg-type]
    assert k.constant_time_eq(None) is False  # type: ignore[arg-type]
    assert k.constant_time_eq(42) is False  # type: ignore[arg-type]

    assert calls == [], (
        "hmac.compare_digest must not be called when `other` is not an "
        "ApiKey -- the type gate is the short-circuit"
    )


def test_apikey_accepts_secretstr_via_constructor() -> None:
    """SecretStr-wrapped keys compare identically to str-wrapped ones."""
    k1 = ApiKey(SecretStr("sk-secretstr-input-xyz"))
    k2 = ApiKey("sk-secretstr-input-xyz")
    assert k1.constant_time_eq(k2) is True
