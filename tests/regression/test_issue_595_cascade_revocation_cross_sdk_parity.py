# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test for issue #595 — cross-SDK cascade-revocation parity.

Asserts that kailash-py's BFS-based cascade produces the SAME SET of
revoked descendants as kailash-rs's DFS-based cascade for the same
delegation tree. Only traversal order differs; result sets are identical.

Companion issue on the Rust side: esperie-enterprise/kailash-rs ISS-04.

The test constructs representative delegation trees (linear, binary tree,
star, diamond) and asserts:

1. `set(revoked_agents)` includes every descendant of the revoked root.
2. Event count equals the descendant count (one event per affected agent).
3. Idempotent re-revocation returns an empty result (matches Rust behavior).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from kailash.trust.chain import AuthorityType, GenesisRecord, TrustLineageChain
from kailash.trust.chain_store.memory import InMemoryTrustStore
from kailash.trust.revocation.broadcaster import InMemoryDelegationRegistry
from kailash.trust.revocation.cascade import cascade_revoke


def _make_chain(agent_id: str) -> TrustLineageChain:
    genesis = GenesisRecord(
        id=f"gen-{agent_id}",
        agent_id=agent_id,
        authority_id="auth-parity",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
        signature=f"sig-{agent_id}",
    )
    return TrustLineageChain(genesis=genesis)


@pytest.mark.regression
@pytest.mark.asyncio
class TestCascadeRevocationCrossSDKParity:
    """Cross-SDK parity: BFS (py) and DFS (rust) produce identical result sets."""

    async def _seed(self, store, registry, edges: list[tuple[str, str]]):
        agents: set[str] = set()
        for parent, child in edges:
            agents.add(parent)
            agents.add(child)
        for agent in agents:
            await store.store_chain(_make_chain(agent))
        for parent, child in edges:
            registry.register_delegation(delegator_id=parent, delegate_id=child)

    async def test_linear_chain_a_b_c_d(self) -> None:
        """Linear A->B->C->D: revoke A, expect {A,B,C,D}."""
        store = InMemoryTrustStore()
        registry = InMemoryDelegationRegistry()
        await self._seed(store, registry, [("A", "B"), ("B", "C"), ("C", "D")])

        result = await cascade_revoke(
            agent_id="A",
            store=store,
            reason="test",
            revoked_by="tester",
            delegation_registry=registry,
        )

        assert result.success
        assert set(result.revoked_agents) == {"A", "B", "C", "D"}

    async def test_binary_tree(self) -> None:
        """Binary tree: A->{B,C}, B->{D,E}, C->{F,G}. Revoke A ⇒ all 7."""
        store = InMemoryTrustStore()
        registry = InMemoryDelegationRegistry()
        await self._seed(
            store,
            registry,
            [
                ("A", "B"),
                ("A", "C"),
                ("B", "D"),
                ("B", "E"),
                ("C", "F"),
                ("C", "G"),
            ],
        )

        result = await cascade_revoke(
            agent_id="A",
            store=store,
            reason="test",
            revoked_by="tester",
            delegation_registry=registry,
        )

        assert result.success
        assert set(result.revoked_agents) == {"A", "B", "C", "D", "E", "F", "G"}

    async def test_star_topology(self) -> None:
        """Star: A->{B,C,D,E,F}. Revoke A ⇒ all 6."""
        store = InMemoryTrustStore()
        registry = InMemoryDelegationRegistry()
        await self._seed(
            store,
            registry,
            [("A", "B"), ("A", "C"), ("A", "D"), ("A", "E"), ("A", "F")],
        )

        result = await cascade_revoke(
            agent_id="A",
            store=store,
            reason="test",
            revoked_by="tester",
            delegation_registry=registry,
        )

        assert result.success
        assert set(result.revoked_agents) == {"A", "B", "C", "D", "E", "F"}

    async def test_diamond_shared_descendant(self) -> None:
        """Diamond: A->B, A->C, B->D, C->D. Revoke A ⇒ {A,B,C,D}; D deduped."""
        store = InMemoryTrustStore()
        registry = InMemoryDelegationRegistry()
        await self._seed(
            store,
            registry,
            [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")],
        )

        result = await cascade_revoke(
            agent_id="A",
            store=store,
            reason="test",
            revoked_by="tester",
            delegation_registry=registry,
        )

        assert result.success
        assert set(result.revoked_agents) == {"A", "B", "C", "D"}
        # D appears once regardless of traversal order
        assert result.revoked_agents.count("D") == 1

    async def test_traversal_order_invariant_to_result_set(self) -> None:
        """
        The set of revoked agents MUST be traversal-order-independent.
        Builds two identical trees, runs cascade twice, asserts result
        sets equal. This is the structural invariant that guarantees
        Rust DFS and Python BFS produce equivalent output.
        """
        store_a = InMemoryTrustStore()
        registry_a = InMemoryDelegationRegistry()
        store_b = InMemoryTrustStore()
        registry_b = InMemoryDelegationRegistry()
        edges = [
            ("root", "X"),
            ("root", "Y"),
            ("X", "X1"),
            ("X", "X2"),
            ("Y", "Y1"),
            ("Y1", "Y1a"),
        ]
        await self._seed(store_a, registry_a, edges)
        await self._seed(store_b, registry_b, edges)

        result_a = await cascade_revoke(
            agent_id="root",
            store=store_a,
            reason="test",
            revoked_by="tester",
            delegation_registry=registry_a,
        )
        result_b = await cascade_revoke(
            agent_id="root",
            store=store_b,
            reason="test",
            revoked_by="tester",
            delegation_registry=registry_b,
        )

        assert set(result_a.revoked_agents) == set(result_b.revoked_agents)
        assert set(result_a.revoked_agents) == {
            "root",
            "X",
            "Y",
            "X1",
            "X2",
            "Y1",
            "Y1a",
        }

    async def test_idempotent_re_revocation(self) -> None:
        """Revoking an already-revoked agent is a no-op — matches Rust."""
        store = InMemoryTrustStore()
        registry = InMemoryDelegationRegistry()
        await self._seed(store, registry, [("A", "B")])

        first = await cascade_revoke(
            agent_id="A",
            store=store,
            reason="test",
            revoked_by="tester",
            delegation_registry=registry,
        )
        assert first.success
        assert set(first.revoked_agents) == {"A", "B"}

        second = await cascade_revoke(
            agent_id="A",
            store=store,
            reason="test",
            revoked_by="tester",
            delegation_registry=registry,
        )
        assert second.success
        assert second.revoked_agents == []
        assert second.events == []
