# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Canonical ConstraintEnvelope -- SINGLE source of truth for constraint envelopes.

SPEC-07: ConstraintEnvelope Unification.

This module defines the canonical ``ConstraintEnvelope`` type that replaces the
three previously scattered implementations:

1. ``kailash.trust.chain.ConstraintEnvelope`` -- EATP lineage chain (generic bag)
2. ``kailash.trust.plane.models.ConstraintEnvelope`` -- TrustPlane 5-dimension type
3. ``kailash.trust.pact.config.ConstraintEnvelopeConfig`` -- PACT governance config

The canonical type is a frozen dataclass superset with:

- Five constraint dimensions (financial, operational, temporal, data_access, communication)
- Gradient thresholds for verification gradient classification
- Posture ceiling per ADR-010
- Monotonic tightening via ``intersect()``
- Deterministic canonical JSON for cross-SDK compatibility
- HMAC-SHA256 signing via ``SecretRef``
- NaN/Inf protection on all numeric fields

All new code MUST import from this module. Old import paths emit DeprecationWarning
and delegate here.
"""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    # Error classes
    "EnvelopeValidationError",
    "UnknownEnvelopeFieldError",
    # Dimension dataclasses
    "FinancialConstraint",
    "OperationalConstraint",
    "TemporalConstraint",
    "DataAccessConstraint",
    "CommunicationConstraint",
    # Gradient thresholds
    "GradientThresholds",
    # Canonical envelope
    "ConstraintEnvelope",
    # Posture ceiling
    "AgentPosture",
    # Signing
    "SecretRef",
    "sign_envelope",
    "verify_envelope",
    # Converters
    "from_plane_envelope",
    "to_plane_envelope",
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class EnvelopeValidationError(ValueError):
    """Raised when an envelope fails validation during construction or deserialization."""

    pass


class UnknownEnvelopeFieldError(EnvelopeValidationError):
    """Raised when ``from_dict`` encounters a field not present in the schema."""

    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_finite(value: float | None, field_name: str) -> None:
    """Reject NaN and Inf. Security-critical per trust-plane-security.md rule 3."""
    if value is not None and not math.isfinite(value):
        raise EnvelopeValidationError(
            f"{field_name} must be finite, got {value!r}. "
            f"NaN/Inf values bypass numeric comparisons and break governance checks."
        )


def _validate_finite_int(value: int | None, field_name: str) -> None:
    """Reject non-finite float masquerading as int."""
    if value is not None:
        if isinstance(value, float):
            if not math.isfinite(value):
                raise EnvelopeValidationError(
                    f"{field_name} must be finite, got {value!r}."
                )
        elif not isinstance(value, int):
            raise EnvelopeValidationError(
                f"{field_name} must be int or None, got {type(value).__name__}"
            )


def _min_optional(a: float | None, b: float | None) -> float | None:
    """Return the stricter (lower) of two optional float limits.

    None means unbounded (no limit). If both are None, result is None.
    """
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _min_optional_int(a: int | None, b: int | None) -> int | None:
    """Return the stricter (lower) of two optional int limits."""
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


# ---------------------------------------------------------------------------
# Five Constraint Dimension Dataclasses (frozen)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FinancialConstraint:
    """Financial constraint dimension -- cost and budget boundaries.

    Fields are a superset of:
    - plane/models.FinancialConstraints: max_cost_per_session, max_cost_per_action, budget_tracking
    - pact/config.FinancialConstraintConfig: max_spend_usd, api_cost_budget_usd,
      requires_approval_above_usd, reasoning_required
    """

    budget_limit: float | None = None
    cost_per_call: float | None = None
    currency: str = "USD"
    max_cost_per_session: float | None = None
    max_cost_per_action: float | None = None
    budget_tracking: bool = False
    max_spend_usd: float | None = None
    api_cost_budget_usd: float | None = None
    requires_approval_above_usd: float | None = None
    reasoning_required: bool = False

    def __post_init__(self) -> None:
        _validate_finite(self.budget_limit, "FinancialConstraint.budget_limit")
        _validate_finite(self.cost_per_call, "FinancialConstraint.cost_per_call")
        _validate_finite(
            self.max_cost_per_session, "FinancialConstraint.max_cost_per_session"
        )
        _validate_finite(
            self.max_cost_per_action, "FinancialConstraint.max_cost_per_action"
        )
        _validate_finite(self.max_spend_usd, "FinancialConstraint.max_spend_usd")
        _validate_finite(
            self.api_cost_budget_usd, "FinancialConstraint.api_cost_budget_usd"
        )
        _validate_finite(
            self.requires_approval_above_usd,
            "FinancialConstraint.requires_approval_above_usd",
        )
        # Non-negative guards
        for name, val in [
            ("budget_limit", self.budget_limit),
            ("cost_per_call", self.cost_per_call),
            ("max_cost_per_session", self.max_cost_per_session),
            ("max_cost_per_action", self.max_cost_per_action),
            ("max_spend_usd", self.max_spend_usd),
            ("api_cost_budget_usd", self.api_cost_budget_usd),
            ("requires_approval_above_usd", self.requires_approval_above_usd),
        ]:
            if val is not None and val < 0:
                raise EnvelopeValidationError(
                    f"FinancialConstraint.{name} must be non-negative, got {val}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget_limit": self.budget_limit,
            "cost_per_call": self.cost_per_call,
            "currency": self.currency,
            "max_cost_per_session": self.max_cost_per_session,
            "max_cost_per_action": self.max_cost_per_action,
            "budget_tracking": self.budget_tracking,
            "max_spend_usd": self.max_spend_usd,
            "api_cost_budget_usd": self.api_cost_budget_usd,
            "requires_approval_above_usd": self.requires_approval_above_usd,
            "reasoning_required": self.reasoning_required,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FinancialConstraint:
        return cls(
            budget_limit=data.get("budget_limit"),
            cost_per_call=data.get("cost_per_call"),
            currency=data.get("currency", "USD"),
            max_cost_per_session=data.get("max_cost_per_session"),
            max_cost_per_action=data.get("max_cost_per_action"),
            budget_tracking=data.get("budget_tracking", False),
            max_spend_usd=data.get("max_spend_usd"),
            api_cost_budget_usd=data.get("api_cost_budget_usd"),
            requires_approval_above_usd=data.get("requires_approval_above_usd"),
            reasoning_required=data.get("reasoning_required", False),
        )


@dataclass(frozen=True)
class OperationalConstraint:
    """Operational constraint dimension -- what the agent can do.

    Superset of plane/models.OperationalConstraints and pact/config.OperationalConstraintConfig.
    """

    max_retries: int | None = None
    timeout_seconds: float | None = None
    max_concurrent: int | None = None
    allowed_actions: tuple[str, ...] = ()
    blocked_actions: tuple[str, ...] = ()
    max_actions_per_day: int | None = None
    max_actions_per_hour: int | None = None
    rate_limit_window_type: str = "fixed"
    reasoning_required: bool = False

    def __post_init__(self) -> None:
        _validate_finite(self.timeout_seconds, "OperationalConstraint.timeout_seconds")
        _validate_finite_int(self.max_retries, "OperationalConstraint.max_retries")
        _validate_finite_int(
            self.max_concurrent, "OperationalConstraint.max_concurrent"
        )
        _validate_finite_int(
            self.max_actions_per_day, "OperationalConstraint.max_actions_per_day"
        )
        _validate_finite_int(
            self.max_actions_per_hour, "OperationalConstraint.max_actions_per_hour"
        )
        # Coerce lists to tuples for frozen immutability
        if isinstance(self.allowed_actions, list):
            object.__setattr__(self, "allowed_actions", tuple(self.allowed_actions))
        if isinstance(self.blocked_actions, list):
            object.__setattr__(self, "blocked_actions", tuple(self.blocked_actions))

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
            "max_concurrent": self.max_concurrent,
            "allowed_actions": list(self.allowed_actions),
            "blocked_actions": list(self.blocked_actions),
            "max_actions_per_day": self.max_actions_per_day,
            "max_actions_per_hour": self.max_actions_per_hour,
            "rate_limit_window_type": self.rate_limit_window_type,
            "reasoning_required": self.reasoning_required,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OperationalConstraint:
        return cls(
            max_retries=data.get("max_retries"),
            timeout_seconds=data.get("timeout_seconds"),
            max_concurrent=data.get("max_concurrent"),
            allowed_actions=tuple(data.get("allowed_actions", ())),
            blocked_actions=tuple(data.get("blocked_actions", ())),
            max_actions_per_day=data.get("max_actions_per_day"),
            max_actions_per_hour=data.get("max_actions_per_hour"),
            rate_limit_window_type=data.get("rate_limit_window_type", "fixed"),
            reasoning_required=data.get("reasoning_required", False),
        )


@dataclass(frozen=True)
class TemporalConstraint:
    """Temporal constraint dimension -- time boundaries.

    Superset of plane/models.TemporalConstraints and pact/config.TemporalConstraintConfig.
    """

    valid_from: datetime | None = None
    valid_until: datetime | None = None
    max_duration_seconds: float | None = None
    max_session_hours: float | None = None
    allowed_hours: tuple[int, int] | None = None
    cooldown_minutes: int = 0
    active_hours_start: str | None = None
    active_hours_end: str | None = None
    timezone: str = "UTC"
    blackout_periods: tuple[str, ...] = ()
    reasoning_required: bool = False

    def __post_init__(self) -> None:
        _validate_finite(
            self.max_duration_seconds, "TemporalConstraint.max_duration_seconds"
        )
        _validate_finite(self.max_session_hours, "TemporalConstraint.max_session_hours")
        if self.max_session_hours is not None and self.max_session_hours < 0:
            raise EnvelopeValidationError(
                "TemporalConstraint.max_session_hours must be non-negative"
            )
        if self.cooldown_minutes < 0:
            raise EnvelopeValidationError(
                "TemporalConstraint.cooldown_minutes must be non-negative"
            )
        if self.allowed_hours is not None:
            start, end = self.allowed_hours
            if not (0 <= start <= 23 and 0 <= end <= 23):
                raise EnvelopeValidationError("allowed_hours values must be 0-23")
            if start >= end:
                raise EnvelopeValidationError(
                    "allowed_hours start must be less than end "
                    "(wrap-around windows not supported)"
                )
        # Coerce list to tuple
        if isinstance(self.blackout_periods, list):
            object.__setattr__(self, "blackout_periods", tuple(self.blackout_periods))

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "max_duration_seconds": self.max_duration_seconds,
            "max_session_hours": self.max_session_hours,
            "allowed_hours": list(self.allowed_hours) if self.allowed_hours else None,
            "cooldown_minutes": self.cooldown_minutes,
            "active_hours_start": self.active_hours_start,
            "active_hours_end": self.active_hours_end,
            "timezone": self.timezone,
            "blackout_periods": list(self.blackout_periods),
            "reasoning_required": self.reasoning_required,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TemporalConstraint:
        vf = data.get("valid_from")
        vu = data.get("valid_until")
        ah = data.get("allowed_hours")
        return cls(
            valid_from=datetime.fromisoformat(vf) if isinstance(vf, str) else vf,
            valid_until=datetime.fromisoformat(vu) if isinstance(vu, str) else vu,
            max_duration_seconds=data.get("max_duration_seconds"),
            max_session_hours=data.get("max_session_hours"),
            allowed_hours=(ah[0], ah[1]) if ah and len(ah) >= 2 else None,
            cooldown_minutes=data.get("cooldown_minutes", 0),
            active_hours_start=data.get("active_hours_start"),
            active_hours_end=data.get("active_hours_end"),
            timezone=data.get("timezone", "UTC"),
            blackout_periods=tuple(data.get("blackout_periods", ())),
            reasoning_required=data.get("reasoning_required", False),
        )


@dataclass(frozen=True)
class DataAccessConstraint:
    """Data access constraint dimension -- what data the agent can see and modify.

    Superset of plane/models.DataAccessConstraints and pact/config.DataAccessConstraintConfig.
    """

    allowed_models: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    allowed_resources: tuple[str, ...] = ()
    read_paths: tuple[str, ...] = ()
    write_paths: tuple[str, ...] = ()
    blocked_paths: tuple[str, ...] = ()
    blocked_patterns: tuple[str, ...] = ()
    blocked_data_types: tuple[str, ...] = ()
    reasoning_required: bool = False

    def __post_init__(self) -> None:
        # Coerce lists to tuples
        for attr in (
            "allowed_models",
            "allowed_tools",
            "allowed_resources",
            "read_paths",
            "write_paths",
            "blocked_paths",
            "blocked_patterns",
            "blocked_data_types",
        ):
            val = getattr(self, attr)
            if isinstance(val, list):
                object.__setattr__(self, attr, tuple(val))

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_models": list(self.allowed_models),
            "allowed_tools": list(self.allowed_tools),
            "allowed_resources": list(self.allowed_resources),
            "read_paths": list(self.read_paths),
            "write_paths": list(self.write_paths),
            "blocked_paths": list(self.blocked_paths),
            "blocked_patterns": list(self.blocked_patterns),
            "blocked_data_types": list(self.blocked_data_types),
            "reasoning_required": self.reasoning_required,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DataAccessConstraint:
        return cls(
            allowed_models=tuple(data.get("allowed_models", ())),
            allowed_tools=tuple(data.get("allowed_tools", ())),
            allowed_resources=tuple(data.get("allowed_resources", ())),
            read_paths=tuple(data.get("read_paths", ())),
            write_paths=tuple(data.get("write_paths", ())),
            blocked_paths=tuple(data.get("blocked_paths", ())),
            blocked_patterns=tuple(data.get("blocked_patterns", ())),
            blocked_data_types=tuple(data.get("blocked_data_types", ())),
            reasoning_required=data.get("reasoning_required", False),
        )


@dataclass(frozen=True)
class CommunicationConstraint:
    """Communication constraint dimension -- external communication boundaries.

    Superset of plane/models.CommunicationConstraints and
    pact/config.CommunicationConstraintConfig.
    """

    allowed_channels: tuple[str, ...] = ()
    blocked_channels: tuple[str, ...] = ()
    requires_review: tuple[str, ...] = ()
    max_message_length: int | None = None
    internal_only: bool = False
    external_requires_approval: bool = True
    reasoning_required: bool = False

    def __post_init__(self) -> None:
        _validate_finite_int(
            self.max_message_length,
            "CommunicationConstraint.max_message_length",
        )
        # Coerce lists to tuples
        for attr in ("allowed_channels", "blocked_channels", "requires_review"):
            val = getattr(self, attr)
            if isinstance(val, list):
                object.__setattr__(self, attr, tuple(val))

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_channels": list(self.allowed_channels),
            "blocked_channels": list(self.blocked_channels),
            "requires_review": list(self.requires_review),
            "max_message_length": self.max_message_length,
            "internal_only": self.internal_only,
            "external_requires_approval": self.external_requires_approval,
            "reasoning_required": self.reasoning_required,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CommunicationConstraint:
        return cls(
            allowed_channels=tuple(data.get("allowed_channels", ())),
            blocked_channels=tuple(data.get("blocked_channels", ())),
            requires_review=tuple(data.get("requires_review", ())),
            max_message_length=data.get("max_message_length"),
            internal_only=data.get("internal_only", False),
            external_requires_approval=data.get("external_requires_approval", True),
            reasoning_required=data.get("reasoning_required", False),
        )


# ---------------------------------------------------------------------------
# Gradient Thresholds
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GradientThresholds:
    """Per-dimension thresholds that determine warn/deny gradient classification.

    For each dimension, values represent upper bounds:
    - Below auto_approve_threshold -> AUTO_APPROVED
    - Between auto_approve and flag -> FLAGGED
    - Between flag and hold -> HELD
    - Above hold -> BLOCKED

    Invariant: auto_approve <= flag <= hold for each set of thresholds.
    """

    financial_auto_approve: float | None = None
    financial_flag: float | None = None
    financial_hold: float | None = None

    def __post_init__(self) -> None:
        _validate_finite(
            self.financial_auto_approve,
            "GradientThresholds.financial_auto_approve",
        )
        _validate_finite(self.financial_flag, "GradientThresholds.financial_flag")
        _validate_finite(self.financial_hold, "GradientThresholds.financial_hold")
        # Ordering invariant
        if (
            self.financial_auto_approve is not None
            and self.financial_flag is not None
            and self.financial_hold is not None
        ):
            if not (
                self.financial_auto_approve
                <= self.financial_flag
                <= self.financial_hold
            ):
                raise EnvelopeValidationError(
                    f"GradientThresholds must be ordered: "
                    f"auto_approve ({self.financial_auto_approve}) <= "
                    f"flag ({self.financial_flag}) <= "
                    f"hold ({self.financial_hold})"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "financial_auto_approve": self.financial_auto_approve,
            "financial_flag": self.financial_flag,
            "financial_hold": self.financial_hold,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GradientThresholds:
        return cls(
            financial_auto_approve=data.get("financial_auto_approve"),
            financial_flag=data.get("financial_flag"),
            financial_hold=data.get("financial_hold"),
        )


# ---------------------------------------------------------------------------
# Agent Posture (ADR-010)
# ---------------------------------------------------------------------------


class AgentPosture(str, Enum):
    """Agent posture levels for constraint envelope ceiling per ADR-010.

    Defines the maximum autonomy level an agent can operate at. The posture
    ceiling on a ``ConstraintEnvelope`` restricts the posture level regardless
    of what the trust posture system would otherwise allow.

    The five postures use EATP canonical names (Decision 007) and are ordered
    by increasing autonomy:

    ``PSEUDO`` < ``SUPERVISED`` < ``TOOL`` < ``DELEGATING`` < ``AUTONOMOUS``.

    ``str``-backed so existing wire formats that serialize the posture as a
    lowercase string (e.g. ``"supervised"``) round-trip unchanged. Equality
    against string values is preserved: ``AgentPosture.SUPERVISED ==
    "supervised"`` is ``True``.

    Old names (``PSEUDO_AGENT``, ``SHARED_PLANNING``, ``CONTINUOUS_INSIGHT``,
    ``DELEGATED``) are accepted via ``_missing_()`` for backward compatibility
    with serialized data.
    """

    PSEUDO = "pseudo"
    SUPERVISED = "supervised"
    TOOL = "tool"
    DELEGATING = "delegating"
    AUTONOMOUS = "autonomous"

    @classmethod
    def _missing_(cls, value: object) -> AgentPosture | None:
        """Accept old enum names/values for backward compatibility.

        Maps pre-Decision-007 names to their canonical equivalents so that
        existing serialized envelopes deserialize without error.
        """
        if isinstance(value, str):
            lowered = value.lower().strip()
            aliases: dict[str, AgentPosture] = {
                # Old enum values (wire-format strings)
                "pseudo_agent": cls.PSEUDO,
                "shared_planning": cls.TOOL,
                "continuous_insight": cls.DELEGATING,
                "delegated": cls.AUTONOMOUS,
                # Old enum member names (uppercase)
                "PSEUDO_AGENT": cls.PSEUDO,
                "SHARED_PLANNING": cls.TOOL,
                "CONTINUOUS_INSIGHT": cls.DELEGATING,
                "DELEGATED": cls.AUTONOMOUS,
            }
            # Try exact match first (handles case-sensitive old values)
            if value in aliases:
                return aliases[value]
            # Then try lowered match
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

    @staticmethod
    def ordering() -> dict[AgentPosture, int]:
        """Return the canonical ordering for posture comparison."""
        return {
            AgentPosture.PSEUDO: 0,
            AgentPosture.SUPERVISED: 1,
            AgentPosture.TOOL: 2,
            AgentPosture.DELEGATING: 3,
            AgentPosture.AUTONOMOUS: 4,
        }

    def fits_ceiling(self, ceiling: AgentPosture) -> bool:
        """Return True if this posture is at or below the given ceiling."""
        order = AgentPosture.ordering()
        return order[self] <= order[ceiling]

    def clamp_to_ceiling(self, ceiling: AgentPosture) -> AgentPosture:
        """Return this posture clamped to the ceiling (min of the two)."""
        order = AgentPosture.ordering()
        if order[self] <= order[ceiling]:
            return self
        return ceiling

    def intersect(self, other: AgentPosture | None) -> AgentPosture:
        """Return the stricter (lower autonomy) of two postures.

        Used by :meth:`ConstraintEnvelope.intersect` to combine posture
        ceilings monotonically -- intersecting two envelopes never loosens
        their posture ceiling. ``None`` on the other side is treated as
        unbounded (this posture wins).
        """
        if other is None:
            return self
        order = AgentPosture.ordering()
        return self if order[self] <= order[other] else other

    @classmethod
    def coerce(cls, value: AgentPosture | str | None) -> AgentPosture | None:
        """Coerce a wire-format string to a canonical ``AgentPosture``.

        Accepts an existing ``AgentPosture`` (returned unchanged), the
        lowercase string value (``"supervised"``), or ``None``. Raises
        :class:`EnvelopeValidationError` if the value does not match a
        known posture.
        """
        if value is None:
            return None
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value)
            except ValueError as exc:
                valid = sorted(p.value for p in cls)
                raise EnvelopeValidationError(
                    f"posture must be one of {valid}, got {value!r}"
                ) from exc
        raise EnvelopeValidationError(
            f"posture must be AgentPosture | str | None, got " f"{type(value).__name__}"
        )


# ---------------------------------------------------------------------------
# SecretRef and HMAC Signing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SecretRef:
    """Opaque reference to a secret for HMAC signing.

    Does NOT contain secret material -- it references a key by ID and
    provider so that the signing/verification functions can resolve the
    actual key bytes at runtime.

    Attributes:
        key_id: Identifier for the key (used in kid header for rotation).
        provider: Key provider name (e.g., "env", "vault", "kms").
        algorithm: HMAC algorithm (default: "sha256").
    """

    key_id: str
    provider: str = "env"
    algorithm: str = "sha256"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "provider": self.provider,
            "algorithm": self.algorithm,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SecretRef:
        return cls(
            key_id=data["key_id"],
            provider=data.get("provider", "env"),
            algorithm=data.get("algorithm", "sha256"),
        )


def _resolve_secret(secret_ref: SecretRef) -> bytes:
    """Resolve a SecretRef to actual key bytes.

    Currently supports the "env" provider which reads from environment
    variables. The key_id is used as the environment variable name.

    Raises:
        EnvelopeValidationError: If the secret cannot be resolved.
    """
    import os

    if secret_ref.provider == "env":
        value = os.environ.get(secret_ref.key_id)
        if value is None:
            raise EnvelopeValidationError(
                f"Secret key '{secret_ref.key_id}' not found in environment. "
                f"Set the environment variable to use HMAC signing."
            )
        return value.encode("utf-8")
    raise EnvelopeValidationError(
        f"Unsupported secret provider: {secret_ref.provider!r}. "
        f"Currently only 'env' is supported."
    )


# ---------------------------------------------------------------------------
# Canonical ConstraintEnvelope (frozen dataclass)
# ---------------------------------------------------------------------------

# Known top-level fields for from_dict validation
_KNOWN_FIELDS: frozenset[str] = frozenset(
    {
        "financial",
        "operational",
        "temporal",
        "data_access",
        "communication",
        "gradient_thresholds",
        "posture_ceiling",
        "metadata",
        "envelope_id",
        "signed_by",
        "signed_at",
        "envelope_hash",
    }
)


@dataclass(frozen=True)
class ConstraintEnvelope:
    """Canonical constraint envelope -- single source of truth (SPEC-07).

    A frozen, immutable container for the five EATP constraint dimensions plus
    cross-cutting governance fields (gradient thresholds, posture ceiling).

    Monotonic tightening: ``intersect(other)`` produces a new envelope that is
    at least as restrictive as both inputs on every dimension.

    All numeric fields are validated against NaN/Inf in ``__post_init__``.
    """

    financial: FinancialConstraint | None = None
    operational: OperationalConstraint | None = None
    temporal: TemporalConstraint | None = None
    data_access: DataAccessConstraint | None = None
    communication: CommunicationConstraint | None = None
    gradient_thresholds: GradientThresholds | None = None
    posture_ceiling: AgentPosture | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Coerce posture_ceiling: accept an AgentPosture instance or its
        # wire-format string value (e.g. "supervised"). Invalid values raise
        # an EnvelopeValidationError that names the posture_ceiling field
        # so callers can tell which input was rejected.
        if self.posture_ceiling is not None:
            try:
                coerced = AgentPosture.coerce(self.posture_ceiling)
            except EnvelopeValidationError as exc:
                valid = sorted(p.value for p in AgentPosture)
                raise EnvelopeValidationError(
                    f"posture_ceiling must be one of {valid}, "
                    f"got {self.posture_ceiling!r}"
                ) from exc
            object.__setattr__(self, "posture_ceiling", coerced)
        # Freeze the metadata dict by making a copy
        if self.metadata is not None:
            object.__setattr__(self, "metadata", dict(self.metadata))

    def envelope_hash(self) -> str:
        """SHA-256 of constraint content for tamper detection.

        Uses the canonical JSON representation (sorted keys, no extra whitespace).
        """
        payload = self._hashable_dict()
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()

    def _hashable_dict(self) -> dict[str, Any]:
        """Return the constraint-only dict (excludes metadata/signing fields)."""
        result: dict[str, Any] = {}
        if self.financial is not None:
            result["financial"] = self.financial.to_dict()
        if self.operational is not None:
            result["operational"] = self.operational.to_dict()
        if self.temporal is not None:
            result["temporal"] = self.temporal.to_dict()
        if self.data_access is not None:
            result["data_access"] = self.data_access.to_dict()
        if self.communication is not None:
            result["communication"] = self.communication.to_dict()
        if self.gradient_thresholds is not None:
            result["gradient_thresholds"] = self.gradient_thresholds.to_dict()
        if self.posture_ceiling is not None:
            # Serialize the enum as its lowercase string value so the
            # canonical wire format (e.g. "supervised") matches the Rust
            # SDK and existing cross-SDK fixtures.
            result["posture_ceiling"] = self.posture_ceiling.value
        return result

    def intersect(self, other: ConstraintEnvelope) -> ConstraintEnvelope:
        """Monotonic tightening -- return the intersection (stricter of both).

        For each dimension:
        - Numeric limits: min() of the two (lower = tighter)
        - Allow-lists: set intersection (fewer allowed = tighter)
        - Block-lists: set union (more blocked = tighter)
        - Booleans (reasoning_required, internal_only): OR (True wins = tighter)
        - None dimensions: treated as unbounded; the other side's value is used

        This operation is commutative and associative.
        """
        return ConstraintEnvelope(
            financial=_intersect_financial(self.financial, other.financial),
            operational=_intersect_operational(self.operational, other.operational),
            temporal=_intersect_temporal(self.temporal, other.temporal),
            data_access=_intersect_data_access(self.data_access, other.data_access),
            communication=_intersect_communication(
                self.communication, other.communication
            ),
            gradient_thresholds=_intersect_gradient(
                self.gradient_thresholds, other.gradient_thresholds
            ),
            posture_ceiling=_intersect_posture_ceiling(
                self.posture_ceiling, other.posture_ceiling
            ),
            metadata={**self.metadata, **other.metadata},
        )

    def is_tighter_than(self, other: ConstraintEnvelope) -> bool:
        """Return True if this envelope is at least as tight as other on every dimension.

        Tightening means:
        - Blocklists: this must be a superset (more things blocked)
        - Allowlists: this must be a subset (fewer things allowed)
        - Numeric limits: this must be <= (lower limits)
        - None in other means unrestricted; any value in self is tighter or equal.
        - None in self when other has a value means loosening -> False.
        """
        # Financial dimension
        if other.financial is not None:
            if self.financial is None:
                return False
            if other.financial.max_cost_per_session is not None:
                if self.financial.max_cost_per_session is None:
                    return False
                if (
                    self.financial.max_cost_per_session
                    > other.financial.max_cost_per_session
                ):
                    return False
            if other.financial.max_cost_per_action is not None:
                if self.financial.max_cost_per_action is None:
                    return False
                if (
                    self.financial.max_cost_per_action
                    > other.financial.max_cost_per_action
                ):
                    return False
            if other.financial.budget_tracking and not self.financial.budget_tracking:
                return False
            if other.financial.max_spend_usd is not None:
                if self.financial.max_spend_usd is None:
                    return False
                if self.financial.max_spend_usd > other.financial.max_spend_usd:
                    return False
            if other.financial.budget_limit is not None:
                if self.financial.budget_limit is None:
                    return False
                if self.financial.budget_limit > other.financial.budget_limit:
                    return False

        # Operational dimension
        if other.operational is not None:
            if self.operational is None:
                return False
            # Blocked actions: this must be superset
            if not set(other.operational.blocked_actions).issubset(
                set(self.operational.blocked_actions)
            ):
                return False
            # Allowed actions: if other restricts, this must be subset
            if other.operational.allowed_actions:
                if not self.operational.allowed_actions:
                    return False
                if not set(self.operational.allowed_actions).issubset(
                    set(other.operational.allowed_actions)
                ):
                    return False

        # Temporal dimension
        if other.temporal is not None:
            if self.temporal is None:
                return False
            if other.temporal.max_session_hours is not None:
                if self.temporal.max_session_hours is None:
                    return False
                if self.temporal.max_session_hours > other.temporal.max_session_hours:
                    return False
            if other.temporal.allowed_hours is not None:
                if self.temporal.allowed_hours is None:
                    return False
                if (
                    self.temporal.allowed_hours[0] < other.temporal.allowed_hours[0]
                    or self.temporal.allowed_hours[1] > other.temporal.allowed_hours[1]
                ):
                    return False
            if self.temporal.cooldown_minutes < other.temporal.cooldown_minutes:
                return False

        # Communication dimension
        if other.communication is not None:
            if self.communication is None:
                return False
            if not set(other.communication.blocked_channels).issubset(
                set(self.communication.blocked_channels)
            ):
                return False
            if other.communication.allowed_channels:
                if not self.communication.allowed_channels:
                    return False
                if not set(self.communication.allowed_channels).issubset(
                    set(other.communication.allowed_channels)
                ):
                    return False
            if not set(other.communication.requires_review).issubset(
                set(self.communication.requires_review)
            ):
                return False

        # Data access dimension
        if other.data_access is not None:
            if self.data_access is None:
                return False
            if not set(other.data_access.blocked_paths).issubset(
                set(self.data_access.blocked_paths)
            ):
                return False
            if not set(other.data_access.blocked_patterns).issubset(
                set(self.data_access.blocked_patterns)
            ):
                return False
            if other.data_access.read_paths:
                if not self.data_access.read_paths:
                    return False
                if not set(self.data_access.read_paths).issubset(
                    set(other.data_access.read_paths)
                ):
                    return False
            if other.data_access.write_paths:
                if not self.data_access.write_paths:
                    return False
                if not set(self.data_access.write_paths).issubset(
                    set(other.data_access.write_paths)
                ):
                    return False

        # Posture ceiling: this must be equal or lower (stricter)
        if other.posture_ceiling is not None:
            if self.posture_ceiling is None:
                return False
            order = AgentPosture.ordering()
            if order[self.posture_ceiling] > order[other.posture_ceiling]:
                return False

        return True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a stable-order JSON-serializable dict."""
        result: dict[str, Any] = {}
        if self.financial is not None:
            result["financial"] = self.financial.to_dict()
        if self.operational is not None:
            result["operational"] = self.operational.to_dict()
        if self.temporal is not None:
            result["temporal"] = self.temporal.to_dict()
        if self.data_access is not None:
            result["data_access"] = self.data_access.to_dict()
        if self.communication is not None:
            result["communication"] = self.communication.to_dict()
        if self.gradient_thresholds is not None:
            result["gradient_thresholds"] = self.gradient_thresholds.to_dict()
        if self.posture_ceiling is not None:
            # Serialize the enum as its lowercase string value to match the
            # canonical wire format shared with the Rust SDK.
            result["posture_ceiling"] = self.posture_ceiling.value
        if self.metadata:
            result["metadata"] = self.metadata
        result["envelope_hash"] = self.envelope_hash()
        return result

    def to_canonical_json(self) -> str:
        """Deterministic JSON string (sorted keys, no extra whitespace).

        Suitable for cross-SDK comparison and HMAC signing payloads.
        """
        return json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), default=str
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConstraintEnvelope:
        """Construct from a dict with validation.

        Raises:
            UnknownEnvelopeFieldError: If unknown top-level fields are present.
            EnvelopeValidationError: If field values fail validation.
        """
        unknown = set(data.keys()) - _KNOWN_FIELDS
        if unknown:
            raise UnknownEnvelopeFieldError(
                f"Unknown fields in envelope data: {sorted(unknown)}. "
                f"Known fields: {sorted(_KNOWN_FIELDS)}"
            )

        financial = None
        if "financial" in data and data["financial"] is not None:
            financial = FinancialConstraint.from_dict(data["financial"])

        operational = None
        if "operational" in data and data["operational"] is not None:
            operational = OperationalConstraint.from_dict(data["operational"])

        temporal = None
        if "temporal" in data and data["temporal"] is not None:
            temporal = TemporalConstraint.from_dict(data["temporal"])

        data_access = None
        if "data_access" in data and data["data_access"] is not None:
            data_access = DataAccessConstraint.from_dict(data["data_access"])

        communication = None
        if "communication" in data and data["communication"] is not None:
            communication = CommunicationConstraint.from_dict(data["communication"])

        gradient_thresholds = None
        if "gradient_thresholds" in data and data["gradient_thresholds"] is not None:
            gradient_thresholds = GradientThresholds.from_dict(
                data["gradient_thresholds"]
            )

        return cls(
            financial=financial,
            operational=operational,
            temporal=temporal,
            data_access=data_access,
            communication=communication,
            gradient_thresholds=gradient_thresholds,
            posture_ceiling=data.get("posture_ceiling"),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_yaml(cls, path_or_str: str) -> ConstraintEnvelope:
        """Load from a YAML file path or YAML string.

        If ``path_or_str`` looks like a file path (contains '/' or '\\' or
        ends with '.yaml'/'.yml'), it is loaded from disk. Otherwise it is
        parsed as inline YAML.

        Raises:
            EnvelopeValidationError: If the YAML is malformed or validation fails.
        """
        try:
            import yaml
        except ImportError as exc:
            raise ImportError(
                "PyYAML is required for YAML loading. "
                "Install it with: pip install pyyaml"
            ) from exc

        is_file = (
            "/" in path_or_str
            or "\\" in path_or_str
            or path_or_str.endswith((".yaml", ".yml"))
        )
        if is_file:
            try:
                from pathlib import Path

                from kailash.trust._locking import safe_read_text

                text = safe_read_text(Path(path_or_str))
                data = yaml.safe_load(text)
            except FileNotFoundError:
                raise EnvelopeValidationError(f"YAML file not found: {path_or_str}")
            except OSError as exc:
                raise EnvelopeValidationError(
                    f"Cannot read YAML file {path_or_str}: {exc}"
                )
            except yaml.YAMLError as exc:
                raise EnvelopeValidationError(
                    f"Invalid YAML in file {path_or_str}: {exc}"
                )
        else:
            try:
                data = yaml.safe_load(path_or_str)
            except yaml.YAMLError as exc:
                raise EnvelopeValidationError(f"Invalid YAML string: {exc}")

        if not isinstance(data, dict):
            raise EnvelopeValidationError(
                f"YAML must produce a dict, got {type(data).__name__}"
            )

        return cls.from_dict(data)


# ---------------------------------------------------------------------------
# Intersection Helpers (monotonic tightening)
# ---------------------------------------------------------------------------


def _intersect_financial(
    a: FinancialConstraint | None, b: FinancialConstraint | None
) -> FinancialConstraint | None:
    """Intersect financial dimensions: min() of numeric limits."""
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return FinancialConstraint(
        budget_limit=_min_optional(a.budget_limit, b.budget_limit),
        cost_per_call=_min_optional(a.cost_per_call, b.cost_per_call),
        currency=a.currency,  # preserve first
        max_cost_per_session=_min_optional(
            a.max_cost_per_session, b.max_cost_per_session
        ),
        max_cost_per_action=_min_optional(a.max_cost_per_action, b.max_cost_per_action),
        budget_tracking=a.budget_tracking or b.budget_tracking,
        max_spend_usd=_min_optional(a.max_spend_usd, b.max_spend_usd),
        api_cost_budget_usd=_min_optional(a.api_cost_budget_usd, b.api_cost_budget_usd),
        requires_approval_above_usd=_min_optional(
            a.requires_approval_above_usd, b.requires_approval_above_usd
        ),
        reasoning_required=a.reasoning_required or b.reasoning_required,
    )


def _intersect_operational(
    a: OperationalConstraint | None, b: OperationalConstraint | None
) -> OperationalConstraint | None:
    """Intersect operational dimensions: intersection of allowed, union of blocked."""
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    allowed = set(a.allowed_actions) & set(b.allowed_actions)
    blocked = set(a.blocked_actions) | set(b.blocked_actions)
    # Deny-overrides: remove any blocked from allowed
    allowed -= blocked
    return OperationalConstraint(
        max_retries=_min_optional_int(a.max_retries, b.max_retries),
        timeout_seconds=_min_optional(a.timeout_seconds, b.timeout_seconds),
        max_concurrent=_min_optional_int(a.max_concurrent, b.max_concurrent),
        allowed_actions=tuple(sorted(allowed)),
        blocked_actions=tuple(sorted(blocked)),
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
    a: TemporalConstraint | None, b: TemporalConstraint | None
) -> TemporalConstraint | None:
    """Intersect temporal dimensions: overlap of windows, union of blackouts."""
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a

    # allowed_hours: overlap
    allowed_hours = None
    if a.allowed_hours is not None and b.allowed_hours is not None:
        start = max(a.allowed_hours[0], b.allowed_hours[0])
        end = min(a.allowed_hours[1], b.allowed_hours[1])
        if start < end:
            allowed_hours = (start, end)
    elif a.allowed_hours is not None:
        allowed_hours = a.allowed_hours
    elif b.allowed_hours is not None:
        allowed_hours = b.allowed_hours

    # active_hours: overlap (string comparison for HH:MM)
    active_start = None
    active_end = None
    if a.active_hours_start is not None and b.active_hours_start is not None:
        active_start = max(a.active_hours_start, b.active_hours_start)
        end_a = a.active_hours_end or "23:59"
        end_b = b.active_hours_end or "23:59"
        active_end = min(end_a, end_b)
    elif a.active_hours_start is not None:
        active_start = a.active_hours_start
        active_end = a.active_hours_end
    elif b.active_hours_start is not None:
        active_start = b.active_hours_start
        active_end = b.active_hours_end

    return TemporalConstraint(
        valid_from=(
            max(a.valid_from, b.valid_from)
            if a.valid_from and b.valid_from
            else a.valid_from or b.valid_from
        ),
        valid_until=(
            min(a.valid_until, b.valid_until)
            if a.valid_until and b.valid_until
            else a.valid_until or b.valid_until
        ),
        max_duration_seconds=_min_optional(
            a.max_duration_seconds, b.max_duration_seconds
        ),
        max_session_hours=_min_optional(a.max_session_hours, b.max_session_hours),
        allowed_hours=allowed_hours,
        cooldown_minutes=max(a.cooldown_minutes, b.cooldown_minutes),
        active_hours_start=active_start,
        active_hours_end=active_end,
        timezone=a.timezone,
        blackout_periods=tuple(
            sorted(set(a.blackout_periods) | set(b.blackout_periods))
        ),
        reasoning_required=a.reasoning_required or b.reasoning_required,
    )


def _intersect_data_access(
    a: DataAccessConstraint | None, b: DataAccessConstraint | None
) -> DataAccessConstraint | None:
    """Intersect data access: intersection of allowed paths, union of blocked."""
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return DataAccessConstraint(
        allowed_models=tuple(sorted(set(a.allowed_models) & set(b.allowed_models))),
        allowed_tools=tuple(sorted(set(a.allowed_tools) & set(b.allowed_tools))),
        allowed_resources=tuple(
            sorted(set(a.allowed_resources) & set(b.allowed_resources))
        ),
        read_paths=tuple(sorted(set(a.read_paths) & set(b.read_paths))),
        write_paths=tuple(sorted(set(a.write_paths) & set(b.write_paths))),
        blocked_paths=tuple(sorted(set(a.blocked_paths) | set(b.blocked_paths))),
        blocked_patterns=tuple(
            sorted(set(a.blocked_patterns) | set(b.blocked_patterns))
        ),
        blocked_data_types=tuple(
            sorted(set(a.blocked_data_types) | set(b.blocked_data_types))
        ),
        reasoning_required=a.reasoning_required or b.reasoning_required,
    )


def _intersect_communication(
    a: CommunicationConstraint | None, b: CommunicationConstraint | None
) -> CommunicationConstraint | None:
    """Intersect communication: intersection of channels, tighter booleans."""
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return CommunicationConstraint(
        allowed_channels=tuple(
            sorted(set(a.allowed_channels) & set(b.allowed_channels))
        ),
        blocked_channels=tuple(
            sorted(set(a.blocked_channels) | set(b.blocked_channels))
        ),
        requires_review=tuple(sorted(set(a.requires_review) | set(b.requires_review))),
        max_message_length=_min_optional_int(
            a.max_message_length, b.max_message_length
        ),
        internal_only=a.internal_only or b.internal_only,
        external_requires_approval=(
            a.external_requires_approval or b.external_requires_approval
        ),
        reasoning_required=a.reasoning_required or b.reasoning_required,
    )


def _intersect_gradient(
    a: GradientThresholds | None, b: GradientThresholds | None
) -> GradientThresholds | None:
    """Intersect gradient thresholds: min() of each threshold (tighter)."""
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return GradientThresholds(
        financial_auto_approve=_min_optional(
            a.financial_auto_approve, b.financial_auto_approve
        ),
        financial_flag=_min_optional(a.financial_flag, b.financial_flag),
        financial_hold=_min_optional(a.financial_hold, b.financial_hold),
    )


def _intersect_posture_ceiling(
    a: AgentPosture | None, b: AgentPosture | None
) -> AgentPosture | None:
    """Intersect posture ceilings: lower (more restrictive) wins.

    Delegates to :meth:`AgentPosture.intersect` so the monotonic-tightening
    arithmetic lives on the enum itself. ``None`` on either side is treated
    as unbounded.
    """
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return a.intersect(b)


# ---------------------------------------------------------------------------
# HMAC Signing and Verification
# ---------------------------------------------------------------------------


def sign_envelope(
    envelope: ConstraintEnvelope,
    secret_ref: SecretRef,
) -> str:
    """Compute HMAC-SHA256 signature of the envelope's canonical JSON.

    Returns a hex-encoded HMAC digest. The kid (key ID) from the SecretRef
    can be transmitted alongside the signature for key rotation support.

    Args:
        envelope: The ConstraintEnvelope to sign.
        secret_ref: Reference to the signing secret.

    Returns:
        Hex-encoded HMAC-SHA256 digest string.
    """
    key_bytes = _resolve_secret(secret_ref)
    payload = envelope.to_canonical_json().encode("utf-8")
    return hmac_mod.new(key_bytes, payload, hashlib.sha256).hexdigest()


def verify_envelope(
    envelope: ConstraintEnvelope,
    signature: str,
    secret_ref: SecretRef,
) -> bool:
    """Verify HMAC-SHA256 signature of the envelope's canonical JSON.

    Uses constant-time comparison (hmac.compare_digest) per trust-plane
    security rule -- NEVER use equality operators for HMAC comparison.

    Args:
        envelope: The ConstraintEnvelope to verify.
        signature: Hex-encoded HMAC-SHA256 digest to verify against.
        secret_ref: Reference to the verification secret.

    Returns:
        True if the signature matches, False otherwise. Fail-closed on
        any error.
    """
    try:
        key_bytes = _resolve_secret(secret_ref)
        payload = envelope.to_canonical_json().encode("utf-8")
        expected = hmac_mod.new(key_bytes, payload, hashlib.sha256).hexdigest()
        return hmac_mod.compare_digest(expected, signature)
    except Exception:
        logger.exception(
            "HMAC verification failed for envelope -- fail-closed to False"
        )
        return False


# ---------------------------------------------------------------------------
# Converters: canonical <-> plane/models types
# ---------------------------------------------------------------------------


def from_plane_envelope(plane_envelope: Any) -> ConstraintEnvelope:
    """Convert a kailash.trust.plane.models.ConstraintEnvelope to canonical.

    Lazily imports the plane models to avoid circular dependencies.

    Args:
        plane_envelope: A ``kailash.trust.plane.models.ConstraintEnvelope`` instance.

    Returns:
        The equivalent canonical ``ConstraintEnvelope``.
    """
    return ConstraintEnvelope(
        financial=(
            FinancialConstraint(
                max_cost_per_session=plane_envelope.financial.max_cost_per_session,
                max_cost_per_action=plane_envelope.financial.max_cost_per_action,
                budget_tracking=plane_envelope.financial.budget_tracking,
            )
            if hasattr(plane_envelope, "financial")
            and plane_envelope.financial is not None
            else None
        ),
        operational=(
            OperationalConstraint(
                allowed_actions=tuple(plane_envelope.operational.allowed_actions),
                blocked_actions=tuple(plane_envelope.operational.blocked_actions),
            )
            if hasattr(plane_envelope, "operational")
            and plane_envelope.operational is not None
            else None
        ),
        temporal=(
            TemporalConstraint(
                max_session_hours=plane_envelope.temporal.max_session_hours,
                allowed_hours=plane_envelope.temporal.allowed_hours,
                cooldown_minutes=plane_envelope.temporal.cooldown_minutes,
            )
            if hasattr(plane_envelope, "temporal")
            and plane_envelope.temporal is not None
            else None
        ),
        data_access=(
            DataAccessConstraint(
                read_paths=tuple(plane_envelope.data_access.read_paths),
                write_paths=tuple(plane_envelope.data_access.write_paths),
                blocked_paths=tuple(plane_envelope.data_access.blocked_paths),
                blocked_patterns=tuple(plane_envelope.data_access.blocked_patterns),
            )
            if hasattr(plane_envelope, "data_access")
            and plane_envelope.data_access is not None
            else None
        ),
        communication=(
            CommunicationConstraint(
                allowed_channels=tuple(plane_envelope.communication.allowed_channels),
                blocked_channels=tuple(plane_envelope.communication.blocked_channels),
                requires_review=tuple(plane_envelope.communication.requires_review),
            )
            if hasattr(plane_envelope, "communication")
            and plane_envelope.communication is not None
            else None
        ),
        metadata=(
            {"signed_by": plane_envelope.signed_by}
            if hasattr(plane_envelope, "signed_by") and plane_envelope.signed_by
            else {}
        ),
    )


def to_plane_envelope(canonical: ConstraintEnvelope) -> Any:
    """Convert a canonical ConstraintEnvelope to kailash.trust.plane.models type.

    Lazily imports the plane models to avoid circular dependencies.

    Args:
        canonical: A canonical ``ConstraintEnvelope`` instance.

    Returns:
        A ``kailash.trust.plane.models.ConstraintEnvelope`` instance.
    """
    from kailash.trust.plane.models import CommunicationConstraints
    from kailash.trust.plane.models import ConstraintEnvelope as PlaneConstraintEnvelope
    from kailash.trust.plane.models import (
        DataAccessConstraints,
        FinancialConstraints,
        OperationalConstraints,
        TemporalConstraints,
    )

    return PlaneConstraintEnvelope(
        operational=(
            OperationalConstraints(
                allowed_actions=list(canonical.operational.allowed_actions),
                blocked_actions=list(canonical.operational.blocked_actions),
            )
            if canonical.operational is not None
            else OperationalConstraints()
        ),
        data_access=(
            DataAccessConstraints(
                read_paths=list(canonical.data_access.read_paths),
                write_paths=list(canonical.data_access.write_paths),
                blocked_paths=list(canonical.data_access.blocked_paths),
                blocked_patterns=list(canonical.data_access.blocked_patterns),
            )
            if canonical.data_access is not None
            else DataAccessConstraints()
        ),
        financial=(
            FinancialConstraints(
                max_cost_per_session=canonical.financial.max_cost_per_session,
                max_cost_per_action=canonical.financial.max_cost_per_action,
                budget_tracking=canonical.financial.budget_tracking,
            )
            if canonical.financial is not None
            else FinancialConstraints()
        ),
        temporal=(
            TemporalConstraints(
                max_session_hours=canonical.temporal.max_session_hours,
                allowed_hours=canonical.temporal.allowed_hours,
                cooldown_minutes=canonical.temporal.cooldown_minutes,
            )
            if canonical.temporal is not None
            else TemporalConstraints()
        ),
        communication=(
            CommunicationConstraints(
                allowed_channels=list(canonical.communication.allowed_channels),
                blocked_channels=list(canonical.communication.blocked_channels),
                requires_review=list(canonical.communication.requires_review),
            )
            if canonical.communication is not None
            else CommunicationConstraints()
        ),
        signed_by=canonical.metadata.get("signed_by", ""),
    )
