# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Per-recipient disclosure tracing -- leak attribution primitive (issue #1482).

The trust layer already records ``RESOURCE_ACCESS`` audit events (which resource
was touched, by which actor). What it lacked was a way to attribute a LEAKED
artifact back to the specific recipient it was served to.

This module adds three composable pieces:

1. A ``disclosure`` audit event -- a specialization of ``AuditEvent`` (via the
   ``AuditEventType.DISCLOSURE`` action discriminator) carrying a deterministic
   per-``(recipient, resource, session)`` trace token in its ``metadata``.
   Because ``metadata`` participates in the audit event's Merkle hash, the token
   is cryptographically BOUND to the audit record.
2. A reverse-lookup keyed store (``DisclosureStoreProtocol`` /
   ``InMemoryDisclosureStore``) mapping ``trace_token -> DisclosureRecord``.
   Reverse attribution is done by LOOKUP in this store, NEVER by inverting the
   HMAC (which is one-way -- see ``kailash.trust.signing.derivation``).
3. ``DisclosureTracer`` -- ties the two together: derives the token, writes the
   ``disclosure`` audit event, and persists the reverse mapping.

Boundary (engine vs application). Watermark RENDERING (injecting the token into
HTML/PDF/image bytes) is presentation-specific and lives application-side. Only
trace-token derivation, audit binding, and reverse lookup belong here.

