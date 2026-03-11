"""EATP Shadow Enforcement -- gradual rollout without blocking.

Demonstrates:
    - ShadowEnforcer that logs but never blocks
    - Collecting metrics on what would have been blocked
    - Generating a shadow enforcement report
    - Comparing with StrictEnforcer behavior

Run:
    python shadow_mode.py
"""

import asyncio

from eatp import CapabilityRequest, TrustKeyManager, TrustOperations
from eatp.authority import AuthorityPermission, OrganizationalAuthority
from eatp.chain import AuthorityType, CapabilityType, VerificationLevel
from eatp.crypto import generate_keypair
from eatp.enforce.shadow import ShadowEnforcer
from eatp.enforce.strict import StrictEnforcer, Verdict
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
    key_mgr.register_key("key-org", priv_key)

    registry = SimpleAuthorityRegistry()
    registry.register(
        OrganizationalAuthority(
            id="org-main",
            name="Main Org",
            authority_type=AuthorityType.ORGANIZATION,
            public_key=pub_key,
            signing_key_id="key-org",
            permissions=[AuthorityPermission.CREATE_AGENTS],
        )
    )

    ops = TrustOperations(
        authority_registry=registry,
        key_manager=key_mgr,
        trust_store=store,
    )

    # Establish an agent with limited capabilities
    await ops.establish(
        agent_id="agent-worker",
        authority_id="org-main",
        capabilities=[
            CapabilityRequest(capability="read_data", capability_type=CapabilityType.ACCESS),
            CapabilityRequest(capability="generate_report", capability_type=CapabilityType.ACTION),
        ],
    )

    # -- Create shadow enforcer ----------------------------------------------
    shadow = ShadowEnforcer(flag_threshold=1)

    # -- Simulate a series of agent actions ----------------------------------
    print("Running shadow enforcement on simulated agent actions...")
    print("-" * 60)

    test_actions = [
        # (action, should_exist) -- for context
        ("read_data", True),
        ("generate_report", True),
        ("delete_records", False),      # agent does not have this
        ("read_data", True),
        ("write_database", False),       # agent does not have this
        ("generate_report", True),
        ("admin_override", False),       # agent does not have this
        ("read_data", True),
    ]

    for action, _expected in test_actions:
        # Run VERIFY
        result = await ops.verify(
            agent_id="agent-worker",
            action=action,
            level=VerificationLevel.STANDARD,
        )

        # Pass result through shadow enforcer -- never blocks
        verdict = shadow.check(
            agent_id="agent-worker",
            action=action,
            result=result,
        )

        status = "PASS" if result.valid else "DENY"
        print(f"  {action:25s}  verified={status:4s}  shadow_verdict={verdict.value}")

    # -- Print shadow report -------------------------------------------------
    print()
    print(shadow.report())

    # -- Show what strict enforcement would have done ------------------------
    print("\n--- Strict Enforcement Comparison ---")
    strict = StrictEnforcer(flag_threshold=1)

    for action, _expected in test_actions:
        result = await ops.verify(agent_id="agent-worker", action=action)
        verdict = strict.classify(result)

        if verdict == Verdict.BLOCKED:
            print(f"  {action:25s} -> BLOCKED (would raise EATPBlockedError)")
        elif verdict == Verdict.HELD:
            print(f"  {action:25s} -> HELD (would require human review)")
        elif verdict == Verdict.FLAGGED:
            print(f"  {action:25s} -> FLAGGED (logged, execution continues)")
        else:
            print(f"  {action:25s} -> AUTO_APPROVED")

    # -- Demonstrate metrics -------------------------------------------------
    print("\n--- Shadow Metrics ---")
    m = shadow.metrics
    print(f"  Total checks:    {m.total_checks}")
    print(f"  Pass rate:       {m.pass_rate:.1f}%")
    print(f"  Block rate:      {m.block_rate:.1f}%")
    print(f"  Would block:     {m.blocked_count}")
    print(f"  Would hold:      {m.held_count}")
    print(f"  Auto-approved:   {m.auto_approved_count}")

    print("\nShadow enforcement demo completed.")
    print("When ready for production, switch from ShadowEnforcer to StrictEnforcer.")


if __name__ == "__main__":
    asyncio.run(main())
