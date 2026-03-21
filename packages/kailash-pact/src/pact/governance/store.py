# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Governance store protocols and in-memory implementations.

Defines four Protocol classes for governance state persistence:
- OrgStore: compiled organization structures
- EnvelopeStore: role and task envelopes
- ClearanceStore: knowledge clearance assignments
- AccessPolicyStore: KSPs and Cross-Functional Bridges

Each protocol has a corresponding MemoryXxxStore implementation using
OrderedDict with bounded size (MAX_STORE_SIZE) per trust-plane security
rules -- evicts oldest entries when capacity is exceeded.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from typing import Protocol, runtime_checkable

from pact.governance.access import KnowledgeSharePolicy, PactBridge
from pact.governance.clearance import RoleClearance
from pact.governance.compilation import CompiledOrg, OrgNode
from pact.governance.envelopes import RoleEnvelope, TaskEnvelope

logger = logging.getLogger(__name__)

__all__ = [
    "MAX_STORE_SIZE",
    "AccessPolicyStore",
    "ClearanceStore",
    "EnvelopeStore",
    "MemoryAccessPolicyStore",
    "MemoryClearanceStore",
    "MemoryEnvelopeStore",
    "MemoryOrgStore",
    "OrgStore",
]

MAX_STORE_SIZE = 10_000  # Bounded collections per trust-plane security rules


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class OrgStore(Protocol):
    """Protocol for compiled organization persistence."""

    def save_org(self, org: CompiledOrg) -> None: ...
    def load_org(self, org_id: str) -> CompiledOrg | None: ...
    def get_node(self, org_id: str, address: str) -> OrgNode | None: ...
    def query_by_prefix(self, org_id: str, prefix: str) -> list[OrgNode]: ...


@runtime_checkable
class EnvelopeStore(Protocol):
    """Protocol for operating envelope persistence."""

    def save_role_envelope(self, envelope: RoleEnvelope) -> None: ...
    def get_role_envelope(self, target_role_address: str) -> RoleEnvelope | None: ...
    def save_task_envelope(self, envelope: TaskEnvelope) -> None: ...
    def get_active_task_envelope(self, role_address: str, task_id: str) -> TaskEnvelope | None: ...
    def get_ancestor_envelopes(self, role_address: str) -> dict[str, RoleEnvelope]: ...


@runtime_checkable
class ClearanceStore(Protocol):
    """Protocol for knowledge clearance persistence."""

    def grant_clearance(self, clearance: RoleClearance) -> None: ...
    def get_clearance(self, role_address: str) -> RoleClearance | None: ...
    def revoke_clearance(self, role_address: str) -> None: ...


@runtime_checkable
class AccessPolicyStore(Protocol):
    """Protocol for KSP and bridge persistence."""

    def save_ksp(self, ksp: KnowledgeSharePolicy) -> None: ...
    def find_ksp(self, source_prefix: str, target_prefix: str) -> KnowledgeSharePolicy | None: ...
    def list_ksps(self) -> list[KnowledgeSharePolicy]: ...
    def save_bridge(self, bridge: PactBridge) -> None: ...
    def find_bridge(self, role_a_address: str, role_b_address: str) -> PactBridge | None: ...
    def list_bridges(self) -> list[PactBridge]: ...


# ---------------------------------------------------------------------------
# Helper: bounded eviction
# ---------------------------------------------------------------------------


def _evict_oldest(store: OrderedDict, max_size: int) -> None:
    """Evict oldest entries until store is within max_size bounds.

    Args:
        store: The OrderedDict to trim.
        max_size: Maximum number of entries to retain.
    """
    while len(store) > max_size:
        evicted_key, _ = store.popitem(last=False)
        logger.debug("Evicted oldest entry: %s (store size exceeded %d)", evicted_key, max_size)


# ---------------------------------------------------------------------------
# In-memory implementations
# ---------------------------------------------------------------------------


