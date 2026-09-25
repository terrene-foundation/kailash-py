# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""A privileged backup restore preserves clearance state without re-granting it."""

import json
from pathlib import Path

import pytest

from kailash.trust.pact.access import KnowledgeSharePolicy
from kailash.trust.pact.audit import AuditChain
from kailash.trust.pact.clearance import RoleClearance, VettingStatus
from kailash.trust.pact.compilation import RoleDefinition, compile_org
from kailash.trust.pact.config import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    OrgDefinition,
    TrustPostureLevel,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import RoleEnvelope
from kailash.trust.pact.exceptions import PactError
from kailash.trust.pact.stores.backup import (
    backup_governance_store,
    restore_governance_store,
)

pytestmark = pytest.mark.regression


def _engine(*, removed: bool = False, **kwargs: object) -> GovernanceEngine:
    roles = [RoleDefinition(role_id="owner", name="Owner", reports_to_role_id=None)]
    if not removed:
        roles.append(
            RoleDefinition(role_id="worker", name="Worker", reports_to_role_id="owner")
        )
    return GovernanceEngine(
        compile_org(OrgDefinition(org_id="restore", name="Restore", roles=roles)),
        **kwargs,
    )


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_restore_clearance_for_role_removed_from_org(
    tmp_path: Path, backend: str
) -> None:
    source = _engine()
    address = next(
        addr
        for addr, node in source.get_org().nodes.items()
        if node.node_id == "worker"
    )
    clearance = RoleClearance(
        role_address=address,
        max_clearance=ConfidentialityLevel.CONFIDENTIAL,
        compartments=frozenset({"finance"}),
        granted_by_role_address="R1",
        vetting_status=VettingStatus.SUSPENDED,
        nda_signed=True,
    )
    source.grant_clearance(address, clearance)
    source._access_policy_store.save_ksp(
        KnowledgeSharePolicy(
            id="after-clearance",
            source_unit_address="D9",
            target_unit_address="D8",
            max_classification=ConfidentialityLevel.PUBLIC,
        )
    )
    path = tmp_path / "backup.json"
    backup_governance_store(source, str(path))
    target = _engine(
        removed=True, store_backend=backend, store_url=str(tmp_path / "target.db")
    )

    restore_governance_store(target, str(path))

    assert target._clearance_store.get_clearance(address) == clearance
    assert {k.id for k in target._access_policy_store.list_ksps()} == {
        "after-clearance"
    }
    # Restoring the record does not resurrect its removed role in the org.
    assert address not in target.get_org().nodes
    with pytest.raises(PactError):
        target.grant_clearance(address, clearance)


def test_restore_snapshot_is_not_a_live_vetting_transition(tmp_path: Path) -> None:
    source = _engine()
    pending = RoleClearance(
        role_address="R1",
        max_clearance=ConfidentialityLevel.PUBLIC,
        vetting_status=VettingStatus.PENDING,
    )
    source.grant_clearance("R1", pending)
    path = tmp_path / "pending.json"
    backup_governance_store(source, str(path))
    audit = AuditChain("clearance-restore")
    target = _engine(audit_chain=audit)
    target.grant_clearance(
        "R1",
        RoleClearance(role_address="R1", max_clearance=ConfidentialityLevel.PUBLIC),
    )
    with pytest.raises(PactError, match="Invalid vetting status transition"):
        target.grant_clearance("R1", pending)

    restore_governance_store(target, str(path))

    assert target._clearance_store.get_clearance("R1") == pending
    grants = [
        anchor for anchor in audit.anchors if anchor.action == "clearance_granted"
    ]
    assert len(grants) == 2
    assert grants[-1].metadata["role_address"] == "R1"
    assert grants[-1].metadata["vetting_status"] == "pending"


@pytest.mark.parametrize("record_address", ["R9", "R1-R1"])
def test_live_grant_rejects_a_different_record_target(record_address: str) -> None:
    engine = _engine()
    clearance = RoleClearance(
        role_address=record_address, max_clearance=ConfidentialityLevel.SECRET
    )
    with pytest.raises(PactError):
        engine.grant_clearance("R1", clearance)
    assert engine._clearance_store.get_clearance(record_address) is None


def test_live_grant_normalizes_matching_config_aliases() -> None:
    engine = _engine()
    clearance = RoleClearance(
        role_address="owner", max_clearance=ConfidentialityLevel.CONFIDENTIAL
    )
    engine.grant_clearance("R1", clearance)
    stored = engine._clearance_store.get_clearance("R1")
    assert stored is not None
    assert stored.role_address == "R1"
    assert stored.max_clearance == ConfidentialityLevel.CONFIDENTIAL
    assert engine._clearance_store.get_clearance("owner") is None


def _backup_with_child_envelope(path: Path) -> None:
    source = _engine()
    for role, limit in (("R1", 100), ("R1-R1", 25)):
        source.set_role_envelope(
            RoleEnvelope(
                id=role,
                defining_role_address="R1",
                target_role_address=role,
                envelope=ConstraintEnvelopeConfig(
                    id=role,
                    financial=FinancialConstraintConfig(max_spend_usd=limit),
                    operational=OperationalConstraintConfig(allowed_actions=["read"]),
                ),
            )
        )
    backup_governance_store(source, str(path))


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_restored_missing_target_envelope_is_inert(
    tmp_path: Path, backend: str
) -> None:
    path = tmp_path / "envelopes.json"
    _backup_with_child_envelope(path)
    target = _engine(
        removed=True, store_backend=backend, store_url=str(tmp_path / "envelopes.db")
    )
    restore_governance_store(target, str(path))
    assert target._envelope_store.get_role_envelope("R1-R1") is not None
    assert "R1-R1" not in target.get_org().nodes
    assert target.compute_envelope("R1").financial.max_spend_usd == 100
    assert target.verify_action("R1", "read").level == "auto_approved"
    assert target.verify_action("R1-R1", "read").level == "blocked"
    with pytest.raises(PactError):
        target.get_context("R1-R1", TrustPostureLevel.AUTONOMOUS)


@pytest.mark.parametrize("invalid", ["definer", "widening"])
def test_historical_envelope_still_checks_authority(
    tmp_path: Path, invalid: str
) -> None:
    path = tmp_path / "envelopes.json"
    _backup_with_child_envelope(path)
    data = json.loads(path.read_text())
    child = next(
        env for env in data["envelopes"] if env["target_role_address"] == "R1-R1"
    )
    if invalid == "definer":
        child["defining_role_address"] = "R9"
    else:
        child["envelope"]["financial"]["max_spend_usd"] = 101
    path.write_text(json.dumps(data))
    target = _engine(removed=True)
    with pytest.raises(PactError):
        restore_governance_store(target, str(path))
    assert target._envelope_store.get_role_envelope("R1-R1") is None
