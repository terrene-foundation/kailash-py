# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pact.build.config.schema import (
    CONFIDENTIALITY_ORDER,
    CommunicationConstraintConfig,
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    DataAccessConstraintConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TemporalConstraintConfig,
    TrustPostureLevel,
)
from pact.governance.addressing import Address

logger = logging.getLogger(__name__)

__all__ = [
    "EffectiveEnvelopeSnapshot",
    "MonotonicTighteningError",
    "RoleEnvelope",
    "TaskEnvelope",
    "check_degenerate_envelope",
    "compute_effective_envelope",
    "compute_effective_envelope_with_version",
    "default_envelope_for_posture",
    "intersect_envelopes",
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class MonotonicTighteningError(ValueError):
    """Raised when a child envelope violates monotonic tightening relative to its parent."""

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
            raise TypeError(f"{field_name} must be int or None, got {type(value).__name__}")


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


def _min_confidentiality(a: ConfidentialityLevel, b: ConfidentialityLevel) -> ConfidentialityLevel:
    """Return the lower (more restrictive) of two confidentiality levels."""
    if CONFIDENTIALITY_ORDER[a] <= CONFIDENTIALITY_ORDER[b]:
        return a
    return b


# ---------------------------------------------------------------------------
# TODO-3001: Envelope Intersection
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
        _validate_finite(a.requires_approval_above_usd, "financial.requires_approval_above_usd")
        return a

    # Validate all numeric fields before any min() calls
    _validate_finite(a.max_spend_usd, "financial.max_spend_usd (envelope a)")
    _validate_finite(b.max_spend_usd, "financial.max_spend_usd (envelope b)")
    _validate_finite(a.api_cost_budget_usd, "financial.api_cost_budget_usd (envelope a)")
    _validate_finite(b.api_cost_budget_usd, "financial.api_cost_budget_usd (envelope b)")
    _validate_finite(
        a.requires_approval_above_usd, "financial.requires_approval_above_usd (envelope a)"
    )
    _validate_finite(
        b.requires_approval_above_usd, "financial.requires_approval_above_usd (envelope b)"
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
        max_actions_per_day=_min_optional_int(a.max_actions_per_day, b.max_actions_per_day),
        max_actions_per_hour=_min_optional_int(a.max_actions_per_hour, b.max_actions_per_hour),
        rate_limit_window_type=(
            "rolling"
            if a.rate_limit_window_type == "rolling" or b.rate_limit_window_type == "rolling"
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
        blocked_data_types=sorted(set(a.blocked_data_types) | set(b.blocked_data_types)),
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
        external_requires_approval=a.external_requires_approval or b.external_requires_approval,
        reasoning_required=a.reasoning_required or b.reasoning_required,
    )


def intersect_envelopes(
    a: ConstraintEnvelopeConfig, b: ConstraintEnvelopeConfig
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

    Args:
        a: First constraint envelope.
        b: Second constraint envelope.

    Returns:
        A new ConstraintEnvelopeConfig representing the intersection.
    """
    return ConstraintEnvelopeConfig(
        id=f"ix-{uuid.uuid4().hex[:12]}",
        description=f"Intersection of [{a.id}] and [{b.id}]",
        confidentiality_clearance=_min_confidentiality(
            a.confidentiality_clearance, b.confidentiality_clearance
        ),
        financial=_intersect_financial(a.financial, b.financial),
        operational=_intersect_operational(a.operational, b.operational),
        temporal=_intersect_temporal(a.temporal, b.temporal),
        data_access=_intersect_data_access(a.data_access, b.data_access),
        communication=_intersect_communication(a.communication, b.communication),
        max_delegation_depth=_min_optional_int(a.max_delegation_depth, b.max_delegation_depth),
    )


# ---------------------------------------------------------------------------
# TODO-3002: RoleEnvelope
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
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    modified_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def validate_tightening(
        *,
        parent_envelope: ConstraintEnvelopeConfig,
        child_envelope: ConstraintEnvelopeConfig,
    ) -> None:
        """Validate that child_envelope is at most as permissive as parent_envelope.

        Checks each dimension for monotonic tightening violations.

        Args:
            parent_envelope: The supervisor's (defining role's) envelope.
            child_envelope: The proposed envelope for the direct report.

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
        if parent_envelope.financial is not None and child_envelope.financial is not None:
            if child_envelope.financial.max_spend_usd > parent_envelope.financial.max_spend_usd:
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
        child_conf_order = CONFIDENTIALITY_ORDER[child_envelope.confidentiality_clearance]
        parent_conf_order = CONFIDENTIALITY_ORDER[parent_envelope.confidentiality_clearance]
        if child_conf_order > parent_conf_order:
            violations.append(
                f"Confidentiality: child clearance "
                f"({child_envelope.confidentiality_clearance.value}) exceeds parent "
                f"({parent_envelope.confidentiality_clearance.value})"
            )

        # Operational: child allowed_actions must be subset of parent's
        parent_allowed = set(parent_envelope.operational.allowed_actions)
        child_allowed = set(child_envelope.operational.allowed_actions)
        if parent_allowed and child_allowed and not child_allowed.issubset(parent_allowed):
            extra = child_allowed - parent_allowed
            violations.append(
                f"Operational: child allowed_actions {extra} not in parent allowed set"
            )

        # max_delegation_depth: child must not exceed parent
        if (
            parent_envelope.max_delegation_depth is not None
            and child_envelope.max_delegation_depth is not None
            and child_envelope.max_delegation_depth > parent_envelope.max_delegation_depth
        ):
            violations.append(
                f"Delegation: child max_delegation_depth "
                f"({child_envelope.max_delegation_depth}) exceeds parent "
                f"({parent_envelope.max_delegation_depth})"
            )

        if violations:
            msg = "Monotonic tightening violation(s): " + "; ".join(violations)
            logger.error(msg)
            raise MonotonicTighteningError(msg)


# ---------------------------------------------------------------------------
# TODO-3003: TaskEnvelope
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
# TODO-3004: Effective Envelope Computation
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
# TODO-3005: Default Envelopes by Trust Posture
# ---------------------------------------------------------------------------


def default_envelope_for_posture(posture: TrustPostureLevel) -> ConstraintEnvelopeConfig:
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
        TrustPostureLevel.PSEUDO_AGENT: {
            "max_spend_usd": 0.0,
            "confidentiality": ConfidentialityLevel.PUBLIC,
            "allowed_actions": ["read"],
            "internal_only": True,
            "allowed_channels": ["internal"],
            "read_paths": [],
            "write_paths": [],
        },
        TrustPostureLevel.SUPERVISED: {
            "max_spend_usd": 100.0,
            "confidentiality": ConfidentialityLevel.RESTRICTED,
            "allowed_actions": ["read", "write"],
            "internal_only": True,
            "allowed_channels": ["internal", "email"],
            "read_paths": ["/data/public", "/data/team"],
            "write_paths": ["/data/team"],
        },
        TrustPostureLevel.SHARED_PLANNING: {
            "max_spend_usd": 1000.0,
            "confidentiality": ConfidentialityLevel.CONFIDENTIAL,
            "allowed_actions": ["read", "write", "plan", "propose"],
            "internal_only": False,
            "allowed_channels": ["internal", "email", "slack"],
            "read_paths": ["/data/public", "/data/team", "/data/department"],
            "write_paths": ["/data/team", "/data/department"],
        },
        TrustPostureLevel.CONTINUOUS_INSIGHT: {
            "max_spend_usd": 10000.0,
            "confidentiality": ConfidentialityLevel.SECRET,
            "allowed_actions": ["read", "write", "plan", "propose", "execute", "deploy"],
            "internal_only": False,
            "allowed_channels": ["internal", "email", "slack", "teams", "api"],
            "read_paths": ["/data/public", "/data/team", "/data/department", "/data/org"],
            "write_paths": ["/data/team", "/data/department", "/data/org"],
        },
        TrustPostureLevel.DELEGATED: {
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
            "allowed_channels": ["internal", "email", "slack", "teams", "api", "external"],
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
# TODO-3006: Degenerate Envelope Detection
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
                "Financial: effective spend limit is $0.00 -- " "no financial actions possible"
            )

    # Operational dimension
    if not effective.operational.allowed_actions:
        warnings.append("Operational: no allowed actions -- " "agent cannot perform any operations")

    # Communication dimension
    if not effective.communication.allowed_channels:
        warnings.append(
            "Communication: no allowed channels -- " "agent cannot communicate through any channel"
        )

    # Data access dimension
    if not effective.data_access.read_paths and not effective.data_access.write_paths:
        # Only warn if there are also no other capabilities
        # (empty paths might be intentional for non-data agents)
        pass

    return warnings
