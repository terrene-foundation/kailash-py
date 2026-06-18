"""Tests for MiddlewareAuthManager token revocation (sibling of issue #1356).

`MiddlewareAuthManager` is a second, independent JWT verifier in the same
package as `JWTAuthManager`. Before this change it had NO revocation capability:
`verify_token` did `jwt.decode` + a manual exp check with no revocation
consultation, no `jti` claim, and no `revoke_token` method — so a token could
never be invalidated before its natural expiry. #1356 fixed the equivalent gap
in `JWTAuthManager` via a pluggable `TokenRevocationStore`; this change wires the
SAME shared contract into `MiddlewareAuthManager`, so one store can back BOTH
managers in a deployment and revocation propagates across every worker.

These tests pin the contract:
- a `jti` claim is issued (the shared-store revocation key),
- `verify_token` rejects a revoked token with the specific 'revoked' message,
- revocation propagates via a shared store (the multi-worker scenario),
- the default store is documented-process-local,
- `enable_blacklist=False` keeps revocation a no-op,
- the decode-failure fallback records by raw token AND is TTL-bounded,
- backward compat: a pre-change token (no jti) still verifies,
- the FastAPI dependency rejects a revoked bearer token.

It ALSO regression-pins a pre-existing bug fixed alongside the feature: an
invalid/expired token MUST surface a clean `HTTPException(401)` — the prior
`severity="warning"` (not a valid `SeverityLevel`) made the security-event log
raise `ValueError`, which escaped `verify_token` as a non-401 error.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from starlette.exceptions import HTTPException

from kailash.middleware.auth import InMemoryTokenRevocationStore, TokenRevocationStore
from kailash.middleware.auth.auth_manager import MiddlewareAuthManager

SECRET = "a-very-long-secret-key-at-least-32-chars!"


def _mgr(**overrides) -> MiddlewareAuthManager:
    # enable_audit=False keeps the unit tests free of audit-node side effects;
    # the revocation path does not depend on audit logging.
    overrides.setdefault("secret_key", SECRET)
    overrides.setdefault("enable_audit", False)
    return MiddlewareAuthManager(**overrides)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_access_token_carries_jti():
    """create_access_token stamps a jti — the canonical revocation identity."""
    mgr = _mgr()
    token = await mgr.create_access_token("u1", ["read"])
    payload = pyjwt.decode(token, SECRET, algorithms=["HS256"])
    assert "jti" in payload and payload["jti"], "access token has no jti claim"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_revoked_token_rejected_with_revoked_message():
    """A manager rejects a token it revoked, with the specific 'revoked' detail.

    Pins the post-decode ordering: a non-expired revoked token surfaces the
    revocation reason (not a generic decode error), so callers can distinguish
    revoked from malformed.
    """
    mgr = _mgr()
    token = await mgr.create_access_token("u9")
    assert (await mgr.verify_token(token))["user_id"] == "u9"

    await mgr.revoke_token(token)

    with pytest.raises(HTTPException) as exc:
        await mgr.verify_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token has been revoked"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_revocation_propagates_via_shared_store():
    """Two managers sharing ONE store reject a token revoked on either.

    Models two worker processes that share a distributed revocation backend —
    the multi-worker scenario #1356 was about, now extended to
    MiddlewareAuthManager.
    """
    shared = InMemoryTokenRevocationStore()
    worker_a = _mgr(revocation_store=shared)
    worker_b = _mgr(revocation_store=shared)

    token = await worker_a.create_access_token("u1")
    assert (await worker_a.verify_token(token))["user_id"] == "u1"
    assert (await worker_b.verify_token(token))["user_id"] == "u1"

    await worker_a.revoke_token(token)

    with pytest.raises(HTTPException):
        await worker_a.verify_token(token)
    # The fix: worker_b — which never called revoke — also rejects it.
    with pytest.raises(HTTPException):
        await worker_b.verify_token(token)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_default_store_is_process_local():
    """The default (no shared store) is process-local — documented limitation.

    Multi-worker deployments MUST inject a shared store (see
    test_revocation_propagates_via_shared_store).
    """
    worker_a = _mgr()  # default in-memory store
    worker_b = _mgr()  # separate default store

    token = await worker_a.create_access_token("u1")
    await worker_a.revoke_token(token)

    with pytest.raises(HTTPException):
        await worker_a.verify_token(token)
    # Process-local default: worker_b still accepts (separate in-memory store).
    assert (await worker_b.verify_token(token))["user_id"] == "u1"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_blacklist_disabled_means_no_store_and_no_revocation():
    """enable_blacklist=False holds no store and keeps revocation a no-op."""
    mgr = _mgr(enable_blacklist=False)
    assert mgr._revocation_store is None
    token = await mgr.create_access_token("u1")
    await mgr.revoke_token(token)  # no-op
    # Token still verifies because revocation is disabled.
    assert (await mgr.verify_token(token))["user_id"] == "u1"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_revoke_when_decode_fails_records_raw_token():
    """A malformed token presented to revoke_token is recorded by raw string.

    Preserves the 'revoke even if verification fails' behavior so a token
    presented for revocation is never silently ignored.
    """
    store = InMemoryTokenRevocationStore()
    mgr = _mgr(revocation_store=store)
    garbage = "not.a.valid.jwt"
    await mgr.revoke_token(garbage)
    assert store.is_revoked(token=garbage) is True


@pytest.mark.regression
@pytest.mark.asyncio
async def test_revoke_fallback_caps_forged_future_exp_at_token_expiry():
    """A forged far-future exp on an unverifiable token cannot extend entry TTL.

    The decode-failure fallback reads exp from an UNVERIFIED decode
    (attacker-controllable). The entry TTL MUST be capped at the access-token
    lifetime so a forged exp=year-3000 cannot pin the entry for centuries.
    """
    store = InMemoryTokenRevocationStore()
    mgr = _mgr(revocation_store=store, token_expiry_hours=24)
    far_future = datetime(3000, 1, 1, tzinfo=timezone.utc)
    forged = pyjwt.encode(
        {"user_id": "x", "exp": far_future},
        "a-different-secret-key-also-32-chars-x!",  # foreign key → verify fails
        algorithm="HS256",
    )
    await mgr.revoke_token(forged)  # fails verify -> fallback with forged future exp
    stored_exp = store._revoked[forged]  # inspect the entry's bound TTL
    cap = datetime.now(timezone.utc) + timedelta(hours=24)
    assert stored_exp is not None
    assert stored_exp <= cap, "forged future exp was not capped at token_expiry_hours"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_revoke_unverifiable_already_expired_token_self_purges():
    """A revoked-but-already-expired unverifiable token does NOT linger forever."""
    store = InMemoryTokenRevocationStore()
    mgr = _mgr(revocation_store=store)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    foreign = pyjwt.encode(
        {"user_id": "x", "jti": "j1", "exp": past},
        "a-different-secret-key-also-32-chars-x!",
        algorithm="HS256",
    )
    await mgr.revoke_token(foreign)  # fails verify -> fallback bounded by past exp
    assert store.is_revoked(token=foreign) is False
    assert store.count() == 0


@pytest.mark.regression
@pytest.mark.asyncio
async def test_backward_compat_token_without_jti_still_verifies():
    """A pre-change token (no jti claim) still verifies — not falsely rejected.

    Guards the upgrade path: tokens minted before this change carry no jti, so
    is_revoked(jti=None, token=...) keys only on the raw token against an empty
    store and returns False.
    """
    mgr = _mgr()
    legacy = pyjwt.encode(
        {
            "user_id": "old",
            "permissions": [],
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        SECRET,
        algorithm="HS256",
    )
    assert "jti" not in pyjwt.decode(legacy, SECRET, algorithms=["HS256"])
    assert (await mgr.verify_token(legacy))["user_id"] == "old"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_custom_revocation_store_protocol_shape():
    """A custom in-process backend satisfying the contract works end-to-end."""

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
    mgr = _mgr(revocation_store=store)
    token = await mgr.create_access_token("custom")
    await mgr.revoke_token(token)
    assert len(store.revoked) == 1
    with pytest.raises(HTTPException):
        await mgr.verify_token(token)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_invalid_token_raises_clean_401_not_valueerror():
    """Regression: invalid/expired tokens surface HTTPException(401), not ValueError.

    Before the fix, verify_token's error path logged the security event with
    severity="warning" — not a valid SeverityLevel (CRITICAL/HIGH/MEDIUM/LOW/INFO)
    — so SecurityEventNode raised ValueError, which escaped verify_token as a
    non-401 error. The fix maps the severity to a valid level.
    """
    mgr = _mgr()
    with pytest.raises(HTTPException) as exc:
        await mgr.verify_token("garbage.token.value")
    assert exc.value.status_code == 401

    # Expired token: also a clean 401, not a ValueError.
    expired_mgr = _mgr(token_expiry_hours=-1)
    expired = await expired_mgr.create_access_token("u2")
    with pytest.raises(HTTPException) as exc2:
        await expired_mgr.verify_token(expired)
    assert exc2.value.status_code == 401


@pytest.mark.regression
@pytest.mark.asyncio
async def test_revoke_token_audit_path_does_not_raise():
    """revoke_token with enable_audit=True (the PRODUCTION default) exercises the
    audit_logger.execute path and must not raise.

    Pins the audit branch against the same kwarg/severity-mismatch bug class that
    made the security-event log raise ValueError before this change — every other
    test in this file sets enable_audit=False, so this is the only coverage of the
    `if self.enable_audit: self.audit_logger.execute(...)` block in revoke_token.
    """
    # enable_audit defaults True; do NOT use the _mgr helper (it forces it off).
    mgr = MiddlewareAuthManager(secret_key=SECRET, enable_audit=True)
    token = await mgr.create_access_token("u-audit")
    await mgr.revoke_token(token)  # audit logging runs here; must not raise
    # The revocation still took effect through the audited path.
    with pytest.raises(HTTPException) as exc:
        await mgr.verify_token(token)
    assert exc.value.status_code == 401


@pytest.mark.regression
@pytest.mark.asyncio
async def test_logging_failure_does_not_break_revocation_401():
    """A SecurityEventNode failure MUST NOT convert the revoked-token 401 into a 500.

    Regression for the R1/R2 bypass-lens finding: security-event logging is
    best-effort (`_emit_security_event` swallows backend failures), so a revoked
    token still surfaces a clean HTTPException(401) — never a raw exception / 500 —
    even if the logging backend raises. The auth decision is fail-closed and
    independent of observability.
    """
    mgr = _mgr()
    token = await mgr.create_access_token("u1")
    await mgr.revoke_token(token)

    # Fault-inject: the security-event logging backend raises (e.g. backend down).
    def _boom(*args, **kwargs):
        raise RuntimeError("security log backend down")

    mgr.security_logger.execute = _boom  # type: ignore[assignment]

    with pytest.raises(HTTPException) as exc:
        await mgr.verify_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token has been revoked"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_dependency_rejects_revoked_bearer_token():
    """End-to-end through the FastAPI dependency: a revoked bearer token → 401.

    The user-facing composition: get_current_user_dependency calls verify_token;
    a revoked token makes it fall through to the final 'Not authenticated' 401.
    """
    from fastapi.security import HTTPAuthorizationCredentials
    from starlette.requests import Request

    mgr = _mgr()
    token = await mgr.create_access_token("u1", ["read"])
    dep = mgr.get_current_user_dependency()

    scope = {"type": "http", "headers": [], "method": "GET", "path": "/"}
    request = Request(scope)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    # Before revocation: the dependency resolves the user.
    user = await dep(request, creds)
    assert user["user_id"] == "u1"

    await mgr.revoke_token(token)

    # After revocation: verify_token raises 401; the dependency has no API key
    # fallback header, so it surfaces the final 401.
    with pytest.raises(HTTPException) as exc:
        await dep(request, creds)
    assert exc.value.status_code == 401
