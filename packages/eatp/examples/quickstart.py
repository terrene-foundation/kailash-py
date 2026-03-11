"""EATP Quickstart -- 4-operation lifecycle in one script.

Demonstrates:
    1. ESTABLISH -- create initial trust for an agent
    2. VERIFY -- check if the agent can perform an action
    3. DELEGATE -- transfer a capability to another agent
    4. AUDIT -- record an action in the immutable audit trail

Run:
    python quickstart.py
"""

import asyncio

from eatp import CapabilityRequest, TrustKeyManager, TrustOperations
from eatp.authority import AuthorityPermission, OrganizationalAuthority
from eatp.chain import ActionResult, AuthorityType, CapabilityType
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
    key_mgr.register_key("key-acme", priv_key)

    registry = SimpleAuthorityRegistry()
    registry.register(
        OrganizationalAuthority(
            id="org-acme",
            name="ACME Corp",
            authority_type=AuthorityType.ORGANIZATION,
            public_key=pub_key,
            signing_key_id="key-acme",
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

    # -- 1. ESTABLISH --------------------------------------------------------
    print("1. ESTABLISH -- creating trust for agent-analyst")
    chain = await ops.establish(
        agent_id="agent-analyst",
        authority_id="org-acme",
        capabilities=[
            CapabilityRequest(
                capability="analyze_data",
                capability_type=CapabilityType.ACTION,
            ),
            CapabilityRequest(
                capability="read_reports",
                capability_type=CapabilityType.ACCESS,
            ),
        ],
        constraints=["audit_required"],
    )
    print(f"   Chain created with {len(chain.capabilities)} capabilities")
    print(f"   Genesis ID: {chain.genesis.id}")

    # -- 2. VERIFY -----------------------------------------------------------
    print("\n2. VERIFY -- checking agent can analyze data")
    result = await ops.verify(agent_id="agent-analyst", action="analyze_data")
    print(f"   Allowed: {result.valid}")
    print(f"   Level: {result.level.value}")

    # Verify an action the agent does NOT have
    result_denied = await ops.verify(agent_id="agent-analyst", action="delete_records")
    print(f"\n   Verify 'delete_records': {result_denied.valid}")
    print(f"   Reason: {result_denied.reason}")

    # -- 3. DELEGATE ---------------------------------------------------------
    print("\n3. DELEGATE -- delegating 'analyze_data' to agent-junior")
    delegation = await ops.delegate(
        delegator_id="agent-analyst",
        delegatee_id="agent-junior",
        task_id="task-q4-report",
        capabilities=["analyze_data"],
        additional_constraints=["no_pii_export"],
    )
    print(f"   Delegation ID: {delegation.id}")
    print(f"   Constraints: {delegation.constraint_subset}")

    # Verify the delegatee
    junior_result = await ops.verify(agent_id="agent-junior", action="analyze_data")
    print(f"   Junior can analyze_data: {junior_result.valid}")

    # -- 4. AUDIT ------------------------------------------------------------
    print("\n4. AUDIT -- recording action in audit trail")
    anchor = await ops.audit(
        agent_id="agent-analyst",
        action="analyze_data",
        resource="finance_db.quarterly_revenue",
        result=ActionResult.SUCCESS,
        context_data={"rows_processed": 1200, "duration_ms": 340},
    )
    print(f"   Audit anchor ID: {anchor.id}")
    print(f"   Trust chain hash: {anchor.trust_chain_hash[:16]}...")
    print(f"   Signed: {'Yes' if anchor.signature else 'No'}")

    print("\nAll four EATP operations completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
