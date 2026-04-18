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


def test_apikey_deepcopy_returns_distinct_instance_with_same_secret() -> None:
    """copy.deepcopy(ApiKey) routes through __init__ rather than __slots__ restore.

    Contract: deepcopy returns a distinct ApiKey object whose
    constant_time_eq against the original returns True. The fingerprint is
    re-derived (same value), not copied byte-for-byte from __slots__.
    """
    import copy

    original = ApiKey("sk-hunter2-deepcopy-probe")
    clone = copy.deepcopy(original)

    assert clone is not original, "deepcopy must produce a distinct object"
    assert clone.constant_time_eq(original) is True
    assert clone.fingerprint == original.fingerprint


def test_apikey_copy_returns_distinct_instance() -> None:
    import copy

    original = ApiKey("sk-hunter2-copy-probe")
    clone = copy.copy(original)
    assert clone is not original
    assert clone.constant_time_eq(original) is True


def test_apikey_pickle_roundtrip_does_not_leak_through_slots() -> None:
    """pickle.dumps/loads of ApiKey uses __reduce__ (no __slots__ exposure).

    Contract: round-trip preserves secret equality (callers using pickle
    for in-process queues still work) while routing through __init__.
    The pickled payload still contains the secret bytes — this test proves
    the reconstruction path, NOT that the pickle envelope is secure.
    (The MUST-NOT-pickle-across-trust-boundaries rule is documented in
    the class docstring.)
    """
    import pickle

    original = ApiKey("sk-hunter2-pickle-probe")
    payload = pickle.dumps(original)
    reconstructed = pickle.loads(payload)

    assert reconstructed is not original
    assert reconstructed.constant_time_eq(original) is True
    assert reconstructed.fingerprint == original.fingerprint


def test_apikey_reduce_declares_init_reconstruction() -> None:
    """__reduce__ MUST name the class + secret, not the slot tuple.

    Defense against future __slots__ layout changes: the reconstruction
    routes through __init__, which re-derives the fingerprint. If anyone
    later replaces __reduce__ with a __getstate__/__setstate__ that skips
    __init__, this test fails and the review catches it.
    """
    original = ApiKey("sk-hunter2-reduce-probe")
    reducer = original.__reduce__()
    # (class, args_tuple) shape — no __slots__ dict as third element.
    assert len(reducer) == 2
    assert reducer[0] is ApiKey
    assert len(reducer[1]) == 1  # just the secret


def test_apikey_repr_still_does_not_leak_after_deepcopy() -> None:
    """The secret MUST NOT appear in repr of a deepcopied ApiKey either."""
    import copy

    raw = "sk-hunter2-repr-after-deepcopy"
    original = ApiKey(raw)
    clone = copy.deepcopy(original)
    assert raw not in repr(clone)
    assert "hunter2" not in repr(clone)
    assert "fingerprint=" in repr(clone)
