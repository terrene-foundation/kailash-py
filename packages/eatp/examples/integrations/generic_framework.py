"""EATP Generic Framework Integration -- universal patterns for any agent framework.

Demonstrates three integration patterns that work with any Python framework:

    Pattern 1: Decorator-based (@verified, @audited, @shadow)
        Zero-config integration -- add a decorator to any function.

    Pattern 2: StrictEnforcer middleware
        Explicit control -- verify and enforce in your own flow.

    Pattern 3: ShadowEnforcer for gradual rollout
        Observe-first -- log what would be blocked without breaking anything.

Each pattern is independent. Choose the one that fits your deployment stage:
    - Greenfield project: start with Pattern 1 (decorators)
    - Existing system: start with Pattern 3 (shadow), then promote to Pattern 2

Run:
    python examples/integrations/generic_framework.py
"""

import asyncio
from typing import Any, Dict, List

from eatp import CapabilityRequest, TrustKeyManager, TrustOperations
from eatp.authority import AuthorityPermission, OrganizationalAuthority
from eatp.chain import ActionResult, AuthorityType, CapabilityType, VerificationLevel
from eatp.crypto import generate_keypair
from eatp.enforce.decorators import audited, shadow, verified
from eatp.enforce.shadow import ShadowEnforcer
from eatp.enforce.strict import EATPBlockedError, StrictEnforcer, Verdict
from eatp.store.memory import InMemoryTrustStore


class SimpleAuthorityRegistry:
    """Minimal in-memory authority registry for examples."""

    def __init__(self):
        self._authorities = {}

    async def initialize(self):
        pass

    def register(self, authority: OrganizationalAuthority):
        self._authorities[authority.id] = authority

    async def get_authority(self, authority_id: str, include_inactive: bool = False):
        authority = self._authorities.get(authority_id)
        if authority is None:
            raise KeyError(f"Authority not found: {authority_id}")
        return authority


async def setup_eatp() -> TrustOperations:
    """Create EATP infrastructure and establish agent trust."""
    store = InMemoryTrustStore()
    await store.initialize()

    key_mgr = TrustKeyManager()
    priv_key, pub_key = generate_keypair()
    key_mgr.register_key("key-org", priv_key)

    registry = SimpleAuthorityRegistry()
    registry.register(
        OrganizationalAuthority(
            id="org-platform",
            name="Platform Team",
            authority_type=AuthorityType.ORGANIZATION,
            public_key=pub_key,
            signing_key_id="key-org",
            permissions=[
                AuthorityPermission.CREATE_AGENTS,
                AuthorityPermission.DELEGATE_TRUST,
            ],
        )
    )

    ops = TrustOperations(
        authority_registry=registry,
        key_manager=key_mgr,
        trust_store=store,
    )

    # Establish an agent with specific capabilities
    await ops.establish(
        agent_id="agent-001",
        authority_id="org-platform",
        capabilities=[
            CapabilityRequest(
                capability="analyze", capability_type=CapabilityType.ACTION
            ),
            CapabilityRequest(
                capability="read_data", capability_type=CapabilityType.ACCESS
            ),
            CapabilityRequest(
                capability="generate_report", capability_type=CapabilityType.ACTION
            ),
        ],
        constraints=["audit_required"],
    )

    return ops


# ===========================================================================
# Pattern 1: Decorator-based integration
# ===========================================================================

# Define decorated functions -- ops is injected via set_ops() after setup.
# The decorators handle VERIFY (before) and AUDIT (after) automatically.


@verified(agent_id="agent-001", action="analyze")
async def analyze_data(dataset: str) -> Dict[str, Any]:
    """Analyze a dataset. EATP verifies trust before execution.

    If agent-001 does not have the 'analyze' capability, this function
    is never called -- EATPBlockedError is raised instead.
    """
    return {
        "dataset": dataset,
        "records": 1500,
        "anomalies": 7,
        "status": "complete",
    }


