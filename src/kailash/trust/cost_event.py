# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Cost event tracking with call_id deduplication (SPEC-08).

Provides a canonical ``CostEvent`` frozen dataclass for recording individual
LLM/API costs, and a ``CostDeduplicator`` that prevents double-counting when
the same call_id is reported more than once (e.g., retries, duplicate webhook
deliveries).

Key design principles:
- FROZEN: CostEvent is immutable after creation.
- FINITE: All monetary fields validated with ``math.isfinite()``.
- DEDUP: CostDeduplicator uses a bounded LRU set to reject duplicate call_ids.
- SOURCE VALIDATION: Every cost event must declare its source (provider name).
"""

from __future__ import annotations

import logging
import math
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from kailash.trust.exceptions import TrustError

logger = logging.getLogger(__name__)

__all__ = [
    "CostEvent",
    "CostDeduplicator",
    "CostEventError",
    "DuplicateCostError",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_DEDUP_CAPACITY = 10_000
"""Maximum number of call_ids to track for deduplication."""

_VALID_SOURCES = frozenset(
    {
        "openai",
        "anthropic",
        "google",
        "deepseek",
        "mistral",
        "azure",
        "bedrock",
        "local",
        "test",
    }
)
"""Well-known cost event sources. Unknown sources are still accepted with
a warning log, but validation ensures the field is non-empty."""


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CostEventError(TrustError):
    """Base exception for cost event operations."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, details=details or {})


class DuplicateCostError(CostEventError):
    """Raised when a duplicate call_id is detected."""

    def __init__(self, call_id: str) -> None:
        # Do not echo raw call_id into the message to prevent log poisoning.
        fingerprint = hash(call_id) & 0xFFFF
        super().__init__(
            f"Duplicate cost event detected (fingerprint={fingerprint:04x})",
            details={"fingerprint": f"{fingerprint:04x}"},
        )
        self.call_id = call_id


