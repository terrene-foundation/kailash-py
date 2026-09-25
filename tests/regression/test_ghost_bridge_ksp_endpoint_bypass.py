# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests -- ``create_bridge`` / ``create_ksp`` never checked EXISTENCE.

Site 4 of issue #2238, the same absent-identifier-read-as-success class as the
``defining_role_address`` and ``parent_envelope_id`` sites.  Both methods
guarded the *shape* of their identifiers and never the *existence*:

``create_bridge`` ran ``Address.parse`` (which rejects malformed input and
nothing else -- ``"D9-R9"`` parses cleanly) and then computed the LCA
SYNTACTICALLY from the parsed strings.  A well-formed address naming no node
sailed through the parse, the LCA computation, the LCA-approval check, and the
bilateral-consent check, and the bridge was persisted.

``create_ksp`` performed no validation whatsoever -- not even a parse.

MEASURED on the unfixed tree, control-and-subject on real engines with real
stores::

    BRIDGE CONTROL   real pair (VP, LEAD) unapproved -> PactError
                     "Bridge requires approval from LCA: D1-R1"
    BRIDGE CONTROL   real pair, wrong approver       -> PactError
    BRIDGE CONTROL   real pair, LCA-approved         -> ACCEPTED
    BRIDGE SUBJECT   (VP, "D1-R1-T9-R9")   <- role_b exists nowhere
                     -> ACCEPTED and PERSISTED
    BRIDGE SUBJECT   ("D9-R9", "D9-R9-T9-R9")        -> ACCEPTED, with the
                     non-existent "D9-R9" recording the LCA approval

    KSP CONTROL      real units (source="D1", target="D2")
                     -> check_access flips False -> True
    KSP SUBJECT      source="D9"/target="D8"         -> ACCEPTED
    KSP SUBJECT      source="NOT-AN-ADDRESS"         -> ACCEPTED
    KSP SUBJECT      source=""                       -> ACCEPTED
    KSP SUBJECT      source="d1-r1" (case variant)   -> ACCEPTED

The controls are what make the subjects readable: they prove each gate is
REACHABLE, so a non-raising subject cannot be explained away as "the gate is
unreachable from this method".

PARITY IS THE RATIONALE.  The YAML authoring surface already resolves every one
of these identifiers fail-closed before it constructs the object --
``yaml_resolvers.resolve_bridge`` resolves ``role_a`` and ``role_b`` through
``_resolve_role_address``, and ``resolve_ksp`` resolves ``source`` and
``target`` through ``_resolve_unit_address``.  The engine methods were the only
surface that accepted a name nothing backs.

SCOPE, STATED HONESTLY.  For the bridge, an access escalation was NOT
demonstrated: a ghost endpoint matches no requesting role and its domain
matches no real owner, so the persisted record is inert at enforcement.  What
the fix closes is the unchecked, unreviewable WRITE -- a governance record that
asserts a connection between a real role and nothing.  For the KSP, an
unresolvable unit cannot prefix-match a real one (every well-formed prefix of a
real address is itself a node), so that too is a write-integrity fix rather
than a demonstrated escalation.