The server-held derivation key MUST come from injected key material -- pass it
to the constructor, or use ``DisclosureTracer.from_env`` which reads a base64
key from an environment variable and fail-closes if it is missing
(``rules/security.md`` -- no hardcoded secrets).
"""

from __future__ import annotations

import base64
import logging
import os
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Protocol, Tuple, runtime_checkable

from kailash.trust.audit_store import (
    AuditEvent,
    AuditEventType,
    InMemoryAuditStore,
    SqliteAuditStore,
)
from kailash.trust.exceptions import TrustError
from kailash.trust.signing.derivation import derive_trace_token

logger = logging.getLogger(__name__)

_DEFAULT_MAX_RECORDS = 10_000
"""Default bound for in-memory disclosure stores (trust-plane-security Rule 4)."""


class DisclosureError(TrustError):
    """Base exception for disclosure-tracing operations."""


@dataclass(frozen=True)
class DisclosureRecord:
    """Reverse-lookup entry mapping a trace token back to its recipient.

    Attributes:
        trace_token: The derived per-recipient trace token (HMAC hex).
        recipient: Stable identity of the recipient the artifact was served to.
        resource: Identifier of the disclosed resource.
        session: Session / delivery-context identifier.
        event_id: ``event_id`` of the bound ``disclosure`` audit event.
        timestamp: ISO-8601 UTC string of when the disclosure was recorded.
        metadata: Additional application context.
    """

    trace_token: str
    recipient: str
    resource: str
    session: str
    event_id: str
    timestamp: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "trace_token": self.trace_token,
            "recipient": self.recipient,
            "resource": self.resource,
            "session": self.session,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DisclosureRecord":
        """Reconstruct from a dict produced by ``to_dict``."""
        return cls(
            trace_token=str(data["trace_token"]),
            recipient=str(data["recipient"]),
            resource=str(data["resource"]),
            session=str(data["session"]),
            event_id=str(data["event_id"]),
            timestamp=str(data["timestamp"]),
            metadata=dict(data.get("metadata") or {}),
        )


@runtime_checkable
class DisclosureStoreProtocol(Protocol):
    """Keyed store mapping ``trace_token -> DisclosureRecord`` for reverse lookup."""

    async def put(self, record: DisclosureRecord) -> None:
        """Persist a disclosure record, keyed by its ``trace_token``."""
        ...

    async def get(self, trace_token: str) -> Optional[DisclosureRecord]:
        """Return the record for ``trace_token``, or None if unknown."""
        ...


class InMemoryDisclosureStore:
    """Dict-backed reverse-lookup store, bounded per trust-plane-security Rule 4.

    Keyed by ``trace_token``. Because the token is deterministic, re-recording
    the same ``(recipient, resource, session)`` overwrites the prior entry
    in-place (idempotent) rather than growing the store.
    """

    def __init__(self, max_records: int = _DEFAULT_MAX_RECORDS) -> None:
        if max_records < 1:
            raise DisclosureError("max_records must be at least 1")
        self._max_records = max_records
        self._records: "OrderedDict[str, DisclosureRecord]" = OrderedDict()

    @property
    def count(self) -> int:
        """Number of records in the store."""
        return len(self._records)

    async def put(self, record: DisclosureRecord) -> None:
        """Persist ``record`` keyed by its ``trace_token`` (idempotent overwrite)."""
        # Overwrite-in-place keeps deterministic re-recording idempotent.
        if record.trace_token in self._records:
            self._records.pop(record.trace_token)
        self._records[record.trace_token] = record

        # Bounded: evict oldest 10% at capacity.
        if len(self._records) > self._max_records:
            drop = max(1, self._max_records // 10)
            for _ in range(drop):
                self._records.popitem(last=False)

    async def get(self, trace_token: str) -> Optional[DisclosureRecord]:
        """Return the record for ``trace_token``, or None if unknown."""
        return self._records.get(trace_token)


class DisclosureTracer:
    """Derive per-recipient trace tokens, bind them to audit events, and index them.

    Composes a server-held derivation key, an ``AuditStore`` (for the bound
    ``disclosure`` audit event), and a ``DisclosureStoreProtocol`` (for reverse
    lookup). The server key is injected -- never hardcoded.

    Example::

        import os
        from kailash.trust.audit_store import InMemoryAuditStore
        from kailash.trust.disclosure import DisclosureTracer

        audit = InMemoryAuditStore()
        tracer = DisclosureTracer.from_env("KAILASH_DISCLOSURE_TRACE_KEY", audit)
        event, token = await tracer.record_disclosure(
            recipient="user-42", resource="report-2026-q2", session="sess-abc",
        )
        assert (await tracer.lookup_recipient(token)) == "user-42"
    """

    def __init__(
        self,
        server_key: bytes,
        audit_store: Any,
        store: Optional[DisclosureStoreProtocol] = None,
    ) -> None:
        if not isinstance(server_key, (bytes, bytearray)):
            raise TypeError(
                f"server_key must be bytes, got {type(server_key).__name__}"
            )
        if not server_key:
            raise DisclosureError(
                "server_key must be non-empty; source it from injected key "
                "material (environment variable or key manager), never a literal"
            )
        self._server_key = bytes(server_key)
        self._audit_store = audit_store
        self._store: DisclosureStoreProtocol = store or InMemoryDisclosureStore()

    @classmethod
    def from_env(
        cls,
        env_var: str,
        audit_store: Any,
        store: Optional[DisclosureStoreProtocol] = None,
    ) -> "DisclosureTracer":
        """Build a tracer from a base64 server key in an environment variable.

        Fail-closes with ``DisclosureError`` if the variable is unset or empty
        so a missing key can never silently degrade into an insecure default.

        Args:
            env_var: Name of the environment variable holding the base64 key.
            audit_store: An ``AuditStore`` (InMemory or Sqlite) for bound events.
            store: Optional reverse-lookup store (defaults to in-memory).

        Returns:
            A configured ``DisclosureTracer``.

        Raises:
            DisclosureError: If ``env_var`` is unset/empty or not valid base64.
        """
        raw = os.environ.get(env_var)
        if not raw:
            raise DisclosureError(
                f"environment variable {env_var!r} is unset or empty; a "
                "disclosure trace key MUST be provisioned (no hardcoded default)"
            )
        try:
            key = base64.b64decode(raw, validate=True)
        except Exception as exc:  # noqa: BLE001 - re-raised as typed error
            raise DisclosureError(
                f"environment variable {env_var!r} is not valid base64: {exc}"
            ) from exc
        if not key:
            raise DisclosureError(
                f"environment variable {env_var!r} decoded to an empty key"
            )
        return cls(key, audit_store, store=store)

    def derive_token(self, recipient: str, resource: str, session: str) -> str:
        """Derive (without recording) the trace token for the given tuple.

        Deterministic and one-way -- see ``derive_trace_token``.
        """
        return derive_trace_token(self._server_key, recipient, resource, session)

    async def record_disclosure(
        self,
        *,
        recipient: str,
        resource: str,
        session: str,
        actor: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[AuditEvent, str]:
        """Derive the token, write the bound audit event, and index the mapping.

        The token is stored in the audit event's ``metadata["trace_token"]`` --
        which participates in the event's Merkle hash, binding the token to the
        immutable audit record. The reverse mapping (``token -> recipient``) is
        persisted in the keyed store; recipient identity is NOT written into the
        audit event, so leak attribution requires the server-side store, not the
        served artifact.

        Args:
            recipient: Recipient the artifact is served to (the attribution target).
            resource: Identifier of the resource being disclosed.
            session: Session / delivery-context identifier.
            actor: Who performed the disclosure (defaults to a system marker).
            metadata: Extra context; merged into the audit event metadata (the
                reserved keys ``trace_token`` and ``session`` are set by this
                method and MUST NOT be overridden).

        Returns:
            ``(audit_event, trace_token)``.

        Raises:
            DisclosureError: If a reserved metadata key is supplied, or the
                audit store type is unsupported.
        """
        extra = dict(metadata) if metadata else {}
        for reserved in ("trace_token", "session"):
            if reserved in extra:
                raise DisclosureError(
                    f"metadata key {reserved!r} is reserved by DisclosureTracer"
                )

        token = self.derive_token(recipient, resource, session)
        event_meta: Dict[str, Any] = {
            **extra,
            "trace_token": token,
            "session": session,
        }
        disclosing_actor = actor or "system"
        action = AuditEventType.DISCLOSURE.value

        # isinstance dispatch (not hasattr) per zero-tolerance Rule 3d: the two
        # canonical stores have different create signatures. Fail-closed on any
        # other store type rather than silently skipping the audit binding.
        if isinstance(self._audit_store, SqliteAuditStore):
            event = await self._audit_store.create_and_append(
                actor=disclosing_actor,
                action=action,
                resource=resource,
                metadata=event_meta,
            )
        elif isinstance(self._audit_store, InMemoryAuditStore):
            event = self._audit_store.create_event(
                actor=disclosing_actor,
                action=action,
                resource=resource,
                metadata=event_meta,
            )
            await self._audit_store.append(event)
        else:
            raise DisclosureError(
                "audit_store must be an InMemoryAuditStore or SqliteAuditStore, "
                f"got {type(self._audit_store).__name__}"
            )

        record = DisclosureRecord(
            trace_token=token,
            recipient=recipient,
            resource=resource,
            session=session,
            event_id=event.event_id,
            timestamp=event.timestamp,
            metadata=extra,
        )
        await self._store.put(record)

        logger.info(
            "disclosure.recorded",
            extra={
                "resource": resource,
                "session": session,
                "event_id": event.event_id,
                # recipient + token deliberately NOT logged (attribution data).
            },
        )
        return event, token

    async def lookup(self, trace_token: str) -> Optional[DisclosureRecord]:
        """Reverse-lookup the full disclosure record for a trace token."""
        return await self._store.get(trace_token)

    async def lookup_recipient(self, trace_token: str) -> Optional[str]:
        """Reverse-lookup the recipient a trace token was derived for, or None."""
        record = await self._store.get(trace_token)
        return record.recipient if record is not None else None


__all__ = [
    "DisclosureError",
    "DisclosureRecord",
    "DisclosureStoreProtocol",
    "InMemoryDisclosureStore",
    "DisclosureTracer",
]