@audited(agent_id="agent-001")
async def transform_results(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Transform analysis results. EATP records an audit trail after execution.

    The function runs unconditionally, and an AUDIT anchor is created
    with a hash of the input arguments and output result.
    """
    return {
        "summary": f"Processed {raw['records']} records, found {raw['anomalies']} anomalies",
        "source": raw["dataset"],
    }


@verified(agent_id="agent-001", action="delete_records")
async def delete_records(table: str) -> str:
    """Delete records -- agent-001 does NOT have this capability.

    This function will never execute; the @verified decorator blocks it.
    """
    return f"Deleted all records from {table}"


@shadow(agent_id="agent-001", action="analyze")
async def analyze_shadow(dataset: str) -> Dict[str, Any]:
    """Shadow-mode analysis -- logs trust verdict but never blocks.

    Use this during gradual rollout to observe verification outcomes
    without affecting existing behavior.
    """
    return {"dataset": dataset, "records": 1500, "shadow_mode": True}


async def demo_pattern_1(ops: TrustOperations):
    """Demonstrate decorator-based integration."""
    print("=" * 60)
    print("Pattern 1: Decorator-based Integration")
    print("=" * 60)

    # Inject TrustOperations into the decorated functions
    analyze_data.set_ops(ops)
    transform_results.set_ops(ops)
    delete_records.set_ops(ops)
    analyze_shadow.set_ops(ops)

    # 1a: Authorized action -- @verified passes
    print("\n  1a. @verified -- authorized action (analyze)")
    result = await analyze_data("quarterly_revenue")
    print(f"      Result: {result}")

    # 1b: Audited action -- always runs, creates audit trail
    print("\n  1b. @audited -- recording audit trail")
    transformed = await transform_results(result)
    print(f"      Transformed: {transformed}")

    # 1c: Unauthorized action -- @verified blocks
    print("\n  1c. @verified -- unauthorized action (delete_records)")
    try:
        await delete_records("users")
        print("      ERROR: Should have been blocked")
    except EATPBlockedError as e:
        print(f"      Correctly blocked: {e}")

    # 1d: Shadow mode -- logs but does not block
    print("\n  1d. @shadow -- observe without blocking")
    shadow_result = await analyze_shadow("test_dataset")
    print(f"      Result: {shadow_result}")
    shadow_enforcer = analyze_shadow.shadow_enforcer
    print(
        f"      Shadow metrics: {shadow_enforcer.metrics.total_checks} checks, "
        f"{shadow_enforcer.metrics.pass_rate:.0f}% pass rate"
    )


# ===========================================================================
# Pattern 2: StrictEnforcer middleware
# ===========================================================================


async def demo_pattern_2(ops: TrustOperations):
    """Demonstrate StrictEnforcer middleware pattern."""
    print("\n" + "=" * 60)
    print("Pattern 2: StrictEnforcer Middleware")
    print("=" * 60)

    enforcer = StrictEnforcer()

    # 2a: Verify and enforce -- authorized
    print("\n  2a. StrictEnforcer -- authorized action")
    result = await ops.verify(agent_id="agent-001", action="analyze")
    verdict = enforcer.enforce(agent_id="agent-001", action="analyze", result=result)
    print(f"      Verdict: {verdict.value}")
    print(f"      Enforcement records: {len(enforcer.records)}")

    # 2b: Verify and enforce -- unauthorized
    print("\n  2b. StrictEnforcer -- unauthorized action")
    result = await ops.verify(agent_id="agent-001", action="admin_override")
    try:
        enforcer.enforce(agent_id="agent-001", action="admin_override", result=result)
        print("      ERROR: Should have been blocked")
    except EATPBlockedError as e:
        print(f"      Correctly blocked: {e.reason}")
        print(f"      Total enforcement records: {len(enforcer.records)}")

    # 2c: Classify without enforcing (inspect mode)
    print("\n  2c. StrictEnforcer.classify -- inspect without raising")
    for action in ["read_data", "generate_report", "delete_all"]:
        result = await ops.verify(agent_id="agent-001", action=action)
        verdict = enforcer.classify(result)
        print(f"      {action:20s} -> {verdict.value}")


# ===========================================================================
# Pattern 3: ShadowEnforcer for gradual rollout
# ===========================================================================


async def demo_pattern_3(ops: TrustOperations):
    """Demonstrate ShadowEnforcer for gradual rollout."""
    print("\n" + "=" * 60)
    print("Pattern 3: ShadowEnforcer for Gradual Rollout")
    print("=" * 60)

    shadow_enforcer = ShadowEnforcer()

    # Simulate a series of actions -- mix of authorized and unauthorized
    actions = [
        "analyze",  # authorized
        "read_data",  # authorized
        "generate_report",  # authorized
        "delete_records",  # NOT authorized
        "analyze",  # authorized
        "admin_override",  # NOT authorized
        "read_data",  # authorized
        "deploy_to_prod",  # NOT authorized
    ]

    print("\n  Running shadow enforcement on 8 actions...")
    for action in actions:
        result = await ops.verify(
            agent_id="agent-001",
            action=action,
            level=VerificationLevel.STANDARD,
        )
        verdict = shadow_enforcer.check(
            agent_id="agent-001",
            action=action,
            result=result,
        )
        status = "PASS" if result.valid else "DENY"
        print(f"    {action:20s} verified={status:4s} shadow={verdict.value}")

    # Print the shadow report
    print()
    print(shadow_enforcer.report())

    # Decision point: is the block rate acceptable?
    metrics = shadow_enforcer.metrics
    print(f"\n  Decision: block rate is {metrics.block_rate:.1f}%")
    if metrics.block_rate < 50:
        print("  Recommendation: safe to promote to StrictEnforcer")
    else:
        print("  Recommendation: review blocked actions before promoting")


# ===========================================================================
# Main
# ===========================================================================


async def main():
    ops = await setup_eatp()
    caps = await ops.get_agent_capabilities("agent-001")
    constraints = await ops.get_agent_constraints("agent-001")
    print(f"Agent capabilities: {caps}")
    print(f"Agent constraints: {constraints}")

    await demo_pattern_1(ops)
    await demo_pattern_2(ops)
    await demo_pattern_3(ops)

    print("\n" + "=" * 60)
    print("Summary: Three Integration Patterns")
    print("=" * 60)
    print(
        "  Pattern 1 (Decorators):     Lowest friction -- add @verified to any function"
    )
    print(
        "  Pattern 2 (StrictEnforcer):  Full control -- verify + enforce in your flow"
    )
    print("  Pattern 3 (ShadowEnforcer):  Zero risk -- observe before enforcing")
    print("\nGeneric framework integration completed.")


if __name__ == "__main__":
    asyncio.run(main())
