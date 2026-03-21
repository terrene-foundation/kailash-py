# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for PACT governance audit -- EATP Audit Anchor subtypes.

Covers:
- TODO-4003: PactAuditAction enum values
- create_pact_audit_details() output structure
- barrier_enforced includes step_failed
- All 10 action types
"""

from __future__ import annotations

import pytest

from pact.governance.audit import PactAuditAction, create_pact_audit_details


# ===========================================================================
# PactAuditAction enum
# ===========================================================================


class TestPactAuditAction:
    """PactAuditAction enum values and string backing."""

    def test_is_string_enum(self) -> None:
        assert isinstance(PactAuditAction.ENVELOPE_CREATED, str)

    def test_envelope_created_value(self) -> None:
        assert PactAuditAction.ENVELOPE_CREATED.value == "envelope_created"

    def test_envelope_modified_value(self) -> None:
        assert PactAuditAction.ENVELOPE_MODIFIED.value == "envelope_modified"

    def test_clearance_granted_value(self) -> None:
        assert PactAuditAction.CLEARANCE_GRANTED.value == "clearance_granted"

    def test_clearance_revoked_value(self) -> None:
        assert PactAuditAction.CLEARANCE_REVOKED.value == "clearance_revoked"

    def test_barrier_enforced_value(self) -> None:
        assert PactAuditAction.BARRIER_ENFORCED.value == "barrier_enforced"

    def test_ksp_created_value(self) -> None:
        assert PactAuditAction.KSP_CREATED.value == "ksp_created"

    def test_ksp_revoked_value(self) -> None:
        assert PactAuditAction.KSP_REVOKED.value == "ksp_revoked"

    def test_bridge_established_value(self) -> None:
        assert PactAuditAction.BRIDGE_ESTABLISHED.value == "bridge_established"

    def test_bridge_revoked_value(self) -> None:
        assert PactAuditAction.BRIDGE_REVOKED.value == "bridge_revoked"

    def test_address_computed_value(self) -> None:
        assert PactAuditAction.ADDRESS_COMPUTED.value == "address_computed"

    def test_all_ten_actions_exist(self) -> None:
        """Exactly 10 action types per thesis Section 5.7 normative mapping."""
        assert len(PactAuditAction) == 10


# ===========================================================================
# create_pact_audit_details
# ===========================================================================


class TestCreatePactAuditDetails:
    """create_pact_audit_details() output structure and field handling."""

    def test_minimal_details(self) -> None:
        details = create_pact_audit_details(
            PactAuditAction.ENVELOPE_CREATED,
            role_address="D1-R1",
        )
        assert details["pact_action"] == "envelope_created"
        assert details["role_address"] == "D1-R1"

    def test_target_address_included_when_present(self) -> None:
        details = create_pact_audit_details(
            PactAuditAction.CLEARANCE_GRANTED,
            role_address="D1-R1",
            target_address="D1-R1-T1-R1",
        )
        assert details["target_address"] == "D1-R1-T1-R1"

    def test_target_address_excluded_when_empty(self) -> None:
        details = create_pact_audit_details(
            PactAuditAction.CLEARANCE_GRANTED,
            role_address="D1-R1",
        )
        assert "target_address" not in details

    def test_reason_included_when_present(self) -> None:
        details = create_pact_audit_details(
            PactAuditAction.CLEARANCE_REVOKED,
            role_address="D1-R1-T1-R1",
            reason="NDA expired",
        )
        assert details["reason"] == "NDA expired"

    def test_reason_excluded_when_empty(self) -> None:
        details = create_pact_audit_details(
            PactAuditAction.CLEARANCE_REVOKED,
            role_address="D1-R1-T1-R1",
        )
        assert "reason" not in details

    def test_barrier_enforced_includes_step_failed(self) -> None:
        """barrier_enforced actions should include the step_failed field."""
        details = create_pact_audit_details(
            PactAuditAction.BARRIER_ENFORCED,
            role_address="D1-R1-T1-R1",
            step_failed=3,
            reason="Missing compartments",
        )
        assert details["pact_action"] == "barrier_enforced"
        assert details["step_failed"] == 3
        assert details["reason"] == "Missing compartments"

    def test_step_failed_excluded_when_none(self) -> None:
        details = create_pact_audit_details(
            PactAuditAction.ENVELOPE_CREATED,
            role_address="D1-R1",
        )
        assert "step_failed" not in details

    def test_extra_kwargs_included(self) -> None:
        details = create_pact_audit_details(
            PactAuditAction.KSP_CREATED,
            role_address="D1-R1",
            ksp_id="ksp-42",
            source_unit="D1",
            target_unit="D2",
        )
        assert details["ksp_id"] == "ksp-42"
        assert details["source_unit"] == "D1"
        assert details["target_unit"] == "D2"

    def test_bridge_established_details(self) -> None:
        details = create_pact_audit_details(
            PactAuditAction.BRIDGE_ESTABLISHED,
            role_address="D1-R1",
            target_address="D2-R1",
            bridge_type="standing",
        )
        assert details["pact_action"] == "bridge_established"
        assert details["bridge_type"] == "standing"

    def test_address_computed_details(self) -> None:
        details = create_pact_audit_details(
            PactAuditAction.ADDRESS_COMPUTED,
            role_address="D1-R1-D2-R1-T1-R1",
        )
        assert details["pact_action"] == "address_computed"
        assert details["role_address"] == "D1-R1-D2-R1-T1-R1"

    def test_all_fields_populated(self) -> None:
        """Full details dict with every field populated."""
        details = create_pact_audit_details(
            PactAuditAction.BARRIER_ENFORCED,
            role_address="D1-R1-T1-R1",
            target_address="D2-R1",
            reason="Classification exceeded",
            step_failed=2,
            effective_clearance="restricted",
            item_classification="confidential",
        )
        assert details["pact_action"] == "barrier_enforced"
        assert details["role_address"] == "D1-R1-T1-R1"
        assert details["target_address"] == "D2-R1"
        assert details["reason"] == "Classification exceeded"
        assert details["step_failed"] == 2
        assert details["effective_clearance"] == "restricted"
        assert details["item_classification"] == "confidential"
