# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Knowledge item classification and pre-retrieval filtering.

A KnowledgeItem represents a piece of organizational knowledge with a
classification level, owning unit, and optional compartment restrictions.
Access decisions are made by comparing a role's clearance against the
item's classification and compartments.

KnowledgeFilter is a pre-retrieval lifecycle gate: it evaluates BEFORE
data is fetched, unlike ``can_access()`` which checks AFTER the caller
already has the data. Implementations narrow or deny queries before any
data leaves the store.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from kailash.trust.pact.config import ConfidentialityLevel

logger = logging.getLogger(__name__)

__all__ = [
    "FilterDecision",
    "KnowledgeFilter",
    "KnowledgeItem",
    "KnowledgeQuery",
]


@dataclass(frozen=True)
class KnowledgeItem:
    """A classified knowledge item in the organizational structure.

    Attributes:
        item_id: Unique identifier for this knowledge item.
        classification: Confidentiality level (PUBLIC through TOP_SECRET).
        owning_unit_address: The D or T prefix that owns this data.
            This determines containment -- roles within or above this
            unit have structural access (subject to clearance checks).
        compartments: Named compartments this item belongs to.
            For SECRET and TOP_SECRET items, accessing roles must hold
            ALL compartments the item belongs to.
        description: Human-readable description of the knowledge item.
    """

    item_id: str
    classification: ConfidentialityLevel
    owning_unit_address: str  # D or T prefix that owns this data
    compartments: frozenset[str] = field(default_factory=frozenset)
    description: str = ""


# ---------------------------------------------------------------------------
# Pre-retrieval filtering -- KnowledgeQuery / FilterDecision / KnowledgeFilter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KnowledgeQuery:
    """Describes what data is being requested before retrieval.

    Used by ``KnowledgeFilter`` to evaluate a query scope *before* any
    data leaves the store. All fields are optional -- ``None`` means
    "unrestricted on this dimension".

    Attributes:
        item_ids: Specific item IDs being requested, or None for all.
        classifications: Classification levels requested, or None for all.
        owning_units: Owning unit addresses requested, or None for all.
        description: Human-readable description of the query intent.
    """

    item_ids: frozenset[str] | None = None
    classifications: frozenset[str] | None = None
    owning_units: frozenset[str] | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for audit logging.

        Returns:
            Dict with all fields. Frozensets are serialized as sorted lists.
        """
        return {
            "item_ids": sorted(self.item_ids) if self.item_ids is not None else None,
            "classifications": (
                sorted(self.classifications)
                if self.classifications is not None
                else None
            ),
            "owning_units": (
                sorted(self.owning_units) if self.owning_units is not None else None
            ),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KnowledgeQuery:
        """Deserialize from a dictionary.

        Args:
            data: Dict with serialized KnowledgeQuery fields.

        Returns:
            A KnowledgeQuery instance.
        """
        return cls(
            item_ids=(
                frozenset(data["item_ids"])
                if data.get("item_ids") is not None
                else None
            ),
            classifications=(
                frozenset(data["classifications"])
                if data.get("classifications") is not None
                else None
            ),
            owning_units=(
                frozenset(data["owning_units"])
                if data.get("owning_units") is not None
                else None
            ),
            description=data.get("description", ""),
        )


@dataclass(frozen=True)
class FilterDecision:
    """Result of a ``KnowledgeFilter.filter_before_retrieval()`` evaluation.

    Attributes:
        allowed: Whether the query is allowed to proceed.
        filtered_scope: A narrowed KnowledgeQuery if the filter partially
            allowed the request (e.g., removed some classifications).
            None when fully allowed or fully denied.
        reason: Human-readable explanation of the decision.
        audit_anchor_id: Unique ID for audit trail linkage. Auto-generated
            if not provided.
    """

    allowed: bool
    filtered_scope: KnowledgeQuery | None = None
    reason: str = ""
    audit_anchor_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for audit logging.

        Returns:
            Dict with all fields.
        """
        return {
            "allowed": self.allowed,
            "filtered_scope": (
                self.filtered_scope.to_dict()
                if self.filtered_scope is not None
                else None
            ),
            "reason": self.reason,
            "audit_anchor_id": self.audit_anchor_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FilterDecision:
        """Deserialize from a dictionary.

        Args:
            data: Dict with serialized FilterDecision fields.

        Returns:
            A FilterDecision instance.
        """
        return cls(
            allowed=data["allowed"],
            filtered_scope=(
                KnowledgeQuery.from_dict(data["filtered_scope"])
                if data.get("filtered_scope") is not None
                else None
            ),
            reason=data.get("reason", ""),
            audit_anchor_id=data.get("audit_anchor_id", str(uuid.uuid4())),
        )


@runtime_checkable
class KnowledgeFilter(Protocol):
    """Pre-retrieval lifecycle gate for knowledge access.

    Implementations evaluate a query scope BEFORE any data is fetched.
    This is the first line of defense -- it prevents data from even
    leaving the store if the role's envelope does not permit the query.

    The GovernanceEngine calls ``filter_before_retrieval()`` as a pre-step
    before the existing 5-step ``can_access()`` algorithm. If the filter
    denies the query, no data is retrieved and the decision is logged.

    Error handling: Implementations MUST NOT raise exceptions. If an error
    occurs, return ``FilterDecision(allowed=False, reason="...")``. The
    GovernanceEngine additionally wraps the call in a fail-closed guard.
    """

    def filter_before_retrieval(
        self,
        role_address: str,
        query: KnowledgeQuery,
        envelope: Any,  # EffectiveEnvelopeSnapshot -- Any to avoid circular import
    ) -> FilterDecision:
        """Evaluate whether a role may proceed with a knowledge query.

        Args:
            role_address: The D/T/R address of the requesting role.
            query: Describes what data is being requested.
            envelope: The effective envelope snapshot for the role.
                Type is ``EffectiveEnvelopeSnapshot`` (passed as Any
                to avoid circular import).

        Returns:
            A FilterDecision indicating allow/deny/narrow with reason.
        """
        ...
