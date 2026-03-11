"""EATP Multi-Level Delegation -- 3-level chain with progressive constraint tightening.

Demonstrates:
    - Organization -> Senior Agent -> Junior Agent -> Specialist Agent
    - Each level adds constraints (tightening-only rule)
    - Verification at each level shows narrowing permissions
    - Delegation depth tracking

Run:
    python multi_delegation.py
"""

import asyncio

from eatp import CapabilityRequest, TrustKeyManager, TrustOperations
from eatp.authority import AuthorityPermission, OrganizationalAuthority
from eatp.chain import AuthorityType, CapabilityType, VerificationLevel
from eatp.crypto import generate_keypair
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


async def main():
    # -- Setup ---------------------------------------------------------------
    store = InMemoryTrustStore()
    await store.initialize()

    key_mgr = TrustKeyManager()
    priv_key, pub_key = generate_keypair()
    key_mgr.register_key("key-corp", priv_key)

    registry = SimpleAuthorityRegistry()
    registry.register(
        OrganizationalAuthority(
            id="org-corp",
            name="Global Corp",
            authority_type=AuthorityType.ORGANIZATION,
            public_key=pub_key,
            signing_key_id="key-corp",
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

    # -- Level 0: Establish senior agent with broad capabilities -------------
    print("Level 0: ESTABLISH senior-agent (broad capabilities)")
    await ops.establish(
        agent_id="senior-agent",
        authority_id="org-corp",
        capabilities=[
            CapabilityRequest(capability="analyze_data", capability_type=CapabilityType.ACTION),
            CapabilityRequest(capability="generate_report", capability_type=CapabilityType.ACTION),
            CapabilityRequest(capability="read_financials", capability_type=CapabilityType.ACCESS),
            CapabilityRequest(capability="send_notification", capability_type=CapabilityType.ACTION),
        ],
        constraints=["audit_required"],
    )
    senior_caps = await ops.get_agent_capabilities("senior-agent")
    print(f"   Capabilities: {senior_caps}")
    print(f"   Constraints: {await ops.get_agent_constraints('senior-agent')}")

    # -- Level 1: Delegate to junior agent (tighter constraints) -------------
    print("\nLevel 1: DELEGATE to junior-agent (adding read_only)")
    await ops.delegate(
        delegator_id="senior-agent",
        delegatee_id="junior-agent",
        task_id="task-financial-review",
        capabilities=["analyze_data", "read_financials"],
        additional_constraints=["read_only"],
    )
    junior_caps = await ops.get_agent_capabilities("junior-agent")
    junior_constraints = await ops.get_agent_constraints("junior-agent")
    print(f"   Capabilities: {junior_caps}")
    print(f"   Constraints: {junior_constraints}")

    # -- Level 2: Delegate to specialist agent (even tighter) ----------------
    print("\nLevel 2: DELEGATE to specialist-agent (adding no_pii_export)")
    await ops.delegate(
        delegator_id="junior-agent",
        delegatee_id="specialist-agent",
        task_id="task-pii-safe-analysis",
        capabilities=["analyze_data"],
        additional_constraints=["no_pii_export"],
    )
    specialist_caps = await ops.get_agent_capabilities("specialist-agent")
    specialist_constraints = await ops.get_agent_constraints("specialist-agent")
    print(f"   Capabilities: {specialist_caps}")
    print(f"   Constraints: {specialist_constraints}")

    # -- Verify at each level ------------------------------------------------
    print("\n--- Verification Results ---")

    for agent_id in ["senior-agent", "junior-agent", "specialist-agent"]:
        result = await ops.verify(
            agent_id=agent_id,
            action="analyze_data",
            level=VerificationLevel.STANDARD,
        )
        chain = await store.get_chain(agent_id)
        depth = len(chain.delegations)
        n_constraints = len(chain.constraint_envelope.active_constraints)
        print(
            f"   {agent_id:20s} | analyze_data={result.valid!s:5s} | "
            f"delegations={depth} | constraints={n_constraints}"
        )

    # Specialist cannot read_financials (was not delegated)
    result_denied = await ops.verify(agent_id="specialist-agent", action="read_financials")
    print(f"\n   specialist-agent read_financials: {result_denied.valid} ({result_denied.reason})")

    # Senior can do everything
    result_report = await ops.verify(agent_id="senior-agent", action="generate_report")
    print(f"   senior-agent generate_report: {result_report.valid}")

    print("\nMulti-level delegation with progressive tightening completed.")


if __name__ == "__main__":
    asyncio.run(main())
