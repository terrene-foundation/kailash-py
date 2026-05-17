# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Domain event model for the public :class:`kailash.EventBus`.

A strongly-typed, JSON-serializable event envelope carrying a
``correlation_id`` for distributed tracing and a ``schema_version`` for
forward-compatible evolution.  This is the canonical public event model;
it is intentionally dependency-light so that ``import kailash.events``
never drags in the heavy middleware/auth import chain.

The contract is byte-compatible with
``kailash.middleware.communication.DomainEvent`` (same ``to_dict`` /
``from_dict`` keys) so events can cross the two surfaces unchanged.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, Optional

__all__ = ["DomainEvent"]


@dataclass
class DomainEvent:
    """Immutable domain event transported through the EventBus.

    Attributes:
        event_type: Dot-delimited event type (e.g. ``"order.created"``).
        payload: Arbitrary JSON-serializable event data.
        correlation_id: UUID linking related events across a workflow or
            saga. Auto-generated when not supplied.
        timestamp: Timezone-aware UTC creation time. Auto-generated.
        actor: Optional id of the entity that caused the event.
        schema_version: Semantic version of the payload schema.
    """

    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    actor: Optional[str] = None
    schema_version: str = "1.0"

    _SUPPORTED_SCHEMA_VERSIONS: ClassVar[frozenset] = frozenset({"1.0"})

    def __post_init__(self) -> None:
        if not self.event_type:
            raise ValueError("event_type must be a non-empty string")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict")
        if not isinstance(self.correlation_id, str) or not self.correlation_id:
            raise ValueError("correlation_id must be a non-empty string")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime instance")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC)")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "event_type": self.event_type,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DomainEvent":
        """Deserialize from a dict produced by :meth:`to_dict`.

        Raises:
            ValueError: If required fields are missing or malformed.
            KeyError: If a required key is absent.
        """
        timestamp_raw = data["timestamp"]
        if isinstance(timestamp_raw, str):
            ts = datetime.fromisoformat(timestamp_raw)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        elif isinstance(timestamp_raw, datetime):
            ts = timestamp_raw
        else:
            raise ValueError(
                "timestamp must be an ISO-8601 string or datetime, "
                f"got {type(timestamp_raw)}"
            )
        return cls(
            event_type=data["event_type"],
            payload=data.get("payload", {}),
            correlation_id=data.get("correlation_id", str(uuid.uuid4())),
            timestamp=ts,
            actor=data.get("actor"),
            schema_version=data.get("schema_version", "1.0"),
        )