class MemoryOrgStore:
    """In-memory OrgStore using OrderedDict with bounded size.

    Stores compiled organizations keyed by org_id. Evicts oldest entries
    when exceeding MAX_STORE_SIZE. All public methods are thread-safe via
    an internal ``threading.Lock``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._orgs: OrderedDict[str, CompiledOrg] = OrderedDict()

    def save_org(self, org: CompiledOrg) -> None:
        """Save a compiled organization, overwriting any existing entry."""
        with self._lock:
            # Move to end if updating existing key, or insert new
            if org.org_id in self._orgs:
                self._orgs.move_to_end(org.org_id)
            self._orgs[org.org_id] = org
            _evict_oldest(self._orgs, MAX_STORE_SIZE)
        logger.info("Saved org '%s' (%d nodes)", org.org_id, len(org.nodes))

    def load_org(self, org_id: str) -> CompiledOrg | None:
        """Load a compiled organization by ID, or None if not found."""
        with self._lock:
            org = self._orgs.get(org_id)
        if org is None:
            logger.debug("Org '%s' not found in store", org_id)
        return org

    def get_node(self, org_id: str, address: str) -> OrgNode | None:
        """Look up a single node by org_id and address."""
        with self._lock:
            org = self._orgs.get(org_id)
        if org is None:
            logger.debug("get_node: org '%s' not found in store", org_id)
            return None
        return org.nodes.get(address)

    def query_by_prefix(self, org_id: str, prefix: str) -> list[OrgNode]:
        """Return all nodes whose address starts with the given prefix."""
        with self._lock:
            org = self._orgs.get(org_id)
        if org is None:
            logger.debug("query_by_prefix: org '%s' not found in store", org_id)
            return []
        results = []
        for addr, node in org.nodes.items():
            if addr == prefix or addr.startswith(prefix + "-"):
                results.append(node)
        return results


class MemoryEnvelopeStore:
    """In-memory EnvelopeStore using OrderedDict with bounded size.

    Role envelopes are keyed by target_role_address.
    Task envelopes are keyed by (role_address, task_id) derived from
    the TaskEnvelope's parent_envelope_id relationship. All public methods
    are thread-safe via an internal ``threading.Lock``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._role_envelopes: OrderedDict[str, RoleEnvelope] = OrderedDict()
        self._task_envelopes: OrderedDict[str, TaskEnvelope] = OrderedDict()

    def save_role_envelope(self, envelope: RoleEnvelope) -> None:
        """Save a role envelope, keyed by target_role_address."""
        key = envelope.target_role_address
        with self._lock:
            if key in self._role_envelopes:
                self._role_envelopes.move_to_end(key)
            self._role_envelopes[key] = envelope
            _evict_oldest(self._role_envelopes, MAX_STORE_SIZE)
        logger.info(
            "Saved role envelope '%s' for target '%s'",
            envelope.id,
            key,
        )

    def get_role_envelope(self, target_role_address: str) -> RoleEnvelope | None:
        """Get a role envelope by target role address."""
        with self._lock:
            return self._role_envelopes.get(target_role_address)

    def save_task_envelope(self, envelope: TaskEnvelope) -> None:
        """Save a task envelope, keyed by task_id.

        Task IDs are unique identifiers for specific task assignments.
        The parent_envelope_id links back to the RoleEnvelope being
        narrowed, and can be used for cross-referencing.
        """
        key = envelope.task_id
        with self._lock:
            if key in self._task_envelopes:
                self._task_envelopes.move_to_end(key)
            self._task_envelopes[key] = envelope
            _evict_oldest(self._task_envelopes, MAX_STORE_SIZE)
        logger.info(
            "Saved task envelope '%s' for task '%s' (parent envelope '%s')",
            envelope.id,
            envelope.task_id,
            envelope.parent_envelope_id,
        )

    def get_active_task_envelope(self, role_address: str, task_id: str) -> TaskEnvelope | None:
        """Get an active (non-expired) task envelope by role address and task ID.

        Looks up by task_id. The role_address parameter is accepted for
        interface compatibility and future filtering; task IDs are unique
        per assignment.
        """
        with self._lock:
            te = self._task_envelopes.get(task_id)
        if te is None:
            return None
        if te.is_expired:
            logger.debug(
                "Task envelope '%s' for role '%s' task '%s' is expired",
                te.id,
                role_address,
                task_id,
            )
            return None
        return te

    def get_ancestor_envelopes(self, role_address: str) -> dict[str, RoleEnvelope]:
        """Return all RoleEnvelopes for addresses that are ancestors of the given address.

        An address A is considered an ancestor of B if B starts with A
        (exact match or A followed by '-'). This includes the address itself.

        Args:
            role_address: The D/T/R positional address to find ancestors for.

        Returns:
            Dict mapping ancestor target_role_address to RoleEnvelope.
        """
        result: dict[str, RoleEnvelope] = {}
        with self._lock:
            for addr, envelope in self._role_envelopes.items():
                # addr is an ancestor if role_address starts with addr
                if role_address == addr or role_address.startswith(addr + "-"):
                    result[addr] = envelope
        return result


