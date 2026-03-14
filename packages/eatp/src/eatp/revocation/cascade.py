# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cascade revocation with TrustStore integration.

Provides a high-level ``cascade_revoke()`` function that wires the existing
``CascadeRevocationManager`` BFS cascade into ``TrustStore`` for atomic
chain invalidation with audit trail.

Atomicity:
    The function collects all revocation events first, then soft-deletes
    affected chains in the TrustStore. If a chain deletion fails (e.g.,
    chain not found), the error is recorded but does not abort the cascade
    — partial revocation is safer than no revocation. All events are
    broadcast regardless.

Idempotency:
    Revoking an already-revoked agent is a no-op: the function returns
    ``RevocationResult(success=True, events=[], revoked_agents=[])``.
    This is checked via TrustStore — if the chain is already soft-deleted
    (inactive), the agent is considered already revoked.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from eatp.exceptions import TrustChainNotFoundError
from eatp.revocation.broadcaster import (
    CascadeRevocationManager,
    DelegationRegistry,
    InMemoryDelegationRegistry,
    InMemoryRevocationBroadcaster,
    RevocationBroadcaster,
    RevocationEvent,
)
from eatp.store import TrustStore

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

    1. Checks idempotency (already-revoked → no-op)
    2. Runs BFS cascade via ``CascadeRevocationManager``
    3. Soft-deletes all affected chains in the ``TrustStore``
    4. Returns a complete audit trail

    Args:
        agent_id: The agent to revoke.
        store: TrustStore for chain invalidation (soft-delete).
        reason: Human-readable reason for revocation.
        revoked_by: ID of the entity performing the revocation.
        broadcaster: Optional broadcaster. Defaults to InMemoryRevocationBroadcaster.
        delegation_registry: Optional delegation registry. Defaults to
            InMemoryDelegationRegistry (empty — no cascades beyond target).

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
    all_agents = set()
    for event in events:
        all_agents.add(event.target_id)
        all_agents.update(event.affected_agents)

    # Soft-delete chains in TrustStore for each affected agent
    revoked_agents: List[str] = []
    errors: Dict[str, str] = {}

    for affected_id in all_agents:
        try:
            await store.delete_chain(affected_id, soft_delete=True)
            revoked_agents.append(affected_id)
            logger.debug(f"[REVOKE] Soft-deleted chain for agent '{affected_id}'")
        except TrustChainNotFoundError:
            # Chain doesn't exist or already deleted — not an error
            logger.debug(
                f"[REVOKE] Chain for agent '{affected_id}' not found "
                f"(may not have a chain or already revoked)"
            )
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            errors[affected_id] = error_msg
            logger.error(
                f"[REVOKE] Failed to soft-delete chain for agent "
                f"'{affected_id}': {error_msg}"
            )

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
