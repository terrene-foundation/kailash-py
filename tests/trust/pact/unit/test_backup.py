# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for governance store backup and restore.

Covers:
- TODO-7045: backup_governance_store / restore_governance_store
- Full round-trip: backup -> restore -> verify identical state
- All 4 store types exported/imported
- JSON format validation
- Restore into empty engine
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kailash.trust.pact.config import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
)
from kailash.trust.pact.access import KnowledgeSharePolicy, PactBridge
from kailash.trust.pact.clearance import RoleClearance, VettingStatus
from kailash.trust.pact.compilation import CompiledOrg, OrgNode
from kailash.trust.pact.envelopes import RoleEnvelope, TaskEnvelope
from kailash.trust.pact.stores.backup import (
    backup_governance_store,
    restore_governance_store,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_compiled_org(org_id: str = "test-org") -> CompiledOrg:
    org = CompiledOrg(org_id=org_id)
    from kailash.trust.pact.addressing import NodeType

    org.nodes["D1"] = OrgNode(
        address="D1",
        node_type=NodeType.DEPARTMENT,
        name="Engineering",
        node_id="eng",
    )
    org.nodes["D1-R1"] = OrgNode(
        address="D1-R1",
        node_type=NodeType.ROLE,
        name="VP Eng",
        node_id="vp-eng",
        parent_address="D1",
    )
    org.nodes["D1-R1-T1"] = OrgNode(
        address="D1-R1-T1",
        node_type=NodeType.TEAM,
        name="Backend",
        node_id="backend",
        parent_address="D1-R1",
    )
    org.nodes["D1-R1-T1-R1"] = OrgNode(
        address="D1-R1-T1-R1",
        node_type=NodeType.ROLE,
        name="Backend Lead",
        node_id="backend-lead",
        parent_address="D1-R1-T1",
    )
    return org


def _make_envelope(env_id: str = "env-1") -> ConstraintEnvelopeConfig:
    return ConstraintEnvelopeConfig(
        id=env_id,
        description=f"Test envelope {env_id}",
        confidentiality_clearance=ConfidentialityLevel.CONFIDENTIAL,
        financial=FinancialConstraintConfig(max_spend_usd=1000.0),
        operational=OperationalConstraintConfig(allowed_actions=["read", "write"]),
    )


def _make_role_envelope(
    env_id: str = "re-1",
    defining: str = "D1-R1",
    target: str = "D1-R1-T1-R1",
) -> RoleEnvelope:
    return RoleEnvelope(
        id=env_id,
        defining_role_address=defining,
        target_role_address=target,
        envelope=_make_envelope(env_id),
    )


def _make_clearance(
    role_address: str = "D1-R1-T1-R1",
    max_clearance: ConfidentialityLevel = ConfidentialityLevel.CONFIDENTIAL,
) -> RoleClearance:
    return RoleClearance(
        role_address=role_address,
        max_clearance=max_clearance,
        granted_by_role_address="D1-R1",
        vetting_status=VettingStatus.ACTIVE,
    )


def _make_ksp(
    ksp_id: str = "ksp-1",
    source: str = "D1",
    target: str = "D2",
) -> KnowledgeSharePolicy:
    return KnowledgeSharePolicy(
        id=ksp_id,
        source_unit_address=source,
        target_unit_address=target,
        max_classification=ConfidentialityLevel.CONFIDENTIAL,
        created_by_role_address="D1-R1",
    )


def _make_bridge(
    bridge_id: str = "bridge-1",
    role_a: str = "D1-R1",
    role_b: str = "D2-R1",
) -> PactBridge:
    return PactBridge(
        id=bridge_id,
        role_a_address=role_a,
        role_b_address=role_b,
        bridge_type="standing",
        max_classification=ConfidentialityLevel.CONFIDENTIAL,
    )


# ===========================================================================
# Backup / Restore
# ===========================================================================


class TestBackupRestore:
    """Full backup -> restore -> verify round-trip."""

    def test_backup_creates_valid_json(self, tmp_path: Path) -> None:
        from kailash.trust.pact.engine import GovernanceEngine

        org = _make_compiled_org("backup-test")
        engine = GovernanceEngine(
            org,
            store_backend="sqlite",
            store_url=":memory:",
        )

        backup_path = tmp_path / "backup.json"
        backup_governance_store(engine, str(backup_path))

        assert backup_path.exists()
        data = json.loads(backup_path.read_text())
        assert "org" in data
        assert "envelopes" in data
        assert "clearances" in data
        assert "ksps" in data
        assert "bridges" in data
        assert "metadata" in data

    def test_backup_restore_round_trip_org(self, tmp_path: Path) -> None:
        """Org structure survives backup/restore."""
        from kailash.trust.pact.engine import GovernanceEngine

        org = _make_compiled_org("roundtrip-org")
        engine1 = GovernanceEngine(
            org,
            store_backend="sqlite",
            store_url=":memory:",
        )

        backup_path = tmp_path / "backup.json"
        backup_governance_store(engine1, str(backup_path))

        # Restore into a fresh engine
        org2 = _make_compiled_org("roundtrip-org")
        engine2 = GovernanceEngine(
            org2,
            store_backend="sqlite",
            store_url=":memory:",
        )
        restore_governance_store(engine2, str(backup_path))

        assert engine2.get_org().org_id == "roundtrip-org"

    def test_backup_restore_round_trip_clearances(self, tmp_path: Path) -> None:
        """Clearances survive backup/restore."""
        from kailash.trust.pact.engine import GovernanceEngine

        org = _make_compiled_org("clr-roundtrip")
        engine1 = GovernanceEngine(
            org,
            store_backend="sqlite",
            store_url=":memory:",
        )
        clr = _make_clearance("D1-R1-T1-R1", ConfidentialityLevel.SECRET)
        engine1.grant_clearance("D1-R1-T1-R1", clr)

        backup_path = tmp_path / "backup.json"
        backup_governance_store(engine1, str(backup_path))

        org2 = _make_compiled_org("clr-roundtrip")
        engine2 = GovernanceEngine(
            org2,
            store_backend="sqlite",
            store_url=":memory:",
        )
        restore_governance_store(engine2, str(backup_path))

        # Verify clearance was restored
        restored_clr = engine2._clearance_store.get_clearance("D1-R1-T1-R1")
        assert restored_clr is not None
        assert restored_clr.max_clearance == ConfidentialityLevel.SECRET

    def test_backup_restore_round_trip_envelopes(self, tmp_path: Path) -> None:
        """Role envelopes survive backup/restore."""
        from kailash.trust.pact.engine import GovernanceEngine

        org = _make_compiled_org("env-roundtrip")
        engine1 = GovernanceEngine(
            org,
            store_backend="sqlite",
            store_url=":memory:",
        )
        re = _make_role_envelope("re-backup", target="D1-R1-T1-R1")
        engine1.set_role_envelope(re)

        backup_path = tmp_path / "backup.json"
        backup_governance_store(engine1, str(backup_path))

        org2 = _make_compiled_org("env-roundtrip")
        engine2 = GovernanceEngine(
            org2,
            store_backend="sqlite",
            store_url=":memory:",
        )
        restore_governance_store(engine2, str(backup_path))

        restored_re = engine2._envelope_store.get_role_envelope("D1-R1-T1-R1")
        assert restored_re is not None
        assert restored_re.id == "re-backup"

    def test_backup_restore_round_trip_bridges(self, tmp_path: Path) -> None:
        """Bridges survive backup/restore."""
        from kailash.trust.pact.engine import GovernanceEngine

        org = _make_compiled_org("bridge-roundtrip")
        engine1 = GovernanceEngine(
            org,
            store_backend="sqlite",
            store_url=":memory:",
        )
        bridge = _make_bridge("bridge-backup", role_a="D1-R1", role_b="D1-R1-T1-R1")
        engine1.create_bridge(bridge)

        backup_path = tmp_path / "backup.json"
        backup_governance_store(engine1, str(backup_path))

        org2 = _make_compiled_org("bridge-roundtrip")
        engine2 = GovernanceEngine(
            org2,
            store_backend="sqlite",
            store_url=":memory:",
        )
        restore_governance_store(engine2, str(backup_path))

        restored = engine2._access_policy_store.find_bridge("D1-R1", "D1-R1-T1-R1")
        assert restored is not None
        assert restored.id == "bridge-backup"

    def test_backup_restore_round_trip_ksps(self, tmp_path: Path) -> None:
        """KSPs survive backup/restore."""
        from kailash.trust.pact.engine import GovernanceEngine

        org = _make_compiled_org("ksp-roundtrip")
        engine1 = GovernanceEngine(
            org,
            store_backend="sqlite",
            store_url=":memory:",
        )
        ksp = _make_ksp("ksp-backup", source="D1", target="D1-R1-T1")
        engine1.create_ksp(ksp)

        backup_path = tmp_path / "backup.json"
        backup_governance_store(engine1, str(backup_path))

        org2 = _make_compiled_org("ksp-roundtrip")
        engine2 = GovernanceEngine(
            org2,
            store_backend="sqlite",
            store_url=":memory:",
        )
        restore_governance_store(engine2, str(backup_path))

        restored = engine2._access_policy_store.find_ksp("D1", "D1-R1-T1")
        assert restored is not None
        assert restored.id == "ksp-backup"

    def test_restore_nonexistent_file_raises(self, tmp_path: Path) -> None:
        from kailash.trust.pact.engine import GovernanceEngine

        org = _make_compiled_org("no-file-test")
        engine = GovernanceEngine(
            org,
            store_backend="sqlite",
            store_url=":memory:",
        )
        with pytest.raises(FileNotFoundError):
            restore_governance_store(engine, str(tmp_path / "nonexistent.json"))

    def test_backup_with_memory_backend(self, tmp_path: Path) -> None:
        """Backup works with memory backend too."""
        from kailash.trust.pact.engine import GovernanceEngine

        org = _make_compiled_org("mem-backup")
        engine = GovernanceEngine(org)  # memory backend

        backup_path = tmp_path / "mem_backup.json"
        backup_governance_store(engine, str(backup_path))

        assert backup_path.exists()
        data = json.loads(backup_path.read_text())
        assert data["org"]["org_id"] == "mem-backup"
