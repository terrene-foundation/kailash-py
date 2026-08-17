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

**A key is two parts: a public id and a secret.** The presented form is
``sk_<key_id>.<secret>``. The store is addressed by ``key_id``, which is NOT a
credential -- it identifies a record and authorizes nothing. Only the secret
authorizes, and only its salted HMAC-SHA256 digest is stored; the plaintext is
returned to the caller exactly once, at creation. So a store dump, a log line,
or a database backup leaks nothing presentable, and -- unlike addressing the
store by a digest of the whole key -- an audit line can name WHICH key was used
without ever handling the secret.

Example -- sharing issued keys across workers::

    from kailash.middleware.auth import APIKeyStore, MiddlewareAuthManager

    class RedisAPIKeyStore(APIKeyStore):
        def __init__(self, client):
            self._client = client  # a synchronous redis client

        def store(self, *, key_id, record):
            self._client.set(f"apikey:{key_id}", json.dumps(record.to_dict()))

        def lookup(self, *, key_id):
            raw = self._client.get(f"apikey:{key_id}")
            return APIKeyRecord.from_dict(json.loads(raw)) if raw else None

        def revoke(self, *, key_id):
            return bool(self._client.delete(f"apikey:{key_id}"))

    manager = MiddlewareAuthManager(
        secret_key=..., api_key_store=RedisAPIKeyStore(redis_client)
    )
