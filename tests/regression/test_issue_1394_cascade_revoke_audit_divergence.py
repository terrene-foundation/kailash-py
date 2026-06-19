# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression for issue #1394 — cascade_revoke audit/store divergence.

cascade_revoke() previously returned ``RevocationResult(success=False,
revoked_agents=[])`` on ANY partial failure — even when the best-effort
rollback could NOT restore an already-soft-deleted chain. Those chains remain
revoked in the store, so the result claimed "no agents revoked" while chains
were still deleted (store state and audit result diverged).

This regression pins the ground-truth-reporting contract: any chain that the
rollback cannot restore remains revoked AND is reported in ``revoked_agents``,
so store state and the result always agree.

Found by the holistic post-multi-wave redteam of the PACT/trust-plane surface.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

import pytest

from kailash.trust.chain import AuthorityType, GenesisRecord, TrustLineageChain
from kailash.trust.chain_store.memory import InMemoryTrustStore
from kailash.trust.exceptions import TrustChainNotFoundError
from kailash.trust.revocation.broadcaster import (
    InMemoryDelegationRegistry,
    InMemoryRevocationBroadcaster,
)
from kailash.trust.revocation.cascade import cascade_revoke

pytestmark = pytest.mark.regression


def _make_chain(agent_id: str, authority_id: str = "auth-1") -> TrustLineageChain:
    return TrustLineageChain(
        genesis=GenesisRecord(
            id=f"gen-{agent_id}",
            agent_id=agent_id,
            authority_id=authority_id,
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            signature="sig-test-genesis",
        )
    )


class FailDeleteAndRestoreStore(InMemoryTrustStore):
    """Simulates the DOUBLE failure: a chain deletion fails (triggering the
    rollback path) AND, once armed, restoring an already-deleted chain also
    fails. The chain whose restore fails remains soft-deleted (revoked).
    """

    def __init__(
        self,
        fail_delete_on: Optional[List[str]] = None,
        fail_restore_on: Optional[List[str]] = None,
    ):
        super().__init__()
        self._fail_delete_on = set(fail_delete_on or [])
        self._fail_restore_on = set(fail_restore_on or [])
        self._armed = False

    def arm(self) -> None:
        """Activate restore failures (after test setup has stored chains)."""
        self._armed = True

    async def delete_chain(self, agent_id: str, soft_delete: bool = True) -> None:
        if agent_id in self._fail_delete_on:
            raise RuntimeError(f"Simulated delete failure for agent '{agent_id}'")
        return await super().delete_chain(agent_id, soft_delete=soft_delete)

    async def store_chain(
        self, chain: TrustLineageChain, expires_at: Optional[datetime] = None
    ) -> str:
        if self._armed and chain.genesis.agent_id in self._fail_restore_on:
            raise RuntimeError(
                f"Simulated restore failure for agent '{chain.genesis.agent_id}'"
            )
        return await super().store_chain(chain, expires_at=expires_at)


async def test_unrestorable_chain_reported_in_revoked_agents(caplog):
    """When rollback cannot restore a deleted chain, revoked_agents reports it."""
    registry = InMemoryDelegationRegistry()
    broadcaster = InMemoryRevocationBroadcaster()
    # agent-A deletes successfully, then its rollback restore fails;
    # agent-B's delete fails (which triggers the rollback path).
    store = FailDeleteAndRestoreStore(
        fail_delete_on=["agent-B"], fail_restore_on=["agent-A"]
    )
    await store.store_chain(_make_chain("agent-A"))
    await store.store_chain(_make_chain("agent-B"))
    registry.register_delegation("agent-A", "agent-B")
    store.arm()  # restores of agent-A now fail

    with caplog.at_level(logging.WARNING):
        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="issue-1394 double-failure ground-truth regression",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

    # The delete that failed is surfaced as an error; success is False.
    assert result.success is False
    assert "agent-B" in result.errors

    # GROUND TRUTH: agent-A remains soft-deleted (revoked) because its rollback
    # restore failed — it MUST be reported, not zeroed (the issue-1394 bug).
    assert result.revoked_agents == ["agent-A"]

    # The store agrees: agent-A's active chain is gone.
    with pytest.raises(TrustChainNotFoundError):
        await store.get_chain("agent-A", include_inactive=False)

    # Operator-visible warning names the un-restorable chain.
    warning_messages = [
        r.message for r in caplog.records if r.levelno >= logging.WARNING
    ]
    assert any(
        "could not be restored" in m for m in warning_messages
    ), f"expected an unrestorable-chain warning, got: {warning_messages}"


async def test_clean_rollback_still_reports_empty_revoked_agents():
    """When rollback fully succeeds, prior behavior is preserved (nothing revoked)."""
    registry = InMemoryDelegationRegistry()
    broadcaster = InMemoryRevocationBroadcaster()
    store = FailDeleteAndRestoreStore(fail_delete_on=["agent-B"], fail_restore_on=[])
    await store.store_chain(_make_chain("agent-A"))
    await store.store_chain(_make_chain("agent-B"))
    registry.register_delegation("agent-A", "agent-B")
    store.arm()

    result = await cascade_revoke(
        agent_id="agent-A",
        store=store,
        reason="issue-1394 clean-rollback control",
        revoked_by="admin",
        broadcaster=broadcaster,
        delegation_registry=registry,
    )

    assert result.success is False
    assert "agent-B" in result.errors
    # agent-A was deleted then successfully restored -> not revoked.
    assert result.revoked_agents == []
    chain = await store.get_chain("agent-A", include_inactive=False)
    assert chain.genesis.agent_id == "agent-A"