# ---------------------------------------------------------------------------
# CostEvent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostEvent:
    """Canonical cost event for tracking individual LLM/API charges.

    Every field that influences budget accounting is validated in
    ``__post_init__`` with ``math.isfinite()`` to prevent NaN/Inf bypass.

    Attributes:
        cost_id: Unique identifier for this cost event.
        call_id: Provider-issued call identifier for deduplication.
        timestamp: UTC timestamp as ISO-8601 string.
        source: Provider name (e.g., "openai", "anthropic").
        model: Model identifier used for the call.
        input_tokens: Number of input tokens consumed.
        output_tokens: Number of output tokens generated.
        cost_microdollars: Cost in microdollars (1 USD = 1,000,000).
        agent_id: Agent that initiated the call.
        workflow_id: Workflow context for the call.
        metadata: Additional context.
    """

    cost_id: str
    call_id: str
    timestamp: str
    source: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_microdollars: int
    agent_id: Optional[str] = None
    workflow_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validate source is non-empty
        if not self.source or not isinstance(self.source, str):
            raise CostEventError(
                "CostEvent source must be a non-empty string",
                details={"source_type": type(self.source).__name__},
            )
        if self.source not in _VALID_SOURCES:
            logger.warning(
                "cost_event.unknown_source",
                extra={"source": self.source, "cost_id": self.cost_id},
            )

        # Validate call_id is non-empty
        if not self.call_id or not isinstance(self.call_id, str):
            raise CostEventError(
                "CostEvent call_id must be a non-empty string",
                details={"call_id_type": type(self.call_id).__name__},
            )

        # Validate numeric fields are finite integers (no NaN/Inf bypass)
        for field_name in ("input_tokens", "output_tokens", "cost_microdollars"):
            val = getattr(self, field_name)
            if not isinstance(val, int):
                raise CostEventError(
                    f"CostEvent {field_name} must be an integer",
                    details={"field": field_name, "type": type(val).__name__},
                )
            # int is always finite, but guard against float masquerading
            if not math.isfinite(float(val)):
                raise CostEventError(
                    f"CostEvent {field_name} must be finite",
                    details={"field": field_name},
                )
            if val < 0:
                raise CostEventError(
                    f"CostEvent {field_name} must be non-negative",
                    details={"field": field_name, "value": val},
                )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary for JSON storage."""
        return {
            "cost_id": self.cost_id,
            "call_id": self.call_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_microdollars": self.cost_microdollars,
            "agent_id": self.agent_id,
            "workflow_id": self.workflow_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CostEvent:
        """Deserialize from a plain dictionary.

        Unknown extra keys are ignored. Missing optional keys default to
        ``None`` or the field default.
        """
        return cls(
            cost_id=str(data["cost_id"]),
            call_id=str(data["call_id"]),
            timestamp=str(data["timestamp"]),
            source=str(data["source"]),
            model=str(data["model"]),
            input_tokens=int(data["input_tokens"]),
            output_tokens=int(data["output_tokens"]),
            cost_microdollars=int(data["cost_microdollars"]),
            agent_id=data.get("agent_id"),
            workflow_id=data.get("workflow_id"),
            metadata=dict(data.get("metadata") or {}),
        )

    @classmethod
    def create(
        cls,
        *,
        call_id: str,
        source: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_microdollars: int,
        agent_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        cost_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> CostEvent:
        """Factory method to create a CostEvent with auto-generated defaults.

        Args:
            call_id: Provider-issued call identifier.
            source: Provider name.
            model: Model identifier.
            input_tokens: Input token count.
            output_tokens: Output token count.
            cost_microdollars: Cost in microdollars.
            agent_id: Optional agent identifier.
            workflow_id: Optional workflow context.
            metadata: Optional additional context.
            cost_id: Override the auto-generated UUID.
            timestamp: Override the auto-generated timestamp.

        Returns:
            A new frozen CostEvent.
        """
        return cls(
            cost_id=cost_id or str(uuid.uuid4()),
            call_id=call_id,
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
            source=source,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_microdollars=cost_microdollars,
            agent_id=agent_id,
            workflow_id=workflow_id,
            metadata=dict(metadata) if metadata else {},
        )


# ---------------------------------------------------------------------------
# CostDeduplicator
# ---------------------------------------------------------------------------


class CostDeduplicator:
    """Bounded LRU deduplicator for cost event call_ids.

    Tracks seen call_ids in an OrderedDict to maintain insertion order
    and evict the oldest entries when capacity is reached. This prevents
    double-counting when the same API call is reported multiple times.

    Thread-safe: uses no external locks because the GIL protects single
    dict operations. For async usage, the caller is expected to serialize
    access at the application level.

    Args:
        capacity: Maximum number of call_ids to track (default 10,000).
    """

    def __init__(self, capacity: int = _DEFAULT_DEDUP_CAPACITY) -> None:
        if capacity < 1:
            raise CostEventError(
                "CostDeduplicator capacity must be at least 1",
                details={"capacity": capacity},
            )
        self._capacity = capacity
        self._seen: OrderedDict[str, None] = OrderedDict()

    @property
    def count(self) -> int:
        """Number of tracked call_ids."""
        return len(self._seen)

    @property
    def capacity(self) -> int:
        """Maximum capacity."""
        return self._capacity

    def check_and_record(self, cost_event: CostEvent) -> bool:
        """Check if a cost event's call_id has been seen before.

        If the call_id is new, records it and returns True.
        If the call_id is a duplicate, raises DuplicateCostError.

        Args:
            cost_event: The cost event to check.

        Returns:
            True if the event is new (not a duplicate).

        Raises:
            DuplicateCostError: If the call_id has been seen before.
        """
        call_id = cost_event.call_id
        if call_id in self._seen:
            raise DuplicateCostError(call_id)

        # Record the new call_id
        self._seen[call_id] = None

        # Evict oldest entries if over capacity
        while len(self._seen) > self._capacity:
            self._seen.popitem(last=False)

        return True

    def is_duplicate(self, call_id: str) -> bool:
        """Check if a call_id has been seen without recording it.

        Args:
            call_id: The call identifier to check.

        Returns:
            True if the call_id is a duplicate.
        """
        return call_id in self._seen

    def clear(self) -> None:
        """Clear all tracked call_ids."""
        self._seen.clear()