"""

import hashlib
import hmac
import secrets
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

__all__ = [
    "APIKeyRecord",
    "APIKeyStore",
    "InMemoryAPIKeyStore",
    "derive_secret_digest",
    "generate_api_key",
    "generate_salt",
    "split_api_key",
]


#: Separates the public key id from the secret half in a presented key.
#: ``.`` is not produced by ``secrets.token_urlsafe`` (whose alphabet is
#: ``[A-Za-z0-9_-]``), so it cannot occur inside either half and the split is
#: unambiguous.
_KEY_PART_SEPARATOR = "."

#: Bytes of randomness in the public key id. 96 bits is far beyond any
#: collision concern for an issued-key namespace, and the id is NOT a secret --
#: it identifies the record, it does not authorize anything.
_KEY_ID_BYTES = 12

#: Bytes of randomness in the secret half. 256 bits from the OS CSPRNG: this is
#: the only part that authorizes, and it is what the digest protects.
_KEY_SECRET_BYTES = 32


def generate_api_key() -> tuple[str, str, str]:
    """Mint a key, returning ``(presented_key, key_id, secret)``.

    The presented form is ``sk_<key_id>.<secret>``. Splitting it is what lets
    the store be addressed by a NON-SECRET id:

    * **Lookup is O(1) on a value that is not a credential.** The store maps
      ``key_id -> record``, so verification finds the candidate record without
      any secret material being used as a lookup key.
    * **The id is safe to log.** An audit line, a rate-limit counter, or a
      support ticket can name WHICH key was used without ever handling the
      secret. The previous digest-addressed design could not identify a key in
      a log at all.
    * **The secret is compared in constant time** against a stored keyed digest
      (see :func:`derive_secret_digest`), rather than being hashed into a
      dictionary key.
    """
    key_id = secrets.token_urlsafe(_KEY_ID_BYTES)
    secret = secrets.token_urlsafe(_KEY_SECRET_BYTES)
    return f"sk_{key_id}{_KEY_PART_SEPARATOR}{secret}", key_id, secret


def split_api_key(api_key: str) -> Optional[tuple[str, str]]:
    """Split a presented key into ``(key_id, secret)``, or ``None`` if malformed.

    ``None`` rather than an exception: a malformed key is an ordinary failed
    authentication attempt driven by an anonymous caller, not a server fault,
    and raising here would put an exception on the unauthenticated request path
    (the amplification shape of #2114).
    """
    if not isinstance(api_key, str) or not api_key.startswith("sk_"):
        return None
    key_id, separator, secret = api_key[len("sk_") :].partition(_KEY_PART_SEPARATOR)
    if not separator or not key_id or not secret:
        return None
    return key_id, secret


def derive_secret_digest(secret: str, salt: str) -> str:
    """Return the salted keyed digest of a key's secret half.

    HMAC-SHA256 with a per-record random salt as the MAC key. Three properties,
    in the order they matter:

    * **Constant cost.** This runs on every request, including every
      unauthenticated one. A deliberately-expensive KDF (bcrypt/scrypt/argon2,
      ~10^2 ms) here would hand an anonymous caller a CPU amplifier: each
      garbage key submitted would cost the server a full KDF. Cheap verification
      is a requirement of this path, not a shortcut.
    * **Nothing to guess.** The secret is 256 bits from the OS CSPRNG
      (:func:`generate_api_key`) and is never caller-chosen, so the offline
      dictionary attack a slow KDF defends against has no purchase: recovering
      it means inverting the MAC over a uniform 2^256 space.
    * **Per-record salt.** Two records with the same secret produce different
      digests, so a store dump reveals no equality relationships between keys
      and no precomputation carries from one record to the next.

    Args:
        secret: The secret half of a presented key.
        salt: The record's salt, generated once at issue time.

    Returns:
        Lowercase hex HMAC-SHA256 digest.

    Raises:
        TypeError: ``secret`` or ``salt`` is not a ``str``. Refused rather than
            coerced: a ``bytes`` input digests differently from the equivalent
            ``str`` and would silently fail to match the record it created.
    """
    if not isinstance(secret, str):
        raise TypeError(f"secret must be a str, got {type(secret).__name__}")
    if not isinstance(salt, str):
        raise TypeError(f"salt must be a str, got {type(salt).__name__}")
    # CodeQL reports `py/weak-sensitive-data-hashing` (security-severity high)
    # on the call below, and the report is a FALSE POSITIVE that has no
    # available suppression. Recorded here because the next reader will meet
    # the red check before they meet #2146.
    #
    # Why the rule does not apply: `secret` is a 256-bit CSPRNG token from
    # `generate_api_key`, never a user-chosen password, so the offline guessing
    # attack a password-safe KDF defends against has nothing to work against.
    # Adopting a KDF would be a REGRESSION, not a fix: this runs on every
    # request including unauthenticated ones, so a ~10^2 ms KDF hands an
    # anonymous caller a CPU-burn amplifier.
    #
    # THREE suppressions were tried and MEASURED not to work; none is left in
    # place, because a marker that does nothing looks exactly like a fix and
    # stops the next person from looking for the real one (the lesson
    # `.github/codeql/sanitizers/sanitizers.model.yml` records about itself):
    #   1. sanitizer-pack model -- `neutralModel` has no effect on an in-source
    #      function and `summaryModel` kind `value` propagates taint. Refuted in
    #      this repo already, on PR #2103.
    #   2. keyed HMAC instead of a bare digest -- the alert simply moved from
    #      `hashlib.sha256` to `hmac.new` (api_keys.py:117 -> :170).
    #   3. an inline `# codeql[py/weak-sensitive-data-hashing]` comment -- the
    #      alert persisted (:170 -> :177, shifted only by these comment lines).
    #
    # Renaming `secret` would likely clear it, since the rule keys on
    # name-driven classification, and is deliberately NOT done: it changes no
    # behaviour, makes this line less honest, and games a check that must keep
    # firing for genuine password hashing elsewhere in this tree. Disposition
    # and Rule 1b proof: #2146.
    return hmac.new(
        salt.encode("utf-8"), secret.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def generate_salt() -> str:
    """Return a fresh per-record salt for :func:`derive_secret_digest`."""
    return secrets.token_urlsafe(_KEY_ID_BYTES)


@dataclass
class APIKeyRecord:
    """Metadata for one issued API key. Never holds the key itself.

    Holds the SALTED DIGEST of the key's secret half, never the secret itself,
    so a record that leaks yields nothing presentable.

    Attributes:
        user_id: The principal the key authenticates as.
        key_name: Human-readable label chosen at creation.
        secret_digest: ``derive_secret_digest(secret, salt)`` for this key.
        salt: Per-record MAC key for that digest, generated once at issue time.
        permissions: Permissions granted to bearers of this key.
        created_at: Issue time (timezone-aware UTC).
        expires_at: Optional natural expiry. A key past it fails verification
            and is purged lazily.
        metadata: Free-form caller data. Carried through verification.
    """

    user_id: str
    key_name: str
    secret_digest: str = ""
    salt: str = ""
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

    def verify_secret(self, secret: str) -> bool:
        """Whether ``secret`` is this key's secret half, compared in constant time.

        ``hmac.compare_digest`` over two hex digests: both are ASCII by
        construction, so the non-ASCII ``TypeError`` that #2114 turned into a
        log flood cannot arise here. A record with no stored digest verifies
        NOTHING -- that is the fail-closed direction for a malformed or
        partially-restored record.
        """
        if not self.secret_digest or not isinstance(secret, str):
            return False
        return hmac.compare_digest(
            derive_secret_digest(secret, self.salt), self.secret_digest
        )

    def to_dict(self, *, include_secret_digest: bool = False) -> Dict[str, Any]:
        """Serializable view.

        ``user_id`` and ``permissions`` are top-level because that is what
        ``MiddlewareAuthManager.get_current_user_dependency`` reads off the
        result to build the request principal.

        Args:
            include_secret_digest: Include ``secret_digest`` and ``salt``. OFF by
                default because this method's other caller is
                ``verify_api_key``'s RETURN VALUE, which flows to the
                application: a verifier has no use for the digest, and shipping
                it there would put verification material into request-handling
                code and any log that records the principal. An
                :class:`APIKeyStore` implementation persisting a record passes
                True.
        """
        data = {
            "user_id": self.user_id,
            "key_name": self.key_name,
            "permissions": list(self.permissions),
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": dict(self.metadata),
        }
        if include_secret_digest:
            data["secret_digest"] = self.secret_digest
            data["salt"] = self.salt
        return data

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
            secret_digest=data.get("secret_digest", ""),
            salt=data.get("salt", ""),
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

    Implementations are addressed by ``key_id`` -- the PUBLIC half of a key,
    which authorizes nothing -- and never see the plaintext secret. Only its
    salted digest reaches a record. An implementation that stores the secret
    defeats the point of the interface.
    """

    @abstractmethod
    def store(self, *, key_id: str, record: APIKeyRecord) -> None:
        """Persist ``record`` under ``key_id``, replacing any existing entry."""

    @abstractmethod
    def lookup(self, *, key_id: str) -> Optional[APIKeyRecord]:
        """Return the record for ``key_id``, or ``None`` if there is none.

        MUST return ``None`` for an expired record rather than the record: a
        caller that has to remember to re-check expiry is a caller that will
        eventually forget. Returning a record is NOT authentication -- the
        caller still verifies the secret against it.
        """

    @abstractmethod
    def revoke(self, *, key_id: str) -> bool:
        """Drop the entry for ``key_id``. Returns whether one was present."""

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

    def store(self, *, key_id: str, record: APIKeyRecord) -> None:
        with self._lock:
            self._purge_expired_locked()
            self._keys[key_id] = record

    def lookup(self, *, key_id: str) -> Optional[APIKeyRecord]:
        with self._lock:
            self._purge_expired_locked()
            return self._keys.get(key_id)

    def revoke(self, *, key_id: str) -> bool:
        with self._lock:
            return self._keys.pop(key_id, None) is not None

    def count(self) -> int:
        with self._lock:
            self._purge_expired_locked()
            return len(self._keys)

    def _purge_expired_locked(self) -> None:
        """Drop naturally-expired keys. Caller holds the lock."""
        now = datetime.now(timezone.utc)
        expired = [k for k, rec in self._keys.items() if rec.is_expired(now=now)]
        for key_id in expired:
            del self._keys[key_id]
