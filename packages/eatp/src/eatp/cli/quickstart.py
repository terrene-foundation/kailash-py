# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP CLI Quickstart -- interactive demo of all 4 trust operations.

Demonstrates the Enterprise Agent Trust Protocol in 30 seconds:
1. ESTABLISH: Create authority and agent with capabilities
2. VERIFY: Verify agent authorization (shows APPROVED)
3. DELEGATE: Delegate from agent-1 to agent-2 with constraints
4. VERIFY: Verify delegated agent (shows tightened constraints)
5. AUDIT: Record an action in the immutable audit trail
6. Trust Score: Display computed trust score

Run directly::

    python -m eatp.cli.quickstart

Or programmatically::

    from eatp.cli.quickstart import run_quickstart
    import asyncio
    asyncio.run(run_quickstart())
"""

import asyncio
import logging
from datetime import datetime, timezone

from eatp.authority import AuthorityPermission, OrganizationalAuthority
from eatp.chain import (
    ActionResult,
    AuthorityType,
    CapabilityType,
)
from eatp.crypto import generate_keypair
from eatp.operations import CapabilityRequest, TrustKeyManager, TrustOperations
from eatp.scoring import compute_trust_score
from eatp.store.memory import InMemoryTrustStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ANSI escape codes (no external dependencies)
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_MAGENTA = "\033[35m"
_CYAN = "\033[36m"
_WHITE = "\033[37m"
_BG_GREEN = "\033[42m"
_BG_BLUE = "\033[44m"

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_WIDTH = 60
_SEPARATOR = _DIM + "-" * _WIDTH + _RESET


def _header(text: str) -> str:
    """Format a section header."""
    return f"{_BOLD}{_CYAN}{text}{_RESET}"


def _step(number: int, label: str) -> str:
    """Format a numbered step marker."""
    return f"{_BOLD}{_MAGENTA}[Step {number}]{_RESET} {_BOLD}{label}{_RESET}"


def _ok(text: str) -> str:
    """Format a success message."""
    return f"  {_GREEN}>>>{_RESET} {text}"


def _info(text: str) -> str:
    """Format an info message."""
    return f"  {_BLUE}---{_RESET} {text}"


def _detail(text: str) -> str:
    """Format a detail line (indented)."""
    return f"      {_DIM}{text}{_RESET}"


# ---------------------------------------------------------------------------
# In-memory authority registry (satisfies AuthorityRegistryProtocol)
# ---------------------------------------------------------------------------


class _QuickstartAuthorityRegistry:
    """Minimal authority registry for the quickstart demo.

    Stores authorities in memory. Satisfies the
    AuthorityRegistryProtocol interface required by TrustOperations.
    """

    def __init__(self) -> None:
        self._authorities: dict[str, OrganizationalAuthority] = {}

    async def initialize(self) -> None:
        """Initialize the registry (no-op for in-memory)."""

    def register(self, authority: OrganizationalAuthority) -> None:
        """Register an authority for later retrieval."""
        self._authorities[authority.id] = authority

    async def get_authority(
        self,
        authority_id: str,
        include_inactive: bool = False,
    ) -> OrganizationalAuthority:
        """Retrieve an authority by ID.

        Args:
            authority_id: The authority ID to look up.
            include_inactive: Whether to include inactive authorities.

        Returns:
            The matching OrganizationalAuthority.

        Raises:
            KeyError: If the authority_id is not found in the registry.
        """
        authority = self._authorities.get(authority_id)
        if authority is None:
            raise KeyError(
                f"Authority not found in quickstart registry: "
                f"'{authority_id}'. "
                f"Available: {list(self._authorities.keys())}"
            )
        return authority

    async def update_authority(self, authority: OrganizationalAuthority) -> None:
        """Persist changes to an authority record."""
        self._authorities[authority.id] = authority


# ---------------------------------------------------------------------------
# Quickstart implementation
# ---------------------------------------------------------------------------


async def run_quickstart(verbose: bool = False) -> None:
    """Run the EATP quickstart demo.

    Demonstrates all 4 EATP operations (ESTABLISH, VERIFY, DELEGATE,
    AUDIT) using real cryptographic operations with an in-memory store.

    Args:
        verbose: If True, print additional detail about internal
                 state such as chain hashes and capability IDs.
    """
    # ------------------------------------------------------------------
    # Banner
    # ------------------------------------------------------------------
    print()
    print(_header("EATP Quickstart Demo"))
    print(_SEPARATOR)
    print(_info("Demonstrating all 4 EATP trust operations"))
    print()

    # ------------------------------------------------------------------
    # Setup: keypair, authority, store, operations
    # ------------------------------------------------------------------
    print(_step(1, "ESTABLISH -- Create authority and agent"))
    print()

    private_key, public_key = generate_keypair()
    authority_id = "demo-authority"
    signing_key_id = "key-demo"

    authority = OrganizationalAuthority(
        id=authority_id,
        name="Demo Authority",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=public_key,
        signing_key_id=signing_key_id,
        permissions=[
            AuthorityPermission.CREATE_AGENTS,
            AuthorityPermission.DELEGATE_TRUST,
            AuthorityPermission.GRANT_CAPABILITIES,
        ],
    )

    registry = _QuickstartAuthorityRegistry()
    registry.register(authority)

    key_manager = TrustKeyManager()
    key_manager.register_key(signing_key_id, private_key)

    store = InMemoryTrustStore()
    await store.initialize()

    trust_ops = TrustOperations(
        authority_registry=registry,
        key_manager=key_manager,
        trust_store=store,
    )
    await trust_ops.initialize()

    print(_ok("Authority created: Demo Authority"))
    if verbose:
        print(_detail(f"Authority ID: {authority_id}"))
        print(_detail(f"Public key:   {public_key[:24]}..."))

    # ------------------------------------------------------------------
    # Step 1: ESTABLISH agent-1
    # ------------------------------------------------------------------
    agent1_id = "compliance-agent"
    chain1 = await trust_ops.establish(
        agent_id=agent1_id,
        authority_id=authority_id,
        capabilities=[
            CapabilityRequest(
                capability="analyze_data",
                capability_type=CapabilityType.ACTION,
            ),
            CapabilityRequest(
                capability="generate_report",
                capability_type=CapabilityType.ACTION,
            ),
            CapabilityRequest(
                capability="read_database",
                capability_type=CapabilityType.ACCESS,
            ),
        ],
        constraints=["audit_required"],
    )

    cap_names = [c.capability for c in chain1.capabilities]
    print(_ok(f"Agent established: {agent1_id}"))
    print(_detail(f"Capabilities: {', '.join(cap_names)}"))
    print(_detail("Constraints:  audit_required"))
    if verbose:
        print(_detail(f"Genesis ID:   {chain1.genesis.id}"))
        print(_detail(f"Chain hash:   {chain1.hash()[:16]}..."))
    print()

    # ------------------------------------------------------------------
    # Step 2: VERIFY agent-1 can analyze_data
    # ------------------------------------------------------------------
    print(_step(2, "VERIFY -- Check agent authorization"))
    print()

    result = await trust_ops.verify(
        agent_id=agent1_id,
        action="analyze_data",
    )

    if result.valid:
        print(_ok(f"VERIFIED / APPROVED: {agent1_id}"))
        print(_detail(f"Action: analyze_data"))
        if result.capability_used:
            print(_detail(f"Capability: {result.capability_used}"))
        if result.effective_constraints:
            constraints_str = ", ".join(result.effective_constraints)
            print(_detail(f"Constraints: {constraints_str}"))
    else:
        print(f"  {_YELLOW}!!!{_RESET} DENIED: {result.reason}")

    if verbose:
        print(_detail(f"Level: {result.level.value}"))
    print()

    # ------------------------------------------------------------------
    # Step 3: DELEGATE from agent-1 to agent-2 with constraints
    # ------------------------------------------------------------------
    print(_step(3, "DELEGATE -- Transfer trust with constraints"))
    print()

    agent2_id = "trading-agent"
    delegation = await trust_ops.delegate(
        delegator_id=agent1_id,
        delegatee_id=agent2_id,
        task_id="task-quarterly-analysis",
        capabilities=["analyze_data", "read_database"],
        additional_constraints=["read_only", "no_pii_export"],
    )

    print(_ok(f"Delegated: {agent1_id} -> {agent2_id}"))
    print(_detail("Capabilities: analyze_data, read_database"))
    print(_detail("Added constraints: read_only, no_pii_export"))
    if verbose:
        print(_detail(f"Delegation ID: {delegation.id}"))
        print(_detail(f"Constraint subset: {', '.join(delegation.constraint_subset)}"))
    print()

    # ------------------------------------------------------------------
    # Step 4: VERIFY delegated agent (shows tightened constraints)
    # ------------------------------------------------------------------
    print(_step(4, "VERIFY -- Check delegated agent authorization"))
    print()

    result2 = await trust_ops.verify(
        agent_id=agent2_id,
        action="analyze_data",
    )

    if result2.valid:
        print(_ok(f"VERIFIED / APPROVED: {agent2_id}"))
        print(_detail("Action: analyze_data"))
        if result2.effective_constraints:
            constraints_str = ", ".join(result2.effective_constraints)
            print(_detail(f"Constraints: {constraints_str}"))
        else:
            # Show the delegation-level constraints
            chain2 = await store.get_chain(agent2_id)
            env_constraints = [str(c.value) for c in chain2.constraint_envelope.active_constraints]
            if env_constraints:
                print(_detail(f"Constraints: {', '.join(env_constraints)}"))
    else:
        print(f"  {_YELLOW}!!!{_RESET} DENIED: {result2.reason}")

    if verbose:
        print(_detail(f"Level: {result2.level.value}"))
        if result2.capability_used:
            print(_detail(f"Capability: {result2.capability_used}"))
    print()

    # ------------------------------------------------------------------
    # Step 5: AUDIT -- Record an action
    # ------------------------------------------------------------------
    print(_step(5, "AUDIT -- Record action in immutable trail"))
    print()

    anchor = await trust_ops.audit(
        agent_id=agent1_id,
        action="analyze_data",
        resource="finance_db.quarterly_results",
        result=ActionResult.SUCCESS,
        context_data={
            "rows_analyzed": 1500,
            "duration_ms": 342,
        },
    )

    print(_ok(f"Audit anchor recorded for {agent1_id}"))
    print(_detail(f"Action:   analyze_data"))
    print(_detail(f"Resource: finance_db.quarterly_results"))
    print(_detail(f"Result:   {anchor.result.value}"))
    if verbose:
        print(_detail(f"Anchor ID:  {anchor.id}"))
        print(_detail(f"Chain hash: {anchor.trust_chain_hash[:16]}..."))
        ts = anchor.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        print(_detail(f"Timestamp:  {ts}"))
    print()

    # ------------------------------------------------------------------
    # Step 6: Trust Score
    # ------------------------------------------------------------------
    print(_step(6, "Trust Score -- Compute agent trust level"))
    print()

    score = await compute_trust_score(agent1_id, store)

    print(_ok(f"Trust Score for {agent1_id}: {_BOLD}{score.score}/100{_RESET} (Grade {score.grade})"))
    if verbose:
        for factor, value in score.breakdown.items():
            factor_label = factor.replace("_", " ").title()
            print(_detail(f"{factor_label}: {value:.1f}"))
    print()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(_SEPARATOR)
    print(_header("Quickstart Complete"))
    print()
    print(_info("All 4 EATP operations demonstrated:"))
    print(_detail("ESTABLISH - Created authority + agent"))
    print(_detail("VERIFY    - Checked agent authorization"))
    print(_detail("DELEGATE  - Transferred trust with constraints"))
    print(_detail("AUDIT     - Recorded action in immutable trail"))
    print()

    # ------------------------------------------------------------------
    # Next steps
    # ------------------------------------------------------------------
    print(_header("Your turn! Try:"))
    print()
    print(f"  {_WHITE}eatp init --name 'My Org'{_RESET}")
    print(f"  {_WHITE}eatp establish my-agent --authority <id> --capabilities read,write{_RESET}")
    print(f"  {_WHITE}eatp verify my-agent --action read{_RESET}")
    print(f"  {_WHITE}eatp delegate --from my-agent --to helper --capabilities read{_RESET}")
    print(f"  {_WHITE}eatp status{_RESET}")
    print()
    print(f"{_DIM}Docs: https://eatp.dev | pip install eatp{_RESET}")
    print(_RESET)


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for ``python -m eatp.cli.quickstart``."""
    asyncio.run(run_quickstart(verbose=False))


if __name__ == "__main__":
    main()
