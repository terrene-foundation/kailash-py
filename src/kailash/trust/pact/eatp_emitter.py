# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Synchronous EATP record emission protocol for PACT governance events.

The EATP TrustStore API is async and stores complete TrustLineageChain objects.
GovernanceEngine is synchronous and emits individual records per governance event.
This module bridges the gap with a synchronous protocol and default implementation.

See: PACT spec Section 5.7 (normative record type mappings).
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Protocol, runtime_checkable

from kailash.trust.chain import (
    CapabilityAttestation,
    DelegationRecord,
    GenesisRecord,
)

logger = logging.getLogger(__name__)

__all__ = [
    "InMemoryPactEmitter",
    "PactEatpEmitter",
]


@runtime_checkable
class PactEatpEmitter(Protocol):
    """Synchronous protocol for emitting EATP records from PACT governance events.

    Implementations may buffer, store to file, forward to an async TrustStore,
    or simply collect for inspection.

    GovernanceEngine calls these methods OUTSIDE its lock (same pattern as
    _emit_audit), so implementations must be independently thread-safe if
    shared across threads.
    """

    def emit_genesis(self, record: GenesisRecord) -> None:
        """Emit a GenesisRecord (org creation)."""
        ...

    def emit_delegation(self, record: DelegationRecord) -> None:
        """Emit a DelegationRecord (envelope set, bridge creation)."""
        ...

    def emit_capability(self, record: CapabilityAttestation) -> None:
        """Emit a CapabilityAttestation (clearance grant)."""
        ...


class InMemoryPactEmitter:
    """Collects EATP records in bounded deques for inspection and testing.

    Thread-safe: deque with maxlen is atomic for append on CPython (GIL).
    For non-CPython runtimes, wrap in a threading.Lock.

    Args:
        maxlen: Maximum number of records per type. Oldest records are
            evicted when the limit is reached (FIFO).
    """

    def __init__(self, maxlen: int = 10_000) -> None:
        self.genesis_records: deque[GenesisRecord] = deque(maxlen=maxlen)
        self.delegation_records: deque[DelegationRecord] = deque(maxlen=maxlen)
        self.capability_records: deque[CapabilityAttestation] = deque(maxlen=maxlen)

    def emit_genesis(self, record: GenesisRecord) -> None:
        self.genesis_records.append(record)

    def emit_delegation(self, record: DelegationRecord) -> None:
        self.delegation_records.append(record)

    def emit_capability(self, record: CapabilityAttestation) -> None:
        self.capability_records.append(record)
