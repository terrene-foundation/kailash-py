# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for audit log integrity (hash chain verification).

Covers:
- TODO-7044: Audit chain integrity
- content_hash = SHA-256 of details_json
- chain_hash = SHA-256 of (previous_chain_hash + content_hash)
- Append-only: no UPDATE or DELETE allowed
- engine.verify_audit_integrity() walks chain and verifies all hashes
- Tamper detection: modified entries detected
"""

from __future__ import annotations

import hashlib
import json

import pytest

from pact.build.config.schema import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
)
from pact.governance.compilation import CompiledOrg, OrgNode
from pact.governance.stores.sqlite import (
    SqliteAccessPolicyStore,
    SqliteClearanceStore,
    SqliteEnvelopeStore,
    SqliteOrgStore,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_compiled_org(org_id: str = "test-org") -> CompiledOrg:
    org = CompiledOrg(org_id=org_id)
    from pact.governance.addressing import NodeType

    org.nodes["D1"] = OrgNode(
        address="D1", node_type=NodeType.DEPARTMENT, name="Eng", node_id="eng"
    )
    org.nodes["D1-R1"] = OrgNode(
        address="D1-R1",
        node_type=NodeType.ROLE,
        name="Lead",
        node_id="lead",
        parent_address="D1",
    )
    return org


# ===========================================================================
# Audit Chain Integrity
# ===========================================================================


class TestAuditIntegrity:
    """Verify audit chain hash integrity mechanism."""

    def test_audit_log_records_content_hash(self) -> None:
        """Each audit entry should have content_hash = SHA-256(details_json)."""
        from pact.governance.stores.sqlite import SqliteAuditLog

        log = SqliteAuditLog(":memory:")
        log.append("test_action", {"key": "value"})
        entries = log.get_all_entries()
        assert len(entries) == 1

        entry = entries[0]
        expected_content_hash = hashlib.sha256(
            json.dumps({"key": "value"}, sort_keys=True).encode()
        ).hexdigest()
        assert entry["content_hash"] == expected_content_hash

    def test_audit_log_chain_hash_links(self) -> None:
        """chain_hash should link each entry to its predecessor."""
        from pact.governance.stores.sqlite import SqliteAuditLog

        log = SqliteAuditLog(":memory:")
        log.append("action_1", {"step": 1})
        log.append("action_2", {"step": 2})
        log.append("action_3", {"step": 3})

        entries = log.get_all_entries()
        assert len(entries) == 3

        # First entry: chain_hash = SHA-256("" + content_hash)
        first_content = hashlib.sha256(json.dumps({"step": 1}, sort_keys=True).encode()).hexdigest()
        first_chain = hashlib.sha256(("" + first_content).encode()).hexdigest()
        assert entries[0]["chain_hash"] == first_chain

        # Second entry: chain_hash = SHA-256(first_chain + second_content)
        second_content = hashlib.sha256(
            json.dumps({"step": 2}, sort_keys=True).encode()
        ).hexdigest()
        second_chain = hashlib.sha256((first_chain + second_content).encode()).hexdigest()
        assert entries[1]["chain_hash"] == second_chain

        # Third entry
        third_content = hashlib.sha256(json.dumps({"step": 3}, sort_keys=True).encode()).hexdigest()
        third_chain = hashlib.sha256((second_chain + third_content).encode()).hexdigest()
        assert entries[2]["chain_hash"] == third_chain

    def test_verify_audit_integrity_valid(self) -> None:
        """verify_audit_integrity returns True for an untampered chain."""
        from pact.governance.stores.sqlite import SqliteAuditLog

        log = SqliteAuditLog(":memory:")
        for i in range(5):
            log.append(f"action_{i}", {"index": i})

        is_valid, error = log.verify_integrity()
        assert is_valid is True
        assert error is None

    def test_verify_audit_integrity_empty(self) -> None:
        """Empty audit log should verify successfully."""
        from pact.governance.stores.sqlite import SqliteAuditLog

        log = SqliteAuditLog(":memory:")
        is_valid, error = log.verify_integrity()
        assert is_valid is True
        assert error is None

    def test_verify_audit_integrity_detects_tampered_content(self) -> None:
        """If details_json is modified, verify_integrity detects the mismatch."""
        from pact.governance.stores.sqlite import SqliteAuditLog

        log = SqliteAuditLog(":memory:")
        log.append("action_1", {"original": True})
        log.append("action_2", {"original": True})

        # Tamper with the first entry's details_json directly via SQL
        conn = log._get_connection()
        conn.execute(
            "UPDATE pact_audit_log SET details_json = ? WHERE id = 1",
            (json.dumps({"tampered": True}),),
        )
        conn.commit()

        is_valid, error = log.verify_integrity()
        assert is_valid is False
        assert error is not None
        assert "content_hash" in error.lower() or "tamper" in error.lower()

    def test_verify_audit_integrity_detects_tampered_chain(self) -> None:
        """If chain_hash is modified, verify_integrity detects it."""
        from pact.governance.stores.sqlite import SqliteAuditLog

        log = SqliteAuditLog(":memory:")
        log.append("action_1", {"step": 1})
        log.append("action_2", {"step": 2})

        # Tamper with chain_hash of first entry
        conn = log._get_connection()
        conn.execute(
            "UPDATE pact_audit_log SET chain_hash = ? WHERE id = 1",
            ("deadbeef" * 8,),
        )
        conn.commit()

        is_valid, error = log.verify_integrity()
        assert is_valid is False
        assert error is not None

    def test_audit_log_append_only_design(self) -> None:
        """The append method only inserts, never updates or deletes."""
        from pact.governance.stores.sqlite import SqliteAuditLog

        log = SqliteAuditLog(":memory:")
        log.append("action_1", {"data": "first"})
        log.append("action_2", {"data": "second"})

        entries = log.get_all_entries()
        assert len(entries) == 2
        assert entries[0]["action"] == "action_1"
        assert entries[1]["action"] == "action_2"


# ===========================================================================
# Engine Integration with Audit Integrity
# ===========================================================================


class TestEngineAuditIntegrity:
    """GovernanceEngine.verify_audit_integrity() end-to-end."""

    def test_engine_verify_audit_integrity(self) -> None:
        from pact.governance.engine import GovernanceEngine
        from pact.governance.clearance import RoleClearance, VettingStatus

        org = _make_compiled_org("audit-test")
        engine = GovernanceEngine(
            org,
            store_backend="sqlite",
            store_url=":memory:",
        )

        # Perform some mutations that emit audit entries
        clr = RoleClearance(
            role_address="D1-R1",
            max_clearance=ConfidentialityLevel.CONFIDENTIAL,
            granted_by_role_address="R1",
            vetting_status=VettingStatus.ACTIVE,
        )
        engine.grant_clearance("D1-R1", clr)

        # Verify integrity
        is_valid, error = engine.verify_audit_integrity()
        assert is_valid is True
        assert error is None

    def test_engine_verify_audit_integrity_no_audit_log(self) -> None:
        """Engine without audit log should report integrity as valid (no entries)."""
        from pact.governance.engine import GovernanceEngine

        org = _make_compiled_org("no-audit-test")
        engine = GovernanceEngine(org)  # memory backend, no sqlite audit log

        is_valid, error = engine.verify_audit_integrity()
        assert is_valid is True
        assert error is None
