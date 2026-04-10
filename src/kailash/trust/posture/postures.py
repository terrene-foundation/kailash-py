# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP Trust Posture state machine and mapping.

Maps trust verification results to EATP trust postures.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class TrustPosture(str, Enum):
    """Trust posture levels matching EATP specification (Decision 007).

    Five graduated trust postures for agent autonomy using canonical EATP names:
    - AUTONOMOUS: Agent operates with full autonomy; remote monitoring (autonomy_level=5)
    - DELEGATING: Agent executes, human monitors in real-time (autonomy_level=4)
    - SUPERVISED: Agent proposes actions, human approves each one (autonomy_level=3)
    - TOOL: Human and agent co-plan; agent executes approved plans (autonomy_level=2)
    - PSEUDO: Agent is interface only; human performs all reasoning (autonomy_level=1)

    Old names (DELEGATED, CONTINUOUS_INSIGHT, SHARED_PLANNING, PSEUDO_AGENT) are
    accepted via ``_missing_()`` for backward compatibility with serialized data.
    """

    AUTONOMOUS = "autonomous"
    DELEGATING = "delegating"
    SUPERVISED = "supervised"
    TOOL = "tool"
    PSEUDO = "pseudo"

    @classmethod
    def _missing_(cls, value: object) -> TrustPosture | None:
        """Accept old enum names/values for backward compatibility.

        Maps pre-Decision-007 names to their canonical equivalents so that
        existing serialized postures deserialize without error.
        """
        if isinstance(value, str):
            lowered = value.lower().strip()
            aliases: dict[str, TrustPosture] = {
                # Old enum values (wire-format strings)
                "delegated": cls.AUTONOMOUS,
                "continuous_insight": cls.DELEGATING,
                "shared_planning": cls.SUPERVISED,
                "pseudo_agent": cls.PSEUDO,
                # CARE spec L1 aliases
                "pseudo": cls.PSEUDO,
                "pseudoagent": cls.PSEUDO,
            }
            # Try exact match first
            if value in aliases:
                return aliases[value]
            # Then lowered
            if lowered in aliases:
                return aliases[lowered]
            # Normalize hyphens/spaces to underscores
            normalized = lowered.replace("-", "_").replace(" ", "_")
            if normalized in aliases:
                return aliases[normalized]
            # Try matching canonical values
            for member in cls:
                if member.value == normalized:
                    return member
        return None

    @property
    def autonomy_level(self) -> int:
        """Return the autonomy level for this posture (5=highest, 1=lowest)."""
        levels = {
            TrustPosture.AUTONOMOUS: 5,
            TrustPosture.DELEGATING: 4,
            TrustPosture.SUPERVISED: 3,
            TrustPosture.TOOL: 2,
            TrustPosture.PSEUDO: 1,
        }
        return levels[self]

    def can_upgrade_to(self, target: TrustPosture) -> bool:
        """Check if this posture can upgrade to target posture."""
        return target.autonomy_level > self.autonomy_level

    def can_downgrade_to(self, target: TrustPosture) -> bool:
        """Check if this posture can downgrade to target posture."""
        return target.autonomy_level < self.autonomy_level

    def __lt__(self, other: object) -> bool:
        """Less than comparison based on autonomy level."""
        if not isinstance(other, TrustPosture):
            return NotImplemented
        return self.autonomy_level < other.autonomy_level

    def __le__(self, other: object) -> bool:
        """Less than or equal comparison based on autonomy level."""
        if not isinstance(other, TrustPosture):
            return NotImplemented
        return self.autonomy_level <= other.autonomy_level

    def __gt__(self, other: object) -> bool:
        """Greater than comparison based on autonomy level."""
        if not isinstance(other, TrustPosture):
            return NotImplemented
        return self.autonomy_level > other.autonomy_level

    def __ge__(self, other: object) -> bool:
        """Greater than or equal comparison based on autonomy level."""
        if not isinstance(other, TrustPosture):
            return NotImplemented
        return self.autonomy_level >= other.autonomy_level


class PostureTransition(str, Enum):
    """Types of posture transitions."""

    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    MAINTAIN = "maintain"
    EMERGENCY_DOWNGRADE = "emergency_downgrade"


