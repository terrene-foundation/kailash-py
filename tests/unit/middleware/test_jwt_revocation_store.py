"""Regression tests for issue #1356 — JWTAuthManager token revocation is process-local.

Before the fix, ``JWTAuthManager`` backed token revocation with an in-memory
``set`` scoped to one manager instance, so a token revoked on one worker stayed
valid on every other worker in a multi-worker deployment. The fix introduces a
pluggable ``TokenRevocationStore``: a SHARED store propagates revocation across
every manager that shares it; the default ``InMemoryTokenRevocationStore`` is
process-local (the documented original behavior).

These tests pin the chosen contract (acceptance criteria of #1356):
- revocation propagates via a shared store, and
- the default store is documented-process-local.
"""

from __future__ import annotations

import pytest

from kailash.middleware.auth import (
    InMemoryTokenRevocationStore,
    JWTAuthManager,
    JWTConfig,
    TokenRevocationStore,
)

SECRET = "a-very-long-secret-key-at-least-32-chars!"


def _cfg(**overrides) -> JWTConfig:
    return JWTConfig(secret_key=SECRET, algorithm="HS256", **overrides)


@pytest.mark.regression
def test_revocation_propagates_via_shared_store():
    """The fix: two managers sharing ONE store reject a token revoked on either.

    Models two worker processes that share a distributed revocation backend.
    """
    shared = InMemoryTokenRevocationStore()
    worker_a = JWTAuthManager(config=_cfg(), revocation_store=shared)
    worker_b = JWTAuthManager(config=_cfg(), revocation_store=shared)

    token = worker_a.create_token_pair(user_id="u1").access_token
    # Both accept it before revocation.
    assert worker_a.verify_token(token)["sub"] == "u1"
    assert worker_b.verify_token(token)["sub"] == "u1"

    worker_a.revoke_token(token)

    with pytest.raises(Exception):
        worker_a.verify_token(token)
    # The fix: worker_b — which never called revoke — also rejects it.
    with pytest.raises(Exception):
        worker_b.verify_token(token)


@pytest.mark.regression
def test_default_store_is_process_local():
    """The default (no shared store) is process-local — documented limitation.

    This is the original behavior the issue described; it is preserved by design
    for single-process deployments. Multi-worker deployments MUST inject a shared
    store (see ``test_revocation_propagates_via_shared_store``).
    """
    worker_a = JWTAuthManager(config=_cfg())  # default in-memory store
    worker_b = JWTAuthManager(config=_cfg())  # separate default store

    token = worker_a.create_token_pair(user_id="u1").access_token
    worker_a.revoke_token(token)

    with pytest.raises(Exception):
        worker_a.verify_token(token)
    # Process-local default: worker_b still accepts (separate in-memory store).
    assert worker_b.verify_token(token)["sub"] == "u1"


@pytest.mark.regression
def test_same_manager_rejects_revoked_token():
    """Baseline: a manager rejects a token it revoked itself (unchanged behavior)."""
    mgr = JWTAuthManager(config=_cfg())
    token = mgr.create_token_pair(user_id="u9").access_token
    assert mgr.verify_token(token)["sub"] == "u9"
    mgr.revoke_token(token)
    with pytest.raises(Exception):
        mgr.verify_token(token)


@pytest.mark.regression
def test_revoke_when_decode_fails_still_records():
    """Preserves the original 'revoke even if verification fails' behavior.

    A malformed/garbage token presented to ``revoke_token`` is recorded by raw
    token string rather than silently ignored.
    """
    store = InMemoryTokenRevocationStore()
    mgr = JWTAuthManager(config=_cfg(), revocation_store=store)
    garbage = "not.a.valid.jwt"
    mgr.revoke_token(garbage)
    assert store.is_revoked(token=garbage) is True


@pytest.mark.regression
def test_blacklist_disabled_means_no_store_and_no_revocation():
    """enable_blacklist=False keeps revocation a no-op (no store held)."""
    mgr = JWTAuthManager(config=_cfg(enable_blacklist=False))
    assert mgr._revocation_store is None
    token = mgr.create_token_pair(user_id="u1").access_token
    mgr.revoke_token(token)  # no-op
    # Token still verifies because revocation is disabled.
    assert mgr.verify_token(token)["sub"] == "u1"


@pytest.mark.regression
def test_get_stats_reports_one_entry_per_revoked_token():
    """get_stats counts one revoked entry per token (jti-keyed, not double-counted)."""
    mgr = JWTAuthManager(config=_cfg())
    t1 = mgr.create_token_pair(user_id="u1").access_token
    t2 = mgr.create_token_pair(user_id="u2").access_token
    mgr.revoke_token(t1)
    mgr.revoke_token(t2)
    assert mgr.get_stats()["blacklisted_tokens"] == 2


@pytest.mark.regression
def test_revocation_store_protocol_shape():
    """Structural: a custom in-process backend can implement the contract."""

    class DictStore(TokenRevocationStore):
        def __init__(self):
            self.revoked: set[str] = set()

        def revoke(self, *, jti=None, token=None, expires_at=None):
            ident = jti or token
            if ident:
                self.revoked.add(ident)

        def is_revoked(self, *, jti=None, token=None):
            return any(i and i in self.revoked for i in (jti, token))

    store = DictStore()
    mgr = JWTAuthManager(config=_cfg(), revocation_store=store)
    token = mgr.create_token_pair(user_id="custom").access_token
    mgr.revoke_token(token)
    assert len(store.revoked) == 1
    with pytest.raises(Exception):
        mgr.verify_token(token)


@pytest.mark.regression
def test_in_memory_store_purges_expired_entries():
    """Expired revocation entries are purged so the store does not grow unbounded."""
    from datetime import datetime, timedelta, timezone

    store = InMemoryTokenRevocationStore()
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    store.revoke(jti="expired-jti", expires_at=past)
    # Lazy purge on next access drops the expired entry.
    assert store.is_revoked(jti="expired-jti") is False
    assert store.count() == 0
