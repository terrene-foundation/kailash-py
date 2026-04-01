# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Envelope adapter -- converts governance envelopes to trust-layer ConstraintEnvelope.

The governance layer's compute_effective_envelope() is CANONICAL. This adapter
produces trust-layer ConstraintEnvelope instances for backward compatibility
with ExecutionRuntime and GradientEngine.

FAIL-CLOSED: If conversion fails, raises EnvelopeAdapterError.
Does NOT fall back to legacy standalone ConstraintEnvelope.

Per governance.md MUST NOT Rule 3: new code uses governance envelopes, not legacy.
This adapter bridges the two layers for code that still uses the trust-layer evaluator.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

from kailash.trust.pact.config import ConstraintEnvelopeConfig
from kailash.trust.pact.exceptions import PactError

logger = logging.getLogger(__name__)

__all__ = [
    "EnvelopeAdapterError",
    "GovernanceEnvelopeAdapter",
]

# Lazy import trust-plane models to avoid hard dependency at import time.
# This adapter is used when bridging governance to trust-plane; callers
# that never call to_constraint_envelope() pay no import cost.
_trust_models = None


def _get_trust_models() -> Any:
    """Lazy-load kailash.trust.plane.models for trust-layer envelope types."""
    global _trust_models
    if _trust_models is None:
        try:
            from kailash.trust.plane import models as m

            _trust_models = m
        except ImportError as exc:
            raise EnvelopeAdapterError(
                "kailash.trust.plane not available. Install kailash[trust] "
                "to use the trust-layer envelope adapter."
            ) from exc
    return _trust_models


if TYPE_CHECKING:
    from kailash.trust.plane.models import ConstraintEnvelope as TrustConstraintEnvelope
    from kailash.trust.pact.engine import GovernanceEngine


class EnvelopeAdapterError(PactError):
    """Raised when envelope conversion fails. Fail-closed -- no fallback."""

    pass


def _validate_finite_fields(config: ConstraintEnvelopeConfig) -> None:
    """Validate that all numeric fields in a ConstraintEnvelopeConfig are finite.

    Security-critical: NaN bypasses all numeric comparisons (NaN < X is always
    False). Inf bypasses budget checks (cost > Inf is always False). Both must
    be rejected explicitly.

    Per trust-plane-security.md rule 3 and governance.md rule 4.

    Args:
        config: The constraint envelope config to validate.

    Raises:
        EnvelopeAdapterError: If any numeric field is NaN or Inf.
    """
    fields_to_check: list[tuple[str, float | None]] = []

    if config.financial is not None:
        fields_to_check.extend(
            [
                ("financial.max_spend_usd", config.financial.max_spend_usd),
                ("financial.api_cost_budget_usd", config.financial.api_cost_budget_usd),
                (
                    "financial.requires_approval_above_usd",
                    config.financial.requires_approval_above_usd,
                ),
            ]
        )

    # Operational rate limits (P-H9)
    if config.operational is not None:
        if config.operational.max_actions_per_day is not None:
            fields_to_check.append(
                (
                    "operational.max_actions_per_day",
                    float(config.operational.max_actions_per_day),
                )
            )
        if config.operational.max_actions_per_hour is not None:
            fields_to_check.append(
                (
                    "operational.max_actions_per_hour",
                    float(config.operational.max_actions_per_hour),
                )
            )

    if config.max_delegation_depth is not None:
        fields_to_check.append(
            ("max_delegation_depth", float(config.max_delegation_depth))
        )

    for field_name, value in fields_to_check:
        if value is not None and not math.isfinite(value):
            raise EnvelopeAdapterError(
                f"Envelope contains non-finite value in {field_name}: {value!r}. "
                f"NaN/Inf values bypass numeric comparisons and break governance checks."
            )


