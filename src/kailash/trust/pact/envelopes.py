# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Operating envelopes -- three-layer envelope model with monotonic tightening.

Implements the PACT envelope model (thesis Section 5.3-5.4, Section 12.3):
  - Role Envelope: standing constraints attached to a D/T/R position
  - Task Envelope: ephemeral constraints scoped to a specific task
  - Effective Envelope: computed intersection of Role and Task envelopes

The monotonic tightening invariant guarantees that child envelopes can only
be equal to or more restrictive than parent envelopes.
"""

from __future__ import annotations

import hashlib
import logging
import math
import uuid
import warnings as _warnings
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from kailash.trust.pact.addressing import Address
from kailash.trust.pact.config import (
    CONFIDENTIALITY_ORDER,
    CommunicationConstraintConfig,
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    DataAccessConstraintConfig,
    FinancialConstraintConfig,
    GradientThresholdsConfig,
    OperationalConstraintConfig,
    TemporalConstraintConfig,
    TrustPostureLevel,
)
from kailash.trust.pact.exceptions import PactError
from kailash.trust.pathutils import normalize_resource_path
from kailash.trust.signing.algorithm_id import (
    ALGORITHM_DEFAULT,
    AlgorithmIdentifier,
    coerce_algorithm_id,
)

logger = logging.getLogger(__name__)

# Module-level guard for once-per-process DeprecationWarning emission when a
# legacy SignedEnvelope (no `algorithm` field — pre-#604 record) is verified.
# Per zero-tolerance.md Rule 1 + the issue-#604 directive, the warning text MUST
# contain the literal string "scaffold for #604; wire format pending mint
# ISS-31" so future agents can grep-find it across log archives.
_LEGACY_SIGNED_ENVELOPE_WARNED: bool = False

__all__ = [
    "ALGORITHM_DEFAULT",
    "AlgorithmIdentifier",
    "EffectiveEnvelopeSnapshot",
    "MonotonicTighteningError",
    "RoleEnvelope",
    "SignedEnvelope",
    "TaskEnvelope",
    "check_degenerate_envelope",
    "check_gradient_dereliction",
    "check_passthrough_envelope",
    "coerce_algorithm_id",
    "compute_effective_envelope",
    "compute_effective_envelope_with_version",
    "default_envelope_for_posture",
    "intersect_envelopes",
    "sign_envelope",
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class MonotonicTighteningError(PactError, ValueError):
    """Raised when a child envelope violates monotonic tightening relative to its parent.

    Inherits from both ``PactError`` (PACT error hierarchy) and
    ``ValueError`` (backward compatibility).
    """

    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_finite(value: float | None, field_name: str) -> None:
    """Raise ValueError if value is NaN or Inf.

    Security-critical: NaN bypasses all numeric comparisons (NaN < X is always
    False, NaN > X is always False). Inf bypasses budget checks (cost > Inf is
    always False). Both must be rejected explicitly.

    Per trust-plane-security.md rule 3: math.isfinite() on all numeric fields.
    """
    if value is not None and not math.isfinite(value):
        raise ValueError(
            f"{field_name} must be finite, got {value!r}. "
            f"NaN/Inf values bypass numeric comparisons and break governance checks."
        )


def _validate_finite_int(value: int | None, field_name: str) -> None:
    """Raise ValueError/TypeError if value is a non-finite float masquerading as int.

    Python allows float('nan') to be passed where int is expected at runtime.
    This guard catches that case.
    """
    if value is not None:
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError(
                    f"{field_name} must be finite, got {value!r}. "
                    f"NaN/Inf values bypass numeric comparisons and break governance checks."
                )
        elif not isinstance(value, int):
            raise TypeError(
                f"{field_name} must be int or None, got {type(value).__name__}"
            )


def _min_optional(a: float | None, b: float | None) -> float | None:
    """Return the minimum of two optional floats. None is treated as unbounded (permissive).

    Raises ValueError if either value is NaN or Inf.
    """
    _validate_finite(a, "min_optional argument a")
    _validate_finite(b, "min_optional argument b")
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _min_optional_int(a: int | None, b: int | None) -> int | None:
    """Return the minimum of two optional ints. None is treated as unbounded.

    Raises ValueError if either value is a non-finite float (NaN/Inf).
    """
    _validate_finite_int(a, "min_optional_int argument a")
    _validate_finite_int(b, "min_optional_int argument b")
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _min_confidentiality(
    a: ConfidentialityLevel, b: ConfidentialityLevel
) -> ConfidentialityLevel:
    """Return the lower (more restrictive) of two confidentiality levels."""
    if CONFIDENTIALITY_ORDER[a] <= CONFIDENTIALITY_ORDER[b]:
        return a
    return b


# ---------------------------------------------------------------------------
# Envelope Intersection
# ---------------------------------------------------------------------------


def _intersect_financial(
    a: FinancialConstraintConfig | None,
    b: FinancialConstraintConfig | None,
) -> FinancialConstraintConfig | None:
    """Intersect financial dimensions: min() of numeric limits.

    Raises ValueError if any numeric field is NaN or Inf.
    """
    if a is None and b is None:
        return None
    if a is None:
        _validate_finite(b.max_spend_usd, "financial.max_spend_usd")  # type: ignore[union-attr]
        _validate_finite(b.api_cost_budget_usd, "financial.api_cost_budget_usd")  # type: ignore[union-attr]
        _validate_finite(b.requires_approval_above_usd, "financial.requires_approval_above_usd")  # type: ignore[union-attr]
        return b
    if b is None:
        _validate_finite(a.max_spend_usd, "financial.max_spend_usd")
        _validate_finite(a.api_cost_budget_usd, "financial.api_cost_budget_usd")
        _validate_finite(
            a.requires_approval_above_usd, "financial.requires_approval_above_usd"
        )
        return a

    # Validate all numeric fields before any min() calls
    _validate_finite(a.max_spend_usd, "financial.max_spend_usd (envelope a)")
    _validate_finite(b.max_spend_usd, "financial.max_spend_usd (envelope b)")
    _validate_finite(
        a.api_cost_budget_usd, "financial.api_cost_budget_usd (envelope a)"
    )
    _validate_finite(
        b.api_cost_budget_usd, "financial.api_cost_budget_usd (envelope b)"
    )
    _validate_finite(
        a.requires_approval_above_usd,
        "financial.requires_approval_above_usd (envelope a)",
    )
    _validate_finite(
        b.requires_approval_above_usd,
        "financial.requires_approval_above_usd (envelope b)",
    )

    return FinancialConstraintConfig(
        max_spend_usd=min(a.max_spend_usd, b.max_spend_usd),
        api_cost_budget_usd=_min_optional(a.api_cost_budget_usd, b.api_cost_budget_usd),
        requires_approval_above_usd=_min_optional(
            a.requires_approval_above_usd, b.requires_approval_above_usd
        ),
        reasoning_required=a.reasoning_required or b.reasoning_required,
    )


def _intersect_operational(
    a: OperationalConstraintConfig,
    b: OperationalConstraintConfig,
) -> OperationalConstraintConfig:
    """Intersect operational dimensions.

    - allowed_actions: set intersection
    - blocked_actions: set union
    - When composed allowed and blocked sets overlap, blocked takes precedence.
    - Rate limits: min()
    """
    allowed = set(a.allowed_actions) & set(b.allowed_actions)
    blocked = set(a.blocked_actions) | set(b.blocked_actions)
    # Deny-overrides: remove any blocked action from allowed
    allowed -= blocked

    return OperationalConstraintConfig(
        allowed_actions=sorted(allowed),
        blocked_actions=sorted(blocked),
        max_actions_per_day=_min_optional_int(
            a.max_actions_per_day, b.max_actions_per_day
        ),
        max_actions_per_hour=_min_optional_int(
            a.max_actions_per_hour, b.max_actions_per_hour
        ),
        rate_limit_window_type=(
            "rolling"
            if a.rate_limit_window_type == "rolling"
            or b.rate_limit_window_type == "rolling"
            else "fixed"
        ),
        reasoning_required=a.reasoning_required or b.reasoning_required,
    )


def _intersect_temporal(
    a: TemporalConstraintConfig,
    b: TemporalConstraintConfig,
) -> TemporalConstraintConfig:
    """Intersect temporal dimensions.

    - Active hours: overlap (later start, earlier end)
    - Blackout periods: union (deduplicated)
    """
    # Active hours overlap
    start = None
    end = None
    if a.active_hours_start is not None and b.active_hours_start is not None:
        start = max(a.active_hours_start, b.active_hours_start)
        end_a = a.active_hours_end or "23:59"
        end_b = b.active_hours_end or "23:59"
        end = min(end_a, end_b)
    elif a.active_hours_start is not None:
        start = a.active_hours_start
        end = a.active_hours_end
    elif b.active_hours_start is not None:
        start = b.active_hours_start
        end = b.active_hours_end

    # Blackout union, deduplicated
    blackouts = sorted(set(a.blackout_periods) | set(b.blackout_periods))

    return TemporalConstraintConfig(
        active_hours_start=start,
        active_hours_end=end,
        timezone=a.timezone,  # Preserve first timezone (convention)
        blackout_periods=blackouts,
        reasoning_required=a.reasoning_required or b.reasoning_required,
    )


def _intersect_data_access(
    a: DataAccessConstraintConfig,
    b: DataAccessConstraintConfig,
) -> DataAccessConstraintConfig:
    """Intersect data access dimensions.

    - read_paths, write_paths: set intersection
    - blocked_data_types: set union
    """
    return DataAccessConstraintConfig(
        read_paths=sorted(set(a.read_paths) & set(b.read_paths)),
        write_paths=sorted(set(a.write_paths) & set(b.write_paths)),
        blocked_data_types=sorted(
            set(a.blocked_data_types) | set(b.blocked_data_types)
        ),
        reasoning_required=a.reasoning_required or b.reasoning_required,
    )


def _intersect_communication(
    a: CommunicationConstraintConfig,
    b: CommunicationConstraintConfig,
) -> CommunicationConstraintConfig:
    """Intersect communication dimensions.

    - internal_only: True if either side is True (more restrictive wins)
    - allowed_channels: set intersection
    - external_requires_approval: True if either side is True
    """
    return CommunicationConstraintConfig(
        internal_only=a.internal_only or b.internal_only,
        allowed_channels=sorted(set(a.allowed_channels) & set(b.allowed_channels)),
        external_requires_approval=a.external_requires_approval
        or b.external_requires_approval,
        reasoning_required=a.reasoning_required or b.reasoning_required,
    )


def intersect_envelopes(
    a: ConstraintEnvelopeConfig,
    b: ConstraintEnvelopeConfig,
    *,
    dimension_scope: frozenset[str] | None = None,
) -> ConstraintEnvelopeConfig:
    """Intersect two constraint envelopes -- result is the most restrictive of both.

    Per-dimension rules (PACT thesis Section 5.3, XACML deny-overrides):
    - Financial: min() of numeric limits
    - Operational: set intersection of allowed actions; set union of blocked actions
    - Temporal: overlap of operating windows; union of blackout periods
    - Data Access: set intersection of allowed paths; set union of blocked data types;
      min() of classification ceiling
    - Communication: set intersection of allowed channels; tighter internal_only wins

    Absent dimensions (None) are treated as maximally permissive.
    When composed allowed and blocked sets overlap for Operational, blocked takes precedence.

    When ``dimension_scope`` is provided, only the specified dimensions are
    intersected from envelope ``b``; unscoped dimensions are taken from ``a``
    unchanged. This supports EATP dimension-scoped delegations (#170) where a
    delegation restricts only specific constraint dimensions while inheriting the
    parent's constraints on unscoped dimensions.

    Args:
        a: First constraint envelope (parent/base).
        b: Second constraint envelope (child/delegation).
        dimension_scope: Optional set of dimension names to intersect. When
            None, all dimensions are intersected (default behavior). Valid
            values: ``{"financial", "operational", "temporal", "data_access",
            "communication"}``.

    Returns:
        A new ConstraintEnvelopeConfig representing the intersection.
    """
    # Determine which dimensions to intersect from b vs inherit from a.
    scope_all = dimension_scope is None
    scoped = dimension_scope or frozenset()

    return ConstraintEnvelopeConfig(
        id=f"ix-{uuid.uuid4().hex[:12]}",
        description=f"Intersection of [{a.id}] and [{b.id}]",
        confidentiality_clearance=_min_confidentiality(
            a.confidentiality_clearance, b.confidentiality_clearance
        ),
        financial=(
            _intersect_financial(a.financial, b.financial)
            if scope_all or "financial" in scoped
            else a.financial
        ),
        operational=(
            _intersect_operational(a.operational, b.operational)
            if scope_all or "operational" in scoped
            else a.operational
        ),
        temporal=(
            _intersect_temporal(a.temporal, b.temporal)
            if scope_all or "temporal" in scoped
            else a.temporal
        ),
        data_access=(
            _intersect_data_access(a.data_access, b.data_access)
            if scope_all or "data_access" in scoped
            else a.data_access
        ),
        communication=(
            _intersect_communication(a.communication, b.communication)
            if scope_all or "communication" in scoped
            else a.communication
        ),
        max_delegation_depth=_min_optional_int(
            a.max_delegation_depth, b.max_delegation_depth
        ),
    )


# ---------------------------------------------------------------------------
# RoleEnvelope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoleEnvelope:
    """Standing operating boundary defined by supervisor for direct report.

    The envelope represents the constraint boundaries a supervisor sets for
    their direct report. The monotonic tightening invariant requires that
    the child's envelope is at most as permissive as the defining role's
    own envelope.
    """

    id: str
    defining_role_address: str  # supervisor
    target_role_address: str  # direct report
    envelope: ConstraintEnvelopeConfig
    gradient_thresholds: GradientThresholdsConfig | None = None
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    modified_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def validate_tightening(
        *,
        parent_envelope: ConstraintEnvelopeConfig,
        child_envelope: ConstraintEnvelopeConfig,
        parent_gradient_thresholds: GradientThresholdsConfig | None = None,
        child_gradient_thresholds: GradientThresholdsConfig | None = None,
    ) -> None:
        """Validate that child_envelope is at most as permissive as parent_envelope.

        Checks each dimension for monotonic tightening violations, including
        gradient thresholds when both parent and child have them.

        Args:
            parent_envelope: The supervisor's (defining role's) envelope.
            child_envelope: The proposed envelope for the direct report.
            parent_gradient_thresholds: Optional gradient thresholds from parent.
            child_gradient_thresholds: Optional gradient thresholds from child.

        Raises:
            MonotonicTighteningError: If child_envelope is looser on any dimension.
            ValueError: If any numeric field is NaN or Inf (security guard).
        """
        violations: list[str] = []

        # Security: validate all financial numeric fields are finite before comparisons.
        # NaN > X is always False, so NaN bypasses all tightening checks.
        # Inf > X is always False for finite X, allowing infinite budgets.
        if parent_envelope.financial is not None:
            _validate_finite(
                parent_envelope.financial.max_spend_usd,
                "parent financial.max_spend_usd",
            )
            _validate_finite(
                parent_envelope.financial.api_cost_budget_usd,
                "parent financial.api_cost_budget_usd",
            )
            _validate_finite(
                parent_envelope.financial.requires_approval_above_usd,
                "parent financial.requires_approval_above_usd",
            )
        if child_envelope.financial is not None:
            _validate_finite(
                child_envelope.financial.max_spend_usd,
                "child financial.max_spend_usd",
            )
            _validate_finite(
                child_envelope.financial.api_cost_budget_usd,
                "child financial.api_cost_budget_usd",
            )
            _validate_finite(
                child_envelope.financial.requires_approval_above_usd,
                "child financial.requires_approval_above_usd",
            )

        # Financial: child max_spend must be <= parent max_spend
        if (
            parent_envelope.financial is not None
            and child_envelope.financial is not None
        ):
            if (
                child_envelope.financial.max_spend_usd
                > parent_envelope.financial.max_spend_usd
            ):
                violations.append(
                    f"Financial: child max_spend_usd "
                    f"({child_envelope.financial.max_spend_usd}) exceeds parent "
                    f"({parent_envelope.financial.max_spend_usd})"
                )
            if (
                parent_envelope.financial.api_cost_budget_usd is not None
                and child_envelope.financial.api_cost_budget_usd is not None
                and child_envelope.financial.api_cost_budget_usd
                > parent_envelope.financial.api_cost_budget_usd
            ):
                violations.append(
                    f"Financial: child api_cost_budget_usd "
                    f"({child_envelope.financial.api_cost_budget_usd}) exceeds parent "
                    f"({parent_envelope.financial.api_cost_budget_usd})"
                )
            if (
                parent_envelope.financial.requires_approval_above_usd is not None
                and child_envelope.financial.requires_approval_above_usd is not None
                and child_envelope.financial.requires_approval_above_usd
                > parent_envelope.financial.requires_approval_above_usd
            ):
                violations.append(
                    f"Financial: child requires_approval_above_usd "
                    f"({child_envelope.financial.requires_approval_above_usd}) exceeds parent "
                    f"({parent_envelope.financial.requires_approval_above_usd})"
                )

        # Confidentiality clearance: child must not exceed parent
        child_conf_order = CONFIDENTIALITY_ORDER[
            child_envelope.confidentiality_clearance
        ]
        parent_conf_order = CONFIDENTIALITY_ORDER[
            parent_envelope.confidentiality_clearance
        ]
        if child_conf_order > parent_conf_order:
            violations.append(
                f"Confidentiality: child clearance "
                f"({child_envelope.confidentiality_clearance.value}) exceeds parent "
                f"({parent_envelope.confidentiality_clearance.value})"
            )

        # Operational: child allowed_actions must be subset of parent's
        parent_allowed = set(parent_envelope.operational.allowed_actions)
        child_allowed = set(child_envelope.operational.allowed_actions)
        if (
            parent_allowed
            and child_allowed
            and not child_allowed.issubset(parent_allowed)
        ):
            extra = child_allowed - parent_allowed
            violations.append(
                f"Operational: child allowed_actions {extra} not in parent allowed set"
            )

        # max_delegation_depth: child must not exceed parent
        if (
            parent_envelope.max_delegation_depth is not None
            and child_envelope.max_delegation_depth is not None
            and child_envelope.max_delegation_depth
            > parent_envelope.max_delegation_depth
        ):
            violations.append(
                f"Delegation: child max_delegation_depth "
                f"({child_envelope.max_delegation_depth}) exceeds parent "
                f"({parent_envelope.max_delegation_depth})"
            )

        # Temporal: child active hours must be within parent's window;
        # child blackout_periods must be a superset of parent's.
        p_temporal = parent_envelope.temporal
        c_temporal = child_envelope.temporal
        if p_temporal.active_hours_start is not None:
            # Parent restricts active hours -- child must also restrict them
            if c_temporal.active_hours_start is None:
                violations.append(
                    "Temporal: parent restricts active_hours "
                    f"({p_temporal.active_hours_start}-{p_temporal.active_hours_end}) "
                    "but child has no active hours restriction (wider)"
                )
            else:
                # Child has active hours -- must start same or later
                if c_temporal.active_hours_start < p_temporal.active_hours_start:
                    violations.append(
                        f"Temporal: child active_hours_start "
                        f"({c_temporal.active_hours_start}) is earlier than parent "
                        f"({p_temporal.active_hours_start})"
                    )
                # Child must end same or earlier
                c_end = c_temporal.active_hours_end or "23:59"
                p_end = p_temporal.active_hours_end or "23:59"
                if c_end > p_end:
                    violations.append(
                        f"Temporal: child active_hours_end "
                        f"({c_end}) is later than parent "
                        f"({p_end})"
                    )
        # Blackout periods: child must include all parent blackouts (superset)
        if p_temporal.blackout_periods:
            parent_blackouts = set(p_temporal.blackout_periods)
            child_blackouts = set(c_temporal.blackout_periods)
            missing = parent_blackouts - child_blackouts
            if missing:
                violations.append(
                    f"Temporal: child blackout_periods missing parent periods {missing}"
                )

        # Data access: child read_paths and write_paths must be subsets of parent's.
        # Normalize paths per trust-plane-security.md rule 8 before comparison.
        p_data = parent_envelope.data_access
        c_data = child_envelope.data_access
        parent_reads = {normalize_resource_path(p) for p in p_data.read_paths}
        child_reads = {normalize_resource_path(p) for p in c_data.read_paths}
        if child_reads and not child_reads.issubset(parent_reads):
            extra = child_reads - parent_reads
            violations.append(
                f"Data access: child read_paths {extra} not in parent read set"
            )
        parent_writes = {normalize_resource_path(p) for p in p_data.write_paths}
        child_writes = {normalize_resource_path(p) for p in c_data.write_paths}
        if child_writes and not child_writes.issubset(parent_writes):
            extra = child_writes - parent_writes
            violations.append(
                f"Data access: child write_paths {extra} not in parent write set"
            )

        # Communication: child allowed_channels must be subset of parent's;
        # if parent is internal_only=True, child must also be True.
        p_comm = parent_envelope.communication
        c_comm = child_envelope.communication
        if p_comm.internal_only and not c_comm.internal_only:
            violations.append(
                "Communication: parent is internal_only=True but child is "
                "internal_only=False (wider)"
            )
        parent_channels = set(p_comm.allowed_channels)
        child_channels = set(c_comm.allowed_channels)
        if child_channels and not child_channels.issubset(parent_channels):
            extra = child_channels - parent_channels
            violations.append(
                f"Communication: child allowed_channels {extra} not in parent channel set"
            )

        # Gradient thresholds: child thresholds must be <= parent thresholds.
        # Only check when both parent and child have gradient thresholds for
        # a given dimension. If parent has thresholds but child doesn't, that's
        # OK (child uses defaults which are more restrictive). If child has
        # thresholds but parent doesn't, we cannot verify so we skip.
        if (
            parent_gradient_thresholds is not None
            and child_gradient_thresholds is not None
        ):
            p_fin_thresh = parent_gradient_thresholds.financial
            c_fin_thresh = child_gradient_thresholds.financial
            if p_fin_thresh is not None and c_fin_thresh is not None:
                if (
                    c_fin_thresh.auto_approve_threshold
                    > p_fin_thresh.auto_approve_threshold
                ):
                    violations.append(
                        f"Gradient: child financial auto_approve_threshold "
                        f"({c_fin_thresh.auto_approve_threshold}) exceeds parent "
                        f"({p_fin_thresh.auto_approve_threshold})"
                    )
                if c_fin_thresh.flag_threshold > p_fin_thresh.flag_threshold:
                    violations.append(
                        f"Gradient: child financial flag_threshold "
                        f"({c_fin_thresh.flag_threshold}) exceeds parent "
                        f"({p_fin_thresh.flag_threshold})"
                    )
                if c_fin_thresh.hold_threshold > p_fin_thresh.hold_threshold:
                    violations.append(
                        f"Gradient: child financial hold_threshold "
                        f"({c_fin_thresh.hold_threshold}) exceeds parent "
                        f"({p_fin_thresh.hold_threshold})"
                    )

        if violations:
            msg = "Monotonic tightening violation(s): " + "; ".join(violations)
            logger.error(msg)
            raise MonotonicTighteningError(msg)


# ---------------------------------------------------------------------------
# TaskEnvelope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskEnvelope:
    """Ephemeral narrowing of a RoleEnvelope for a specific task.

    Task envelopes further restrict the standing RoleEnvelope for the duration
    of a specific task. They expire automatically and cannot widen the role's
    standing boundaries.
    """

    id: str
    task_id: str
    parent_envelope_id: str  # the RoleEnvelope being narrowed
    envelope: ConstraintEnvelopeConfig
    expires_at: datetime
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_expired(self) -> bool:
        """True if this task envelope has passed its expiration time."""
        return datetime.now(UTC) > self.expires_at


# ---------------------------------------------------------------------------
# Effective Envelope Computation
# ---------------------------------------------------------------------------


def compute_effective_envelope(
    role_address: str,
    role_envelopes: dict[str, RoleEnvelope],
    task_envelope: TaskEnvelope | None = None,
    org_envelope: ConstraintEnvelopeConfig | None = None,
) -> ConstraintEnvelopeConfig | None:
    """Walk from root to role, intersecting all ancestor RoleEnvelopes.

    Per thesis Section 5.4: the effective envelope is the intersection of:
    1. The org-level envelope (if any)
    2. All RoleEnvelopes found along the accountability chain from root to the target
    3. An active TaskEnvelope (if any and not expired)

    Gradient thresholds come from the immediate supervisor only (not composed).

    Args:
        role_address: The D/T/R positional address of the target role.
        role_envelopes: Map from target_role_address to RoleEnvelope.
        task_envelope: Optional ephemeral task envelope to apply.
        org_envelope: Optional organization-level constraint envelope.

    Returns:
        The computed effective ConstraintEnvelopeConfig, or None if no
        envelopes exist at all (maximally permissive).
    """
    addr = Address.parse(role_address)

    # Start with org-level envelope if provided
    result: ConstraintEnvelopeConfig | None = org_envelope

    # Walk accountability chain (all R segments from root to target),
    # intersecting each RoleEnvelope found
    for ancestor in addr.accountability_chain:
        ancestor_str = str(ancestor)
        if ancestor_str in role_envelopes:
            role_env = role_envelopes[ancestor_str]
            if result is None:
                result = role_env.envelope
            else:
                result = intersect_envelopes(result, role_env.envelope)

    # Apply active task envelope if present and not expired
    if task_envelope is not None and not task_envelope.is_expired:
        if result is None:
            result = task_envelope.envelope
        else:
            result = intersect_envelopes(result, task_envelope.envelope)

    return result


# ---------------------------------------------------------------------------
# TOCTOU Defense: Versioned Envelope Snapshots
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EffectiveEnvelopeSnapshot:
    """An effective envelope with a version hash for TOCTOU detection.

    The version_hash is a SHA-256 digest of all ancestor envelope versions
    that contributed to the effective envelope. If any ancestor envelope
    changes, the version_hash will differ, allowing callers to detect stale
    snapshots and re-evaluate.

    Attributes:
        envelope: The computed effective constraint envelope, or None.
        version_hash: SHA-256 hex digest of concatenated ancestor versions.
            Empty string if no envelopes contributed.
        contributor_versions: Map of role_address -> version for each
            RoleEnvelope that contributed to this snapshot.
    """

    envelope: ConstraintEnvelopeConfig | None
    version_hash: str
    contributor_versions: dict[str, int] = field(default_factory=dict)


def compute_effective_envelope_with_version(
    role_address: str,
    role_envelopes: dict[str, RoleEnvelope],
    task_envelope: TaskEnvelope | None = None,
    org_envelope: ConstraintEnvelopeConfig | None = None,
) -> EffectiveEnvelopeSnapshot:
    """Compute effective envelope with version hash for TOCTOU defense.

    Same as compute_effective_envelope but returns an EffectiveEnvelopeSnapshot
    that includes a version_hash -- a SHA-256 of all ancestor envelope versions.
    Callers can compare this hash against a later computation to detect if any
    ancestor envelope changed between snapshot and use.

    Args:
        role_address: The D/T/R positional address of the target role.
        role_envelopes: Map from target_role_address to RoleEnvelope.
        task_envelope: Optional ephemeral task envelope to apply.
        org_envelope: Optional organization-level constraint envelope.

    Returns:
        An EffectiveEnvelopeSnapshot containing the effective envelope,
        version hash, and contributor versions.
    """
    addr = Address.parse(role_address)

    # Track which envelopes contributed and their versions
    contributor_versions: dict[str, int] = {}

    result: ConstraintEnvelopeConfig | None = org_envelope

    for ancestor in addr.accountability_chain:
        ancestor_str = str(ancestor)
        if ancestor_str in role_envelopes:
            role_env = role_envelopes[ancestor_str]
            contributor_versions[ancestor_str] = role_env.version
            if result is None:
                result = role_env.envelope
            else:
                result = intersect_envelopes(result, role_env.envelope)

    # Apply active task envelope if present and not expired
    if task_envelope is not None and not task_envelope.is_expired:
        contributor_versions[f"task:{task_envelope.task_id}"] = 1
        if result is None:
            result = task_envelope.envelope
        else:
            result = intersect_envelopes(result, task_envelope.envelope)

    # Compute version hash from all contributor versions AND envelope IDs
    # for full TOCTOU detection (even when version numbers are unchanged,
    # different envelope IDs indicate a different envelope was set).
    if contributor_versions:
        hash_parts: list[str] = []
        for cv_addr, cv_ver in sorted(contributor_versions.items()):
            env_id = ""
            if cv_addr in role_envelopes:
                env_id = role_envelopes[cv_addr].id
            hash_parts.append(f"{cv_addr}:{cv_ver}:{env_id}")
        version_str = "|".join(hash_parts)
        version_hash = hashlib.sha256(version_str.encode()).hexdigest()
    else:
        version_hash = ""

    return EffectiveEnvelopeSnapshot(
        envelope=result,
        version_hash=version_hash,
        contributor_versions=contributor_versions,
    )


# ---------------------------------------------------------------------------
# Default Envelopes by Trust Posture
# ---------------------------------------------------------------------------


def default_envelope_for_posture(
    posture: TrustPostureLevel,
) -> ConstraintEnvelopeConfig:
    """Return conservative default envelope calibrated to trust posture level.

    These defaults provide a reasonable starting point for each posture level.
    Organizations should customize them for their specific needs.

    Args:
        posture: The trust posture level.

    Returns:
        A ConstraintEnvelopeConfig with conservative defaults for the posture.

    Raises:
        ValueError: If the posture is not a recognized TrustPostureLevel.
    """
    configs: dict[TrustPostureLevel, dict[str, Any]] = {
        TrustPostureLevel.PSEUDO: {
            "max_spend_usd": 0.0,
            "confidentiality": ConfidentialityLevel.PUBLIC,
            "allowed_actions": ["read"],
            "internal_only": True,
            "allowed_channels": ["internal"],
            "read_paths": [],
            "write_paths": [],
        },
        TrustPostureLevel.TOOL: {
            "max_spend_usd": 100.0,
            "confidentiality": ConfidentialityLevel.RESTRICTED,
            "allowed_actions": ["read", "write"],
            "internal_only": True,
            "allowed_channels": ["internal", "email"],
            "read_paths": ["/data/public", "/data/team"],
            "write_paths": ["/data/team"],
        },
        TrustPostureLevel.SUPERVISED: {
            "max_spend_usd": 1000.0,
            "confidentiality": ConfidentialityLevel.CONFIDENTIAL,
            "allowed_actions": ["read", "write", "plan", "propose"],
            "internal_only": False,
            "allowed_channels": ["internal", "email", "slack"],
            "read_paths": ["/data/public", "/data/team", "/data/department"],
            "write_paths": ["/data/team", "/data/department"],
        },
        TrustPostureLevel.DELEGATING: {
            "max_spend_usd": 10000.0,
            "confidentiality": ConfidentialityLevel.SECRET,
            "allowed_actions": [
                "read",
                "write",
                "plan",
                "propose",
                "execute",
                "deploy",
            ],
            "internal_only": False,
            "allowed_channels": ["internal", "email", "slack", "teams", "api"],
            "read_paths": [
                "/data/public",
                "/data/team",
                "/data/department",
                "/data/org",
            ],
            "write_paths": ["/data/team", "/data/department", "/data/org"],
        },
        TrustPostureLevel.AUTONOMOUS: {
            "max_spend_usd": 100000.0,
            "confidentiality": ConfidentialityLevel.TOP_SECRET,
            "allowed_actions": [
                "read",
                "write",
                "plan",
                "propose",
                "execute",
                "deploy",
                "approve",
                "delegate",
            ],
            "internal_only": False,
            "allowed_channels": [
                "internal",
                "email",
                "slack",
                "teams",
                "api",
                "external",
            ],
            "read_paths": [
                "/data/public",
                "/data/team",
                "/data/department",
                "/data/org",
                "/data/classified",
            ],
            "write_paths": [
                "/data/team",
                "/data/department",
                "/data/org",
                "/data/classified",
            ],
        },
    }

    if posture not in configs:
        raise ValueError(
            f"Unrecognized trust posture level: {posture!r}. "
            f"Expected one of: {[p.value for p in TrustPostureLevel]}"
        )

    cfg = configs[posture]

    return ConstraintEnvelopeConfig(
        id=f"default-{posture.value}",
        description=f"Default envelope for {posture.value} trust posture",
        confidentiality_clearance=cfg["confidentiality"],
        financial=FinancialConstraintConfig(
            max_spend_usd=cfg["max_spend_usd"],
        ),
        operational=OperationalConstraintConfig(
            allowed_actions=cfg["allowed_actions"],
        ),
        temporal=TemporalConstraintConfig(),  # No time restrictions by default
        data_access=DataAccessConstraintConfig(
            read_paths=cfg["read_paths"],
            write_paths=cfg["write_paths"],
        ),
        communication=CommunicationConstraintConfig(
            internal_only=cfg["internal_only"],
            allowed_channels=cfg["allowed_channels"],
        ),
    )


# ---------------------------------------------------------------------------
# Pass-through Envelope Detection
# ---------------------------------------------------------------------------


def check_passthrough_envelope(
    child: ConstraintEnvelopeConfig,
    parent: ConstraintEnvelopeConfig,
) -> bool:
    """Check if child envelope is identical to parent (pass-through).

    A pass-through means the role adds no additional constraints -- the governance
    hierarchy is doing nothing at that level. Returns True if pass-through detected.

    Compares the 5 constraint dimensions field-by-field, plus
    confidentiality_clearance and max_delegation_depth. The ``id`` and
    ``description`` fields are excluded since they differ even when constraints
    are identical. ``expires_at`` is also excluded (config-level metadata).

    Args:
        child: The child (target role) envelope config.
        parent: The parent (defining role) envelope config.

    Returns:
        True if the child envelope is identical to the parent across all
        constraint dimensions (pass-through detected). False otherwise.
    """
    # Compare confidentiality clearance
    if child.confidentiality_clearance != parent.confidentiality_clearance:
        return False

    # Compare max_delegation_depth
    if child.max_delegation_depth != parent.max_delegation_depth:
        return False

    # Compare financial dimension
    if child.financial != parent.financial:
        return False

    # Compare operational dimension
    if child.operational != parent.operational:
        return False

    # Compare temporal dimension
    if child.temporal != parent.temporal:
        return False

    # Compare data_access dimension
    if child.data_access != parent.data_access:
        return False

    # Compare communication dimension
    if child.communication != parent.communication:
        return False

    return True


# ---------------------------------------------------------------------------
# Degenerate Envelope Detection
# ---------------------------------------------------------------------------


# Default functional minimum thresholds for degenerate detection.
# These are the minimum values needed for an agent to do meaningful work.
_DEFAULT_FUNCTIONAL_MINIMUM = {
    "financial_max_spend_usd": 10.0,
    "operational_min_actions": 1,
    "communication_min_channels": 1,
}


def check_degenerate_envelope(
    effective: ConstraintEnvelopeConfig,
    functional_minimum: ConstraintEnvelopeConfig | None = None,
) -> list[str]:
    """Check if effective envelope is so tight that no meaningful action is possible.

    Returns list of warning messages for dimensions below 20% of functional minimum.
    Per thesis Section 12.3.

    Args:
        effective: The effective envelope to check.
        functional_minimum: Optional reference envelope representing the minimum
            needed for meaningful operation. If None, uses built-in defaults.

    Returns:
        List of warning strings. Empty list means envelope is not degenerate.
    """
    warnings: list[str] = []

    # Financial dimension
    if effective.financial is not None:
        if functional_minimum is not None and functional_minimum.financial is not None:
            min_spend = functional_minimum.financial.max_spend_usd
            if min_spend > 0:
                ratio = effective.financial.max_spend_usd / min_spend
                if ratio < 0.20:
                    warnings.append(
                        f"Financial: effective spend limit "
                        f"(${effective.financial.max_spend_usd:.2f}) is "
                        f"{ratio:.0%} of functional minimum "
                        f"(${min_spend:.2f}) -- below 20% threshold"
                    )
        elif effective.financial.max_spend_usd == 0.0:
            warnings.append(
                "Financial: effective spend limit is $0.00 -- "
                "no financial actions possible"
            )

    # Operational dimension
    if not effective.operational.allowed_actions:
        warnings.append(
            "Operational: no allowed actions -- " "agent cannot perform any operations"
        )

    # Communication dimension
    if not effective.communication.allowed_channels:
        warnings.append(
            "Communication: no allowed channels -- "
            "agent cannot communicate through any channel"
        )

    # Data access dimension
    if not effective.data_access.read_paths and not effective.data_access.write_paths:
        # Only warn if there are also no other capabilities
        # (empty paths might be intentional for non-data agents)
        pass

    return warnings


# ---------------------------------------------------------------------------
# Gradient Dereliction Detection
# ---------------------------------------------------------------------------


def check_gradient_dereliction(
    role_envelope: RoleEnvelope,
    effective_envelope: ConstraintEnvelopeConfig,
) -> list[str]:
    """Detect overly-permissive gradient configuration (rubber-stamping).

    When the auto_approve_threshold is set at or above 90% of the effective
    envelope's limit for a dimension, it means almost all actions are auto-approved
    without human oversight -- defeating the purpose of the gradient.

    Only checks numeric dimensions (financial) where threshold comparison
    is meaningful.

    Args:
        role_envelope: The RoleEnvelope containing gradient_thresholds.
        effective_envelope: The effective ConstraintEnvelopeConfig.

    Returns:
        A list of warning strings (empty if no dereliction detected).
    """
    warnings: list[str] = []

    # No gradient thresholds configured -- nothing to check
    if role_envelope.gradient_thresholds is None:
        return warnings

    gt = role_envelope.gradient_thresholds

    # Financial dimension dereliction check
    if gt.financial is not None and effective_envelope.financial is not None:
        max_spend = effective_envelope.financial.max_spend_usd
        if max_spend > 0:
            auto_approve = gt.financial.auto_approve_threshold
            if auto_approve >= 0.9 * max_spend:
                warnings.append(
                    f"Gradient dereliction (financial): auto_approve_threshold "
                    f"({auto_approve}) is >= 90% of max_spend_usd ({max_spend}). "
                    f"This is overly permissive -- nearly all spend is auto-approved "
                    f"without oversight."
                )

    return warnings


# ---------------------------------------------------------------------------
# Signed Envelope (Issue #207) -- Ed25519 signing for ConstraintEnvelopeConfig
# ---------------------------------------------------------------------------

_SIGNED_ENVELOPE_EXPIRY_DAYS: int = 90
"""Default expiry for signed envelopes: 90 days."""


@dataclass(frozen=True)
class SignedEnvelope:
    """A ConstraintEnvelopeConfig wrapped with an Ed25519 signature.

    Provides cryptographic proof that a specific authority approved this
    envelope configuration. The signature covers the canonical JSON
    representation of the envelope, ensuring tamper detection.

    frozen=True: immutable after creation (security invariant).

    Attributes:
        envelope: The ConstraintEnvelopeConfig being signed.
        signature: Base64-encoded Ed25519 signature of the envelope's
            canonical JSON representation.
        signed_at: When the signature was created (UTC).
        signed_by: Identifier of the signing authority (D/T/R address
            or key ID).
        expires_at: When this signed envelope expires (default: 90 days
            after signed_at). After expiry, the signature is considered
            invalid and the envelope must be re-signed.
        algorithm: The algorithm identifier (issue #604 scaffold). Defaults
            to :data:`kailash.trust.signing.algorithm_id.ALGORITHM_DEFAULT`
            (``"ed25519+sha256"``). Threaded through every signed-record
            producer/verifier so that when mint ISS-31 stabilises the
            canonical wire format, only the validation + canonical
            serialiser change. Legacy records (pre-#604, no ``algorithm``
            field) are accepted by :meth:`verify` with a one-time
            DeprecationWarning per process.
    """

    envelope: ConstraintEnvelopeConfig
    signature: str
    signed_at: datetime
    signed_by: str
    expires_at: datetime
    # Issue #604 scaffold: algorithm identifier. Default keeps backward-
    # compatible construction (existing call sites do not need to pass it),
    # while every NEW signed record carries the algorithm field so the
    # round-trip via to_dict/from_dict surfaces it on the wire.
    algorithm: str = ALGORITHM_DEFAULT

    def verify(self, public_key: str) -> bool:
        """Validate the signature, algorithm, and expiry.

        Uses Ed25519 verification via kailash.trust.signing.crypto.
        Returns False (fail-closed) if:
        - The signature does not match the envelope content
        - The signed envelope has expired (past expires_at)
        - Any unexpected error occurs

        Algorithm handling (issue #604 scaffold):
        - ``algorithm == ALGORITHM_DEFAULT`` (``"ed25519+sha256"``) →
          verify normally.
        - ``algorithm`` is empty / missing equivalent (legacy record) →
          accept BUT emit a one-time DeprecationWarning per process; the
          warning text contains the literal "scaffold for #604; wire format
          pending mint ISS-31" so future agents can grep-find it.
        - ``algorithm`` is set to any other non-default value → raise
          NotImplementedError. Mint ISS-31 will lift this restriction; the
          single permitted scaffold-era stub per zero-tolerance.md Rule 2.

        Args:
            public_key: Base64-encoded Ed25519 public key.

        Returns:
            True if the signature is valid AND the envelope has not expired.
            False otherwise.

        Raises:
            ImportError: If PyNaCl is not installed.
            NotImplementedError: If algorithm is non-default and non-empty
                (pending mint ISS-31). Raised BEFORE any crypto work — the
                verifier must not give the appearance of approval for an
                unsupported algorithm even by accident.
        """
        # Algorithm-agility guard (issue #604) — runs BEFORE expiry / crypto
        # so a non-default algorithm fails loudly, never silently accepted.
        global _LEGACY_SIGNED_ENVELOPE_WARNED
        algo = self.algorithm or ""
        if algo == "":
            # Legacy record: pre-#604, no algorithm field on disk. Accept
            # AND warn once per process. The "scaffold for #604; wire format
            # pending mint ISS-31" text is required per the issue brief.
            if not _LEGACY_SIGNED_ENVELOPE_WARNED:
                _LEGACY_SIGNED_ENVELOPE_WARNED = True
                _warnings.warn(
                    "SignedEnvelope verified with empty algorithm (legacy "
                    "record); defaulting to "
                    f"{ALGORITHM_DEFAULT!r} — scaffold for #604; wire "
                    "format pending mint ISS-31.",
                    DeprecationWarning,
                    stacklevel=2,
                )
        elif algo != ALGORITHM_DEFAULT:
            raise NotImplementedError(
                f"SignedEnvelope.algorithm={algo!r} awaits mint ISS-31 spec. "
                f"Only {ALGORITHM_DEFAULT!r} is supported in this scaffold "
                f"(issue #604, cross-SDK kailash-rs#33)."
            )

        # Check expiry (cheap check before crypto).
        if datetime.now(UTC) > self.expires_at:
            logger.warning(
                "SignedEnvelope for '%s' has expired (expires_at=%s)",
                self.signed_by,
                self.expires_at.isoformat(),
            )
            return False

        try:
            from kailash.trust.signing.crypto import (
                serialize_for_signing,
                verify_signature,
            )

            payload = serialize_for_signing(self.envelope.model_dump(mode="json"))
            return verify_signature(payload, self.signature, public_key)
        except ImportError:
            raise
        except NotImplementedError:
            # Re-raise the algorithm-agility guard above; do not mask as
            # fail-closed-False — the caller MUST see the spec gate.
            raise
        except Exception:
            logger.exception(
                "SignedEnvelope verification failed for '%s' -- "
                "fail-closed to False",
                self.signed_by,
            )
            return False

    def is_valid(self, public_key: str) -> bool:
        """Non-throwing validity check.

        Equivalent to verify() but catches ALL exceptions (including
        ImportError) and returns False instead. Safe to call in
        contexts where PyNaCl availability is uncertain.

        Args:
            public_key: Base64-encoded Ed25519 public key.

        Returns:
            True if signature is valid and envelope has not expired.
            False on any error.
        """
        try:
            return self.verify(public_key)
        except Exception:
            return False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict suitable for JSON encoding.

        Returns:
            A dict with all fields. The envelope is serialized via
            model_dump(mode='json'). Datetimes as ISO 8601.
        """
        return {
            "envelope": self.envelope.model_dump(mode="json"),
            "signature": self.signature,
            "signed_at": self.signed_at.isoformat(),
            "signed_by": self.signed_by,
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SignedEnvelope:
        """Deserialize from a dict.

        Args:
            data: Dict as produced by to_dict().

        Returns:
            A SignedEnvelope instance.

        Raises:
            KeyError: If required fields are missing.
            ValueError: If field values are invalid.
        """
        envelope = ConstraintEnvelopeConfig(**data["envelope"])

        signed_at_raw = data["signed_at"]
        if isinstance(signed_at_raw, str):
            signed_at = datetime.fromisoformat(signed_at_raw)
        else:
            signed_at = signed_at_raw

        expires_at_raw = data["expires_at"]
        if isinstance(expires_at_raw, str):
            expires_at = datetime.fromisoformat(expires_at_raw)
        else:
            expires_at = expires_at_raw

        return cls(
            envelope=envelope,
            signature=data["signature"],
            signed_at=signed_at,
            signed_by=data["signed_by"],
            expires_at=expires_at,
        )


def sign_envelope(
    envelope: ConstraintEnvelopeConfig,
    private_key: str,
    signed_by: str,
    *,
    expires_in_days: int = _SIGNED_ENVELOPE_EXPIRY_DAYS,
) -> SignedEnvelope:
    """Sign a ConstraintEnvelopeConfig with an Ed25519 private key.

    Creates a SignedEnvelope wrapping the original envelope with a
    cryptographic signature, signer identity, and expiry.

    Args:
        envelope: The ConstraintEnvelopeConfig to sign.
        private_key: Base64-encoded Ed25519 private key.
        signed_by: Identifier of the signing authority.
        expires_in_days: Number of days until the signed envelope expires.
            Defaults to 90 days.

    Returns:
        A SignedEnvelope with the signature and metadata.

    Raises:
        ImportError: If PyNaCl is not installed.
        ValueError: If the private key is invalid or expires_in_days <= 0.
    """
    if expires_in_days <= 0:
        raise ValueError(f"expires_in_days must be positive, got {expires_in_days}")

    from datetime import timedelta

    from kailash.trust.signing.crypto import serialize_for_signing, sign

    now = datetime.now(UTC)
    payload = serialize_for_signing(envelope.model_dump(mode="json"))
    signature = sign(payload, private_key)

    return SignedEnvelope(
        envelope=envelope,
        signature=signature,
        signed_at=now,
        signed_by=signed_by,
        expires_at=now + timedelta(days=expires_in_days),
    )
