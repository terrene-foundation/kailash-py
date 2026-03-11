# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Kaizen Trust Revocation Module - Real-time Cascade Revocation.

This module provides pub/sub revocation event broadcasting for real-time
cascade revocation. When an agent is revoked, all delegates in the
delegation tree receive immediate notification.

Part of CARE-007: Revocation Event Broadcasting.

Key Components:
- RevocationType: Enum of revocation event types
- RevocationEvent: Record of a revocation event
- RevocationBroadcaster: ABC for revocation broadcasting
- InMemoryRevocationBroadcaster: In-memory implementation
- DelegationRegistry: Protocol for delegation lookups
- InMemoryDelegationRegistry: In-memory delegation tracking
- CascadeRevocationManager: Handles cascade revocation through delegation trees
- TrustRevocationList: Tracks revoked agents in real-time

Example:
    from eatp.revocation import (
        InMemoryRevocationBroadcaster,
        InMemoryDelegationRegistry,
        CascadeRevocationManager,
        TrustRevocationList,
        RevocationEvent,
        RevocationType,
    )

    # Set up broadcasting
    broadcaster = InMemoryRevocationBroadcaster()
    registry = InMemoryDelegationRegistry()

    # Register delegations
    registry.register_delegation("agent-A", "agent-B")
    registry.register_delegation("agent-B", "agent-C")

    # Create cascade manager
    manager = CascadeRevocationManager(broadcaster, registry)

    # Subscribe to revocation events
    trl = TrustRevocationList(broadcaster)
    trl.initialize()

    # Revoke an agent and cascade to delegates
    events = manager.cascade_revoke(
        target_id="agent-A",
        revoked_by="admin",
        reason="Security violation"
    )

    # Check if an agent is revoked
    assert trl.is_revoked("agent-A")
    assert trl.is_revoked("agent-B")
    assert trl.is_revoked("agent-C")

    # Clean up
    trl.close()
"""

from eatp.revocation.broadcaster import (
    CascadeRevocationManager,
    DeadLetterEntry,
    DelegationRegistry,
    InMemoryDelegationRegistry,
    InMemoryRevocationBroadcaster,
    RevocationBroadcaster,
    RevocationEvent,
    RevocationType,
    TrustRevocationList,
)

__all__ = [
    # Enums
    "RevocationType",
    # Data structures
    "RevocationEvent",
    "DeadLetterEntry",
    # Broadcaster
    "RevocationBroadcaster",
    "InMemoryRevocationBroadcaster",
    # Delegation Registry
    "DelegationRegistry",
    "InMemoryDelegationRegistry",
    # Cascade Manager
    "CascadeRevocationManager",
    # Trust Revocation List
    "TrustRevocationList",
]