def _config_to_trust_envelope(
    config: ConstraintEnvelopeConfig,
) -> TrustConstraintEnvelope:
    """Map governance ConstraintEnvelopeConfig to trust-layer ConstraintEnvelope.

    Converts PACT's Pydantic config types to kailash.trust.plane's frozen
    dataclass constraint types. Field names differ between the two systems:

    - PACT financial: max_spend_usd, api_cost_budget_usd
    - Trust financial: max_cost_per_session, max_cost_per_action

    The adapter maps the governance semantics to the closest trust-layer
    equivalents. Where no direct equivalent exists, the value is preserved
    as closely as possible.

    Args:
        config: The governance ConstraintEnvelopeConfig.

    Returns:
        A trust-layer ConstraintEnvelope.
    """
    m = _get_trust_models()

    # --- Operational ---
    operational = m.OperationalConstraints(
        allowed_actions=(
            config.operational.allowed_actions if config.operational else []
        ),
        blocked_actions=(
            config.operational.blocked_actions if config.operational else []
        ),
    )

    # --- Data Access ---
    data_access = m.DataAccessConstraints(
        read_paths=config.data_access.read_paths if config.data_access else [],
        write_paths=config.data_access.write_paths if config.data_access else [],
        blocked_paths=(
            config.data_access.blocked_data_types if config.data_access else []
        ),
    )

    # --- Financial ---
    if config.financial is not None:
        financial = m.FinancialConstraints(
            max_cost_per_session=config.financial.max_spend_usd,
            max_cost_per_action=config.financial.requires_approval_above_usd,
            budget_tracking=True,
        )
    else:
        financial = m.FinancialConstraints()

    # --- Temporal ---
    if config.temporal is not None:
        allowed_hours = None
        if config.temporal.active_hours_start and config.temporal.active_hours_end:
            try:
                start_h = int(config.temporal.active_hours_start.split(":")[0])
                end_h = int(config.temporal.active_hours_end.split(":")[0])
                if start_h < end_h:
                    allowed_hours = (start_h, end_h)
            except (ValueError, IndexError):
                pass
        temporal = m.TemporalConstraints(
            allowed_hours=allowed_hours,
        )
    else:
        temporal = m.TemporalConstraints()

    # --- Communication ---
    communication = m.CommunicationConstraints(
        allowed_channels=(
            config.communication.allowed_channels if config.communication else []
        ),
        blocked_channels=[],
    )

    return m.ConstraintEnvelope(
        operational=operational,
        data_access=data_access,
        financial=financial,
        temporal=temporal,
        communication=communication,
        signed_by=f"governance:{config.id}",
    )


class GovernanceEnvelopeAdapter:
    """Converts governance envelopes to trust-layer ConstraintEnvelope.

    The governance layer's compute_effective_envelope() is CANONICAL.
    This adapter produces trust-layer ConstraintEnvelope instances for
    backward compatibility with ExecutionRuntime and GradientEngine.

    FAIL-CLOSED: If conversion fails, raises EnvelopeAdapterError.
    Does NOT fall back to legacy standalone ConstraintEnvelope.

    Args:
        engine: The GovernanceEngine to use for envelope computation.
    """

    def __init__(self, engine: GovernanceEngine) -> None:
        self._engine = engine

    def to_constraint_envelope(
        self,
        role_address: str,
        task_id: str | None = None,
    ) -> TrustConstraintEnvelope:
        """Convert governance effective envelope to trust-layer ConstraintEnvelope.

        Steps:
        1. Call engine.compute_envelope() to get ConstraintEnvelopeConfig
        2. Validate all numeric fields are finite (NaN/Inf guard)
        3. Map config fields to trust-layer ConstraintEnvelope constructor
        4. Return the trust-layer envelope

        Args:
            role_address: The D/T/R address of the role.
            task_id: Optional task ID for task-specific envelope narrowing.

        Returns:
            A trust-layer ConstraintEnvelope wrapping the governance effective envelope.

        Raises:
            EnvelopeAdapterError: If conversion fails (fail-closed, no fallback).
        """
        try:
            config = self._engine.compute_envelope(role_address, task_id=task_id)

            if config is None:
                raise EnvelopeAdapterError(
                    f"No effective envelope for role_address='{role_address}'"
                    + (f", task_id='{task_id}'" if task_id else "")
                    + " -- governance is fail-closed"
                )

            # Step 2: Validate all numeric fields are finite
            _validate_finite_fields(config)

            # Step 3: Map governance config to trust-layer envelope
            trust_envelope = _config_to_trust_envelope(config)

            logger.debug(
                "Adapted governance envelope for role_address='%s' (task_id=%s) -> "
                "trust-layer ConstraintEnvelope signed_by='%s'",
                role_address,
                task_id,
                trust_envelope.signed_by,
            )

            return trust_envelope

        except EnvelopeAdapterError:
            raise
        except PactError as exc:
            # Known governance errors — safe to include message
            raise EnvelopeAdapterError(
                f"Envelope conversion failed for role_address='{role_address}'"
                + (f", task_id='{task_id}'" if task_id else "")
                + f": {exc}"
            ) from exc
        except Exception as exc:
            # Unknown errors — log details, sanitize message (P-H7)
            logger.exception(
                "Unexpected error in envelope conversion for role_address=%s",
                role_address,
            )
            raise EnvelopeAdapterError(
                f"Envelope conversion failed for role_address='{role_address}'"
                + (f", task_id='{task_id}'" if task_id else "")
                + " — see server logs for details"
            ) from exc