``created_by_role_address`` is deliberately NOT validated: the HTTP surface
records it through ``unverified_actor_claim`` (#2194) as a caller-asserted
audit label with no enforcement role, so resolving it would break that
contract.
"""

from __future__ import annotations

import pytest

from kailash.trust.pact.access import KnowledgeSharePolicy, PactBridge
from kailash.trust.pact.addressing import Address
from kailash.trust.pact.clearance import (
    ConfidentialityLevel,
    RoleClearance,
    TrustPostureLevel,
    VettingStatus,
)
from kailash.trust.pact.compilation import RoleDefinition, compile_org
from kailash.trust.pact.config import (
    DepartmentConfig,
    OrgDefinition,
    TeamConfig,
)
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.exceptions import PactError
from kailash.trust.pact.knowledge import KnowledgeItem

pytestmark = [pytest.mark.regression]

_POSTURE = TrustPostureLevel.SUPERVISED


def _org() -> OrgDefinition:
    return OrgDefinition(
        org_id="ghost-endpoint-org",
        name="Ghost Endpoint Org",
        departments=[
            DepartmentConfig(department_id="d-eng", name="Engineering"),
            DepartmentConfig(department_id="d-fin", name="Finance"),
        ],
        teams=[TeamConfig(id="t-backend", name="Backend", workspace="ws-backend")],
        roles=[
            RoleDefinition(
                role_id="r-vp",
                name="VP Engineering",
                reports_to_role_id=None,
                is_primary_for_unit="d-eng",
            ),
            RoleDefinition(
                role_id="r-lead",
                name="Lead Developer",
                reports_to_role_id="r-vp",
                is_primary_for_unit="t-backend",
            ),
            RoleDefinition(
                role_id="r-cfo",
                name="CFO",
                reports_to_role_id=None,
                is_primary_for_unit="d-fin",
            ),
        ],
    )


@pytest.fixture
def org_and_addrs() -> tuple[GovernanceEngine, dict[str, str]]:
    compiled = compile_org(_org())
    addresses = {node.name: addr for addr, node in compiled.nodes.items()}
    return GovernanceEngine(compiled), addresses


def _bridge(role_a: str, role_b: str, bridge_id: str = "br-subject") -> PactBridge:
    return PactBridge(
        id=bridge_id,
        role_a_address=role_a,
        role_b_address=role_b,
        bridge_type="standing",
        max_classification=ConfidentialityLevel.RESTRICTED,
    )


def _ksp(source: str, target: str, ksp_id: str = "ksp-subject") -> KnowledgeSharePolicy:
    return KnowledgeSharePolicy(
        id=ksp_id,
        source_unit_address=source,
        target_unit_address=target,
        max_classification=ConfidentialityLevel.RESTRICTED,
    )


# ===================================================================
# create_bridge -- CONTROL
# ===================================================================


def test_control_unapproved_real_bridge_is_refused(
    org_and_addrs: tuple[GovernanceEngine, dict[str, str]],
) -> None:
    """Known-answer control: the LCA-approval gate is reachable and fires."""
    engine, addrs = org_and_addrs
    with pytest.raises(PactError) as excinfo:
        engine.create_bridge(_bridge(addrs["VP Engineering"], addrs["Lead Developer"]))
    assert "requires approval" in str(excinfo.value).lower()


def test_control_approved_real_bridge_is_created(
    org_and_addrs: tuple[GovernanceEngine, dict[str, str]],
) -> None:
    """Known-answer control: the same call SUCCEEDS once the LCA approves.

    Without this pole, a fix that refused every bridge would satisfy the
    refusal assertions below for the wrong reason.
    """
    engine, addrs = org_and_addrs
    vp, lead = addrs["VP Engineering"], addrs["Lead Developer"]
    lca = Address.lowest_common_ancestor(Address.parse(vp), Address.parse(lead))
    assert lca is not None
    engine.approve_bridge(vp, lead, str(lca))
    engine.create_bridge(_bridge(vp, lead, "br-real"))

    stored = {b.id for b in engine._access_policy_store.list_bridges()}
    assert stored == {"br-real"}


# ===================================================================
# create_bridge -- POLE 1, a well-formed endpoint that exists nowhere
# ===================================================================


def test_ghost_bridge_endpoint_is_refused(
    org_and_addrs: tuple[GovernanceEngine, dict[str, str]],
) -> None:
    """THE BYPASS PROOF: role_b names no node while role_a is real.

    The LCA of the real VP and the ghost is the REAL VP, so a legitimate
    approval already exists -- the ghost is the only thing wrong with this
    call, and it was accepted and persisted pre-fix.
    """
    engine, addrs = org_and_addrs
    vp = addrs["VP Engineering"]
    ghost = "D1-R1-T9-R9"

    lca = Address.lowest_common_ancestor(Address.parse(vp), Address.parse(ghost))
    assert lca is not None and str(lca) == vp  # the REAL VP is the LCA
    engine.approve_bridge(vp, ghost, vp)

    with pytest.raises(PactError) as excinfo:
        engine.create_bridge(_bridge(vp, ghost))
    assert ghost in str(excinfo.value)


def test_ghost_sourced_bridge_is_refused(
    org_and_addrs: tuple[GovernanceEngine, dict[str, str]],
) -> None:
    """The same hole on the ``role_a`` side."""
    engine, addrs = org_and_addrs
    lead, ghost = addrs["Lead Developer"], "D1-R1-T9-R9"
    engine.approve_bridge(ghost, lead, addrs["VP Engineering"])

    with pytest.raises(PactError) as excinfo:
        engine.create_bridge(_bridge(ghost, lead))
    assert ghost in str(excinfo.value)


def test_bridge_between_two_ghosts_is_refused(
    org_and_addrs: tuple[GovernanceEngine, dict[str, str]],
) -> None:
    """Both endpoints absent, and the "LCA" that approves them is absent too.

    Measured pre-fix: this pair shares a syntactic accountability chain, so its
    LCA is the ghost ``"D9-R9"``; ``approve_bridge`` then RECORDED that ghost as
    the approving LCA (the vacancy guard asks ``approver_node is not None and
    ...``, so an absent approver skips it) and ``create_bridge`` accepted the
    pair. Both halves are asserted here: the approval must be refused, and the
    bridge must not be creatable regardless.
    """
    engine, _addrs = org_and_addrs
    with pytest.raises(PactError):
        engine.approve_bridge("D9-R9", "D9-R9-T9-R9", "D9-R9")

    with pytest.raises(PactError):
        engine.create_bridge(_bridge("D9-R9", "D9-R9-T9-R9", "br-double-ghost"))

    assert engine._access_policy_store.list_bridges() == []


def test_ghost_bridge_refusal_persists_nothing(
    org_and_addrs: tuple[GovernanceEngine, dict[str, str]],
) -> None:
    """Fail-closed means the store never saw the bridge."""
    engine, addrs = org_and_addrs
    vp = addrs["VP Engineering"]
    ghost = "D1-R1-T9-R9"
    engine.approve_bridge(vp, ghost, vp)

    with pytest.raises(PactError):
        engine.create_bridge(_bridge(vp, ghost))

    assert engine._access_policy_store.list_bridges() == []


# ===================================================================
# create_bridge -- POLE 2
# ===================================================================


def test_legitimate_cross_branch_bridge_still_created(
    org_and_addrs: tuple[GovernanceEngine, dict[str, str]],
) -> None:
    """Two real roles with a compliance-role approval are still accepted.

    ``self._compliance_role`` is the documented alternative to the LCA, so the
    existence check must not be implemented as "approver must equal the LCA".
    """
    compiled = compile_org(_org())
    addresses = {node.name: addr for addr, node in compiled.nodes.items()}
    vp = addresses["VP Engineering"]
    engine = GovernanceEngine(compiled)
    engine.register_compliance_role(vp)

    engine.approve_bridge(vp, addresses["Lead Developer"], vp)
    engine.create_bridge(
        _bridge(vp, addresses["Lead Developer"], "br-compliance-approved")
    )
    assert {b.id for b in engine._access_policy_store.list_bridges()} == {
        "br-compliance-approved"
    }


# ===================================================================
# create_ksp -- CONTROL
# ===================================================================


def _clearance(address: str) -> RoleClearance:
    return RoleClearance(
        role_address=address,
        max_clearance=ConfidentialityLevel.TOP_SECRET,
        vetting_status=VettingStatus.ACTIVE,
    )


def test_control_real_unit_ksp_grants_access(
    org_and_addrs: tuple[GovernanceEngine, dict[str, str]],
) -> None:
    """Known-answer control: a KSP between two REAL units flips the decision.

    Establishes the red BEFORE the green: the same ``check_access`` call is
    asserted blocked first, so the post-KSP ``allowed`` cannot be satisfied by
    an unrelated structural path.
    """
    engine, addrs = org_and_addrs
    cfo = addrs["CFO"]
    engine.grant_clearance(cfo, _clearance(cfo))
    item = KnowledgeItem(
        item_id="i-eng",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1",
    )

    assert engine.check_access(cfo, item, _POSTURE).allowed is False
    engine.create_ksp(_ksp("D1", "D2", "ksp-real"))
    assert engine.check_access(cfo, item, _POSTURE).allowed is True


# ===================================================================
# create_ksp -- POLE 1, unit addresses that resolve to nothing
# ===================================================================


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("D9", "D8"),
        ("D9-R9-T9", "D8-R8-T8"),
        ("NOT-AN-ADDRESS", "ALSO-GARBAGE"),
        ("", ""),
        ("d1", "d2"),
    ],
    ids=[
        "ghost-departments",
        "ghost-team-prefixes",
        "garbage",
        "empty-strings",
        "case-variants",
    ],
)
def test_unresolvable_ksp_unit_address_is_refused(
    org_and_addrs: tuple[GovernanceEngine, dict[str, str]],
    source: str,
    target: str,
) -> None:
    """THE BYPASS PROOF: neither unit need name anything real to be accepted.

    Pre-fix all five pairs were ACCEPTED and persisted; ``create_ksp`` did not
    even run ``Address.parse``, so "NOT-AN-ADDRESS" and "" were stored
    verbatim as governance records.
    """
    engine, _addrs = org_and_addrs
    with pytest.raises(PactError):
        engine.create_ksp(_ksp(source, target))

    assert engine._access_policy_store.list_ksps() == []


def test_ksp_refusal_names_the_offending_unit(
    org_and_addrs: tuple[GovernanceEngine, dict[str, str]],
) -> None:
    """The refusal must be actionable -- it names the unresolvable unit."""
    engine, _addrs = org_and_addrs
    with pytest.raises(PactError) as excinfo:
        engine.create_ksp(_ksp("D1", "D9-R9-T9"))
    assert "D9-R9-T9" in str(excinfo.value)


# ===================================================================
# create_ksp -- POLE 2
# ===================================================================


def test_positional_unit_addresses_still_accepted(
    org_and_addrs: tuple[GovernanceEngine, dict[str, str]],
) -> None:
    """The ordinary positional form is untouched, and is what gets stored."""
    engine, _addrs = org_and_addrs
    engine.create_ksp(_ksp("D1", "D2", "ksp-positional"))
    stored = engine._access_policy_store.list_ksps()
    assert len(stored) == 1
    assert stored[0].source_unit_address == "D1"
    assert stored[0].target_unit_address == "D2"


def test_config_unit_ids_are_accepted_and_normalised(
    org_and_addrs: tuple[GovernanceEngine, dict[str, str]],
) -> None:
    """A config dept/team id names a REAL unit -- accepted, resolved, stored.

    This is the negative pole that forbids a deny-everything fix: the YAML
    surface (``resolve_ksp`` -> ``_resolve_unit_address``) accepts config unit
    ids, so the engine must too.  Pre-fix this pair was accepted but stored
    VERBATIM as ``"d-eng"``/``"d-fin"`` -- keys that can never match at
    enforcement, where ``_check_ksps`` compares against positional addresses.
    """
    engine, _addrs = org_and_addrs
    engine.create_ksp(_ksp("d-eng", "d-fin", "ksp-config-ids"))

    stored = engine._access_policy_store.list_ksps()
    assert len(stored) == 1
    assert stored[0].source_unit_address == "D1"
    assert stored[0].target_unit_address == "D2"