class MemoryClearanceStore:
    """In-memory ClearanceStore using OrderedDict with bounded size.

    Clearances are keyed by role_address. All public methods are thread-safe
    via an internal ``threading.Lock``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._clearances: OrderedDict[str, RoleClearance] = OrderedDict()

    def grant_clearance(self, clearance: RoleClearance) -> None:
        """Grant or update a clearance for a role address."""
        key = clearance.role_address
        with self._lock:
            if key in self._clearances:
                self._clearances.move_to_end(key)
            self._clearances[key] = clearance
            _evict_oldest(self._clearances, MAX_STORE_SIZE)
        logger.info(
            "Granted clearance '%s' to role '%s'",
            clearance.max_clearance.value,
            key,
        )

    def get_clearance(self, role_address: str) -> RoleClearance | None:
        """Get the clearance for a role address, or None if not found."""
        with self._lock:
            return self._clearances.get(role_address)

    def revoke_clearance(self, role_address: str) -> None:
        """Revoke clearance for a role address. No-op if not found."""
        with self._lock:
            removed = self._clearances.pop(role_address, None)
        if removed is not None:
            logger.info("Revoked clearance for role '%s'", role_address)
        else:
            logger.debug(
                "revoke_clearance: no clearance found for role '%s'",
                role_address,
            )


class MemoryAccessPolicyStore:
    """In-memory AccessPolicyStore using OrderedDict with bounded size.

    KSPs are keyed by their id.
    Bridges are keyed by their id. All public methods are thread-safe via
    an internal ``threading.Lock``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ksps: OrderedDict[str, KnowledgeSharePolicy] = OrderedDict()
        self._bridges: OrderedDict[str, PactBridge] = OrderedDict()

    # ---- KSP operations ----

    def save_ksp(self, ksp: KnowledgeSharePolicy) -> None:
        """Save a Knowledge Share Policy."""
        with self._lock:
            if ksp.id in self._ksps:
                self._ksps.move_to_end(ksp.id)
            self._ksps[ksp.id] = ksp
            _evict_oldest(self._ksps, MAX_STORE_SIZE)
        logger.info(
            "Saved KSP '%s': %s -> %s",
            ksp.id,
            ksp.source_unit_address,
            ksp.target_unit_address,
        )

    def find_ksp(self, source_prefix: str, target_prefix: str) -> KnowledgeSharePolicy | None:
        """Find a KSP matching the given source and target prefixes.

        KSPs are directional: source shares WITH target. This method
        searches for a KSP where source_unit_address matches source_prefix
        and target_unit_address matches target_prefix. It does NOT check
        the reverse direction -- KSPs are unidirectional by design.

        Args:
            source_prefix: The source unit address prefix.
            target_prefix: The target unit address prefix.

        Returns:
            The first matching KSP, or None if no match found.
        """
        with self._lock:
            for ksp in self._ksps.values():
                if (
                    ksp.source_unit_address == source_prefix
                    and ksp.target_unit_address == target_prefix
                ):
                    return ksp
        return None

    def list_ksps(self) -> list[KnowledgeSharePolicy]:
        """Return all stored KSPs."""
        with self._lock:
            return list(self._ksps.values())

    # ---- Bridge operations ----

    def save_bridge(self, bridge: PactBridge) -> None:
        """Save a Cross-Functional Bridge."""
        with self._lock:
            if bridge.id in self._bridges:
                self._bridges.move_to_end(bridge.id)
            self._bridges[bridge.id] = bridge
            _evict_oldest(self._bridges, MAX_STORE_SIZE)
        logger.info(
            "Saved bridge '%s': %s <-> %s (%s)",
            bridge.id,
            bridge.role_a_address,
            bridge.role_b_address,
            bridge.bridge_type,
        )

    def find_bridge(self, role_a_address: str, role_b_address: str) -> PactBridge | None:
        """Find a bridge connecting two role addresses.

        Bridges are symmetric in lookup -- find_bridge(A, B) and
        find_bridge(B, A) return the same bridge. The bilateral flag
        controls access direction, not lookup.

        Args:
            role_a_address: One side of the bridge.
            role_b_address: The other side of the bridge.

        Returns:
            The first matching bridge, or None if no match found.
        """
        with self._lock:
            for bridge in self._bridges.values():
                if (
                    bridge.role_a_address == role_a_address
                    and bridge.role_b_address == role_b_address
                ) or (
                    bridge.role_a_address == role_b_address
                    and bridge.role_b_address == role_a_address
                ):
                    return bridge
        return None

    def list_bridges(self) -> list[PactBridge]:
        """Return all stored bridges."""
        with self._lock:
            return list(self._bridges.values())