@dataclass
class TransitionGuard:
    """Guard that validates posture transitions.

    Guards can approve or reject transitions based on custom logic.
    """

    name: str
    check_fn: Callable[[PostureTransitionRequest], bool]
    applies_to: List[PostureTransition] = field(
        default_factory=lambda: [PostureTransition.UPGRADE]
    )
    reason_on_failure: str = "Guard check failed"

    def check(self, request: PostureTransitionRequest) -> bool:
        """Check if the transition is allowed."""
        if request.transition_type not in self.applies_to:
            return True  # Guard doesn't apply to this transition type
        return self.check_fn(request)


@dataclass
class PostureTransitionRequest:
    """Request to transition an agent's posture."""

    agent_id: str
    from_posture: TrustPosture
    to_posture: TrustPosture
    reason: str = ""
    requester_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def transition_type(self) -> PostureTransition:
        """Determine the type of transition."""
        if self.to_posture.autonomy_level > self.from_posture.autonomy_level:
            return PostureTransition.UPGRADE
        elif self.to_posture.autonomy_level < self.from_posture.autonomy_level:
            return PostureTransition.DOWNGRADE
        else:
            return PostureTransition.MAINTAIN

    @property
    def is_upgrade(self) -> bool:
        """Check if this is an upgrade transition."""
        return self.transition_type == PostureTransition.UPGRADE

    @property
    def is_downgrade(self) -> bool:
        """Check if this is a downgrade transition."""
        return self.transition_type in (
            PostureTransition.DOWNGRADE,
            PostureTransition.EMERGENCY_DOWNGRADE,
        )


@dataclass
class TransitionResult:
    """Result of a posture transition attempt."""

    success: bool
    from_posture: TrustPosture
    to_posture: TrustPosture
    transition_type: PostureTransition
    reason: str = ""
    blocked_by: Optional[str] = None  # Name of guard that blocked
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "success": self.success,
            "from_posture": self.from_posture.value,
            "to_posture": self.to_posture.value,
            "transition_type": self.transition_type.value,
            "reason": self.reason,
            "blocked_by": self.blocked_by,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# PostureEvidence and PostureEvaluationResult dataclasses
# ---------------------------------------------------------------------------

_VALID_DECISIONS = frozenset({"approved", "denied", "deferred"})


