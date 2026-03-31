# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: restrictive PACT defaults block legitimate operations.

Bug 1: FinancialConstraintConfig defaults to max_spend_usd=0.0 via
default_factory, contradicting the M23/2301 docstring that says financial
should default to None (skip financial dimension). Any action with cost>0
is blocked on a default-constructed envelope.

Bug 2: CommunicationConstraintConfig defaults to internal_only=True,
blocking all external communication on default-constructed envelopes.
Most agents need external communication; the predefined postures already
set explicit values per trust level.
"""
import pytest

from kailash.trust.pact.config import (
    CommunicationConstraintConfig,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
)


@pytest.mark.regression
class TestRestrictiveDefaults:
    """Default-constructed envelopes should not block legitimate operations."""

    def test_financial_defaults_to_none(self) -> None:
        """ConstraintEnvelopeConfig().financial should be None (skip dimension)."""
        envelope = ConstraintEnvelopeConfig(id="test-default")
        assert envelope.financial is None, (
            "financial should default to None per M23/2301 -- "
            "not FinancialConstraintConfig(max_spend_usd=0.0)"
        )

    def test_communication_internal_only_defaults_false(self) -> None:
        """CommunicationConstraintConfig().internal_only should be False."""
        comm = CommunicationConstraintConfig()
        assert comm.internal_only is False, (
            "internal_only should default to False -- "
            "agents should not be restricted to internal channels by default"
        )

    def test_default_envelope_allows_external_communication(self) -> None:
        """A default envelope should not block external communication."""
        envelope = ConstraintEnvelopeConfig(id="test-default")
        assert envelope.communication.internal_only is False

    def test_default_envelope_skips_financial_evaluation(self) -> None:
        """A default envelope with financial=None should not block cost actions."""
        envelope = ConstraintEnvelopeConfig(id="test-default")
        # financial is None, so the engine skips financial evaluation entirely
        assert envelope.financial is None

    def test_explicit_financial_still_works(self) -> None:
        """Explicit FinancialConstraintConfig still enforces limits."""
        fin = FinancialConstraintConfig(max_spend_usd=100.0)
        assert fin.max_spend_usd == 100.0

    def test_explicit_internal_only_still_works(self) -> None:
        """Explicit internal_only=True still restricts communication."""
        comm = CommunicationConstraintConfig(internal_only=True)
        assert comm.internal_only is True
