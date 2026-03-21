# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
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

from pact.build.config.schema import ConstraintEnvelopeConfig
from pact.trust.constraint.envelope import ConstraintEnvelope

if TYPE_CHECKING:
    from pact.governance.engine import GovernanceEngine

logger = logging.getLogger(__name__)

__all__ = [
    "EnvelopeAdapterError",
    "GovernanceEnvelopeAdapter",
]


class EnvelopeAdapterError(Exception):
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

    if config.max_delegation_depth is not None:
        # max_delegation_depth is int, but could be a float at runtime
        fields_to_check.append(("max_delegation_depth", float(config.max_delegation_depth)))

    for field_name, value in fields_to_check:
        if value is not None and not math.isfinite(value):
            raise EnvelopeAdapterError(
                f"Envelope contains non-finite value in {field_name}: {value!r}. "
                f"NaN/Inf values bypass numeric comparisons and break governance checks."
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
    ) -> ConstraintEnvelope:
        """Convert governance effective envelope to trust-layer ConstraintEnvelope.

        Steps:
        1. Call engine.compute_envelope() to get ConstraintEnvelopeConfig
        2. Validate all numeric fields are finite (NaN/Inf guard)
        3. Wrap in trust-layer ConstraintEnvelope with evaluation capability
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

            # Step 3: Create trust-layer ConstraintEnvelope from the config.
            # ConstraintEnvelope is a Pydantic model that wraps a
            # ConstraintEnvelopeConfig and adds evaluate_action() capability.
            trust_envelope = ConstraintEnvelope(config=config)

            logger.debug(
                "Adapted governance envelope for role_address='%s' (task_id=%s) -> "
                "ConstraintEnvelope id='%s'",
                role_address,
                task_id,
                trust_envelope.id,
            )

            return trust_envelope

        except EnvelopeAdapterError:
            raise
        except Exception as exc:
            raise EnvelopeAdapterError(
                f"Envelope conversion failed for role_address='{role_address}'"
                + (f", task_id='{task_id}'" if task_id else "")
                + f": {exc}"
            ) from exc
