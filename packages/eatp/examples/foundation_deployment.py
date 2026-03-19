# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Terrene Foundation EATP Deployment -- production reference implementation.

This script demonstrates how the Terrene Foundation deploys EATP for its own
AI agent infrastructure.  It walks through the complete lifecycle:

    1. Create the Foundation authority keypair (Ed25519)
    2. Establish Foundation AI agents with appropriate constraints
    3. Configure EATP verification for agent workflows
    4. Publish the Foundation's genesis record
    5. Make the entire trust chain externally verifiable

Run:
    python foundation_deployment.py

Prerequisites:
    pip install eatp
"""

import asyncio
import json
from datetime import datetime, timezone

from eatp import (
    CapabilityRequest,
    InMemoryTrustStore,
    TrustKeyManager,
    TrustOperations,
    VerificationLevel,
)
from eatp.authority import AuthorityPermission, OrganizationalAuthority
from eatp.chain import ActionResult, AuthorityType, CapabilityType
from eatp.constraint_validator import ConstraintValidator
from eatp.crypto import generate_keypair, verify_signature
from eatp.enforce import StrictEnforcer, Verdict
from eatp.enforce.challenge import ChallengeProtocol


# ---------------------------------------------------------------------------
# Helper: minimal in-memory authority registry (production would use ESA DB)
# ---------------------------------------------------------------------------


class FoundationAuthorityRegistry:
    """In-memory authority registry for the Foundation deployment.

    In production this would be backed by the ESA PostgreSQL store
    (eatp.esa.registry.ESARegistry). For this demonstration we keep
    everything in memory so the example is self-contained.
    """

    def __init__(self):
        self._authorities: dict[str, OrganizationalAuthority] = {}

    async def initialize(self) -> None:
        """No-op for in-memory registry."""

    def register(self, authority: OrganizationalAuthority) -> None:
        """Register an authority in the local registry."""
        self._authorities[authority.id] = authority

    async def get_authority(
        self,
        authority_id: str,
        include_inactive: bool = False,
    ) -> OrganizationalAuthority:
        """Retrieve an authority by ID."""
        authority = self._authorities.get(authority_id)
        if authority is None:
            raise KeyError(f"Authority not found: {authority_id}")
        if not authority.is_active and not include_inactive:
            raise KeyError(f"Authority is inactive: {authority_id}")
        return authority


async def main() -> None:
    # ======================================================================
    # STEP 1: Create the Foundation authority keypair
    # ======================================================================
    # The Foundation is the root of trust.  Its Ed25519 keypair is the
    # cryptographic anchor that signs every genesis record.  In production
    # the private key lives in an HSM; here we generate it in memory.
    print("=" * 72)
    print("STEP 1: Create Foundation Authority Keypair")
    print("=" * 72)

    foundation_private_key, foundation_public_key = generate_keypair()
    print(f"  Public key  : {foundation_public_key[:32]}...")
    print(f"  Algorithm   : Ed25519 (PyNaCl)")
    print(f"  Key length  : 256-bit")

    # Register the key in the key manager so TrustOperations can sign
    key_mgr = TrustKeyManager()
    key_mgr.register_key("foundation-root-key", foundation_private_key)

    # Create the Foundation authority record
    authority_registry = FoundationAuthorityRegistry()
    foundation_authority = OrganizationalAuthority(
        id="terrene-foundation",
        name="Terrene Foundation",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=foundation_public_key,
        signing_key_id="foundation-root-key",
        permissions=[
            AuthorityPermission.CREATE_AGENTS,
            AuthorityPermission.DELEGATE_TRUST,
            AuthorityPermission.GRANT_CAPABILITIES,
            AuthorityPermission.REVOKE_CAPABILITIES,
            AuthorityPermission.CREATE_SUBORDINATE_AUTHORITIES,
        ],
        metadata={
            "organization": "Terrene Foundation",
            "purpose": "Root trust authority for Foundation AI agents",
            "website": "https://terrenefoundation.org",
        },
    )
    authority_registry.register(foundation_authority)
    print(f"  Authority ID: {foundation_authority.id}")
    print(f"  Permissions : {[p.value for p in foundation_authority.permissions]}")

    # Initialize the trust store and operations
    trust_store = InMemoryTrustStore()
    await trust_store.initialize()

    ops = TrustOperations(
        authority_registry=authority_registry,
        key_manager=key_mgr,
        trust_store=trust_store,
    )

    # ======================================================================
    # STEP 2: Establish Foundation AI agents with constraints
    # ======================================================================
    # Each Foundation agent gets a trust chain that defines exactly what
    # it can do.  Constraints enforce the principle of least privilege.
    print()
    print("=" * 72)
    print("STEP 2: Establish Foundation AI Agents")
    print("=" * 72)

    # --- Agent 1: Research Analyst -----------------------------------------
    # Can analyze public data and generate reports, but cannot access
    # private repositories or make external API calls.
    print("\n  [Agent] foundation-research-analyst")
    research_chain = await ops.establish(
        agent_id="foundation-research-analyst",
        authority_id="terrene-foundation",
        capabilities=[
            CapabilityRequest(
                capability="analyze_public_data",
                capability_type=CapabilityType.ACTION,
                constraints=["audit_required", "no_pii_export"],
                scope={"datasets": ["arxiv", "semantic_scholar", "open_patents"]},
            ),
            CapabilityRequest(
                capability="generate_report",
                capability_type=CapabilityType.ACTION,
                constraints=["audit_required"],
            ),
            CapabilityRequest(
                capability="read_knowledge_base",
                capability_type=CapabilityType.ACCESS,
                scope={"collections": ["foundation-public", "research-papers"]},
            ),
        ],
        constraints=["audit_required", "no_pii_export", "business_hours_only"],
    )
    print(f"    Genesis ID     : {research_chain.genesis.id}")
    print(f"    Capabilities   : {len(research_chain.capabilities)}")
    all_constraints = list(dict.fromkeys(c for cap in research_chain.capabilities for c in cap.constraints))
    print(f"    Constraints    : {all_constraints}")

    # --- Agent 2: Code Review Agent ----------------------------------------
    # Can read source code and run static analysis, but cannot write to
    # repositories or execute arbitrary code.
    print("\n  [Agent] foundation-code-reviewer")
    reviewer_chain = await ops.establish(
        agent_id="foundation-code-reviewer",
        authority_id="terrene-foundation",
        capabilities=[
            CapabilityRequest(
                capability="read_source_code",
                capability_type=CapabilityType.ACCESS,
                constraints=["audit_required"],
                scope={"repositories": ["eatp-python", "eatp-rust"]},
            ),
            CapabilityRequest(
                capability="run_static_analysis",
                capability_type=CapabilityType.ACTION,
                constraints=["audit_required", "sandbox_only"],
            ),
            CapabilityRequest(
                capability="submit_review_comments",
                capability_type=CapabilityType.ACTION,
                constraints=["audit_required", "human_review_required"],
            ),
        ],
        constraints=["audit_required", "sandbox_only"],
    )
    print(f"    Genesis ID     : {reviewer_chain.genesis.id}")
    print(f"    Capabilities   : {len(reviewer_chain.capabilities)}")

    # --- Agent 3: Governance Monitor ---------------------------------------
    # Watches over other agents. Has read access to audit trails and can
    # flag anomalies, but cannot modify trust chains or agent capabilities.
    print("\n  [Agent] foundation-governance-monitor")
    monitor_chain = await ops.establish(
        agent_id="foundation-governance-monitor",
        authority_id="terrene-foundation",
        capabilities=[
            CapabilityRequest(
                capability="read_audit_trail",
                capability_type=CapabilityType.ACCESS,
                constraints=["audit_required"],
            ),
            CapabilityRequest(
                capability="flag_anomaly",
                capability_type=CapabilityType.ACTION,
                constraints=["audit_required"],
            ),
            CapabilityRequest(
                capability="generate_compliance_report",
                capability_type=CapabilityType.ACTION,
                constraints=["audit_required"],
            ),
        ],
        constraints=["audit_required", "read_only_trust_store"],
    )
    print(f"    Genesis ID     : {monitor_chain.genesis.id}")
    print(f"    Capabilities   : {len(monitor_chain.capabilities)}")

    # ======================================================================
    # STEP 3: Configure EATP verification for agent workflows
    # ======================================================================
    # Before any agent performs an action, EATP verifies that:
    #   (a) the agent has a valid trust chain
    #   (b) the chain includes the required capability
    #   (c) all constraints are satisfied
    # The StrictEnforcer translates verification results into verdicts.
    print()
    print("=" * 72)
    print("STEP 3: Configure Verification for Agent Workflows")
    print("=" * 72)

    # 3a. Verify that the research analyst can analyze public data
    print("\n  Verifying 'analyze_public_data' for research-analyst...")
    result = await ops.verify(
        agent_id="foundation-research-analyst",
        action="analyze_public_data",
        level=VerificationLevel.STANDARD,
    )
    print(f"    Valid  : {result.valid}")
    print(f"    Level  : {result.level.value}")

    # 3b. Verify that the research analyst CANNOT delete records
    print("\n  Verifying 'delete_records' for research-analyst (should fail)...")
    denied_result = await ops.verify(
        agent_id="foundation-research-analyst",
        action="delete_records",
    )
    print(f"    Valid  : {denied_result.valid}")
    print(f"    Reason : {denied_result.reason}")

    # 3c. Demonstrate constraint tightening via delegation
    # The research analyst delegates a subset of its capabilities
    # to a junior agent -- constraints can only tighten, never loosen.
    print("\n  Delegating 'analyze_public_data' to junior-researcher...")
    delegation = await ops.delegate(
        delegator_id="foundation-research-analyst",
        delegatee_id="foundation-junior-researcher",
        task_id="task-literature-review-2026-q1",
        capabilities=["analyze_public_data"],
        additional_constraints=["read_only", "max_100_queries"],
    )
    print(f"    Delegation ID  : {delegation.id}")
    print(f"    Constraints    : {delegation.constraint_subset}")

    # Verify the tightening invariant using ConstraintValidator
    validator = ConstraintValidator()
    tightening_result = validator.validate_tightening(
        parent_constraints={"cost_limit": 10000, "rate_limit": 100},
        child_constraints={"cost_limit": 2000, "rate_limit": 50},
    )
    print(f"\n  Constraint tightening valid: {tightening_result.valid}")

    # 3d. Challenge-response verification (live key possession proof)
    print("\n  Running challenge-response verification...")
    protocol = ChallengeProtocol(challenge_timeout_seconds=60)

    # The governance monitor challenges the research analyst
    challenge = protocol.create_challenge(
        challenger_id="foundation-governance-monitor",
        target_agent_id="foundation-research-analyst",
        required_proof="analyze_public_data",
    )
    print(f"    Challenge ID   : {challenge.challenge_id}")

    # The research analyst responds by signing the nonce
    response = protocol.respond_to_challenge(
        challenge=challenge,
        agent_key=foundation_private_key,
        chain=research_chain,
    )
    print(f"    Response agent : {response.agent_id}")

    # The governance monitor verifies the response
    is_valid = protocol.verify_response(
        challenge=challenge,
        response=response,
        agent_public_key=foundation_public_key,
    )
    print(f"    Verified       : {is_valid}")

    # 3e. Set up strict enforcement for production
    enforcer = StrictEnforcer()
    verify_result = await ops.verify(
        agent_id="foundation-research-analyst",
        action="analyze_public_data",
    )
    verdict = enforcer.classify(verify_result)
    print(f"\n  StrictEnforcer verdict: {verdict.value}")

    # ======================================================================
    # STEP 4: Publish the Foundation's genesis record
    # ======================================================================
    # The genesis record is the root of every trust chain.  Publishing it
    # means making it available for external verification.  In production
    # this would be written to a public ledger or well-known endpoint.
    print()
    print("=" * 72)
    print("STEP 4: Publish Foundation Genesis Records")
    print("=" * 72)

    # Record audit entries for the establishment actions
    for agent_id in [
        "foundation-research-analyst",
        "foundation-code-reviewer",
        "foundation-governance-monitor",
    ]:
        anchor = await ops.audit(
            agent_id=agent_id,
            action="agent_established",
            resource=f"trust-chain/{agent_id}",
            result=ActionResult.SUCCESS,
            context_data={
                "authority": "terrene-foundation",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        print(f"  [{agent_id}]")
        print(f"    Audit anchor   : {anchor.id}")
        print(f"    Chain hash     : {anchor.trust_chain_hash[:24]}...")

    # Serialize the genesis records for publication
    # In production you would POST this to a well-known EATP endpoint
    # or write it to a distributed ledger.
    genesis_manifest = {
        "protocol": "EATP",
        "version": "2.0",
        "authority": {
            "id": foundation_authority.id,
            "name": foundation_authority.name,
            "public_key": foundation_authority.public_key,
            "authority_type": foundation_authority.authority_type.value,
        },
        "agents": [],
        "published_at": datetime.now(timezone.utc).isoformat(),
    }

    for agent_id, chain in [
        ("foundation-research-analyst", research_chain),
        ("foundation-code-reviewer", reviewer_chain),
        ("foundation-governance-monitor", monitor_chain),
    ]:
        genesis_manifest["agents"].append(
            {
                "agent_id": agent_id,
                "genesis_id": chain.genesis.id,
                "authority_id": chain.genesis.authority_id,
                "capabilities": [cap.capability for cap in chain.capabilities],
                "chain_hash": chain.hash(),
            }
        )

    print(f"\n  Genesis manifest ({len(genesis_manifest['agents'])} agents):")
    print(f"    {json.dumps(genesis_manifest, indent=2, default=str)[:500]}...")

    # ======================================================================
    # STEP 5: Make the trust chain externally verifiable
    # ======================================================================
    # Any third party can verify Foundation agent trust chains by:
    #   1. Obtaining the Foundation's public key (from genesis manifest)
    #   2. Retrieving an agent's trust chain
    #   3. Verifying signatures and constraint integrity
    print()
    print("=" * 72)
    print("STEP 5: External Trust Chain Verification")
    print("=" * 72)

    # Simulate an external verifier checking the research analyst
    target_agent = "foundation-research-analyst"
    chain = await trust_store.get_chain(target_agent)

    # 5a. Verify genesis record signature
    genesis = chain.genesis
    print(f"\n  Verifying chain for: {target_agent}")
    print(f"    Genesis ID     : {genesis.id}")
    print(f"    Authority      : {genesis.authority_id}")
    print(f"    Agent ID       : {genesis.agent_id}")

    sig_valid = verify_signature(
        payload=genesis.to_signing_payload(),
        signature=genesis.signature,
        public_key=foundation_public_key,
    )
    print(f"    Genesis sig OK : {sig_valid}")

    # 5b. Verify chain integrity (hash chain)
    chain_hash = chain.hash()
    print(f"    Chain hash     : {chain_hash[:24]}...")

    # 5c. Verify capabilities are properly attested
    for cap in chain.capabilities:
        print(f"    Capability     : {cap.capability} ({cap.capability_type.value})")
        print(f"      Attester     : {cap.attester_id}")
        print(f"      Constraints  : {cap.constraints}")

    # 5d. Full EATP VERIFY operation
    full_result = await ops.verify(
        agent_id=target_agent,
        action="analyze_public_data",
        level=VerificationLevel.FULL,
    )
    print(f"\n    Full verification:")
    print(f"      Valid        : {full_result.valid}")
    print(f"      Level        : {full_result.level.value}")

    # 5e. List all chains to show the complete trust topology
    all_chains = await trust_store.list_chains(authority_id="terrene-foundation")
    print(f"\n  Foundation trust topology: {len(all_chains)} agent(s)")
    for c in all_chains:
        print(f"    - {c.genesis.agent_id} ({len(c.capabilities)} capabilities)")

    print()
    print("=" * 72)
    print("Foundation EATP deployment complete.")
    print("All trust chains are signed, audited, and externally verifiable.")
    print("=" * 72)


if __name__ == "__main__":
    asyncio.run(main())
