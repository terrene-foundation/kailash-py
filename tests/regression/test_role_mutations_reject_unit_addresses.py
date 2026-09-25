# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Role mutation APIs must not promote department/team nodes to identities."""

import pytest

from kailash.trust.pact.access import KnowledgeItem, PactBridge, can_access
from kailash.trust.pact.clearance import RoleClearance, VettingStatus
from kailash.trust.pact.compilation import RoleDefinition, compile_org
from kailash.trust.pact.config import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    DepartmentConfig,
    OrgDefinition,
    TeamConfig,
    TrustPostureLevel,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelopes import RoleEnvelope
from kailash.trust.pact.exceptions import PactError

pytestmark = pytest.mark.regression


def _engine() -> GovernanceEngine:
    return GovernanceEngine(
        compile_org(
            OrgDefinition(
                org_id="role-types",
                name="Role types",
                departments=[DepartmentConfig(department_id="eng", name="Engineering")],
                teams=[TeamConfig(id="backend", name="Backend", workspace="backend")],
                roles=[
                    RoleDefinition(
                        role_id="owner",
                        name="Owner",
                        reports_to_role_id=None,
                        is_primary_for_unit="eng",
                    ),
                    RoleDefinition(
                        role_id="worker",
                        name="Worker",
                        reports_to_role_id="owner",
                        is_primary_for_unit="backend",
                    ),
                ],
            )
        )
    )


@pytest.mark.parametrize("unit_id", ["eng", "backend"])
@pytest.mark.parametrize(
    "mutation",
    ["grant", "revoke", "transition", "define", "target", "bridge_a", "bridge_b"],
)
def test_role_mutation_rejects_non_role_node(unit_id: str, mutation: str) -> None:
    engine = _engine()
    nodes = {node.node_id: node.address for node in engine.get_org().nodes.values()}
    unit, owner, worker = nodes[unit_id], nodes["owner"], nodes["worker"]
    clearance = RoleClearance(
        role_address=unit, max_clearance=ConfidentialityLevel.PUBLIC
    )
    # Legacy state ensures revoke/transition cannot pass only because no record exists.
    engine._clearance_store.grant_clearance(clearance)
    with pytest.raises(PactError, match="resolve"):
        if mutation == "grant":
            engine.grant_clearance(unit, clearance)
        elif mutation == "revoke":
            engine.revoke_clearance(unit)
        elif mutation == "transition":
            engine.transition_clearance(unit, VettingStatus.SUSPENDED)
        elif mutation in {"define", "target"}:
            engine.set_role_envelope(
                RoleEnvelope(
                    id="unit-envelope",
                    defining_role_address=unit if mutation == "define" else owner,
                    target_role_address=unit if mutation == "target" else worker,
                    envelope=ConstraintEnvelopeConfig(id="unit-constraints"),
                )
            )
        else:
            engine.create_bridge(
                PactBridge(
                    id="unit-bridge",
                    bridge_type="standing",
                    role_a_address=unit if mutation == "bridge_a" else owner,
                    role_b_address=unit if mutation == "bridge_b" else worker,
                    max_classification=ConfidentialityLevel.PUBLIC,
                )
            )


def test_real_role_grant_still_authorizes_real_team_access() -> None:
    engine = _engine()
    nodes = {node.node_id: node.address for node in engine.get_org().nodes.values()}
    item = KnowledgeItem(
        item_id="team-item",
        classification=ConfidentialityLevel.PUBLIC,
        owning_unit_address=nodes["backend"],
    )
    assert not engine.check_access(
        nodes["owner"], item, TrustPostureLevel.AUTONOMOUS
    ).allowed
    engine.grant_clearance(
        "owner",
        RoleClearance(
            role_address=nodes["owner"], max_clearance=ConfidentialityLevel.PUBLIC
        ),
    )
    assert engine.check_access(
        nodes["owner"], item, TrustPostureLevel.AUTONOMOUS
    ).allowed


@pytest.mark.parametrize("unit_id", ["eng", "backend"])
def test_legacy_unit_clearance_cannot_authorize_access(unit_id: str) -> None:
    engine = _engine()
    nodes = {node.node_id: node.address for node in engine.get_org().nodes.values()}
    unit = nodes[unit_id]
    clearance = RoleClearance(
        role_address=unit, max_clearance=ConfidentialityLevel.PUBLIC
    )
    engine._clearance_store.grant_clearance(clearance)
    item = KnowledgeItem(
        item_id="team",
        classification=ConfidentialityLevel.PUBLIC,
        owning_unit_address=nodes["backend"],
    )
    direct = can_access(
        unit,
        item,
        TrustPostureLevel.AUTONOMOUS,
        engine.get_org(),
        {unit: clearance},
        [],
        [],
    )
    assert not direct.allowed
    assert direct.step_failed == 1
    assert not engine.check_access(unit, item, TrustPostureLevel.AUTONOMOUS).allowed


@pytest.mark.parametrize("unit_id", ["eng", "backend"])
@pytest.mark.parametrize(
    "mutation", ["consent", "compliance", "approve", "reject", "context"]
)
def test_bridge_authority_and_context_require_roles(
    unit_id: str, mutation: str
) -> None:
    engine = _engine()
    nodes = {node.node_id: node.address for node in engine.get_org().nodes.values()}
    unit, owner, worker = nodes[unit_id], nodes["owner"], nodes["worker"]
    engine.approve_bridge(owner, worker, owner)
    # Legacy registration must not let a non-role approve or revoke approval.
    engine._compliance_role = unit
    with pytest.raises(PactError):
        if mutation == "consent":
            engine.consent_bridge(unit, "bridge")
        elif mutation == "compliance":
            engine.register_compliance_role(unit)
        elif mutation == "approve":
            engine.approve_bridge(owner, worker, unit)
        elif mutation == "reject":
            engine.reject_bridge(owner, worker, unit)
        else:
            engine.get_context(unit)


def test_raw_access_rejects_a_clearance_for_another_role() -> None:
    engine = _engine()
    nodes = {node.node_id: node.address for node in engine.get_org().nodes.values()}
    owner, worker = nodes["owner"], nodes["worker"]
    item = KnowledgeItem(
        item_id="team",
        classification=ConfidentialityLevel.PUBLIC,
        owning_unit_address=nodes["backend"],
    )
    for record_address, allowed in ((owner, True), (worker, False)):
        clearance = RoleClearance(
            role_address=record_address, max_clearance=ConfidentialityLevel.PUBLIC
        )
        decision = can_access(
            owner,
            item,
            TrustPostureLevel.AUTONOMOUS,
            engine.get_org(),
            {owner: clearance},
            [],
            [],
        )
        assert decision.allowed is allowed


@pytest.mark.parametrize("unit_id", ["eng", "backend"])
def test_yaml_role_resolution_rejects_non_role_nodes(unit_id: str) -> None:
    from kailash.trust.pact.yaml_loader import ConfigurationError
    from kailash.trust.pact.yaml_resolvers import _resolve_role_address

    org = _engine().get_org()
    address = next(
        node.address for node in org.nodes.values() if node.node_id == unit_id
    )
    with pytest.raises(ConfigurationError):
        _resolve_role_address(org, address, ctx="regression")
    assert _resolve_role_address(org, "owner", ctx="control") == "D1-R1"
