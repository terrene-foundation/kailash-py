# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Trust posture mapping for Enterprise-App integration.

Maps Kaizen trust verification results to Enterprise-App trust postures.

See: TODO-204 Enterprise-App Streaming Integration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class TrustPosture(str, Enum):
    """Trust posture levels for Enterprise-App.

    Determines how an agent's actions are handled:
    - FULL_AUTONOMY: Agent can act freely without approval (autonomy_level=5)
    - ASSISTED: Agent acts with AI assistance but minimal oversight (autonomy_level=4)
    - SUPERVISED: Agent actions are logged but not blocked (autonomy_level=3)
    - HUMAN_DECIDES: Each action requires human approval (autonomy_level=2)
    - BLOCKED: Action is denied (autonomy_level=1)
    """

    FULL_AUTONOMY = "full_autonomy"
    ASSISTED = "assisted"
    SUPERVISED = "supervised"
    HUMAN_DECIDES = "human_decides"
    BLOCKED = "blocked"

    @property
    def autonomy_level(self) -> int:
        """Return the autonomy level for this posture (5=highest, 1=lowest)."""
        levels = {
            TrustPosture.FULL_AUTONOMY: 5,
            TrustPosture.ASSISTED: 4,
            TrustPosture.SUPERVISED: 3,
            TrustPosture.HUMAN_DECIDES: 2,
            TrustPosture.BLOCKED: 1,
        }
        return levels[self]

    def can_upgrade_to(self, target: TrustPosture) -> bool:
        """Check if this posture can upgrade to target posture."""
        return target.autonomy_level > self.autonomy_level

    def can_downgrade_to(self, target: TrustPosture) -> bool:
        """Check if this posture can downgrade to target posture."""
        return target.autonomy_level < self.autonomy_level

    def __lt__(self, other: TrustPosture) -> bool:
        """Less than comparison based on autonomy level."""
        if not isinstance(other, TrustPosture):
            return NotImplemented
        return self.autonomy_level < other.autonomy_level

    def __le__(self, other: TrustPosture) -> bool:
        """Less than or equal comparison based on autonomy level."""
        if not isinstance(other, TrustPosture):
            return NotImplemented
        return self.autonomy_level <= other.autonomy_level

    def __gt__(self, other: TrustPosture) -> bool:
        """Greater than comparison based on autonomy level."""
        if not isinstance(other, TrustPosture):
            return NotImplemented
        return self.autonomy_level > other.autonomy_level

    def __ge__(self, other: TrustPosture) -> bool:
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


