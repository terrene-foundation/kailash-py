# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
CARE-036: Knowledge Entry Structures for Trust Knowledge Ledger.

Defines the core data structures for knowledge entries within the Trust
Knowledge Ledger. Knowledge entries represent verified information that
agents can contribute and reference.

Key Components:
- KnowledgeType: Enum for categorizing knowledge (FACTUAL, PROCEDURAL, etc.)
- KnowledgeEntry: Dataclass representing a single knowledge entry with
  trust chain references and verification tracking
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


class KnowledgeType(Enum):
    """
    Type of knowledge stored in a knowledge entry.

    Categories:
    - FACTUAL: Verified facts and data points
    - PROCEDURAL: Step-by-step procedures and methods
    - TACIT_TRACE: Implicit knowledge derived from agent behavior
    - INSIGHT: Analytical conclusions and interpretations
    - DECISION_RATIONALE: Reasoning behind decisions made
    """

    FACTUAL = "factual"
    PROCEDURAL = "procedural"
    TACIT_TRACE = "tacit_trace"
    INSIGHT = "insight"
    DECISION_RATIONALE = "decision_rationale"


@dataclass
class KnowledgeEntry:
    """
    A knowledge entry in the Trust Knowledge Ledger.

    Represents a piece of verified knowledge contributed by an agent,
    with references to the trust chain that authorizes it and optional
    constraint envelope references.

    Attributes:
        entry_id: Unique identifier (format: "ke-{uuid_hex[:12]}")
        content: The knowledge content as a string
        content_type: Type of knowledge (from KnowledgeType enum)
        source_agent_id: ID of the agent that contributed this knowledge
        trust_chain_ref: Reference to the trust chain authorizing this entry
        constraint_envelope_ref: Optional reference to constraint envelope
        created_at: UTC timestamp of creation
        verified_by: List of agent IDs that have verified this entry
        confidence_score: Confidence level (0.0 to 1.0, default 0.8)
        metadata: Additional metadata as key-value pairs
    """

    entry_id: str
    content: str
    content_type: KnowledgeType
    source_agent_id: str
    trust_chain_ref: str
    constraint_envelope_ref: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    verified_by: List[str] = field(default_factory=list)
    confidence_score: float = 0.8
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        content: str,
        content_type: KnowledgeType,
        source_agent_id: str,
        trust_chain_ref: str,
        constraint_envelope_ref: Optional[str] = None,
        confidence_score: float = 0.8,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "KnowledgeEntry":
        """
        Factory method to create a new KnowledgeEntry with auto-generated ID.

        Args:
            content: The knowledge content
            content_type: Type of knowledge
            source_agent_id: ID of the contributing agent
            trust_chain_ref: Reference to authorizing trust chain
            constraint_envelope_ref: Optional constraint envelope reference
            confidence_score: Confidence level (0.0 to 1.0)
            metadata: Optional additional metadata

        Returns:
            A new KnowledgeEntry instance with generated entry_id
        """
        entry_id = f"ke-{uuid4().hex[:12]}"
        return cls(
            entry_id=entry_id,
            content=content,
            content_type=content_type,
            source_agent_id=source_agent_id,
            trust_chain_ref=trust_chain_ref,
            constraint_envelope_ref=constraint_envelope_ref,
            created_at=datetime.now(timezone.utc),
            verified_by=[],
            confidence_score=confidence_score,
            metadata=metadata or {},
        )

    def validate(self) -> bool:
        """
        Validate the knowledge entry.

        Checks:
        - entry_id has correct "ke-" prefix
        - confidence_score is between 0.0 and 1.0 (inclusive)
        - content is non-empty
        - source_agent_id is non-empty
        - trust_chain_ref is non-empty

        Returns:
            True if valid

        Raises:
            ValueError: If validation fails with description of the issue
        """
        # Check entry_id prefix
        if not self.entry_id.startswith("ke-"):
            raise ValueError(f"Invalid entry_id format: must start with 'ke-', got '{self.entry_id}'")

        # Check confidence_score bounds
        if self.confidence_score < 0.0:
            raise ValueError(f"confidence_score must be >= 0.0, got {self.confidence_score}")
        if self.confidence_score > 1.0:
            raise ValueError(f"confidence_score must be <= 1.0, got {self.confidence_score}")

        # Check non-empty content
        if not self.content:
            raise ValueError("content must be non-empty")

        # Check non-empty source_agent_id
        if not self.source_agent_id:
            raise ValueError("source_agent_id must be non-empty")

        # Check non-empty trust_chain_ref
        if not self.trust_chain_ref:
            raise ValueError("trust_chain_ref must be non-empty")

        return True

    def is_valid(self) -> bool:
        """
        Check if the knowledge entry is valid without raising exceptions.

        This is an alias for validate() that catches exceptions and returns
        False instead of raising.

        Returns:
            True if valid, False otherwise
        """
        try:
            return self.validate()
        except ValueError:
            return False

    def add_verification(self, verifier_agent_id: str) -> None:
        """
        Add a verifier agent to the verified_by list.

        Only adds the verifier if not already present (no duplicates).

        Args:
            verifier_agent_id: ID of the agent verifying this entry
        """
        if verifier_agent_id not in self.verified_by:
            self.verified_by.append(verifier_agent_id)

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the knowledge entry to a dictionary.

        Converts datetime to ISO format string and enum to its value.

        Returns:
            Dictionary representation suitable for JSON serialization
        """
        return {
            "entry_id": self.entry_id,
            "content": self.content,
            "content_type": self.content_type.value,
            "source_agent_id": self.source_agent_id,
            "trust_chain_ref": self.trust_chain_ref,
            "constraint_envelope_ref": self.constraint_envelope_ref,
            "created_at": self.created_at.isoformat(),
            "verified_by": list(self.verified_by),
            "confidence_score": self.confidence_score,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeEntry":
        """
        Deserialize a knowledge entry from a dictionary.

        Handles missing optional fields with appropriate defaults.

        Args:
            data: Dictionary with KnowledgeEntry fields

        Returns:
            KnowledgeEntry instance
        """
        # Parse created_at - handle both string and datetime
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now(timezone.utc)

        return cls(
            entry_id=data["entry_id"],
            content=data["content"],
            content_type=KnowledgeType(data["content_type"]),
            source_agent_id=data["source_agent_id"],
            trust_chain_ref=data["trust_chain_ref"],
            constraint_envelope_ref=data.get("constraint_envelope_ref"),
            created_at=created_at,
            verified_by=list(data.get("verified_by", [])),
            confidence_score=data.get("confidence_score", 0.8),
            metadata=dict(data.get("metadata", {})),
        )
