# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""University demo -- runnable script showing all 14 PACT governance scenarios.

Run with:
    python -m pact.examples.university.demo

Each scenario demonstrates a specific PACT governance concept using the
university organizational structure.
"""

from __future__ import annotations

import logging
import sys

from pact.build.config.schema import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TrustPostureLevel,
)
from pact.examples.university.barriers import (
    create_university_bridges,
    create_university_ksps,
)
from pact.examples.university.clearance import create_university_clearances
from pact.examples.university.org import create_university_org
from pact.governance.access import KnowledgeSharePolicy, PactBridge
from pact.governance.agent import GovernanceBlockedError, PactGovernedAgent
from pact.governance.clearance import RoleClearance
from pact.governance.decorators import governed_tool
from pact.governance.engine import GovernanceEngine
from pact.governance.envelopes import RoleEnvelope
from pact.governance.knowledge import KnowledgeItem
from pact.governance.testing import MockGovernedAgent
from pact.governance.explain import describe_address, explain_access

logger = logging.getLogger(__name__)

__all__ = ["run_demo"]

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_PASS = "PASS"
_FAIL = "FAIL"
_scenario_count = 0
_pass_count = 0
_fail_count = 0


def _scenario(title: str) -> None:
    global _scenario_count
    _scenario_count += 1
    print(f"\n{'=' * 70}")
    print(f"Scenario {_scenario_count}: {title}")
    print(f"{'=' * 70}")


def _check(description: str, condition: bool) -> None:
    global _pass_count, _fail_count
    if condition:
        _pass_count += 1
        print(f"  [{_PASS}] {description}")
    else:
        _fail_count += 1
        print(f"  [{_FAIL}] {description}")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run_demo() -> int:
    """Run all 14 E2E scenarios. Returns 0 on success, 1 on any failure."""
    global _scenario_count, _pass_count, _fail_count
    _scenario_count = 0
    _pass_count = 0
    _fail_count = 0

    print("PACT Governance Framework -- University Demo")
    print("=" * 70)

    # --- Setup ---
    compiled, org_def = create_university_org()
    engine = GovernanceEngine(org_def)
    org = engine.get_org()

    # Apply clearances
    clearances = create_university_clearances(compiled)
    for addr, clr in clearances.items():
        engine.grant_clearance(addr, clr)

    # Apply bridges and KSPs
    for bridge in create_university_bridges():
        engine.create_bridge(bridge)

    for ksp in create_university_ksps():
        engine.create_ksp(ksp)

    # Apply an envelope for the CS Chair
    cs_chair_addr = "D1-R1-D1-R1-D1-R1-T1-R1"
    dean_eng_addr = "D1-R1-D1-R1-D1-R1"
    cs_chair_envelope = RoleEnvelope(
        id="env-cs-chair",
        defining_role_address=dean_eng_addr,
        target_role_address=cs_chair_addr,
        envelope=ConstraintEnvelopeConfig(
            id="env-cs-chair",
            financial=FinancialConstraintConfig(
                max_spend_usd=10000,
                requires_approval_above_usd=5000,
            ),
            operational=OperationalConstraintConfig(
                allowed_actions=["read", "write", "approve"],
            ),
        ),
    )
    engine.set_role_envelope(cs_chair_envelope)

    print(f"\nOrganization: {engine.org_name}")
    print(f"Nodes: {len(org.nodes)}")
    print(f"Clearances: {len(clearances)}")

    # -----------------------------------------------------------------------
    # Scenario 1: D/T/R Compilation and Addressing
    # -----------------------------------------------------------------------
    _scenario("D/T/R Compilation and Addressing")

    _check("President at D1-R1", org.nodes.get("D1-R1") is not None)
    _check("Provost at D1-R1-D1-R1", org.nodes.get("D1-R1-D1-R1") is not None)
    _check(
        "CS Chair at D1-R1-D1-R1-D1-R1-T1-R1",
        org.nodes.get("D1-R1-D1-R1-D1-R1-T1-R1") is not None,
    )
    _check(
        "IRB Director at D1-R1-D1-R1-D2-R1-T1-R1",
        org.nodes.get("D1-R1-D1-R1-D2-R1-T1-R1") is not None,
    )
    _check("Total nodes >= 20", len(org.nodes) >= 20)

    # -----------------------------------------------------------------------
    # Scenario 2: Clearance Independent of Authority
    # -----------------------------------------------------------------------
    _scenario("Clearance Independent of Authority")

    irb_clr = clearances.get("D1-R1-D1-R1-D2-R1-T1-R1")
    dean_eng_clr = clearances.get("D1-R1-D1-R1-D1-R1")

    _check(
        "IRB Director has SECRET clearance",
        irb_clr is not None and irb_clr.max_clearance == ConfidentialityLevel.SECRET,
    )
    _check(
        "Dean of Engineering has CONFIDENTIAL clearance (lower than IRB)",
        dean_eng_clr is not None
        and dean_eng_clr.max_clearance == ConfidentialityLevel.CONFIDENTIAL,
    )
    _check(
        "IRB Director has human-subjects compartment",
        irb_clr is not None and "human-subjects" in irb_clr.compartments,
    )

    # -----------------------------------------------------------------------
    # Scenario 3: Same-Unit Access (Step 4a)
    # -----------------------------------------------------------------------
    _scenario("Same-Unit Access (Step 4a)")

    cs_doc = KnowledgeItem(
        item_id="doc-cs-curriculum",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D1-R1-D1-R1-T1",  # CS Department team
    )

    decision = engine.check_access(
        "D1-R1-D1-R1-D1-R1-T1-R1",  # CS Chair
        cs_doc,
        TrustPostureLevel.SHARED_PLANNING,
    )
    _check("CS Chair accesses CS Department doc: ALLOWED", decision.allowed)

    # -----------------------------------------------------------------------
    # Scenario 4: Downward Visibility (Step 4b)
    # -----------------------------------------------------------------------
    _scenario("Downward Visibility (Step 4b)")

    decision = engine.check_access(
        "D1-R1-D1-R1",  # Provost
        cs_doc,
        TrustPostureLevel.SHARED_PLANNING,
    )
    _check("Provost accesses CS Department doc (downward): ALLOWED", decision.allowed)

    # -----------------------------------------------------------------------
    # Scenario 5: Cross-Department Denial (Step 5)
    # -----------------------------------------------------------------------
    _scenario("Cross-Department Denial (Step 5)")

    admin_doc = KnowledgeItem(
        item_id="doc-hr-policy",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D2-R1-T1",  # HR team
    )

    decision = engine.check_access(
        "D1-R1-D1-R1-D1-R1-T1-R1",  # CS Chair
        admin_doc,
        TrustPostureLevel.SHARED_PLANNING,
    )
    _check(
        "CS Chair accesses HR doc (no access path): DENIED",
        not decision.allowed,
    )

    # -----------------------------------------------------------------------
    # Scenario 6: Bridge Access (Step 4e)
    # -----------------------------------------------------------------------
    _scenario("Bridge Access (Step 4e)")

    admin_budget = KnowledgeItem(
        item_id="doc-admin-budget",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D2",  # Administration dept
    )

    decision = engine.check_access(
        "D1-R1-D1-R1",  # Provost (has unilateral bridge to VP Admin)
        admin_budget,
        TrustPostureLevel.SHARED_PLANNING,
    )
    _check("Provost accesses Admin budget via bridge: ALLOWED", decision.allowed)

    # -----------------------------------------------------------------------
    # Scenario 7: Unilateral Bridge Direction
    # -----------------------------------------------------------------------
    _scenario("Unilateral Bridge Direction")

    acad_doc = KnowledgeItem(
        item_id="doc-acad-strategy",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D1",  # Academic Affairs dept
    )

    decision = engine.check_access(
        "D1-R1-D2-R1",  # VP Admin (bridge is A->B only, VP Admin is B)
        acad_doc,
        TrustPostureLevel.SHARED_PLANNING,
    )
    _check(
        "VP Admin accesses Academic doc (reverse direction): DENIED",
        not decision.allowed,
    )

    # -----------------------------------------------------------------------
    # Scenario 8: KSP Access (Step 4d)
    # -----------------------------------------------------------------------
    _scenario("KSP Access (Step 4d)")

    acad_personnel = KnowledgeItem(
        item_id="doc-acad-personnel",
        classification=ConfidentialityLevel.RESTRICTED,
        owning_unit_address="D1-R1-D1",  # Academic Affairs
    )

    decision = engine.check_access(
        "D1-R1-D2-R1-T1-R1",  # HR Director (target of KSP from Academic Affairs)
        acad_personnel,
        TrustPostureLevel.SHARED_PLANNING,
    )
    _check(
        "HR Director accesses Academic personnel via KSP: ALLOWED",
        decision.allowed,
    )

    # -----------------------------------------------------------------------
    # Scenario 9: Compartment-Gated Access
    # -----------------------------------------------------------------------
    _scenario("Compartment-Gated Access")

    irb_data = KnowledgeItem(
        item_id="doc-irb-protocol",
        classification=ConfidentialityLevel.SECRET,
        owning_unit_address="D1-R1-D1-R1-D2-R1-T1",  # Research Lab
        compartments=frozenset({"human-subjects"}),
    )

    # IRB Director has SECRET + human-subjects
    decision = engine.check_access(
        "D1-R1-D1-R1-D2-R1-T1-R1",
        irb_data,
        TrustPostureLevel.CONTINUOUS_INSIGHT,
    )
    _check("IRB Director accesses human-subjects data: ALLOWED", decision.allowed)

    # Dean of Engineering has CONFIDENTIAL (no human-subjects compartment)
    decision = engine.check_access(
        "D1-R1-D1-R1-D1-R1",
        irb_data,
        TrustPostureLevel.CONTINUOUS_INSIGHT,
    )
    _check(
        "Dean of Engineering accesses human-subjects data: DENIED (classification)",
        not decision.allowed,
    )

    # -----------------------------------------------------------------------
    # Scenario 10: Posture-Capped Clearance
    # -----------------------------------------------------------------------
    _scenario("Posture-Capped Clearance")

    confidential_doc = KnowledgeItem(
        item_id="doc-confidential-research",
        classification=ConfidentialityLevel.CONFIDENTIAL,
        owning_unit_address="D1-R1-D1-R1-D2-R1-T1",
    )

    # IRB Director at SUPERVISED posture: ceiling is RESTRICTED
    decision = engine.check_access(
        "D1-R1-D1-R1-D2-R1-T1-R1",
        confidential_doc,
        TrustPostureLevel.SUPERVISED,  # Ceiling: RESTRICTED
    )
    _check(
        "IRB Director (SUPERVISED) accesses CONFIDENTIAL: DENIED (posture cap)",
        not decision.allowed,
    )

    # Same role at SHARED_PLANNING: ceiling is CONFIDENTIAL
    decision = engine.check_access(
        "D1-R1-D1-R1-D2-R1-T1-R1",
        confidential_doc,
        TrustPostureLevel.SHARED_PLANNING,  # Ceiling: CONFIDENTIAL
    )
    _check(
        "IRB Director (SHARED_PLANNING) accesses CONFIDENTIAL: ALLOWED",
        decision.allowed,
    )

    # -----------------------------------------------------------------------
    # Scenario 11: Envelope Enforcement
    # -----------------------------------------------------------------------
    _scenario("Envelope Enforcement")

    # CS Chair reads (allowed)
    verdict = engine.verify_action(cs_chair_addr, "read")
    _check(
        f"CS Chair reads: {verdict.level}",
        verdict.level == "auto_approved",
    )

    # CS Chair tries to deploy (not in allowed_actions)
    verdict = engine.verify_action(cs_chair_addr, "deploy")
    _check(
        f"CS Chair deploys: {verdict.level}",
        verdict.level == "blocked",
    )

    # CS Chair spends $3000 (within limit)
    verdict = engine.verify_action(cs_chair_addr, "write", {"cost": 3000})
    _check(
        f"CS Chair writes at $3000: {verdict.level}",
        verdict.level == "auto_approved",
    )

    # CS Chair spends $7000 (above approval threshold, held)
    verdict = engine.verify_action(cs_chair_addr, "write", {"cost": 7000})
    _check(
        f"CS Chair writes at $7000: {verdict.level}",
        verdict.level == "held",
    )

    # CS Chair spends $15000 (above max, blocked)
    verdict = engine.verify_action(cs_chair_addr, "write", {"cost": 15000})
    _check(
        f"CS Chair writes at $15000: {verdict.level}",
        verdict.level == "blocked",
    )

    # -----------------------------------------------------------------------
    # Scenario 12: Governed Agent (Default-Deny)
    # -----------------------------------------------------------------------
    _scenario("Governed Agent (Default-Deny)")

    @governed_tool("read", cost=0.0)
    def tool_read() -> str:
        return "read_result"

    @governed_tool("deploy", cost=500.0)
    def tool_deploy() -> str:
        return "deployed"

    agent = PactGovernedAgent(
        engine=engine,
        role_address=cs_chair_addr,
        posture=TrustPostureLevel.SUPERVISED,
    )
    agent.register_tool("read", cost=0.0)
    agent.register_tool("deploy", cost=500.0)

    # Read is allowed
    result = agent.execute_tool("read", _tool_fn=tool_read)
    _check(f"Agent reads: {result}", result == "read_result")

    # Deploy is blocked (not in allowed_actions)
    blocked = False
    try:
        agent.execute_tool("deploy", _tool_fn=tool_deploy)
    except GovernanceBlockedError:
        blocked = True
    _check("Agent deploy blocked by governance", blocked)

    # Unregistered tool is blocked (default-deny)
    blocked = False
    try:
        agent.execute_tool("unregistered", _tool_fn=lambda: None)
    except GovernanceBlockedError:
        blocked = True
    _check("Unregistered tool blocked (default-deny)", blocked)

    # -----------------------------------------------------------------------
    # Scenario 13: MockGovernedAgent
    # -----------------------------------------------------------------------
    _scenario("MockGovernedAgent for Testing")

    mock = MockGovernedAgent(
        engine=engine,
        role_address=cs_chair_addr,
        tools=[tool_read],
        script=["read", "read", "read"],
        posture=TrustPostureLevel.SUPERVISED,
    )
    results = mock.run()
    _check(
        f"MockGovernedAgent executed 3 reads: {len(results)} results",
        len(results) == 3 and all(r == "read_result" for r in results),
    )

    # -----------------------------------------------------------------------
    # Scenario 14: Frozen GovernanceContext
    # -----------------------------------------------------------------------
    _scenario("Frozen GovernanceContext (Anti-Self-Modification)")

    ctx = engine.get_context(cs_chair_addr, posture=TrustPostureLevel.SUPERVISED)
    _check(f"Context role_address: {ctx.role_address}", ctx.role_address == cs_chair_addr)
    _check(f"Context posture: {ctx.posture.value}", ctx.posture == TrustPostureLevel.SUPERVISED)
    _check(
        f"Context allowed_actions: {sorted(ctx.allowed_actions)}",
        "read" in ctx.allowed_actions and "write" in ctx.allowed_actions,
    )

    # Verify immutability
    immutable = False
    try:
        ctx.posture = TrustPostureLevel.DELEGATED  # type: ignore[misc]
    except AttributeError:
        immutable = True
    _check("Context is frozen (immutable)", immutable)

    # Roundtrip serialization
    data = ctx.to_dict()
    from pact.governance.context import GovernanceContext

    restored = GovernanceContext.from_dict(data)
    _check(
        "Context roundtrip serialization",
        restored.role_address == ctx.role_address and restored.org_id == ctx.org_id,
    )

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print(f"\n{'=' * 70}")
    print(
        f"RESULTS: {_pass_count} passed, {_fail_count} failed out of {_pass_count + _fail_count} checks"
    )
    print(f"{'=' * 70}")

    return 0 if _fail_count == 0 else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    sys.exit(run_demo())
