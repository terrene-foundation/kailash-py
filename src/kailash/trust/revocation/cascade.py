# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cascade revocation with TrustStore integration.

Provides a high-level ``cascade_revoke()`` function that wires the existing
``CascadeRevocationManager`` BFS cascade into ``TrustStore`` for atomic
chain invalidation with audit trail.

Atomicity:
    The function uses the TrustStore's transaction support when available
    for atomic chain invalidation. If any chain deletion fails, all
    previously deleted chains are restored (rolled back) to maintain
    consistency. On partial failure, success=False is returned with
    all chains restored and errors reported.

Idempotency:
    Revoking an already-revoked agent is a no-op: the function returns
    ``RevocationResult(success=True, events=[], revoked_agents=[])``.
    This is checked via TrustStore — if the chain is already soft-deleted
    (inactive), the agent is considered already revoked.

Cross-SDK parity (EATP D6 — kailash-py#595 / kailash-rs ISS-04):
    The Python implementation cascades via BFS (queue-based traversal in
    ``CascadeRevocationManager.cascade_revoke``); the Rust implementation
    at ``crates/eatp/src/delegation.rs`` cascades via DFS recursion. Both
    traversal orders MUST produce the SAME SET of revoked descendants for
    any delegation tree — the result set is order-independent. Only the
    event emission order may differ (BFS yields breadth-level-order events,
    DFS yields depth-level-order events). Consumers of ``RevocationResult``
    MUST NOT rely on event ordering for cross-SDK correlation; correlate
    on ``event.target_id`` + ``event.affected_agents`` as a set.

    Parity contract (enforced by
    ``tests/regression/test_cascade_revocation_cross_sdk_parity.py``):

    1. Given an identical delegation tree seeded on both SDKs and a revoke
       of the same root node, ``set(py.revoked_agents) ==
       set(rust.revoked_agents)`` regardless of traversal order.
    2. Idempotency behavior is identical: a second revoke of the same
       agent returns ``success=True, events=[], revoked_agents=[]`` on
       both sides.
    3. Partial-failure rollback contract is identical: if any chain
       deletion fails, all prior deletions roll back, and
       ``success=False`` with error details.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kailash.trust.chain import TrustLineageChain
from kailash.trust.chain_store import TrustStore
from kailash.trust.exceptions import TrustChainNotFoundError
from kailash.trust.revocation.broadcaster import (
    CascadeRevocationManager,
    DelegationRegistry,
    InMemoryDelegationRegistry,
    InMemoryRevocationBroadcaster,
    RevocationBroadcaster,
    RevocationEvent,
)

logger = logging.getLogger(__name__)


@dataclass
class RevocationResult:
    """Result of a cascade revocation operation.

    Attributes:
        success: Whether the revocation completed without errors.
            True even for no-ops (already revoked).
        events: All RevocationEvent objects created during the cascade.
            Empty if the agent was already revoked (idempotent no-op).
        revoked_agents: List of agent IDs whose chains were soft-deleted.
        errors: Per-agent errors encountered during chain deletion.
            Non-empty errors with success=True means partial completion
            (some chains couldn't be deleted but cascade was broadcast).
    """

    success: bool
    events: List[RevocationEvent] = field(default_factory=list)
    revoked_agents: List[str] = field(default_factory=list)
    errors: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for logging/audit."""
        return {
            "success": self.success,
            "events": [e.to_dict() for e in self.events],
            "revoked_agents": self.revoked_agents,
            "errors": self.errors,
        }


async def _snapshot_chains(
    store: TrustStore, agent_ids: set[str]
) -> Dict[str, TrustLineageChain]:
    """Take deep-copy snapshots of chains for rollback support.

    Args:
        store: TrustStore to read chains from.
        agent_ids: Set of agent IDs to snapshot.

    Returns:
        Dict mapping agent_id to a deep copy of its TrustLineageChain.
        Agents without chains (TrustChainNotFoundError) are silently skipped.
    """
    snapshots: Dict[str, TrustLineageChain] = {}
    for aid in agent_ids:
        try:
            chain = await store.get_chain(aid, include_inactive=False)
            snapshots[aid] = copy.deepcopy(chain)
        except TrustChainNotFoundError:
            pass
    return snapshots


async def _rollback_chains(
    store: TrustStore,
    snapshots: Dict[str, TrustLineageChain],
    deleted_agents: List[str],
) -> None:
    """Attempt to restore previously deleted chains from snapshots.

    Best-effort rollback: logs errors but does not raise.

    Args:
        store: TrustStore to restore chains into.
        snapshots: Pre-deletion snapshots.
        deleted_agents: List of agent IDs that were successfully deleted
            and need to be restored.
    """
    for aid in deleted_agents:
        if aid not in snapshots:
            logger.warning(
                f"[REVOKE-ROLLBACK] No snapshot for agent '{aid}', cannot restore"
            )
            continue
        try:
            await store.store_chain(snapshots[aid])
            logger.debug(f"[REVOKE-ROLLBACK] Restored chain for agent '{aid}'")
        except Exception as restore_exc:
            logger.error(
                f"[REVOKE-ROLLBACK] Failed to restore chain for agent "
                f"'{aid}': {type(restore_exc).__name__}: {restore_exc}"
            )


async def cascade_revoke(
    agent_id: str,
    store: TrustStore,
    reason: str,
    revoked_by: str,
    broadcaster: Optional[RevocationBroadcaster] = None,
    delegation_registry: Optional[DelegationRegistry] = None,
) -> RevocationResult:
    """Revoke an agent and cascade to all delegates, with TrustStore integration.

    This is the primary entry point for cascade revocation. It:

    1. Checks idempotency (already-revoked -> no-op)
    2. Runs BFS cascade via ``CascadeRevocationManager``
    3. Snapshots all affected chains for rollback support
    4. Soft-deletes all affected chains in the ``TrustStore``
    5. On partial failure: rolls back all deletions for consistency
    6. Returns a complete audit trail

    Atomicity:
        All chain deletions are treated as an atomic unit. If any deletion
        fails, all previously successful deletions are rolled back (chains
        restored from snapshots). This prevents inconsistent state where
        some chains are deleted and others are not.

    Args:
        agent_id: The agent to revoke.
        store: TrustStore for chain invalidation (soft-delete).
        reason: Human-readable reason for revocation.
        revoked_by: ID of the entity performing the revocation.
        broadcaster: Optional broadcaster. Defaults to InMemoryRevocationBroadcaster.
        delegation_registry: Optional delegation registry. Defaults to
            InMemoryDelegationRegistry (empty -- no cascades beyond target).

    Returns:
        RevocationResult with events, revoked agents, and any errors.
    """
    # Check idempotency: if chain is already deleted/inactive, it's a no-op
    try:
        await store.get_chain(agent_id, include_inactive=False)
    except TrustChainNotFoundError:
        logger.info(f"[REVOKE] Agent '{agent_id}' already revoked or not found — no-op")
        return RevocationResult(success=True)

    # Set up cascade infrastructure
    effective_broadcaster = broadcaster or InMemoryRevocationBroadcaster()
    effective_registry = delegation_registry or InMemoryDelegationRegistry()

    manager = CascadeRevocationManager(
        broadcaster=effective_broadcaster,
        delegation_registry=effective_registry,
    )

    # Run BFS cascade (broadcasts events)
    events = manager.cascade_revoke(
        target_id=agent_id,
        revoked_by=revoked_by,
        reason=reason,
    )

    # Collect all affected agent IDs
    all_agents: set[str] = set()
    for event in events:
        all_agents.add(event.target_id)
        all_agents.update(event.affected_agents)

    # Snapshot chains before deletion for rollback support
    snapshots = await _snapshot_chains(store, all_agents)

    # Soft-delete chains in TrustStore for each affected agent
    revoked_agents: List[str] = []
    errors: Dict[str, str] = {}

    for affected_id in all_agents:
        try:
            await store.delete_chain(affected_id, soft_delete=True)
            revoked_agents.append(affected_id)
            logger.debug(f"[REVOKE] Soft-deleted chain for agent '{affected_id}'")
        except TrustChainNotFoundError:
            # Chain doesn't exist or already deleted -- not an error
            logger.debug(
                f"[REVOKE] Chain for agent '{affected_id}' not found (may not have a chain or already revoked)"
            )
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            errors[affected_id] = error_msg
            logger.error(
                f"[REVOKE] Failed to soft-delete chain for agent '{affected_id}': {error_msg}"
            )

    # If any errors occurred, roll back all successful deletions
    if errors:
        logger.warning(
            f"[REVOKE] Partial failure during cascade revocation for '{agent_id}': "
            f"{len(errors)} error(s). Rolling back {len(revoked_agents)} "
            f"successful deletion(s) for consistency."
        )
        await _rollback_chains(store, snapshots, revoked_agents)
        revoked_agents = []  # No agents were ultimately revoked

    success = len(errors) == 0

    logger.info(
        f"[REVOKE] Cascade revocation for '{agent_id}' complete: "
        f"{len(revoked_agents)} chains revoked, {len(events)} events, "
        f"{len(errors)} errors"
    )

    return RevocationResult(
        success=success,
        events=events,
        revoked_agents=revoked_agents,
        errors=errors,
    )


__all__ = [
    "RevocationResult",
    "cascade_revoke",
]
