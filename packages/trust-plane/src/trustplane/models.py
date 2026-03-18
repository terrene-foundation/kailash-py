# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Data models for TrustPlane.

Domain models wrapping EATP primitives:
- ConstraintEnvelope: Structured constraints across all 5 EATP dimensions
- DecisionRecord: A decision with full reasoning trace
- MilestoneRecord: A versioned checkpoint
- ReviewRequirement: QUICK/STANDARD/FULL human review levels
- ProjectManifest: Persistent project state
"""

import hashlib
import json
import logging
import math
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "OperationalConstraints",
    "DataAccessConstraints",
    "FinancialConstraints",
    "TemporalConstraints",
    "CommunicationConstraints",
    "ConstraintEnvelope",
    "ReviewRequirement",
    "DecisionType",
    "HumanCompetency",
    "VerificationCategory",
    "ExecutionRecord",
    "EscalationRecord",
    "InterventionRecord",
    "DecisionRecord",
    "MilestoneRecord",
    "ProjectManifest",
]


@dataclass(frozen=True)
class OperationalConstraints:
    """EATP OPERATIONAL dimension — what the AI can do."""

    allowed_actions: list[str] = field(default_factory=list)
    blocked_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_actions": self.allowed_actions,
            "blocked_actions": self.blocked_actions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OperationalConstraints":
        # Note: required_outputs is silently ignored if present in stored data
        # (removed in v0.9.0 — not in EATP spec; constraint model bounds what
        # agents MAY do, not what they MUST produce).
        return cls(
            allowed_actions=data.get("allowed_actions", []),
            blocked_actions=data.get("blocked_actions", []),
        )


@dataclass(frozen=True)
class DataAccessConstraints:
    """EATP DATA_ACCESS dimension — what data the AI can see and modify."""

    read_paths: list[str] = field(default_factory=list)
    write_paths: list[str] = field(default_factory=list)
    blocked_paths: list[str] = field(default_factory=list)
    blocked_patterns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        from trustplane.pathutils import normalize_resource_path

        # frozen=True requires object.__setattr__ in __post_init__
        object.__setattr__(
            self,
            "read_paths",
            [normalize_resource_path(p) for p in self.read_paths],
        )
        object.__setattr__(
            self,
            "write_paths",
            [normalize_resource_path(p) for p in self.write_paths],
        )
        object.__setattr__(
            self,
            "blocked_paths",
            [normalize_resource_path(p) for p in self.blocked_paths],
        )
        object.__setattr__(
            self,
            "blocked_patterns",
            [normalize_resource_path(p) for p in self.blocked_patterns],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "read_paths": self.read_paths,
            "write_paths": self.write_paths,
            "blocked_paths": self.blocked_paths,
            "blocked_patterns": self.blocked_patterns,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DataAccessConstraints":
        return cls(
            read_paths=data.get("read_paths", []),
            write_paths=data.get("write_paths", []),
            blocked_paths=data.get("blocked_paths", []),
            blocked_patterns=data.get("blocked_patterns", []),
        )


@dataclass(frozen=True)
class FinancialConstraints:
    """EATP FINANCIAL dimension — cost boundaries."""

    max_cost_per_session: float | None = None
    max_cost_per_action: float | None = None
    budget_tracking: bool = False

    def __post_init__(self) -> None:
        if self.max_cost_per_session is not None:
            if not math.isfinite(self.max_cost_per_session):
                raise ValueError("max_cost_per_session must be a finite number")
            if self.max_cost_per_session < 0:
                raise ValueError("max_cost_per_session must be non-negative")
        if self.max_cost_per_action is not None:
            if not math.isfinite(self.max_cost_per_action):
                raise ValueError("max_cost_per_action must be a finite number")
            if self.max_cost_per_action < 0:
                raise ValueError("max_cost_per_action must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_cost_per_session": self.max_cost_per_session,
            "max_cost_per_action": self.max_cost_per_action,
            "budget_tracking": self.budget_tracking,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FinancialConstraints":
        return cls(
            max_cost_per_session=data.get("max_cost_per_session"),
            max_cost_per_action=data.get("max_cost_per_action"),
            budget_tracking=data.get("budget_tracking", False),
        )


@dataclass(frozen=True)
class TemporalConstraints:
    """EATP TEMPORAL dimension — time boundaries."""

    max_session_hours: float | None = None
    allowed_hours: tuple[int, int] | None = None
    cooldown_minutes: int = 0

    def __post_init__(self) -> None:
        if self.max_session_hours is not None:
            if not math.isfinite(self.max_session_hours):
                raise ValueError("max_session_hours must be a finite number")
            if self.max_session_hours < 0:
                raise ValueError("max_session_hours must be non-negative")
        if self.cooldown_minutes < 0:
            raise ValueError("cooldown_minutes must be non-negative")
        if self.allowed_hours is not None:
            start, end = self.allowed_hours
            if not (0 <= start <= 23 and 0 <= end <= 23):
                raise ValueError("allowed_hours values must be 0-23")
            if start >= end:
                raise ValueError(
                    "allowed_hours start must be less than end "
                    "(wrap-around windows not supported)"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_session_hours": self.max_session_hours,
            "allowed_hours": list(self.allowed_hours) if self.allowed_hours else None,
            "cooldown_minutes": self.cooldown_minutes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TemporalConstraints":
        ah = data.get("allowed_hours")
        return cls(
            max_session_hours=data.get("max_session_hours"),
            allowed_hours=(ah[0], ah[1]) if ah and len(ah) >= 2 else None,
            cooldown_minutes=data.get("cooldown_minutes", 0),
        )


@dataclass(frozen=True)
class CommunicationConstraints:
    """EATP COMMUNICATION dimension — external communication boundaries."""

    allowed_channels: list[str] = field(default_factory=list)
    blocked_channels: list[str] = field(default_factory=list)
    requires_review: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_channels": self.allowed_channels,
            "blocked_channels": self.blocked_channels,
            "requires_review": self.requires_review,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CommunicationConstraints":
        return cls(
            allowed_channels=data.get("allowed_channels", []),
            blocked_channels=data.get("blocked_channels", []),
            requires_review=data.get("requires_review", []),
        )


@dataclass
class ConstraintEnvelope:
    """Structured constraints across all 5 EATP dimensions.

    Maps directly to EATP ConstraintType enum values:
    - OPERATIONAL → what the AI can do
    - DATA_ACCESS → what data it can see/modify
    - FINANCIAL → cost boundaries
    - TEMPORAL → time boundaries
    - COMMUNICATION → external communication boundaries

    Constraint envelopes are monotonically tightening — once signed,
    they can only be made more restrictive. Loosening requires a new
    Genesis Record (new project).
    """

    operational: OperationalConstraints = field(default_factory=OperationalConstraints)
    data_access: DataAccessConstraints = field(default_factory=DataAccessConstraints)
    financial: FinancialConstraints = field(default_factory=FinancialConstraints)
    temporal: TemporalConstraints = field(default_factory=TemporalConstraints)
    communication: CommunicationConstraints = field(
        default_factory=CommunicationConstraints
    )
    signed_by: str = ""
    signed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "operational": self.operational.to_dict(),
            "data_access": self.data_access.to_dict(),
            "financial": self.financial.to_dict(),
            "temporal": self.temporal.to_dict(),
            "communication": self.communication.to_dict(),
            "signed_by": self.signed_by,
            "signed_at": self.signed_at.isoformat(),
            "envelope_hash": self.envelope_hash(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConstraintEnvelope":
        return cls(
            operational=OperationalConstraints.from_dict(data.get("operational", {})),
            data_access=DataAccessConstraints.from_dict(data.get("data_access", {})),
            financial=FinancialConstraints.from_dict(data.get("financial", {})),
            temporal=TemporalConstraints.from_dict(data.get("temporal", {})),
            communication=CommunicationConstraints.from_dict(
                data.get("communication", {})
            ),
            signed_by=data.get("signed_by", ""),
            signed_at=(
                datetime.fromisoformat(data["signed_at"])
                if "signed_at" in data
                else datetime.now(timezone.utc)
            ),
        )

    @classmethod
    def from_legacy(cls, constraints: list[str], author: str) -> "ConstraintEnvelope":
        """Convert legacy list[str] constraints to ConstraintEnvelope."""
        return cls(
            operational=OperationalConstraints(blocked_actions=constraints),
            signed_by=author,
        )

    def envelope_hash(self) -> str:
        """SHA-256 of constraint content for tamper detection."""
        payload = {
            "operational": self.operational.to_dict(),
            "data_access": self.data_access.to_dict(),
            "financial": self.financial.to_dict(),
            "temporal": self.temporal.to_dict(),
            "communication": self.communication.to_dict(),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()

    def is_tighter_than(self, other: "ConstraintEnvelope") -> bool:
        """Check if this envelope is at least as tight as another.

        Returns True if every constraint in this envelope is equal to or
        tighter than the corresponding constraint in other. Used to enforce
        monotonic tightening per EATP spec.

        Tightening means:
        - Blocklists: this must be a superset (more things blocked)
        - Allowlists: this must be a subset (fewer things allowed)
        - Numeric limits: this must be ≤ (lower limits)
        """
        # Blocked actions: this must be superset of other (more blocked = tighter)
        if not set(other.operational.blocked_actions).issubset(
            set(self.operational.blocked_actions)
        ):
            return False
        # Allowed actions: if other restricts, this must be subset (fewer = tighter)
        # Dropping the allowlist entirely (empty) = unrestricted = loosening
        if other.operational.allowed_actions:
            if not self.operational.allowed_actions:
                return False  # Parent restricts, child unrestricted = loosening
            if not set(self.operational.allowed_actions).issubset(
                set(other.operational.allowed_actions)
            ):
                return False
        # Blocked paths: this must be superset
        if not set(other.data_access.blocked_paths).issubset(
            set(self.data_access.blocked_paths)
        ):
            return False
        # Blocked patterns: this must be superset
        if not set(other.data_access.blocked_patterns).issubset(
            set(self.data_access.blocked_patterns)
        ):
            return False
        # Read paths: if other restricts, this must be subset (fewer readable = tighter)
        if other.data_access.read_paths:
            if not self.data_access.read_paths:
                return False  # Parent restricts, child unrestricted = loosening
            if not set(self.data_access.read_paths).issubset(
                set(other.data_access.read_paths)
            ):
                return False
        # Write paths: if other restricts, this must be subset (fewer writable = tighter)
        if other.data_access.write_paths:
            if not self.data_access.write_paths:
                return False  # Parent restricts, child unrestricted = loosening
            if not set(self.data_access.write_paths).issubset(
                set(other.data_access.write_paths)
            ):
                return False
        # Financial: this must be <= other (tighter = lower limit)
        # None = no limit = unrestricted. Removing a limit is loosening.
        if other.financial.max_cost_per_session is not None:
            if self.financial.max_cost_per_session is None:
                return False  # Parent has limit, child unrestricted = loosening
            if (
                self.financial.max_cost_per_session
                > other.financial.max_cost_per_session
            ):
                return False
        if other.financial.max_cost_per_action is not None:
            if self.financial.max_cost_per_action is None:
                return False
            if self.financial.max_cost_per_action > other.financial.max_cost_per_action:
                return False
        # Budget tracking: if parent requires it, child must too
        if other.financial.budget_tracking and not self.financial.budget_tracking:
            return False
        # Temporal: this must be <= other (tighter = shorter)
        if other.temporal.max_session_hours is not None:
            if self.temporal.max_session_hours is None:
                return False  # Parent has limit, child unrestricted = loosening
            if self.temporal.max_session_hours > other.temporal.max_session_hours:
                return False
        # Allowed hours: child window must be within parent window (narrower = tighter)
        if other.temporal.allowed_hours is not None:
            if self.temporal.allowed_hours is None:
                return False  # Parent restricts hours, child unrestricted = loosening
            if (
                self.temporal.allowed_hours[0] < other.temporal.allowed_hours[0]
                or self.temporal.allowed_hours[1] > other.temporal.allowed_hours[1]
            ):
                return False
        # Cooldown: this must be >= other (longer cooldown = tighter)
        if self.temporal.cooldown_minutes < other.temporal.cooldown_minutes:
            return False
        # Blocked channels: this must be superset
        if not set(other.communication.blocked_channels).issubset(
            set(self.communication.blocked_channels)
        ):
            return False
        # Allowed channels: if other restricts, this must be subset
        if other.communication.allowed_channels:
            if not self.communication.allowed_channels:
                return False  # Parent restricts, child unrestricted = loosening
            if not set(self.communication.allowed_channels).issubset(
                set(other.communication.allowed_channels)
            ):
                return False
        # Requires review: this must be superset (more review = tighter)
        if not set(other.communication.requires_review).issubset(
            set(self.communication.requires_review)
        ):
            return False
        return True


class ReviewRequirement(Enum):
    """Required level of human review for a decision.

    QUICK: Agent-to-agent intermediate work. Hashed, not human-reviewed.
    STANDARD: Decision records. Human can inspect, not required to approve each.
    FULL: Milestone outputs. Human must explicitly engage before work proceeds.

    Note: Distinct from EATP's VerificationLevel (QUICK/STANDARD/FULL) which
    controls cryptographic chain verification depth, not human engagement.
    """

    QUICK = "quick"
    STANDARD = "standard"
    FULL = "full"


class DecisionType(Enum):
    """Built-in decision categories.

    These cover research workflows. For other domains, pass any string
    as decision_type — DecisionRecord accepts both DecisionType enum
    values and arbitrary strings.

    Research types:
        ARGUMENT, LITERATURE, STRUCTURE, SCOPE, FRAMING, EVIDENCE, METHODOLOGY

    Generic types:
        DESIGN, POLICY, TECHNICAL, PROCESS, TRADE_OFF, REQUIREMENT
    """

    # Research
    ARGUMENT = "argument"
    LITERATURE = "literature"
    STRUCTURE = "structure"
    SCOPE = "scope"
    FRAMING = "framing"
    EVIDENCE = "evidence"
    METHODOLOGY = "methodology"

    # Generic
    DESIGN = "design"
    POLICY = "policy"
    TECHNICAL = "technical"
    PROCESS = "process"
    TRADE_OFF = "trade_off"
    REQUIREMENT = "requirement"


def _decision_type_value(dt: "DecisionType | str") -> str:
    """Extract the string value from a DecisionType or plain string."""
    if isinstance(dt, DecisionType):
        return dt.value
    return dt


def _parse_decision_type(value: str) -> "DecisionType | str":
    """Parse a string into a DecisionType if it matches, otherwise keep as string."""
    try:
        return DecisionType(value)
    except ValueError:
        return value


class HumanCompetency(Enum):
    """CARE Mirror Thesis — six categories of irreducible human competency.

    These represent capabilities where human judgment currently provides
    value that AI cannot replicate. Per the CARE Core Thesis (Part IV),
    these are "current AI limitations, not principled impossibilities" —
    a snapshot of 2026, not a permanent boundary.

    The pattern of human engagement across these categories reveals
    what AI can and cannot do (the Mirror Thesis).
    """

    ETHICAL_JUDGMENT = "ethical_judgment"
    RELATIONSHIP_CAPITAL = "relationship_capital"
    CONTEXTUAL_WISDOM = "contextual_wisdom"
    CREATIVE_SYNTHESIS = "creative_synthesis"
    EMOTIONAL_INTELLIGENCE = "emotional_intelligence"
    CULTURAL_NAVIGATION = "cultural_navigation"


class VerificationCategory(Enum):
    """CARE Dual Plane — four verification categories for actions.

    Orthogonal to the three Mirror record types. Indicates
    what the Trust Plane did with the action.
    """

    AUTO_APPROVED = "auto_approved"
    FLAGGED = "flagged"
    HELD = "held"
    BLOCKED = "blocked"


@dataclass
class ExecutionRecord:
    """AI acted autonomously within the constraint envelope.

    The simplest Mirror Thesis record — AI handled this without
    human engagement. Captures what the constraint envelope authorized.

    Typical verification level: QUICK.
    """

    action: str
    constraint_reference: str = ""
    verification_category: VerificationCategory = VerificationCategory.AUTO_APPROVED
    envelope_hash: str = ""
    confidence: float = 0.95
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    execution_id: str = ""

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be 0.0-1.0, got {self.confidence}")
        if not self.execution_id:
            nonce = secrets.token_hex(4)
            content = f"exec:{self.action}:{self.timestamp.isoformat()}:{nonce}"
            self.execution_id = (
                f"exec-{hashlib.sha256(content.encode()).hexdigest()[:12]}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_type": "execution",
            "execution_id": self.execution_id,
            "action": self.action,
            "constraint_reference": self.constraint_reference,
            "verification_category": self.verification_category.value,
            "envelope_hash": self.envelope_hash,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionRecord":
        return cls(
            execution_id=data.get("execution_id", ""),
            action=data["action"],
            constraint_reference=data.get("constraint_reference", ""),
            verification_category=VerificationCategory(
                data.get("verification_category", "auto_approved")
            ),
            envelope_hash=data.get("envelope_hash", ""),
            confidence=data.get("confidence", 0.95),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class EscalationRecord:
    """AI reached the boundary of its constraint envelope and needs human input.

    Captures what triggered the escalation, which competency was needed,
    what the AI recommended, and what the human provided.

    Typical verification level: STANDARD.
    """

    trigger: str
    recommendation: str = ""
    human_response: str = ""
    human_authority: str = ""
    competency_categories: list[HumanCompetency] = field(default_factory=list)
    constraint_dimension: str = ""
    verification_category: VerificationCategory = VerificationCategory.HELD
    resolution: str = ""
    envelope_hash: str = ""
    confidence: float = 0.7
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    escalation_id: str = ""

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be 0.0-1.0, got {self.confidence}")
        if not self.escalation_id:
            nonce = secrets.token_hex(4)
            content = f"esc:{self.trigger}:{self.timestamp.isoformat()}:{nonce}"
            self.escalation_id = (
                f"esc-{hashlib.sha256(content.encode()).hexdigest()[:12]}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_type": "escalation",
            "escalation_id": self.escalation_id,
            "trigger": self.trigger,
            "recommendation": self.recommendation,
            "human_response": self.human_response,
            "human_authority": self.human_authority,
            "competency_categories": [c.value for c in self.competency_categories],
            "constraint_dimension": self.constraint_dimension,
            "verification_category": self.verification_category.value,
            "resolution": self.resolution,
            "envelope_hash": self.envelope_hash,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EscalationRecord":
        return cls(
            escalation_id=data.get("escalation_id", ""),
            trigger=data["trigger"],
            recommendation=data.get("recommendation", ""),
            human_response=data.get("human_response", ""),
            human_authority=data.get("human_authority", ""),
            competency_categories=[
                HumanCompetency(c) for c in data.get("competency_categories", [])
            ],
            constraint_dimension=data.get("constraint_dimension", ""),
            verification_category=VerificationCategory(
                data.get("verification_category", "held")
            ),
            resolution=data.get("resolution", ""),
            envelope_hash=data.get("envelope_hash", ""),
            confidence=data.get("confidence", 0.7),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class InterventionRecord:
    """Human CHOSE to engage even though AI didn't escalate.

    The most revealing data for the Mirror Thesis — the human noticed
    something AI missed. Tracks what was observed and which competency
    category was exercised.

    Typical verification level: FULL.
    """

    observation: str
    action_taken: str = ""
    human_authority: str = ""
    competency_categories: list[HumanCompetency] = field(default_factory=list)
    verification_category: VerificationCategory = VerificationCategory.AUTO_APPROVED
    envelope_hash: str = ""
    confidence: float = 0.5
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    intervention_id: str = ""

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be 0.0-1.0, got {self.confidence}")
        if not self.intervention_id:
            nonce = secrets.token_hex(4)
            content = f"int:{self.observation}:{self.timestamp.isoformat()}:{nonce}"
            self.intervention_id = (
                f"int-{hashlib.sha256(content.encode()).hexdigest()[:12]}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_type": "intervention",
            "intervention_id": self.intervention_id,
            "observation": self.observation,
            "action_taken": self.action_taken,
            "human_authority": self.human_authority,
            "competency_categories": [c.value for c in self.competency_categories],
            "verification_category": self.verification_category.value,
            "envelope_hash": self.envelope_hash,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InterventionRecord":
        return cls(
            intervention_id=data.get("intervention_id", ""),
            observation=data["observation"],
            action_taken=data.get("action_taken", ""),
            human_authority=data.get("human_authority", ""),
            competency_categories=[
                HumanCompetency(c) for c in data.get("competency_categories", [])
            ],
            verification_category=VerificationCategory(
                data.get("verification_category", "auto_approved")
            ),
            envelope_hash=data.get("envelope_hash", ""),
            confidence=data.get("confidence", 0.5),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class DecisionRecord:
    """A decision with full reasoning trace.

    This is the unit of human review — not the conversation that produced it.
    Each record captures what was decided, why, what was rejected, and
    what risks remain. It is designed to be inspectable in 30 seconds.

    The decision_type field accepts both DecisionType enum values and
    arbitrary strings, allowing domain-specific types without subclassing:

        # Using built-in types
        DecisionRecord(decision_type=DecisionType.SCOPE, ...)

        # Using custom domain types
        DecisionRecord(decision_type="compliance_ruling", ...)
        DecisionRecord(decision_type="financial_allocation", ...)
    """

    decision_type: DecisionType | str
    decision: str
    rationale: str
    alternatives: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    review_requirement: ReviewRequirement = ReviewRequirement.STANDARD
    confidentiality: str = "public"
    confidence: float = 0.8
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    author: str = "human"
    related_decisions: list[str] = field(default_factory=list)
    decision_id: str = ""
    cost: float = 0.0

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be 0.0-1.0, got {self.confidence}")
        if self.cost < 0 or (self.cost != 0.0 and not math.isfinite(self.cost)):
            raise ValueError(
                f"cost must be a non-negative finite number, got {self.cost}"
            )
        if not self.decision_id:
            self.decision_id = self._generate_id()

    def _generate_id(self) -> str:
        """Generate a unique ID from content with random nonce."""
        dt_val = _decision_type_value(self.decision_type)
        nonce = secrets.token_hex(4)
        content = f"{dt_val}:{self.decision}:{self.timestamp.isoformat()}:{nonce}"
        return f"dec-{hashlib.sha256(content.encode()).hexdigest()[:12]}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "decision_type": _decision_type_value(self.decision_type),
            "decision": self.decision,
            "rationale": self.rationale,
            "alternatives": self.alternatives,
            "evidence": self.evidence,
            "risks": self.risks,
            "verification_grade": self.review_requirement.value,
            "confidentiality": self.confidentiality,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "author": self.author,
            "related_decisions": self.related_decisions,
            "cost": self.cost,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DecisionRecord":
        for field_name in (
            "decision_id",
            "decision_type",
            "decision",
            "rationale",
            "timestamp",
        ):
            if field_name not in data:
                raise ValueError(
                    f"DecisionRecord.from_dict: missing required field '{field_name}'"
                )
        if not isinstance(data["decision_id"], str):
            raise ValueError("DecisionRecord.from_dict: 'decision_id' must be a string")
        confidence = data.get("confidence", 0.8)
        if not isinstance(confidence, (int, float)) or not math.isfinite(confidence):
            raise ValueError(
                "DecisionRecord.from_dict: 'confidence' must be a finite number"
            )
        cost = data.get("cost", 0.0)
        if not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
            raise ValueError(
                "DecisionRecord.from_dict: 'cost' must be a non-negative finite number"
            )
        return cls(
            decision_id=data["decision_id"],
            decision_type=_parse_decision_type(data["decision_type"]),
            decision=data["decision"],
            rationale=data["rationale"],
            alternatives=data.get("alternatives", []),
            evidence=data.get("evidence", []),
            risks=data.get("risks", []),
            review_requirement=ReviewRequirement(
                data.get("verification_grade", "standard")
            ),
            confidentiality=data.get("confidentiality", "public"),
            confidence=confidence,
            timestamp=datetime.fromisoformat(data["timestamp"]),
            author=data.get("author", "human"),
            related_decisions=data.get("related_decisions", []),
            cost=float(cost),
        )

    def content_hash(self) -> str:
        """SHA-256 of the decision content for tamper detection."""
        payload = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class MilestoneRecord:
    """A versioned checkpoint.

    Milestones are FULL-verification events — the human must explicitly
    engage before work proceeds past a milestone.
    """

    version: str
    description: str
    file_path: str = ""
    file_hash: str = ""
    decision_count: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    author: str = "human"
    milestone_id: str = ""

    def __post_init__(self) -> None:
        if not self.milestone_id:
            nonce = secrets.token_hex(4)
            content = f"milestone:{self.version}:{self.timestamp.isoformat()}:{nonce}"
            self.milestone_id = (
                f"ms-{hashlib.sha256(content.encode()).hexdigest()[:12]}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "milestone_id": self.milestone_id,
            "version": self.version,
            "description": self.description,
            "file_path": self.file_path,
            "file_hash": self.file_hash,
            "decision_count": self.decision_count,
            "timestamp": self.timestamp.isoformat(),
            "author": self.author,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MilestoneRecord":
        for field_name in ("milestone_id", "version", "description", "timestamp"):
            if field_name not in data:
                raise ValueError(
                    f"MilestoneRecord.from_dict: missing required field '{field_name}'"
                )
        timestamp_raw = data["timestamp"]
        if not isinstance(timestamp_raw, str):
            raise ValueError(
                f"MilestoneRecord.from_dict: 'timestamp' must be an ISO-8601 string, "
                f"got {type(timestamp_raw).__name__}"
            )
        return cls(
            milestone_id=data["milestone_id"],
            version=data["version"],
            description=data["description"],
            file_path=data.get("file_path", ""),
            file_hash=data.get("file_hash", ""),
            decision_count=data.get("decision_count", 0),
            timestamp=datetime.fromisoformat(timestamp_raw),
            author=data.get("author", "human"),
        )


@dataclass
class ProjectManifest:
    """Persistent project state stored as manifest.json.

    Tracks the project identity, EATP chain references, and aggregate stats.
    """

    project_id: str
    project_name: str
    author: str
    created_at: datetime
    genesis_id: str = ""
    chain_hash: str = ""
    authority_public_key: str = ""
    total_decisions: int = 0
    total_milestones: int = 0
    total_audits: int = 0
    constraints: list[str] = field(default_factory=list)
    constraint_envelope: ConstraintEnvelope | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "author": self.author,
            "created_at": self.created_at.isoformat(),
            "genesis_id": self.genesis_id,
            "chain_hash": self.chain_hash,
            "authority_public_key": self.authority_public_key,
            "total_decisions": self.total_decisions,
            "total_milestones": self.total_milestones,
            "total_audits": self.total_audits,
            "constraints": self.constraints,
            "metadata": self.metadata,
        }
        if self.constraint_envelope is not None:
            result["constraint_envelope"] = self.constraint_envelope.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectManifest":
        envelope = None
        if "constraint_envelope" in data:
            envelope = ConstraintEnvelope.from_dict(data["constraint_envelope"])
        return cls(
            project_id=data["project_id"],
            project_name=data["project_name"],
            author=data["author"],
            created_at=datetime.fromisoformat(data["created_at"]),
            genesis_id=data.get("genesis_id", ""),
            chain_hash=data.get("chain_hash", ""),
            authority_public_key=data.get("authority_public_key", ""),
            total_decisions=data.get("total_decisions", 0),
            total_milestones=data.get("total_milestones", 0),
            total_audits=data.get("total_audits", 0),
            constraints=data.get("constraints", []),
            constraint_envelope=envelope,
            metadata=data.get("metadata", {}),
        )
