# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for ConfidentialityLevel alignment (TODO-04).

Verifies that kaizen-agents uses the canonical ConfidentialityLevel from
kailash.trust instead of the local DataClassification IntEnum, and that
the backward-compatibility alias works correctly.

Covers:
- Issue #60: Replace DataClassification with ConfidentialityLevel
- Issue #67: "restricted" was mapped to C1_INTERNAL instead of RESTRICTED
"""

from __future__ import annotations

import pytest

from kailash.trust import ConfidentialityLevel


@pytest.mark.regression
class TestConfidentialityAlignment:
    """Verify canonical ConfidentialityLevel is used throughout kaizen-agents."""

    def test_restricted_maps_to_restricted_not_internal(self) -> None:
        """Regression: #67 -- 'restricted' was mapped to C1_INTERNAL instead of RESTRICTED."""
        from kaizen_agents.supervisor import _CLEARANCE_MAP

        assert _CLEARANCE_MAP["restricted"] == ConfidentialityLevel.RESTRICTED

    def test_confidentiality_ordering(self) -> None:
        """ConfidentialityLevel supports < comparison for clearance enforcement."""
        assert ConfidentialityLevel.PUBLIC < ConfidentialityLevel.RESTRICTED
        assert ConfidentialityLevel.RESTRICTED < ConfidentialityLevel.CONFIDENTIAL
        assert ConfidentialityLevel.CONFIDENTIAL < ConfidentialityLevel.SECRET
        assert ConfidentialityLevel.SECRET < ConfidentialityLevel.TOP_SECRET

    def test_confidentiality_ordering_le(self) -> None:
        """ConfidentialityLevel supports <= comparison for clearance filtering."""
        assert ConfidentialityLevel.PUBLIC <= ConfidentialityLevel.PUBLIC
        assert ConfidentialityLevel.PUBLIC <= ConfidentialityLevel.RESTRICTED
        assert ConfidentialityLevel.SECRET <= ConfidentialityLevel.TOP_SECRET

    def test_confidentiality_ordering_ge(self) -> None:
        """ConfidentialityLevel supports >= comparison for monotonic floor."""
        assert ConfidentialityLevel.TOP_SECRET >= ConfidentialityLevel.SECRET
        assert ConfidentialityLevel.SECRET >= ConfidentialityLevel.SECRET
        assert ConfidentialityLevel.RESTRICTED >= ConfidentialityLevel.PUBLIC

    def test_max_works_for_classification(self) -> None:
        """max() works with ConfidentialityLevel for highest-classification selection."""
        result = max(ConfidentialityLevel.PUBLIC, ConfidentialityLevel.SECRET)
        assert result == ConfidentialityLevel.SECRET

    def test_backward_compat_alias_exists(self) -> None:
        """DataClassification is an alias for ConfidentialityLevel."""
        from kaizen_agents.governance.clearance import DataClassification

        assert DataClassification is ConfidentialityLevel

    def test_backward_compat_alias_in_governance_init(self) -> None:
        """DataClassification is re-exported from governance __init__."""
        from kaizen_agents.governance import DataClassification

        assert DataClassification is ConfidentialityLevel

    def test_clearance_map_uses_canonical_enum(self) -> None:
        """All _CLEARANCE_MAP values are ConfidentialityLevel instances."""
        from kaizen_agents.supervisor import _CLEARANCE_MAP

        for key, value in _CLEARANCE_MAP.items():
            assert isinstance(value, ConfidentialityLevel), (
                f"_CLEARANCE_MAP[{key!r}] is {type(value).__name__}, "
                f"expected ConfidentialityLevel"
            )

    def test_clearance_map_complete(self) -> None:
        """_CLEARANCE_MAP covers all expected user-facing strings."""
        from kaizen_agents.supervisor import _CLEARANCE_MAP

        expected_keys = {"public", "internal", "restricted", "confidential", "secret", "top_secret"}
        assert set(_CLEARANCE_MAP.keys()) == expected_keys

    def test_clearance_map_values(self) -> None:
        """_CLEARANCE_MAP maps to correct ConfidentialityLevel values."""
        from kaizen_agents.supervisor import _CLEARANCE_MAP

        assert _CLEARANCE_MAP["public"] == ConfidentialityLevel.PUBLIC
        assert _CLEARANCE_MAP["internal"] == ConfidentialityLevel.RESTRICTED
        assert _CLEARANCE_MAP["restricted"] == ConfidentialityLevel.RESTRICTED
        assert _CLEARANCE_MAP["confidential"] == ConfidentialityLevel.CONFIDENTIAL
        assert _CLEARANCE_MAP["secret"] == ConfidentialityLevel.SECRET
        assert _CLEARANCE_MAP["top_secret"] == ConfidentialityLevel.TOP_SECRET

    def test_classified_value_uses_confidentiality_level(self) -> None:
        """ClassifiedValue accepts ConfidentialityLevel for classification field."""
        from kaizen_agents.governance.clearance import ClassifiedValue

        cv = ClassifiedValue(
            key="test",
            value="data",
            classification=ConfidentialityLevel.SECRET,
        )
        assert cv.classification == ConfidentialityLevel.SECRET

    def test_clearance_enforcer_with_confidentiality_level(self) -> None:
        """ClearanceEnforcer works with ConfidentialityLevel values."""
        from kaizen_agents.governance.clearance import (
            ClassifiedValue,
            ClearanceEnforcer,
        )

        enforcer = ClearanceEnforcer()
        enforcer.register_value(ClassifiedValue("public", "hello", ConfidentialityLevel.PUBLIC))
        enforcer.register_value(ClassifiedValue("secret", "sk-123", ConfidentialityLevel.SECRET))

        visible = enforcer.filter_for_clearance(ConfidentialityLevel.RESTRICTED)
        assert "public" in visible
        assert "secret" not in visible

    def test_classification_assigner_returns_confidentiality_level(self) -> None:
        """ClassificationAssigner.classify() returns ConfidentialityLevel."""
        from kaizen_agents.governance.clearance import ClassificationAssigner

        assigner = ClassificationAssigner()
        level = assigner.classify("greeting", "hello world")
        assert isinstance(level, ConfidentialityLevel)

    def test_supervisor_clearance_level_is_confidentiality_level(self) -> None:
        """GovernedSupervisor.clearance_level returns ConfidentialityLevel."""
        from kaizen_agents.supervisor import GovernedSupervisor

        supervisor = GovernedSupervisor(data_clearance="confidential")
        assert isinstance(supervisor.clearance_level, ConfidentialityLevel)
        assert supervisor.clearance_level == ConfidentialityLevel.CONFIDENTIAL
