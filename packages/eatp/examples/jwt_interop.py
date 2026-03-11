"""EATP JWT Interop -- export and import trust chains as signed JWTs.

Demonstrates:
    - Exporting a trust chain to a JWT token
    - Inspecting JWT claims
    - Importing and verifying a JWT back to a TrustLineageChain
    - Exporting individual capabilities and delegations as JWTs

Requires:
    pip install 'pyjwt[crypto]'

Run:
    python jwt_interop.py
"""

import asyncio
import json

from eatp import CapabilityRequest, TrustKeyManager, TrustOperations
from eatp.authority import AuthorityPermission, OrganizationalAuthority
from eatp.chain import AuthorityType, CapabilityType
from eatp.crypto import generate_keypair
from eatp.store.memory import InMemoryTrustStore

try:
    import jwt as pyjwt
except ImportError:
    print("This example requires pyjwt[crypto]. Install with:")
    print("  pip install 'pyjwt[crypto]'")
    raise SystemExit(1)

from eatp.interop.jwt import (
    export_capability_as_jwt,
    export_chain_as_jwt,
    export_delegation_as_jwt,
    import_chain_from_jwt,
)


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
            id="org-acme",
            name="ACME Corp",
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

    # Establish an agent
    chain = await ops.establish(
        agent_id="agent-data-analyst",
        authority_id="org-acme",
        capabilities=[
            CapabilityRequest(capability="analyze_data", capability_type=CapabilityType.ACTION),
            CapabilityRequest(capability="read_reports", capability_type=CapabilityType.ACCESS),
        ],
        constraints=["read_only", "audit_required"],
    )

    # Delegate to a second agent so the chain has delegation records
    delegation = await ops.delegate(
        delegator_id="agent-data-analyst",
        delegatee_id="agent-junior",
        task_id="task-q4-analysis",
        capabilities=["analyze_data"],
        additional_constraints=["no_pii_export"],
    )

    # -- Export chain as JWT -------------------------------------------------
    # For JWT signing, we use HS256 with a shared secret for simplicity.
    # In production, use EdDSA with proper key management.
    jwt_secret = "eatp-example-secret-key-for-demo-only"

    print("1. Export trust chain as JWT")
    token = export_chain_as_jwt(chain, signing_key=jwt_secret, algorithm="HS256")
    print(f"   Token length: {len(token)} chars")
    print(f"   Token (first 80): {token[:80]}...")

    # -- Inspect JWT claims --------------------------------------------------
    print("\n2. Inspect JWT claims (unverified decode)")
    claims = pyjwt.decode(token, jwt_secret, algorithms=["HS256"])
    print(f"   iss (authority):    {claims['iss']}")
    print(f"   sub (agent):        {claims['sub']}")
    print(f"   eatp_version:       {claims['eatp_version']}")
    print(f"   eatp_type:          {claims['eatp_type']}")
    print(f"   Chain capabilities: {len(claims['eatp_chain']['capabilities'])}")
    print(f"   Chain genesis ID:   {claims['eatp_chain']['genesis']['id']}")

    # -- Import JWT back to TrustLineageChain --------------------------------
    print("\n3. Import JWT back to TrustLineageChain")
    restored_chain = import_chain_from_jwt(token, verify_key=jwt_secret, algorithm="HS256")
    print(f"   Agent ID:      {restored_chain.genesis.agent_id}")
    print(f"   Authority:     {restored_chain.genesis.authority_id}")
    print(f"   Capabilities:  {[c.capability for c in restored_chain.capabilities]}")
    print(f"   Chain intact:  {restored_chain.genesis.id == chain.genesis.id}")

    # -- Export individual capability as JWT ----------------------------------
    print("\n4. Export capability attestation as JWT")
    cap_token = export_capability_as_jwt(
        chain.capabilities[0],
        signing_key=jwt_secret,
        algorithm="HS256",
    )
    cap_claims = pyjwt.decode(cap_token, jwt_secret, algorithms=["HS256"])
    print(f"   Capability:  {cap_claims['eatp_capability']['capability']}")
    print(f"   Type:        {cap_claims['eatp_capability']['capability_type']}")
    print(f"   Attester:    {cap_claims['iss']}")

    # -- Export delegation as JWT --------------------------------------------
    print("\n5. Export delegation record as JWT")
    # Get the delegatee chain which has the delegation records
    delegatee_chain = await store.get_chain("agent-junior")
    del_token = export_delegation_as_jwt(
        delegatee_chain.delegations[0],
        signing_key=jwt_secret,
        algorithm="HS256",
    )
    del_claims = pyjwt.decode(del_token, jwt_secret, algorithms=["HS256"])
    print(f"   Delegator:   {del_claims['iss']}")
    print(f"   Delegatee:   {del_claims['sub']}")
    print(f"   Task:        {del_claims['eatp_delegation']['task_id']}")
    print(f"   Delegated:   {del_claims['eatp_delegation']['capabilities_delegated']}")

    print("\nJWT interop demo completed.")


if __name__ == "__main__":
    asyncio.run(main())
