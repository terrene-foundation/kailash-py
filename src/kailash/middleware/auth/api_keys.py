# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""API key storage for Kailash middleware authentication.

Issue #2108. ``MiddlewareAuthManager`` issued and verified API keys through
``CredentialManagerNode``, which cannot store anything. Measured on the loaded
methods rather than inferred::

    create_api_key -> NodeExecutionError: Node 'CredentialManagerNode' execution
                      failed: ValueError: Credential 'api_credentials' not found
                      in any configured source
    verify_api_key -> HTTPException 401 Invalid API key

``CredentialManagerNode`` **fetches** credentials that already exist in the
environment, a JSON file, or a vault. It has no write path, and its return dict
(``credentials``, ``source``, ``validated``, ``masked_display``, ``metadata``)
has no ``success`` key on any branch -- so ``result.get("success", False)`` was
unconditionally False and API-key authentication could not succeed for any key,
valid or not. An auth path that can only ever reject is a non-functional feature
presented as a working one (``zero-tolerance.md`` Rule 2).

This module supplies what that path actually needs: a place to put issued keys.
The shape deliberately mirrors :mod:`kailash.middleware.auth.revocation` -- an
abstract contract, a process-local in-memory default, and an injection point for
a shared backend -- because the deployment question is identical and a second
idiom for it would be one more thing to learn and to drift.

**Keys are stored hashed, never in plaintext.** The plaintext is returned to the
caller exactly once, at creation. A store dump, a log line, or a database backup
therefore leaks no usable credential -- only SHA-256 digests, which cannot be
presented as an API key.

Example -- sharing issued keys across workers::

    from kailash.middleware.auth import APIKeyStore, MiddlewareAuthManager

    class RedisAPIKeyStore(APIKeyStore):
        def __init__(self, client):
            self._client = client  # a synchronous redis client

        def store(self, *, key_hash, record):
            self._client.set(f"apikey:{key_hash}", json.dumps(record.to_dict()))

        def lookup(self, *, key_hash):
            raw = self._client.get(f"apikey:{key_hash}")
            return APIKeyRecord.from_dict(json.loads(raw)) if raw else None

        def revoke(self, *, key_hash):
            return bool(self._client.delete(f"apikey:{key_hash}"))

    manager = MiddlewareAuthManager(
        secret_key=..., api_key_store=RedisAPIKeyStore(redis_client)
    )
