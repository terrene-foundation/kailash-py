"""
Token Revocation Store for Kailash Middleware JWT Authentication.

`JWTAuthManager` historically backed token revocation with an in-memory ``set``
scoped to a single manager instance. In any multi-worker / multi-pod deployment
(the default production topology) a token revoked on one worker stayed valid on
every other worker until natural expiry — the revocation security control
silently failed to take effect (issue #1356).

This module introduces a pluggable revocation backend so revocation can
propagate across every worker that shares the same store. The contract is
**synchronous** by design: ``JWTAuthManager.verify_token`` / ``revoke_token`` are
synchronous public API on the per-request hot path, so the store must be callable
without an event loop. A shared backend (Redis, a database table, a distributed
cache) is supplied by the deployment by implementing :class:`TokenRevocationStore`;
the SDK ships the contract plus the process-local :class:`InMemoryTokenRevocationStore`
default that preserves the original single-process behavior.

Example — propagating revocation across workers via a shared backend::

    from kailash.middleware.auth import (
        JWTAuthManager, JWTConfig, TokenRevocationStore,
    )

    class RedisRevocationStore(TokenRevocationStore):
        def __init__(self, client):
            self._client = client  # a synchronous redis client

        def revoke(self, *, jti, token=None, expires_at=None):
            key = f"jwt:revoked:{jti or token}"
            ttl = None
            if expires_at is not None:
                from datetime import datetime, timezone
                ttl = max(1, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
            self._client.set(key, "1", ex=ttl)

        def is_revoked(self, *, jti=None, token=None):
            for ident in (jti, token):
                if ident and self._client.exists(f"jwt:revoked:{ident}"):
                    return True
            return False

    store = RedisRevocationStore(redis_client)
    cfg = JWTConfig(secret_key="...")
    # Every worker constructed with the same shared store sees revocations.
    manager = JWTAuthManager(config=cfg, revocation_store=store)
"""

import logging
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class TokenRevocationStore(ABC):
    """Synchronous contract for a JWT revocation backend.

    Implementations decide where revocation state lives. The default
    :class:`InMemoryTokenRevocationStore` keeps it in-process (single-worker
    only); a production deployment supplies a shared backend (Redis, database,
    distributed cache) so a token revoked on one worker is rejected on all of
    them.

    A revoked token is identified by its ``jti`` (JWT ID claim) when available.
    When a token cannot be decoded at revocation time, it is revoked by its raw
    token string instead, so ``is_revoked`` accepts both identifiers.
    """

    @abstractmethod
    def revoke(
        self,
        *,
        jti: Optional[str] = None,
        token: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> None:
        """Record a token as revoked.

        Args:
            jti: The token's ``jti`` claim, when decodable. Preferred identifier.
            token: The raw token string. Used as a fallback identifier when the
                token could not be decoded (so ``jti`` is unknown).
            expires_at: When the token naturally expires. Backends that support
                TTL SHOULD use it to evict the entry once the token can no
                longer be presented, bounding store growth. ``None`` means the
                entry has no known expiry and is retained until evicted.
        """

    @abstractmethod
    def is_revoked(
        self,
        *,
        jti: Optional[str] = None,
        token: Optional[str] = None,
    ) -> bool:
        """Return True if the token identified by ``jti`` or ``token`` is revoked."""

    def count(self) -> Optional[int]:
        """Number of currently-revoked entries, or ``None`` if unknown.

        Used for diagnostics (`JWTAuthManager.get_stats`). External backends that
        cannot cheaply count MAY return ``None``; the default in-memory store
        returns an exact count.
        """
        return None


class InMemoryTokenRevocationStore(TokenRevocationStore):
    """Process-local revocation store (the default).

    Preserves the original single-process behavior: revocations are visible only
    within the worker that performed them. Thread-safe. Entries with a known
    ``expires_at`` are purged lazily once expired so the store does not grow
    without bound for short-lived tokens.

    WARNING: This store is process-local. In a multi-worker / multi-pod
    deployment a token revoked through one worker's manager will NOT be rejected
    by other workers. Supply a shared :class:`TokenRevocationStore` backend
    (Redis, database, distributed cache) to propagate revocation across workers.
    """

    def __init__(self) -> None:
        # identifier -> expires_at (or None when no expiry is known)
        self._revoked: dict[str, Optional[datetime]] = {}
        self._lock = threading.Lock()

    def revoke(
        self,
        *,
        jti: Optional[str] = None,
        token: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> None:
        # Prefer the jti (canonical revocation identity); fall back to the raw
        # token only when the token could not be decoded (jti unknown). One
        # entry per revoked token keeps count() == number of revoked tokens.
        ident = jti or token
        if not ident:
            return
        with self._lock:
            self._purge_expired_locked()
            self._revoked[ident] = expires_at

    def is_revoked(
        self,
        *,
        jti: Optional[str] = None,
        token: Optional[str] = None,
    ) -> bool:
        with self._lock:
            self._purge_expired_locked()
            for ident in (jti, token):
                if ident and ident in self._revoked:
                    return True
            return False

    def count(self) -> int:
        with self._lock:
            self._purge_expired_locked()
            return len(self._revoked)

    def _purge_expired_locked(self) -> None:
        """Drop entries whose token has naturally expired. Caller holds the lock."""
        now = datetime.now(timezone.utc)
        expired = [
            ident
            for ident, exp in self._revoked.items()
            if exp is not None and exp <= now
        ]
        for ident in expired:
            del self._revoked[ident]


__all__ = ["TokenRevocationStore", "InMemoryTokenRevocationStore"]