@dataclass
class PostureEvidence:
    """Evidence supporting a posture transition evaluation.

    Contains quantitative metrics collected by monitoring systems that
    inform posture transition decisions.

    Attributes:
        observation_count: Number of observed actions/interactions.
        success_rate: Fraction of successful actions (0.0 to 1.0).
        time_at_current_posture_hours: Hours spent at the current posture.
        anomaly_count: Number of anomalies detected during observation.
        source: Identifier of the monitoring system that produced this evidence.
        timestamp: When this evidence was collected.
        metadata: Additional context (region, cluster, etc.).
    """

    observation_count: int
    success_rate: float
    time_at_current_posture_hours: float
    anomaly_count: int
    source: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not math.isfinite(self.success_rate):
            raise ValueError(f"success_rate must be finite, got {self.success_rate}")
        if not (0.0 <= self.success_rate <= 1.0):
            raise ValueError(
                f"success_rate must be in [0.0, 1.0], got {self.success_rate}"
            )
        if not math.isfinite(self.time_at_current_posture_hours):
            raise ValueError(
                f"time_at_current_posture_hours must be finite, "
                f"got {self.time_at_current_posture_hours}"
            )
        if self.time_at_current_posture_hours < 0:
            raise ValueError(
                f"time_at_current_posture_hours must be non-negative, "
                f"got {self.time_at_current_posture_hours}"
            )
        if self.observation_count < 0:
            raise ValueError(
                f"observation_count must be non-negative, got {self.observation_count}"
            )
        if self.anomaly_count < 0:
            raise ValueError(
                f"anomaly_count must be non-negative, got {self.anomaly_count}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "observation_count": self.observation_count,
            "success_rate": self.success_rate,
            "time_at_current_posture_hours": self.time_at_current_posture_hours,
            "anomaly_count": self.anomaly_count,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PostureEvidence:
        """Deserialize from dictionary.

        Args:
            data: Dictionary produced by ``to_dict()``.

        Returns:
            PostureEvidence instance.

        Raises:
            KeyError: If a required key is missing.
            ValueError: If a field value is invalid.
        """
        timestamp_raw = data.get("timestamp")
        if timestamp_raw is None:
            raise KeyError("'timestamp' is required in PostureEvidence data")
        if isinstance(timestamp_raw, str):
            timestamp = datetime.fromisoformat(timestamp_raw)
        elif isinstance(timestamp_raw, datetime):
            timestamp = timestamp_raw
        else:
            raise ValueError(
                f"timestamp must be an ISO-format string or datetime, "
                f"got {type(timestamp_raw).__name__}"
            )

        return cls(
            observation_count=data["observation_count"],
            success_rate=data["success_rate"],
            time_at_current_posture_hours=data["time_at_current_posture_hours"],
            anomaly_count=data["anomaly_count"],
            source=data["source"],
            timestamp=timestamp,
            metadata=data.get("metadata", {}),
        )


@dataclass
class PostureEvaluationResult:
    """Result of a posture evaluation.

    Captures the decision (approved / denied / deferred) together with the
    rationale, an optional suggested posture, and supporting evidence.

    Attributes:
        decision: One of ``"approved"``, ``"denied"``, ``"deferred"``.
        rationale: Human-readable explanation of the decision.
        suggested_posture: Posture the evaluator recommends (may be ``None``).
        evidence_summary: Key metrics that informed the decision.
        evaluator_id: Identifier of the evaluator that produced this result.
        timestamp: When the evaluation was performed.
    """

    decision: str
    rationale: str
    suggested_posture: Optional[TrustPosture] = None
    evidence_summary: Dict[str, Any] = field(default_factory=dict)
    evaluator_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.decision not in _VALID_DECISIONS:
            raise ValueError(
                f"decision must be one of {set(_VALID_DECISIONS)}, "
                f"got {self.decision!r}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "decision": self.decision,
            "rationale": self.rationale,
            "suggested_posture": (
                self.suggested_posture.value
                if self.suggested_posture is not None
                else None
            ),
            "evidence_summary": self.evidence_summary,
            "evaluator_id": self.evaluator_id,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PostureEvaluationResult:
        """Deserialize from dictionary.

        Args:
            data: Dictionary produced by ``to_dict()``.

        Returns:
            PostureEvaluationResult instance.

        Raises:
            KeyError: If a required key is missing.
            ValueError: If a field value is invalid.
        """
        timestamp_raw = data.get("timestamp")
        if timestamp_raw is None:
            raise KeyError("'timestamp' is required in PostureEvaluationResult data")
        if isinstance(timestamp_raw, str):
            timestamp = datetime.fromisoformat(timestamp_raw)
        elif isinstance(timestamp_raw, datetime):
            timestamp = timestamp_raw
        else:
            raise ValueError(
                f"timestamp must be an ISO-format string or datetime, "
                f"got {type(timestamp_raw).__name__}"
            )

        suggested_raw = data.get("suggested_posture")
        suggested_posture: Optional[TrustPosture] = None
        if suggested_raw is not None:
            if isinstance(suggested_raw, TrustPosture):
                suggested_posture = suggested_raw
            else:
                suggested_posture = TrustPosture(suggested_raw)

        return cls(
            decision=data["decision"],
            rationale=data["rationale"],
            suggested_posture=suggested_posture,
            evidence_summary=data.get("evidence_summary", {}),
            evaluator_id=data.get("evaluator_id", ""),
            timestamp=timestamp,
        )


# ---------------------------------------------------------------------------
# PostureStore protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class PostureStore(Protocol):
    """Protocol for posture state persistence.

    Any class implementing these four methods can serve as a backing store
    for ``PostureStateMachine``.  The store is responsible for durable
    persistence of posture state and transition history.

    Implementations MUST raise ``KeyError`` from ``get_posture`` when the
    agent has never been registered.  The state machine interprets a
    ``KeyError`` as "use the default posture".
    """

    def get_posture(self, agent_id: str) -> TrustPosture:
        """Return the current posture for *agent_id*.

        Raises:
            KeyError: If the agent has no stored posture.
        """
        ...

    def set_posture(self, agent_id: str, posture: TrustPosture) -> None:
        """Persist the posture for *agent_id*."""
        ...

    def get_history(self, agent_id: str, limit: int = 100) -> List[TransitionResult]:
        """Return the most recent *limit* transition results for *agent_id*."""
        ...

    def record_transition(self, result: TransitionResult) -> None:
        """Persist a transition result."""
        ...


class PostureStateMachine:
    """State machine for managing agent posture transitions.

    Tracks agent postures and enforces transition guards.

    Example:
        >>> machine = PostureStateMachine()
        >>> machine.set_posture("agent-001", TrustPosture.TOOL)
        >>> result = machine.transition(
        ...     PostureTransitionRequest(
        ...         agent_id="agent-001",
        ...         from_posture=TrustPosture.TOOL,
        ...         to_posture=TrustPosture.AUTONOMOUS,
        ...         reason="Agent has proven reliable",
        ...         requester_id="admin-001"
        ...     )
        ... )
    """

    # Default guards that require approval for upgrades
    DEFAULT_GUARDS: List[TransitionGuard] = []

    def __init__(
        self,
        default_posture: TrustPosture = TrustPosture.TOOL,
        require_upgrade_approval: bool = True,
        store: Optional[PostureStore] = None,
    ):
        """Initialize the posture state machine.

        Args:
            default_posture: Default posture for new agents.  Defaults to
                ``TrustPosture.TOOL`` per CARE spec (RT-17): tool
                agents start at the TOOL posture (autonomy_level=2).
                Callers may pass ``TrustPosture.SUPERVISED`` or any
                other posture to override.
            require_upgrade_approval: Whether to require approval for upgrades
            store: Optional persistent store for posture state.  When
                ``None`` (the default), state is kept in memory.  When
                provided, ``get_posture`` / ``set_posture`` and transition
                recording are delegated to the store.
        """
        self._agent_postures: Dict[str, TrustPosture] = {}
        self._default_posture = default_posture
        self._guards: List[TransitionGuard] = []
        self._transition_history: List[TransitionResult] = []
        self._store: Optional[PostureStore] = store
        # ROUND6-002: Maximum transition history to prevent unbounded memory growth
        self._max_history_size = 10000

        # Add default upgrade approval guard if required
        if require_upgrade_approval:
            self._guards.append(
                TransitionGuard(
                    name="upgrade_approval_required",
                    check_fn=lambda req: req.requester_id is not None,
                    applies_to=[PostureTransition.UPGRADE],
                    reason_on_failure="Upgrade requires requester_id for approval",
                )
            )

    def _record_transition(self, result: TransitionResult) -> None:
        """Record a transition result with bounded history (ROUND6-002).

        Appends the result and trims oldest entries if history exceeds max size.
        When a store is configured, the result is also persisted there.
        """
        if self._store is not None:
            try:
                self._store.record_transition(result)
            except Exception:
                logger.exception(
                    "PostureStore.record_transition failed for agent %s",
                    result.metadata.get("agent_id", "<unknown>"),
                )
        self._transition_history.append(result)
        if len(self._transition_history) > self._max_history_size:
            # Keep most recent entries, discard oldest 10%
            trim_count = self._max_history_size // 10
            self._transition_history = self._transition_history[trim_count:]

    def get_posture(self, agent_id: str) -> TrustPosture:
        """Get the current posture for an agent.

        When a store is configured, the posture is read from the store.
        If the store raises ``KeyError`` (agent not yet registered), the
        default posture is returned.
        """
        if self._store is not None:
            try:
                return self._store.get_posture(agent_id)
            except KeyError:
                return self._default_posture
        return self._agent_postures.get(agent_id, self._default_posture)

    def set_posture(self, agent_id: str, posture: TrustPosture) -> None:
        """Set the posture for an agent directly (bypasses guards).

        When a store is configured, the posture is persisted there as
        well as in the in-memory cache.
        """
        if self._store is not None:
            self._store.set_posture(agent_id, posture)
        self._agent_postures[agent_id] = posture

    def transition(self, request: PostureTransitionRequest) -> TransitionResult:
        """Attempt to transition an agent's posture.

        Args:
            request: The transition request

        Returns:
            TransitionResult indicating success or failure
        """
        # Validate from_posture matches current
        current = self.get_posture(request.agent_id)
        if current != request.from_posture:
            return TransitionResult(
                success=False,
                from_posture=current,
                to_posture=request.to_posture,
                transition_type=request.transition_type,
                reason=f"Current posture ({current.value}) does not match request "
                f"from_posture ({request.from_posture.value})",
                timestamp=request.timestamp,
            )

        # Check all guards
        for guard in self._guards:
            if not guard.check(request):
                blocked_metadata = dict(request.metadata)
                blocked_metadata["agent_id"] = request.agent_id
                result = TransitionResult(
                    success=False,
                    from_posture=request.from_posture,
                    to_posture=request.to_posture,
                    transition_type=request.transition_type,
                    reason=guard.reason_on_failure,
                    blocked_by=guard.name,
                    timestamp=request.timestamp,
                    metadata=blocked_metadata,
                )
                self._record_transition(result)
                return result

        # Transition allowed
        self.set_posture(request.agent_id, request.to_posture)
        metadata = dict(request.metadata)
        metadata["agent_id"] = request.agent_id
        result = TransitionResult(
            success=True,
            from_posture=request.from_posture,
            to_posture=request.to_posture,
            transition_type=request.transition_type,
            reason=request.reason,
            timestamp=request.timestamp,
            metadata=metadata,
        )
        self._record_transition(result)
        return result

    def emergency_downgrade(
        self,
        agent_id: str,
        reason: str = "Emergency downgrade",
        requester_id: Optional[str] = None,
    ) -> TransitionResult:
        """Emergency downgrade an agent to PSEUDO.

        Bypasses all guards for immediate security response.

        Args:
            agent_id: The agent to downgrade
            reason: Reason for the emergency downgrade
            requester_id: Who initiated the downgrade

        Returns:
            TransitionResult
        """
        current = self.get_posture(agent_id)
        self.set_posture(agent_id, TrustPosture.PSEUDO)

        emergency_metadata = {"agent_id": agent_id}
        if requester_id:
            emergency_metadata["requester_id"] = requester_id
        result = TransitionResult(
            success=True,
            from_posture=current,
            to_posture=TrustPosture.PSEUDO,
            transition_type=PostureTransition.EMERGENCY_DOWNGRADE,
            reason=reason,
            metadata=emergency_metadata,
        )
        self._record_transition(result)
        return result

    def get_transition_history(
        self,
        agent_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[TransitionResult]:
        """Get transition history, optionally filtered by agent.

        Args:
            agent_id: Optional agent ID to filter by
            limit: Optional limit on number of results

        Returns:
            List of TransitionResult
        """
        history = self._transition_history
        if agent_id:
            history = [r for r in history if r.metadata.get("agent_id") == agent_id]
        if limit:
            history = history[-limit:]
        return list(history)

    def add_guard(self, guard: TransitionGuard) -> None:
        """Add a custom transition guard."""
        self._guards.append(guard)

    def remove_guard(self, guard_name: str) -> bool:
        """Remove a guard by name.

        Args:
            guard_name: Name of the guard to remove

        Returns:
            True if guard was found and removed
        """
        for i, guard in enumerate(self._guards):
            if guard.name == guard_name:
                self._guards.pop(i)
                return True
        return False

    def list_guards(self) -> List[str]:
        """List all active guard names."""
        return [guard.name for guard in self._guards]


@dataclass
class PostureConstraints:
    """Constraints applied with a trust posture."""

    audit_required: bool = False
    approval_required: bool = False
    log_level: str = "info"  # debug, info, warning, error
    allowed_capabilities: Optional[List[str]] = None
    blocked_capabilities: Optional[List[str]] = None
    max_actions_before_review: Optional[int] = None
    require_human_approval_for: Optional[List[str]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "audit_required": self.audit_required,
            "approval_required": self.approval_required,
            "log_level": self.log_level,
            "allowed_capabilities": self.allowed_capabilities,
            "blocked_capabilities": self.blocked_capabilities,
            "max_actions_before_review": self.max_actions_before_review,
            "require_human_approval_for": self.require_human_approval_for,
            "metadata": self.metadata,
        }


@dataclass
class PostureResult:
    """Result of trust posture determination.

    Contains the posture and associated constraints.
    """

    posture: TrustPosture
    constraints: PostureConstraints = field(default_factory=PostureConstraints)
    reason: str = ""
    verification_details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "posture": self.posture.value,
            "constraints": self.constraints.to_dict(),
            "reason": self.reason,
            "verification_details": self.verification_details,
        }


class TrustPostureMapper:
    """
    Maps trust verification results to EATP trust postures.

    Provides the bridge between verification results and
    the EATP trust posture system.

    Example:
        >>> mapper = TrustPostureMapper()
        >>> posture_result = mapper.map_verification_result(verification)
        >>> print(posture_result.posture)  # TrustPosture.AUTONOMOUS
    """

    def __init__(
        self,
        default_posture: TrustPosture = TrustPosture.SUPERVISED,
        sensitive_capabilities: Optional[List[str]] = None,
        high_risk_tools: Optional[List[str]] = None,
    ):
        """
        Initialize posture mapper.

        Args:
            default_posture: Default posture when no specific mapping applies
            sensitive_capabilities: Capabilities requiring human approval
            high_risk_tools: Tools requiring elevated trust level
        """
        self._default_posture = default_posture
        self._sensitive_capabilities = sensitive_capabilities or [
            "delete",
            "modify_config",
            "execute_code",
            "external_api",
            "financial_transaction",
        ]
        self._high_risk_tools = high_risk_tools or [
            "bash_command",
            "delete_file",
            "write_file",
            "http_post",
            "http_put",
            "http_delete",
        ]

    def map_verification_result(
        self,
        verification_result: Any,
        requested_capability: Optional[str] = None,
        requested_tool: Optional[str] = None,
    ) -> PostureResult:
        """
        Map a VerificationResult to a TrustPosture.

        Args:
            verification_result: Kaizen VerificationResult
            requested_capability: Optional capability being requested
            requested_tool: Optional tool being requested

        Returns:
            PostureResult with posture and constraints
        """
        # Handle None or invalid result
        if verification_result is None:
            return PostureResult(
                posture=TrustPosture.PSEUDO,
                reason="No verification result provided",
            )

        # Check if verification was valid
        is_valid = getattr(verification_result, "valid", False)
        if not is_valid:
            return PostureResult(
                posture=TrustPosture.PSEUDO,
                reason=getattr(verification_result, "reason", "Verification failed"),
                verification_details=self._extract_details(verification_result),
            )

        # Extract constraints from verification result
        constraints_dict = getattr(verification_result, "constraints", {}) or {}

        # Determine posture based on constraints
        audit_required = constraints_dict.get("audit_required", False)
        approval_required = constraints_dict.get("approval_required", False)
        human_in_loop = constraints_dict.get("human_in_loop", False)

        # Check for sensitive capability
        is_sensitive = self._is_sensitive_capability(requested_capability)
        is_high_risk_tool = self._is_high_risk_tool(requested_tool)

        # Determine posture
        if approval_required or human_in_loop:
            posture = TrustPosture.TOOL
            reason = "Human approval required"
        elif is_sensitive or is_high_risk_tool:
            posture = TrustPosture.SUPERVISED
            reason = "Sensitive capability or high-risk tool"
            audit_required = True
        elif audit_required:
            # Use DELEGATING when audit is required but no approval needed
            # and trust level is normal or higher
            trust_level = constraints_dict.get("trust_level", "normal")
            if trust_level in ("normal", "high", "full"):
                posture = TrustPosture.DELEGATING
                reason = "Delegating mode with audit logging"
            else:
                posture = TrustPosture.SUPERVISED
                reason = "Audit logging required"
        else:
            # Check trust level if available
            trust_level = constraints_dict.get("trust_level", "normal")
            if trust_level == "high" or trust_level == "full":
                posture = TrustPosture.AUTONOMOUS
                reason = "High trust level"
            else:
                posture = self._default_posture
                reason = f"Default posture ({self._default_posture.value})"

        # Build constraints
        posture_constraints = PostureConstraints(
            audit_required=audit_required,
            approval_required=approval_required,
            log_level="warning" if is_sensitive else "info",
            require_human_approval_for=(
                self._sensitive_capabilities if is_sensitive else None
            ),
            metadata=constraints_dict,
        )

        return PostureResult(
            posture=posture,
            constraints=posture_constraints,
            reason=reason,
            verification_details=self._extract_details(verification_result),
        )

    def map_to_posture(
        self,
        is_valid: bool,
        trust_level: str = "normal",
        audit_required: bool = False,
        approval_required: bool = False,
        reason: str = "",
    ) -> PostureResult:
        """
        Simplified posture mapping from basic parameters.

        Args:
            is_valid: Whether the action is allowed
            trust_level: Trust level (none, low, normal, high, full)
            audit_required: Whether audit logging is required
            approval_required: Whether human approval is required
            reason: Reason for the posture

        Returns:
            PostureResult with posture and constraints
        """
        if not is_valid:
            return PostureResult(
                posture=TrustPosture.PSEUDO,
                reason=reason or "Access denied",
            )

        if approval_required:
            return PostureResult(
                posture=TrustPosture.TOOL,
                constraints=PostureConstraints(
                    approval_required=True,
                    audit_required=True,
                ),
                reason=reason or "Human approval required",
            )

        if trust_level in ("none", "low"):
            return PostureResult(
                posture=TrustPosture.SUPERVISED,
                constraints=PostureConstraints(
                    audit_required=True,
                ),
                reason=reason or "Low trust level requires supervision",
            )

        if audit_required:
            # Use DELEGATING when audit required but trust is normal or higher
            if trust_level in ("normal", "high", "full"):
                return PostureResult(
                    posture=TrustPosture.DELEGATING,
                    constraints=PostureConstraints(
                        audit_required=True,
                    ),
                    reason=reason or "Delegating mode with audit logging",
                )
            else:
                return PostureResult(
                    posture=TrustPosture.SUPERVISED,
                    constraints=PostureConstraints(
                        audit_required=True,
                    ),
                    reason=reason or "Audit logging required",
                )

        if trust_level in ("high", "full"):
            return PostureResult(
                posture=TrustPosture.AUTONOMOUS,
                reason=reason or "High trust level",
            )

        return PostureResult(
            posture=self._default_posture,
            reason=reason or f"Default posture ({self._default_posture.value})",
        )

    def _is_sensitive_capability(self, capability: Optional[str]) -> bool:
        """Check if capability is sensitive."""
        if not capability:
            return False
        capability_lower = capability.lower()
        return any(
            sensitive in capability_lower for sensitive in self._sensitive_capabilities
        )

    def _is_high_risk_tool(self, tool: Optional[str]) -> bool:
        """Check if tool is high risk."""
        if not tool:
            return False
        tool_lower = tool.lower()
        return any(risk_tool in tool_lower for risk_tool in self._high_risk_tools)

    def _extract_details(self, verification_result: Any) -> Dict[str, Any]:
        """Extract details from verification result."""
        details = {}

        # Extract common fields
        for field_name in ("agent_id", "action", "trust_chain_id", "timestamp"):
            if hasattr(verification_result, field_name):
                details[field_name] = getattr(verification_result, field_name)

        # Extract constraints
        if hasattr(verification_result, "constraints"):
            details["constraints"] = verification_result.constraints

        return details


# Convenience functions
def map_verification_to_posture(
    verification_result: Any,
    capability: Optional[str] = None,
    tool: Optional[str] = None,
) -> PostureResult:
    """
    Convenience function to map verification result to posture.

    Args:
        verification_result: Kaizen VerificationResult
        capability: Optional capability being requested
        tool: Optional tool being requested

    Returns:
        PostureResult
    """
    mapper = TrustPostureMapper()
    return mapper.map_verification_result(verification_result, capability, tool)


def get_posture_for_action(
    is_allowed: bool,
    requires_audit: bool = False,
    requires_approval: bool = False,
) -> TrustPosture:
    """
    Get simple posture for an action.

    Args:
        is_allowed: Whether the action is allowed
        requires_audit: Whether audit logging is required
        requires_approval: Whether human approval is required

    Returns:
        TrustPosture enum value
    """
    if not is_allowed:
        return TrustPosture.PSEUDO
    if requires_approval:
        return TrustPosture.TOOL
    if requires_audit:
        return TrustPosture.DELEGATING
    return TrustPosture.AUTONOMOUS


__all__ = [
    # Core posture enum
    "TrustPosture",
    # Transition types
    "PostureTransition",
    # Dataclasses
    "PostureConstraints",
    "PostureResult",
    "PostureEvidence",
    "PostureEvaluationResult",
    "TransitionGuard",
    "PostureTransitionRequest",
    "TransitionResult",
    # Protocol
    "PostureStore",
    # Mapper
    "TrustPostureMapper",
    # State machine
    "PostureStateMachine",
    # Convenience functions
    "map_verification_to_posture",
    "get_posture_for_action",
]
