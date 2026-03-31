# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: #191 — 'pseudo' posture rejected, only 'pseudo_agent' accepted.

The bug: TrustPosture("pseudo") raised ValueError. All other CARE-spec lowercase
posture names worked. Only L1 was broken because the enum value was "pseudo_agent".
Fix: _missing_ classmethod maps "pseudo" → PSEUDO_AGENT.

Cross-SDK: esperie-enterprise/kailash-rs#118
"""
import pytest

from kailash.trust.posture.postures import TrustPosture


@pytest.mark.regression
class TestIssue191PseudoPosture:
    """All CARE-spec posture names must parse correctly."""

    def test_pseudo_lowercase(self) -> None:
        assert TrustPosture("pseudo") is TrustPosture.PSEUDO_AGENT

    def test_pseudo_agent_still_works(self) -> None:
        assert TrustPosture("pseudo_agent") is TrustPosture.PSEUDO_AGENT

    def test_all_care_spec_names(self) -> None:
        """All 5 CARE-spec lowercase posture names must parse."""
        assert TrustPosture("delegated") is TrustPosture.DELEGATED
        assert TrustPosture("continuous_insight") is TrustPosture.CONTINUOUS_INSIGHT
        assert TrustPosture("shared_planning") is TrustPosture.SHARED_PLANNING
        assert TrustPosture("supervised") is TrustPosture.SUPERVISED
        assert TrustPosture("pseudo") is TrustPosture.PSEUDO_AGENT

    def test_case_insensitive(self) -> None:
        assert TrustPosture("PSEUDO") is TrustPosture.PSEUDO_AGENT
        assert TrustPosture("Pseudo") is TrustPosture.PSEUDO_AGENT

    def test_invalid_still_raises(self) -> None:
        with pytest.raises(ValueError):
            TrustPosture("nonexistent_posture")