"""

import hashlib
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

__all__ = [
    "APIKeyRecord",
    "APIKeyStore",
    "InMemoryAPIKeyStore",
    "hash_api_key",
]


def hash_api_key(api_key: str) -> str:
    """Return the SHA-256 hex digest a key is stored and looked up under.

    UTF-8 is encoded explicitly, which also makes this total over every ``str``:
    a non-ASCII key hashes like any other rather than raising the way
    ``secrets.compare_digest`` does (the sibling defect, #2114). Lookup is by
    digest equality in the store, so no constant-time comparison of the key
    itself is needed or performed -- an attacker cannot work backwards from a
    digest to a presentable key, and the timing of a dict lookup reveals only
    what the 401/200 answer already does.

    Args:
        api_key: The plaintext key as presented by the caller.

    Returns:
        Lowercase hex SHA-256 digest.

    Raises:
        TypeError: ``api_key`` is not a ``str``. Refused rather than coerced: a
            ``bytes`` key would hash to a different digest than the equivalent
            ``str``, silently failing to match the record it created.
    """
    if not isinstance(api_key, str):
        raise TypeError(f"api_key must be a str, got {type(api_key).__name__}")
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


@dataclass
class APIKeyRecord:
    """Metadata for one issued API key. Never holds the key itself.

    Attributes:
        user_id: The principal the key authenticates as.
        key_name: Human-readable label chosen at creation.
        permissions: Permissions granted to bearers of this key.
        created_at: Issue time (timezone-aware UTC).
        expires_at: Optional natural expiry. A key past it fails verification
            and is purged lazily.
        metadata: Free-form caller data. Carried through verification.
    """

    user_id: str
    key_name: str
    permissions: List[str] = field(default_factory=list)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self, *, now: Optional[datetime] = None) -> bool:
        """Whether this key is past ``expires_at``."""
        if self.expires_at is None:
            return False
        return self.expires_at <= (now or datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Serializable view, as returned to a successful verifier.

        ``user_id`` and ``permissions`` are top-level because that is what
        ``MiddlewareAuthManager.get_current_user_dependency`` reads off the
        result to build the request principal.
        """
        return {
            "user_id": self.user_id,
            "key_name": self.key_name,
            "permissions": list(self.permissions),
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "APIKeyRecord":
        """Rebuild a record from :meth:`to_dict` output.

        Provided so an external backend can round-trip records without each
        implementation inventing its own encoding.
        """

        def _parse(value: Optional[str]) -> Optional[datetime]:
            return datetime.fromisoformat(value) if value else None

        created = _parse(data.get("created_at")) or datetime.now(timezone.utc)
        return cls(
            user_id=data["user_id"],
            key_name=data.get("key_name", ""),
            permissions=list(data.get("permissions") or []),
            created_at=created,
            expires_at=_parse(data.get("expires_at")),
            metadata=dict(data.get("metadata") or {}),
        )


class APIKeyStore(ABC):
    """Synchronous contract for an issued-API-key backend.

    Synchronous by design, matching :class:`~kailash.middleware.auth.revocation.TokenRevocationStore`:
    verification sits on the per-request hot path and must be callable without
    assuming an event loop.

    Implementations are addressed by the key's SHA-256 digest
    (:func:`hash_api_key`) and never see the plaintext key. An implementation
    that stores the plaintext defeats the point of the interface.
    """

    @abstractmethod
    def store(self, *, key_hash: str, record: APIKeyRecord) -> None:
        """Persist ``record`` under ``key_hash``, replacing any existing entry."""

    @abstractmethod
    def lookup(self, *, key_hash: str) -> Optional[APIKeyRecord]:
        """Return the record for ``key_hash``, or ``None`` if there is none.

        MUST return ``None`` for an expired record rather than the record: a
        caller that has to remember to re-check expiry is a caller that will
        eventually forget.
        """

    @abstractmethod
    def revoke(self, *, key_hash: str) -> bool:
        """Drop the entry for ``key_hash``. Returns whether one was present."""

    def count(self) -> Optional[int]:
        """Number of live keys, or ``None`` if the backend cannot cheaply count."""
        return None


class InMemoryAPIKeyStore(APIKeyStore):
    """Process-local API key store (the default). Thread-safe.

    WARNING: keys issued through one worker are unknown to every other worker.
    In a multi-worker deployment supply a shared :class:`APIKeyStore` backend
    (Redis, database, distributed cache).

    Note that this default fails **closed**: a key the worker does not know is
    refused, so process-locality costs availability for keys issued elsewhere
    and never grants access. That is the opposite direction from the revocation
    store, whose process-local default fails open and is warned about
    accordingly -- which is why this one documents rather than warns.
    """

    def __init__(self) -> None:
        self._keys: Dict[str, APIKeyRecord] = {}
        self._lock = threading.Lock()

    def store(self, *, key_hash: str, record: APIKeyRecord) -> None:
        with self._lock:
            self._purge_expired_locked()
            self._keys[key_hash] = record

    def lookup(self, *, key_hash: str) -> Optional[APIKeyRecord]:
        with self._lock:
            self._purge_expired_locked()
            return self._keys.get(key_hash)

    def revoke(self, *, key_hash: str) -> bool:
        with self._lock:
            return self._keys.pop(key_hash, None) is not None

    def count(self) -> int:
        with self._lock:
            self._purge_expired_locked()
            return len(self._keys)

    def _purge_expired_locked(self) -> None:
        """Drop naturally-expired keys. Caller holds the lock."""
        now = datetime.now(timezone.utc)
        expired = [h for h, rec in self._keys.items() if rec.is_expired(now=now)]
        for key_hash in expired:
            del self._keys[key_hash]