class PostureStateMachine:
    """State machine for managing agent posture transitions.

    Tracks agent postures and enforces transition guards.

    Example:
        >>> machine = PostureStateMachine()
        >>> machine.set_posture("agent-001", TrustPosture.SUPERVISED)
        >>> result = machine.transition(
        ...     PostureTransitionRequest(
        ...         agent_id="agent-001",
        ...         from_posture=TrustPosture.SUPERVISED,
        ...         to_posture=TrustPosture.FULL_AUTONOMY,
        ...         reason="Agent has proven reliable",
        ...         requester_id="admin-001"
        ...     )
        ... )
    """

    # Default guards that require approval for upgrades
    DEFAULT_GUARDS: List[TransitionGuard] = []

    def __init__(
        self,
        default_posture: TrustPosture = TrustPosture.SUPERVISED,
        require_upgrade_approval: bool = True,
    ):
        """Initialize the posture state machine.

        Args:
            default_posture: Default posture for new agents
            require_upgrade_approval: Whether to require approval for upgrades
        """
        self._agent_postures: Dict[str, TrustPosture] = {}
        self._default_posture = default_posture
        self._guards: List[TransitionGuard] = []
        self._transition_history: List[TransitionResult] = []
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
        """
        self._transition_history.append(result)
        if len(self._transition_history) > self._max_history_size:
            # Keep most recent entries, discard oldest 10%
            trim_count = self._max_history_size // 10
            self._transition_history = self._transition_history[trim_count:]

    def get_posture(self, agent_id: str) -> TrustPosture:
        """Get the current posture for an agent."""
        return self._agent_postures.get(agent_id, self._default_posture)

    def set_posture(self, agent_id: str, posture: TrustPosture) -> None:
        """Set the posture for an agent directly (bypasses guards)."""
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
        self._agent_postures[request.agent_id] = request.to_posture
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
        """Emergency downgrade an agent to BLOCKED.

        Bypasses all guards for immediate security response.

        Args:
            agent_id: The agent to downgrade
            reason: Reason for the emergency downgrade
            requester_id: Who initiated the downgrade

        Returns:
            TransitionResult
        """
        current = self.get_posture(agent_id)
        self._agent_postures[agent_id] = TrustPosture.BLOCKED

        emergency_metadata = {"agent_id": agent_id}
        if requester_id:
            emergency_metadata["requester_id"] = requester_id
        result = TransitionResult(
            success=True,
            from_posture=current,
            to_posture=TrustPosture.BLOCKED,
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
    Maps Kaizen trust verification results to Enterprise-App trust postures.

    Provides the bridge between Kaizen's VerificationResult and
    Enterprise-App's trust posture system.

    Example:
        >>> mapper = TrustPostureMapper()
        >>> posture_result = mapper.map_verification_result(verification)
        >>> print(posture_result.posture)  # TrustPosture.FULL_AUTONOMY
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
                posture=TrustPosture.BLOCKED,
                reason="No verification result provided",
            )

        # Check if verification was valid
        is_valid = getattr(verification_result, "valid", False)
        if not is_valid:
            return PostureResult(
                posture=TrustPosture.BLOCKED,
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
            posture = TrustPosture.HUMAN_DECIDES
            reason = "Human approval required"
        elif is_sensitive or is_high_risk_tool:
            posture = TrustPosture.SUPERVISED
            reason = "Sensitive capability or high-risk tool"
            audit_required = True
        elif audit_required:
            # Use ASSISTED when audit is required but no approval needed
            # and trust level is normal or higher
            trust_level = constraints_dict.get("trust_level", "normal")
            if trust_level in ("normal", "high", "full"):
                posture = TrustPosture.ASSISTED
                reason = "Assisted mode with audit logging"
            else:
                posture = TrustPosture.SUPERVISED
                reason = "Audit logging required"
        else:
            # Check trust level if available
            trust_level = constraints_dict.get("trust_level", "normal")
            if trust_level == "high" or trust_level == "full":
                posture = TrustPosture.FULL_AUTONOMY
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
                posture=TrustPosture.BLOCKED,
                reason=reason or "Access denied",
            )

        if approval_required:
            return PostureResult(
                posture=TrustPosture.HUMAN_DECIDES,
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
            # Use ASSISTED when audit required but trust is normal or higher
            if trust_level in ("normal", "high", "full"):
                return PostureResult(
                    posture=TrustPosture.ASSISTED,
                    constraints=PostureConstraints(
                        audit_required=True,
                    ),
                    reason=reason or "Assisted mode with audit logging",
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
                posture=TrustPosture.FULL_AUTONOMY,
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
        return TrustPosture.BLOCKED
    if requires_approval:
        return TrustPosture.HUMAN_DECIDES
    if requires_audit:
        return TrustPosture.ASSISTED
    return TrustPosture.FULL_AUTONOMY


__all__ = [
    # Core posture enum
    "TrustPosture",
    # Transition types
    "PostureTransition",
    # Dataclasses
    "PostureConstraints",
    "PostureResult",
    "TransitionGuard",
    "PostureTransitionRequest",
    "TransitionResult",
    # Mapper
    "TrustPostureMapper",
    # State machine
    "PostureStateMachine",
    # Convenience functions
    "map_verification_to_posture",
    "get_posture_for_action",
]
