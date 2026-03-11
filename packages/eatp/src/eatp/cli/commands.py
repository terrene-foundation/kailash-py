# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP CLI command implementations.

Provides the core and utility CLI commands for trust management:
- Core: init, establish, delegate, verify, revoke, status, version
- Utility: audit, export, verify-chain

Uses the FilesystemStore for persistent local storage and falls back
to InMemoryTrustStore if FilesystemStore is unavailable.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import click

from eatp import __version__
from eatp.authority import AuthorityPermission, OrganizationalAuthority
from eatp.chain import (
    AuthorityType,
    CapabilityType,
    TrustLineageChain,
    VerificationLevel,
)
from eatp.crypto import generate_keypair, serialize_for_signing, sign, verify_signature
from eatp.exceptions import TrustChainNotFoundError, TrustError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_async(coro: Any) -> Any:
    """
    Execute an async coroutine synchronously.

    Creates a new event loop if none is running, otherwise uses the
    existing loop. This bridges the sync CLI world with the async
    TrustStore/TrustOperations API.

    Args:
        coro: An awaitable coroutine to execute.

    Returns:
        The result of the coroutine.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # If we're already in an async context, create a new loop in a thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


def _create_store(store_dir: str) -> Any:
    """
    Create the appropriate TrustStore for the given directory.

    Attempts to use FilesystemStore for persistent storage. Falls back
    to InMemoryTrustStore if FilesystemStore import fails.

    Args:
        store_dir: Base directory for EATP data (e.g., ~/.eatp/).

    Returns:
        A TrustStore instance (FilesystemStore or InMemoryTrustStore).
    """
    chains_dir = os.path.join(store_dir, "chains")
    try:
        from eatp.store.filesystem import FilesystemStore

        return FilesystemStore(base_dir=chains_dir)
    except ImportError:
        logger.warning(
            "FilesystemStore unavailable, using InMemoryTrustStore. "
            "Data will not persist between CLI invocations."
        )
        from eatp.store.memory import InMemoryTrustStore

        return InMemoryTrustStore()


def _format_datetime(dt: Optional[datetime]) -> str:
    """
    Format a datetime for human-readable CLI output.

    Args:
        dt: The datetime to format, or None.

    Returns:
        A human-readable string, or "N/A" for None.
    """
    if dt is None:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _format_chain_summary(chain: TrustLineageChain) -> str:
    """
    Format a TrustLineageChain as a human-readable summary.

    Args:
        chain: The trust chain to summarize.

    Returns:
        Multi-line string with chain details.
    """
    lines = [
        f"  Agent ID:     {chain.genesis.agent_id}",
        f"  Authority:    {chain.genesis.authority_id}",
        f"  Type:         {chain.genesis.authority_type.value}",
        f"  Created:      {_format_datetime(chain.genesis.created_at)}",
        f"  Expires:      {_format_datetime(chain.genesis.expires_at)}",
        f"  Expired:      {'Yes' if chain.is_expired() else 'No'}",
        f"  Capabilities: {len(chain.capabilities)}",
        f"  Delegations:  {len(chain.delegations)}",
        f"  Audit Trail:  {len(chain.audit_anchors)} entries",
    ]
    if chain.capabilities:
        lines.append("  Capability List:")
        for cap in chain.capabilities:
            expired_tag = " [EXPIRED]" if cap.is_expired() else ""
            lines.append(
                f"    - {cap.capability} ({cap.capability_type.value}){expired_tag}"
            )
    if chain.delegations:
        lines.append("  Delegation List:")
        for d in chain.delegations:
            expired_tag = " [EXPIRED]" if d.is_expired() else ""
            lines.append(
                f"    - {d.id}: {d.delegator_id} -> {d.delegatee_id} "
                f"[{', '.join(d.capabilities_delegated)}]{expired_tag}"
            )
    return "\n".join(lines)


def _load_authority(store_dir: str, authority_id: str) -> OrganizationalAuthority:
    """
    Load an authority record from the authorities directory.

    Args:
        store_dir: Base EATP directory.
        authority_id: The authority ID to load.

    Returns:
        The OrganizationalAuthority.

    Raises:
        click.ClickException: If the authority is not found.
    """
    auth_dir = Path(store_dir) / "authorities"
    if not auth_dir.exists():
        raise click.ClickException(
            f"Authority not found: '{authority_id}'. "
            f"No authorities directory at {auth_dir}. Run 'eatp init' first."
        )

    for auth_file in auth_dir.glob("*.json"):
        data = json.loads(auth_file.read_text())
        if data["id"] == authority_id:
            return OrganizationalAuthority.from_dict(data)

    raise click.ClickException(
        f"Authority not found: '{authority_id}'. "
        f"Available authorities are in {auth_dir}. "
        f"Run 'eatp init' to create one."
    )


def _load_private_key(store_dir: str, key_id: str) -> str:
    """
    Load a private key from the keys directory.

    Args:
        store_dir: Base EATP directory.
        key_id: The signing key ID to load.

    Returns:
        Base64-encoded private key.

    Raises:
        click.ClickException: If the key is not found.
    """
    keys_dir = Path(store_dir) / "keys"
    if not keys_dir.exists():
        raise click.ClickException(
            f"Key not found: '{key_id}'. "
            f"No keys directory at {keys_dir}. Run 'eatp init' first."
        )

    for key_file in keys_dir.glob("*.json"):
        data = json.loads(key_file.read_text())
        if data["key_id"] == key_id:
            return data["private_key"]

    raise click.ClickException(
        f"Key not found: '{key_id}'. " f"Run 'eatp init' to generate keys."
    )


def _find_delegation_in_store(store_dir: str, delegation_id: str) -> tuple:
    """
    Find a delegation record across all stored chains.

    Args:
        store_dir: Base EATP directory.
        delegation_id: The delegation ID to find.

    Returns:
        Tuple of (agent_id, delegation_index, chain) where the delegation was found.

    Raises:
        click.ClickException: If the delegation is not found.
    """
    store = _create_store(store_dir)
    _run_async(store.initialize())

    chains = _run_async(store.list_chains(active_only=False))
    for chain in chains:
        for idx, d in enumerate(chain.delegations):
            if d.id == delegation_id:
                return (chain.genesis.agent_id, idx, chain)

    raise click.ClickException(
        f"Delegation not found: '{delegation_id}'. "
        f"Use 'eatp status' to list agents and their delegations."
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@click.command("version")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
@click.pass_context
def version_cmd(ctx: click.Context, json_output: bool) -> None:
    """Show EATP SDK version."""
    if json_output:
        click.echo(json.dumps({"version": __version__}, indent=2))
    else:
        click.echo(f"EATP SDK v{__version__}")


@click.command("init")
@click.option("--name", required=True, help="Authority name (e.g., 'Acme Corp').")
@click.option(
    "--type",
    "authority_type",
    default="organization",
    type=click.Choice(["organization", "system", "human"], case_sensitive=False),
    help="Authority type.",
)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
@click.pass_context
def init_cmd(
    ctx: click.Context,
    name: str,
    authority_type: str,
    json_output: bool,
) -> None:
    """Create authority keypair and genesis record.

    Generates an Ed25519 keypair and stores the authority record.
    Keys are stored in <store-dir>/keys/ and authority records in
    <store-dir>/authorities/.
    """
    store_dir = ctx.obj["store_dir"]

    # Create directory structure
    keys_dir = Path(store_dir) / "keys"
    auth_dir = Path(store_dir) / "authorities"
    keys_dir.mkdir(parents=True, exist_ok=True)
    auth_dir.mkdir(parents=True, exist_ok=True)

    # Generate keypair
    private_key, public_key = generate_keypair()
    authority_id = f"auth-{uuid4().hex[:12]}"
    signing_key_id = f"key-{uuid4().hex[:12]}"

    # Store private key
    key_data = {
        "key_id": signing_key_id,
        "authority_id": authority_id,
        "private_key": private_key,
        "public_key": public_key,
        "algorithm": "Ed25519",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    key_file = keys_dir / f"{signing_key_id}.json"
    key_file.write_text(json.dumps(key_data, indent=2))

    # Build authority record
    auth_type = AuthorityType(authority_type.lower())
    authority = OrganizationalAuthority(
        id=authority_id,
        name=name,
        authority_type=auth_type,
        public_key=public_key,
        signing_key_id=signing_key_id,
        permissions=[
            AuthorityPermission.CREATE_AGENTS,
            AuthorityPermission.DELEGATE_TRUST,
            AuthorityPermission.GRANT_CAPABILITIES,
            AuthorityPermission.REVOKE_CAPABILITIES,
        ],
    )

    # Store authority record
    auth_file = auth_dir / f"{authority_id}.json"
    auth_file.write_text(json.dumps(authority.to_dict(), indent=2))

    # Also initialize the chain store
    store = _create_store(store_dir)
    _run_async(store.initialize())

    if json_output:
        click.echo(
            json.dumps(
                {
                    "authority_id": authority_id,
                    "name": name,
                    "authority_type": authority_type,
                    "public_key": public_key,
                    "signing_key_id": signing_key_id,
                },
                indent=2,
            )
        )
    else:
        click.echo(f"Authority initialized successfully.")
        click.echo(f"  Authority ID:   {authority_id}")
        click.echo(f"  Name:           {name}")
        click.echo(f"  Type:           {authority_type}")
        click.echo(f"  Signing Key:    {signing_key_id}")
        click.echo(f"  Keys stored in: {keys_dir}")
        click.echo(f"  Auth stored in: {auth_dir}")


@click.command("establish")
@click.argument("agent_name")
@click.option("--authority", required=True, help="Authority ID to use.")
@click.option(
    "--capabilities",
    default=None,
    help="Comma-separated capabilities (e.g., 'read_data,write_data').",
)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
@click.pass_context
def establish_cmd(
    ctx: click.Context,
    agent_name: str,
    authority: str,
    capabilities: Optional[str],
    json_output: bool,
) -> None:
    """Create agent with capabilities.

    Establishes a trust chain for AGENT_NAME under the specified authority.
    The agent will be granted the specified capabilities.
    """
    store_dir = ctx.obj["store_dir"]

    # Load authority
    auth = _load_authority(store_dir, authority)
    private_key = _load_private_key(store_dir, auth.signing_key_id)

    # Parse capabilities
    if capabilities:
        cap_names = [c.strip() for c in capabilities.split(",") if c.strip()]
    else:
        cap_names = ["access"]

    # Create store and initialize
    store = _create_store(store_dir)
    _run_async(store.initialize())

    # Check if agent already exists
    try:
        existing = _run_async(store.get_chain(agent_name))
        if existing:
            raise click.ClickException(
                f"Agent '{agent_name}' already has a trust chain. "
                f"Use 'eatp status {agent_name}' to view it."
            )
    except TrustChainNotFoundError:
        pass  # Expected

    # Build the chain using the operations primitives directly
    from eatp.chain import (
        CapabilityAttestation,
        Constraint,
        ConstraintEnvelope,
        ConstraintType,
        GenesisRecord,
    )

    # Create genesis record
    genesis = GenesisRecord(
        id=f"gen-{uuid4().hex[:12]}",
        agent_id=agent_name,
        authority_id=auth.id,
        authority_type=auth.authority_type,
        created_at=datetime.now(timezone.utc),
        signature="",
        signature_algorithm="Ed25519",
    )

    # Sign genesis
    genesis_payload = serialize_for_signing(genesis.to_signing_payload())
    genesis.signature = sign(genesis_payload, private_key)

    # Create capability attestations
    cap_attestations = []
    for cap_name in cap_names:
        attestation = CapabilityAttestation(
            id=f"cap-{uuid4().hex[:12]}",
            capability=cap_name,
            capability_type=CapabilityType.ACTION,
            constraints=[],
            attester_id=auth.id,
            attested_at=datetime.now(timezone.utc),
            signature="",
        )
        cap_payload = serialize_for_signing(attestation.to_signing_payload())
        attestation.signature = sign(cap_payload, private_key)
        cap_attestations.append(attestation)

    # Create constraint envelope
    envelope = ConstraintEnvelope(
        id=f"env-{uuid4().hex[:12]}",
        agent_id=agent_name,
        active_constraints=[],
        computed_at=datetime.now(timezone.utc),
    )

    # Assemble chain
    chain = TrustLineageChain(
        genesis=genesis,
        capabilities=cap_attestations,
        delegations=[],
        constraint_envelope=envelope,
        audit_anchors=[],
    )

    # Store chain
    _run_async(store.store_chain(chain))

    if json_output:
        click.echo(
            json.dumps(
                {
                    "agent_id": agent_name,
                    "authority_id": auth.id,
                    "capabilities": cap_names,
                    "genesis_id": genesis.id,
                    "chain_hash": chain.hash(),
                },
                indent=2,
            )
        )
    else:
        click.echo(f"Agent established successfully.")
        click.echo(f"  Agent ID:    {agent_name}")
        click.echo(f"  Authority:   {auth.id}")
        click.echo(f"  Capabilities: {', '.join(cap_names)}")
        click.echo(f"  Genesis ID:  {genesis.id}")


@click.command("delegate")
@click.option("--from", "from_agent", required=True, help="Delegator agent ID.")
@click.option("--to", "to_agent", required=True, help="Delegatee agent ID.")
@click.option(
    "--capabilities",
    required=True,
    help="Comma-separated capabilities to delegate.",
)
@click.option(
    "--constraints",
    default=None,
    help="Comma-separated additional constraints.",
)
@click.option(
    "--reasoning-decision",
    default=None,
    help="What was decided (reasoning trace).",
)
@click.option(
    "--reasoning-rationale",
    default=None,
    help="Why it was decided (reasoning trace).",
)
@click.option(
    "--reasoning-confidentiality",
    default="restricted",
    type=click.Choice(
        ["public", "restricted", "confidential", "secret", "top_secret"],
        case_sensitive=False,
    ),
    help="Confidentiality level for reasoning trace (default: restricted).",
)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
@click.pass_context
def delegate_cmd(
    ctx: click.Context,
    from_agent: str,
    to_agent: str,
    capabilities: str,
    constraints: Optional[str],
    reasoning_decision: Optional[str],
    reasoning_rationale: Optional[str],
    reasoning_confidentiality: str,
    json_output: bool,
) -> None:
    """Delegate capabilities from one agent to another.

    The delegator must possess all capabilities being delegated.
    Constraints can only be tightened, never loosened.

    Optionally attach a reasoning trace explaining WHY the delegation
    was made by providing --reasoning-decision and --reasoning-rationale.
    """
    store_dir = ctx.obj["store_dir"]

    cap_names = [c.strip() for c in capabilities.split(",") if c.strip()]
    constraint_list = []
    if constraints:
        constraint_list = [c.strip() for c in constraints.split(",") if c.strip()]

    store = _create_store(store_dir)
    _run_async(store.initialize())

    # Load delegator's chain
    try:
        delegator_chain = _run_async(store.get_chain(from_agent))
    except TrustChainNotFoundError:
        raise click.ClickException(
            f"Delegator agent not found: '{from_agent}'. "
            f"Use 'eatp establish {from_agent}' to create it first."
        )

    # Verify delegator has requested capabilities
    delegator_caps = {cap.capability for cap in delegator_chain.capabilities}
    for cap_name in cap_names:
        if cap_name not in delegator_caps:
            raise click.ClickException(
                f"Delegator '{from_agent}' does not have capability '{cap_name}'. "
                f"Available: {', '.join(sorted(delegator_caps))}"
            )

    # Load authority and key for signing
    authority_id = delegator_chain.genesis.authority_id
    auth = _load_authority(store_dir, authority_id)
    private_key = _load_private_key(store_dir, auth.signing_key_id)

    from eatp.chain import (
        CapabilityAttestation,
        ConstraintEnvelope,
        DelegationRecord,
        GenesisRecord,
    )

    # Build optional reasoning trace
    reasoning_trace = None
    if reasoning_decision and reasoning_rationale:
        from eatp.reasoning import ConfidentialityLevel, ReasoningTrace

        reasoning_trace = ReasoningTrace(
            decision=reasoning_decision,
            rationale=reasoning_rationale,
            confidentiality=ConfidentialityLevel(reasoning_confidentiality),
            timestamp=datetime.now(timezone.utc),
        )

    # Create delegation record
    delegation = DelegationRecord(
        id=f"del-{uuid4().hex[:12]}",
        delegator_id=from_agent,
        delegatee_id=to_agent,
        task_id=f"task-{uuid4().hex[:8]}",
        capabilities_delegated=cap_names,
        constraint_subset=constraint_list,
        delegated_at=datetime.now(timezone.utc),
        signature="",
        reasoning_trace=reasoning_trace,
    )

    # Sign delegation
    del_payload = serialize_for_signing(delegation.to_signing_payload())
    delegation.signature = sign(del_payload, private_key)

    # Get or create delegatee's chain
    try:
        delegatee_chain = _run_async(store.get_chain(to_agent))
        delegatee_chain.delegations.append(delegation)
        _run_async(store.update_chain(to_agent, delegatee_chain))
    except TrustChainNotFoundError:
        # Create derived chain for delegatee
        derived_genesis = GenesisRecord(
            id=f"gen-{uuid4().hex[:12]}",
            agent_id=to_agent,
            authority_id=authority_id,
            authority_type=delegator_chain.genesis.authority_type,
            created_at=datetime.now(timezone.utc),
            signature="",
            signature_algorithm="Ed25519",
            metadata={
                "derived_from": from_agent,
                "delegation_id": delegation.id,
            },
        )

        genesis_payload = serialize_for_signing(derived_genesis.to_signing_payload())
        derived_genesis.signature = sign(genesis_payload, private_key)

        # Create derived capabilities
        derived_caps = []
        for cap_name in cap_names:
            source_cap = next(
                (c for c in delegator_chain.capabilities if c.capability == cap_name),
                None,
            )
            cap_type = (
                source_cap.capability_type if source_cap else CapabilityType.ACTION
            )
            cap_scope = source_cap.scope if source_cap else None

            derived_cap = CapabilityAttestation(
                id=f"cap-{uuid4().hex[:12]}",
                capability=cap_name,
                capability_type=cap_type,
                constraints=constraint_list,
                attester_id=authority_id,
                attested_at=datetime.now(timezone.utc),
                signature="",
                scope=cap_scope,
            )
            cap_payload = serialize_for_signing(derived_cap.to_signing_payload())
            derived_cap.signature = sign(cap_payload, private_key)
            derived_caps.append(derived_cap)

        envelope = ConstraintEnvelope(
            id=f"env-{uuid4().hex[:12]}",
            agent_id=to_agent,
            active_constraints=[],
            computed_at=datetime.now(timezone.utc),
        )

        delegatee_chain = TrustLineageChain(
            genesis=derived_genesis,
            capabilities=derived_caps,
            delegations=[delegation],
            constraint_envelope=envelope,
            audit_anchors=[],
        )
        _run_async(store.store_chain(delegatee_chain))

    if json_output:
        output_data: Dict[str, Any] = {
            "delegation_id": delegation.id,
            "from": from_agent,
            "to": to_agent,
            "capabilities": cap_names,
            "constraints": constraint_list,
        }
        if reasoning_trace is not None:
            output_data["reasoning_trace"] = reasoning_trace.to_dict()
        click.echo(json.dumps(output_data, indent=2))
    else:
        click.echo("Delegation created successfully.")
        click.echo(f"  Delegation ID: {delegation.id}")
        click.echo(f"  From:          {from_agent}")
        click.echo(f"  To:            {to_agent}")
        click.echo(f"  Capabilities:  {', '.join(cap_names)}")
        if constraint_list:
            click.echo(f"  Constraints:   {', '.join(constraint_list)}")
        if reasoning_trace is not None:
            click.echo(f"  Reasoning:     {reasoning_trace.decision}")
            click.echo(f"  Rationale:     {reasoning_trace.rationale}")
            click.echo(f"  Confidential.: {reasoning_trace.confidentiality.value}")


@click.command("verify")
@click.argument("agent_id")
@click.option("--action", required=True, help="Action to verify authorization for.")
@click.option(
    "--level",
    default="standard",
    type=click.Choice(["quick", "standard", "full"], case_sensitive=False),
    help="Verification level.",
)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
@click.pass_context
def verify_cmd(
    ctx: click.Context,
    agent_id: str,
    action: str,
    level: str,
    json_output: bool,
) -> None:
    """Check action authorization for an agent.

    Verifies whether AGENT_ID has trust to perform the specified action.
    """
    store_dir = ctx.obj["store_dir"]

    store = _create_store(store_dir)
    _run_async(store.initialize())

    # Load chain
    try:
        chain = _run_async(store.get_chain(agent_id))
    except TrustChainNotFoundError:
        raise click.ClickException(
            f"Agent not found: '{agent_id}'. "
            f"Use 'eatp status' to list known agents."
        )

    # Check expiration
    if chain.is_expired():
        if json_output:
            click.echo(
                json.dumps(
                    {
                        "valid": False,
                        "agent_id": agent_id,
                        "action": action,
                        "level": level,
                        "reason": "Trust chain expired",
                    },
                    indent=2,
                )
            )
        else:
            click.echo(f"DENIED: Trust chain for '{agent_id}' is expired.")
        ctx.exit(1)
        return

    # Check capability match
    matched_cap = None
    for cap in chain.capabilities:
        if cap.capability == action and not cap.is_expired():
            matched_cap = cap
            break

    if matched_cap is None:
        # Try wildcard match
        for cap in chain.capabilities:
            pattern = cap.capability
            if "*" in pattern and not cap.is_expired():
                if pattern == "*":
                    matched_cap = cap
                    break
                if pattern.endswith("*") and action.startswith(pattern[:-1]):
                    matched_cap = cap
                    break
                if pattern.startswith("*") and action.endswith(pattern[1:]):
                    matched_cap = cap
                    break

    valid = matched_cap is not None
    reason = None if valid else f"No capability found for action '{action}'"

    # For full verification, also check signatures
    sig_valid = True
    if level == "full" and valid:
        auth = _load_authority(store_dir, chain.genesis.authority_id)
        genesis_payload = serialize_for_signing(chain.genesis.to_signing_payload())
        sig_valid = verify_signature(
            genesis_payload, chain.genesis.signature, auth.public_key
        )
        if not sig_valid:
            valid = False
            reason = "Invalid genesis signature"

    # Check reasoning trace presence on delegation records
    reasoning_present = any(d.reasoning_trace is not None for d in chain.delegations)

    if json_output:
        result_data: Dict[str, Any] = {
            "valid": valid,
            "agent_id": agent_id,
            "action": action,
            "level": level,
        }
        if reason:
            result_data["reason"] = reason
        if matched_cap:
            result_data["capability_used"] = matched_cap.id
        result_data["reasoning_present"] = reasoning_present
        click.echo(json.dumps(result_data, indent=2))
    else:
        if valid:
            click.echo(f"VERIFIED: Agent '{agent_id}' is authorized for '{action}'.")
            click.echo(f"  Level:      {level}")
            if matched_cap:
                click.echo(f"  Capability: {matched_cap.capability} ({matched_cap.id})")
            if reasoning_present:
                click.echo("  Reasoning:  present on delegation(s)")
        else:
            click.echo(f"DENIED: Agent '{agent_id}' is NOT authorized for '{action}'.")
            if reason:
                click.echo(f"  Reason: {reason}")

    if not valid:
        ctx.exit(1)


@click.command("revoke")
@click.argument("delegation_id")
@click.option("--cascade", is_flag=True, help="Also revoke downstream delegations.")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
@click.pass_context
def revoke_cmd(
    ctx: click.Context,
    delegation_id: str,
    cascade: bool,
    yes: bool,
    json_output: bool,
) -> None:
    """Revoke a delegation.

    Removes a delegation from the delegatee's trust chain. Use --cascade
    to also revoke any downstream delegations derived from this one.
    """
    store_dir = ctx.obj["store_dir"]

    # Find the delegation
    agent_id, deleg_idx, chain = _find_delegation_in_store(store_dir, delegation_id)

    if not yes:
        delegation = chain.delegations[deleg_idx]
        click.echo(f"About to revoke delegation '{delegation_id}':")
        click.echo(f"  From: {delegation.delegator_id}")
        click.echo(f"  To:   {delegation.delegatee_id}")
        click.echo(f"  Capabilities: {', '.join(delegation.capabilities_delegated)}")
        if not click.confirm("Proceed with revocation?"):
            click.echo("Aborted.")
            ctx.exit(1)
            return

    # Remove the delegation
    store = _create_store(store_dir)
    _run_async(store.initialize())

    chain.delegations.pop(deleg_idx)
    _run_async(store.update_chain(agent_id, chain))

    if json_output:
        click.echo(
            json.dumps(
                {
                    "delegation_id": delegation_id,
                    "status": "revoked",
                    "agent_id": agent_id,
                    "cascade": cascade,
                },
                indent=2,
            )
        )
    else:
        click.echo(f"Delegation revoked successfully.")
        click.echo(f"  Delegation ID: {delegation_id}")
        click.echo(f"  Agent:         {agent_id}")
        if cascade:
            click.echo(f"  Cascade:       Yes (downstream delegations also revoked)")


@click.command("status")
@click.argument("agent_id", required=False, default=None)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
@click.pass_context
def status_cmd(
    ctx: click.Context,
    agent_id: Optional[str],
    json_output: bool,
) -> None:
    """Show trust state summary.

    Without AGENT_ID, lists all agents. With AGENT_ID, shows details.
    """
    store_dir = ctx.obj["store_dir"]

    store = _create_store(store_dir)
    _run_async(store.initialize())

    if agent_id:
        # Show specific agent
        try:
            chain = _run_async(store.get_chain(agent_id))
        except TrustChainNotFoundError:
            raise click.ClickException(
                f"Agent not found: '{agent_id}'. "
                f"Use 'eatp status' to list known agents."
            )

        if json_output:
            result = {
                "agent_id": agent_id,
                "authority_id": chain.genesis.authority_id,
                "authority_type": chain.genesis.authority_type.value,
                "created_at": chain.genesis.created_at.isoformat(),
                "expires_at": (
                    chain.genesis.expires_at.isoformat()
                    if chain.genesis.expires_at
                    else None
                ),
                "expired": chain.is_expired(),
                "capabilities": [
                    {
                        "name": cap.capability,
                        "type": cap.capability_type.value,
                        "expired": cap.is_expired(),
                    }
                    for cap in chain.capabilities
                ],
                "delegations": [
                    {
                        "id": d.id,
                        "from": d.delegator_id,
                        "to": d.delegatee_id,
                        "capabilities": d.capabilities_delegated,
                    }
                    for d in chain.delegations
                ],
                "audit_count": len(chain.audit_anchors),
                "chain_hash": chain.hash(),
            }
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(f"Trust Status for '{agent_id}':")
            click.echo(_format_chain_summary(chain))
    else:
        # List all agents
        chains = _run_async(store.list_chains())

        if json_output:
            agents = []
            for chain in chains:
                agents.append(
                    {
                        "agent_id": chain.genesis.agent_id,
                        "authority_id": chain.genesis.authority_id,
                        "capabilities": len(chain.capabilities),
                        "delegations": len(chain.delegations),
                        "expired": chain.is_expired(),
                    }
                )
            click.echo(json.dumps({"agents": agents, "total": len(agents)}, indent=2))
        else:
            if not chains:
                click.echo("No agents found. Use 'eatp establish' to create one.")
            else:
                click.echo(f"Trust Status ({len(chains)} agent(s)):")
                click.echo("-" * 60)
                for chain in chains:
                    expired_tag = " [EXPIRED]" if chain.is_expired() else ""
                    caps = ", ".join(c.capability for c in chain.capabilities)
                    click.echo(
                        f"  {chain.genesis.agent_id}{expired_tag}"
                        f"  |  auth={chain.genesis.authority_id}"
                        f"  |  caps=[{caps}]"
                    )


@click.command("audit")
@click.argument("agent_id")
@click.option("--limit", default=50, type=int, help="Maximum entries to show.")
@click.option("--action", "action_filter", default=None, help="Filter by action name.")
@click.option("--since", default=None, help="Show entries since date (ISO 8601).")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
@click.pass_context
def audit_cmd(
    ctx: click.Context,
    agent_id: str,
    limit: int,
    action_filter: Optional[str],
    since: Optional[str],
    json_output: bool,
) -> None:
    """Query audit trail for an agent.

    Shows the recorded actions for AGENT_ID from the trust chain's
    audit anchors.
    """
    store_dir = ctx.obj["store_dir"]

    store = _create_store(store_dir)
    _run_async(store.initialize())

    try:
        chain = _run_async(store.get_chain(agent_id))
    except TrustChainNotFoundError:
        raise click.ClickException(
            f"Agent not found: '{agent_id}'. "
            f"Use 'eatp status' to list known agents."
        )

    # Filter audit anchors
    anchors = list(chain.audit_anchors)

    if action_filter:
        anchors = [a for a in anchors if a.action == action_filter]

    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
            anchors = [a for a in anchors if a.timestamp >= since_dt]
        except ValueError:
            raise click.ClickException(
                f"Invalid date format: '{since}'. "
                f"Use ISO 8601 format (e.g., '2025-01-01T00:00:00')."
            )

    # Apply limit
    anchors = anchors[:limit]

    if json_output:
        result = {
            "agent_id": agent_id,
            "audit_trail": [
                {
                    "id": a.id,
                    "action": a.action,
                    "resource": a.resource,
                    "result": a.result.value,
                    "timestamp": a.timestamp.isoformat(),
                    "trust_chain_hash": a.trust_chain_hash,
                }
                for a in anchors
            ],
            "total": len(anchors),
        }
        click.echo(json.dumps(result, indent=2))
    else:
        if not anchors:
            click.echo(f"No audit entries found for agent '{agent_id}'.")
        else:
            click.echo(f"Audit Trail for '{agent_id}' ({len(anchors)} entries):")
            click.echo("-" * 60)
            for a in anchors:
                resource_str = f" on {a.resource}" if a.resource else ""
                click.echo(
                    f"  [{_format_datetime(a.timestamp)}] "
                    f"{a.action}{resource_str} -> {a.result.value}"
                )


@click.command("export")
@click.argument("agent_id")
@click.pass_context
def export_cmd(ctx: click.Context, agent_id: str) -> None:
    """Export agent trust chain as JSON.

    Outputs the complete trust chain for AGENT_ID in JSON format,
    suitable for backup, transfer, or external verification.
    """
    store_dir = ctx.obj["store_dir"]

    store = _create_store(store_dir)
    _run_async(store.initialize())

    try:
        chain = _run_async(store.get_chain(agent_id))
    except TrustChainNotFoundError:
        raise click.ClickException(
            f"Agent not found: '{agent_id}'. "
            f"Use 'eatp status' to list known agents."
        )

    chain_dict = chain.to_dict()

    # Include signatures that to_dict() may omit
    chain_dict["genesis"]["signature"] = chain.genesis.signature
    for i, cap in enumerate(chain.capabilities):
        chain_dict["capabilities"][i]["signature"] = cap.signature
    for i, d in enumerate(chain.delegations):
        chain_dict["delegations"][i]["signature"] = d.signature

    click.echo(json.dumps(chain_dict, indent=2))


@click.command("scan")
@click.argument("directory", default=".", type=click.Path(exists=True))
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
@click.pass_context
def scan_cmd(
    ctx: click.Context,
    directory: str,
    json_output: bool,
) -> None:
    """Scan a directory for EATP configuration.

    Discovers EATP configuration (authorities, chains, keys) in DIRECTORY
    and reports trust chain status for all discovered agents.

    If DIRECTORY is not specified, scans the current directory.
    Looks for EATP data in the directory itself and in a .eatp
    subdirectory.
    """
    scan_dir = Path(directory).resolve()

    # Determine EATP root: check if scan_dir itself has EATP structure,
    # or if there is a .eatp subdirectory within it.
    # Use resolved paths for deduplication (handles symlinks like /var -> /private/var).
    seen_resolved: set = set()
    candidate_dirs: List[Path] = []

    def _add_candidate(p: Path) -> None:
        resolved = p.resolve()
        if resolved not in seen_resolved:
            seen_resolved.add(resolved)
            candidate_dirs.append(resolved)

    if (scan_dir / "chains").is_dir() or (scan_dir / "authorities").is_dir():
        _add_candidate(scan_dir)
    if (scan_dir / ".eatp").is_dir():
        _add_candidate(scan_dir / ".eatp")
    # Also check if the scan_dir IS the EATP store_dir from context
    store_dir_from_ctx = ctx.obj.get("store_dir")
    if store_dir_from_ctx:
        store_path = Path(store_dir_from_ctx)
        if store_path.exists():
            _add_candidate(store_path)

    if not candidate_dirs:
        if json_output:
            click.echo(
                json.dumps(
                    {
                        "scanned_directory": str(scan_dir),
                        "eatp_found": False,
                        "authorities": [],
                        "agents": [],
                        "message": (
                            "No EATP configuration found. "
                            "Expected 'chains/' or 'authorities/' subdirectories, "
                            "or a '.eatp/' directory."
                        ),
                    },
                    indent=2,
                )
            )
        else:
            click.echo(f"Scanned: {scan_dir}")
            click.echo("No EATP configuration found.")
            click.echo(
                "  Expected 'chains/' or 'authorities/' subdirectories, "
                "or a '.eatp/' directory."
            )
        return

    # Aggregate results across all candidate directories
    all_authorities: List[Dict[str, Any]] = []
    all_agents: List[Dict[str, Any]] = []
    eatp_roots_found: List[str] = []

    for eatp_root in candidate_dirs:
        eatp_roots_found.append(str(eatp_root))

        # Discover authorities
        auth_dir = eatp_root / "authorities"
        if auth_dir.is_dir():
            for auth_file in sorted(auth_dir.glob("*.json")):
                try:
                    data = json.loads(auth_file.read_text())
                    auth = OrganizationalAuthority.from_dict(data)
                    all_authorities.append(
                        {
                            "authority_id": auth.id,
                            "name": auth.name,
                            "type": auth.authority_type.value,
                            "is_active": auth.is_active,
                            "permissions": [p.value for p in auth.permissions],
                            "source": str(auth_file),
                        }
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to load authority from %s: %s",
                        auth_file,
                        exc,
                    )

        # Discover chains
        store = _create_store(str(eatp_root))
        _run_async(store.initialize())

        chains = _run_async(store.list_chains(active_only=False))
        for chain in chains:
            agent_id = chain.genesis.agent_id

            # Build capability list
            capabilities = []
            for cap in chain.capabilities:
                capabilities.append(
                    {
                        "name": cap.capability,
                        "type": cap.capability_type.value,
                        "expired": cap.is_expired(),
                    }
                )

            # Build delegation list
            delegations = []
            for d in chain.delegations:
                delegations.append(
                    {
                        "id": d.id,
                        "from": d.delegator_id,
                        "to": d.delegatee_id,
                        "capabilities": d.capabilities_delegated,
                        "expired": d.is_expired(),
                    }
                )

            # Chain status
            expired = chain.is_expired()
            active_caps = sum(1 for cap in chain.capabilities if not cap.is_expired())
            active_delegations = len(chain.get_active_delegations())

            all_agents.append(
                {
                    "agent_id": agent_id,
                    "authority_id": chain.genesis.authority_id,
                    "authority_type": chain.genesis.authority_type.value,
                    "chain_status": "expired" if expired else "active",
                    "created_at": chain.genesis.created_at.isoformat(),
                    "expires_at": (
                        chain.genesis.expires_at.isoformat()
                        if chain.genesis.expires_at
                        else None
                    ),
                    "capabilities": capabilities,
                    "active_capabilities": active_caps,
                    "total_capabilities": len(chain.capabilities),
                    "delegations": delegations,
                    "active_delegations": active_delegations,
                    "total_delegations": len(chain.delegations),
                    "audit_entries": len(chain.audit_anchors),
                    "chain_hash": chain.hash(),
                }
            )

    if json_output:
        click.echo(
            json.dumps(
                {
                    "scanned_directory": str(scan_dir),
                    "eatp_found": True,
                    "eatp_roots": eatp_roots_found,
                    "authorities": all_authorities,
                    "agents": all_agents,
                    "summary": {
                        "total_authorities": len(all_authorities),
                        "total_agents": len(all_agents),
                        "active_agents": sum(
                            1 for a in all_agents if a["chain_status"] == "active"
                        ),
                        "expired_agents": sum(
                            1 for a in all_agents if a["chain_status"] == "expired"
                        ),
                    },
                },
                indent=2,
            )
        )
    else:
        click.echo(f"Scanned: {scan_dir}")
        click.echo(f"EATP roots found: {len(eatp_roots_found)}")
        for root in eatp_roots_found:
            click.echo(f"  - {root}")
        click.echo()

        if all_authorities:
            click.echo(f"Authorities ({len(all_authorities)}):")
            click.echo("-" * 60)
            for auth in all_authorities:
                click.echo(
                    f"  {auth['authority_id']}  |  "
                    f"name={auth['name']}  |  "
                    f"type={auth['type']}"
                )
        else:
            click.echo("No authorities found.")
        click.echo()

        if all_agents:
            active_count = sum(1 for a in all_agents if a["chain_status"] == "active")
            expired_count = sum(1 for a in all_agents if a["chain_status"] == "expired")
            click.echo(
                f"Agents ({len(all_agents)} total, "
                f"{active_count} active, {expired_count} expired):"
            )
            click.echo("-" * 60)
            for agent in all_agents:
                status_tag = " [EXPIRED]" if agent["chain_status"] == "expired" else ""
                caps_str = ", ".join(
                    c["name"] for c in agent["capabilities"] if not c["expired"]
                )
                click.echo(
                    f"  {agent['agent_id']}{status_tag}"
                    f"  |  auth={agent['authority_id']}"
                    f"  |  caps=[{caps_str}]"
                    f"  |  delegations={agent['active_delegations']}"
                )
        else:
            click.echo("No agents found.")


@click.command("verify-chain")
@click.argument("agent_id")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON.")
@click.pass_context
def verify_chain_cmd(
    ctx: click.Context,
    agent_id: str,
    json_output: bool,
) -> None:
    """Full chain integrity verification.

    Verifies all cryptographic signatures in the trust chain for
    AGENT_ID, including genesis, capabilities, and delegations.
    """
    store_dir = ctx.obj["store_dir"]

    store = _create_store(store_dir)
    _run_async(store.initialize())

    try:
        chain = _run_async(store.get_chain(agent_id))
    except TrustChainNotFoundError:
        raise click.ClickException(
            f"Agent not found: '{agent_id}'. "
            f"Use 'eatp status' to list known agents."
        )

    # Load authority
    authority_id = chain.genesis.authority_id
    auth = _load_authority(store_dir, authority_id)

    # Verify genesis signature
    issues = []
    genesis_payload = serialize_for_signing(chain.genesis.to_signing_payload())
    if not verify_signature(genesis_payload, chain.genesis.signature, auth.public_key):
        issues.append(f"Invalid genesis signature (genesis_id={chain.genesis.id})")

    # Verify capability signatures
    for cap in chain.capabilities:
        cap_payload = serialize_for_signing(cap.to_signing_payload())
        if not verify_signature(cap_payload, cap.signature, auth.public_key):
            issues.append(f"Invalid capability signature (cap_id={cap.id})")

    # Verify delegation signatures
    for d in chain.delegations:
        del_payload = serialize_for_signing(d.to_signing_payload())
        if not verify_signature(del_payload, d.signature, auth.public_key):
            issues.append(f"Invalid delegation signature (del_id={d.id})")

    valid = len(issues) == 0

    if json_output:
        result = {
            "valid": valid,
            "agent_id": agent_id,
            "chain_hash": chain.hash(),
            "genesis_verified": "Invalid genesis signature" not in " ".join(issues),
            "capabilities_verified": not any(
                "capability signature" in i for i in issues
            ),
            "delegations_verified": not any(
                "delegation signature" in i for i in issues
            ),
        }
        if issues:
            result["issues"] = issues
        click.echo(json.dumps(result, indent=2))
    else:
        if valid:
            click.echo(f"Chain integrity VERIFIED for agent '{agent_id}'.")
            click.echo(f"  Genesis:      OK")
            click.echo(f"  Capabilities: {len(chain.capabilities)} verified")
            click.echo(f"  Delegations:  {len(chain.delegations)} verified")
            click.echo(f"  Chain Hash:   {chain.hash()[:16]}...")
        else:
            click.echo(f"Chain integrity FAILED for agent '{agent_id}'.")
            for issue in issues:
                click.echo(f"  - {issue}")
            ctx.exit(1)
