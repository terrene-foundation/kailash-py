# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for EATP public API exports (TODO-009).

Verifies that the top-level ``eatp`` package exposes all types that users
need without requiring them to dig into sub-module paths.

Written BEFORE the __init__.py change (TDD).  Tests define the contract:
- ConfidentialityLevel and ReasoningTrace importable from ``eatp``
- ConstraintType importable from ``eatp``
- All three names present in ``eatp.__all__``
- Existing exports are not broken by the additions
"""

import pytest


# ---------------------------------------------------------------------------
# 1. Importability from the top-level package
# ---------------------------------------------------------------------------


class TestReasoningExports:
    """ConfidentialityLevel and ReasoningTrace must be importable from kailash.trust."""

    def test_confidentiality_level_importable_from_eatp(self):
        from kailash.trust import ConfidentialityLevel

        # Verify it is the real enum, not some re-export accident
        assert hasattr(ConfidentialityLevel, "PUBLIC")
        assert hasattr(ConfidentialityLevel, "RESTRICTED")
        assert hasattr(ConfidentialityLevel, "TOP_SECRET")

    def test_reasoning_trace_importable_from_eatp(self):
        from kailash.trust import ReasoningTrace

        # Verify it is the real dataclass with expected fields
        field_names = set(ReasoningTrace.__dataclass_fields__.keys())
        assert "decision" in field_names
        assert "rationale" in field_names
        assert "confidentiality" in field_names
        assert "timestamp" in field_names

    def test_confidentiality_level_enum_values(self):
        """Ensure all five classification levels are accessible."""
        from kailash.trust import ConfidentialityLevel

        expected = {"public", "restricted", "confidential", "secret", "top_secret"}
        actual = {level.value for level in ConfidentialityLevel}
        assert actual == expected

    def test_reasoning_trace_identity(self):
        """The eatp-level import must be the exact same class as eatp.reasoning."""
        from kailash.trust import (
            ConfidentialityLevel as CL_top,
            ReasoningTrace as RT_top,
        )
        from kailash.trust.reasoning.traces import (
            ConfidentialityLevel as CL_mod,
            ReasoningTrace as RT_mod,
        )

        assert CL_top is CL_mod, "ConfidentialityLevel must be the same object"
        assert RT_top is RT_mod, "ReasoningTrace must be the same object"


class TestConstraintTypeExport:
    """ConstraintType must be importable from kailash.trust (not just eatp.chain)."""

    def test_constraint_type_importable_from_eatp(self):
        from kailash.trust import ConstraintType

        assert hasattr(ConstraintType, "REASONING_REQUIRED")

    def test_constraint_type_reasoning_required_value(self):
        from kailash.trust import ConstraintType

        assert ConstraintType.REASONING_REQUIRED.value == "reasoning_required"

    def test_constraint_type_identity(self):
        """The eatp-level import must be the exact same class as eatp.chain."""
        from kailash.trust import ConstraintType as CT_top
        from kailash.trust.chain import ConstraintType as CT_mod

        assert CT_top is CT_mod, "ConstraintType must be the same object"


# ---------------------------------------------------------------------------
# 2. __all__ membership
# ---------------------------------------------------------------------------


class TestAllExports:
    """New types must be listed in eatp.__all__."""

    def test_confidentiality_level_in_all(self):
        import kailash.trust

        assert "ConfidentialityLevel" in kailash.trust.__all__

    def test_reasoning_trace_in_all(self):
        import kailash.trust

        assert "ReasoningTrace" in kailash.trust.__all__

    def test_constraint_type_in_all(self):
        import kailash.trust

        assert "ConstraintType" in kailash.trust.__all__


# ---------------------------------------------------------------------------
# 3. Existing exports are not broken
# ---------------------------------------------------------------------------


class TestExistingExportsIntact:
    """Adding new exports must not break any existing ones."""

    @pytest.mark.parametrize(
        "name",
        [
            "TrustOperations",
            "TrustKeyManager",
            "CapabilityRequest",
            "TrustLineageChain",
            "GenesisRecord",
            "DelegationRecord",
            "CapabilityAttestation",
            "ConstraintEnvelope",
            "AuditAnchor",
            "VerificationResult",
            "VerificationLevel",
            "AuthorityType",
            "CapabilityType",
            "TrustStore",
            "InMemoryTrustStore",
            "generate_keypair",
            "sign",
            "verify_signature",
            "OrganizationalAuthority",
            "AuthorityPermission",
            "TrustPosture",
            "PostureStateMachine",
            "TrustError",
            "TrustChainNotFoundError",
        ],
    )
    def test_existing_export_still_importable(self, name):
        import kailash.trust

        assert hasattr(
            kailash.trust, name
        ), f"{name} missing from kailash.trust after changes"
        assert (
            name in kailash.trust.__all__
        ), f"{name} missing from kailash.trust.__all__"
