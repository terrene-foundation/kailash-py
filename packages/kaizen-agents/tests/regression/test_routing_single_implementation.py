# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression suite: one implementation per routing strategy (forest W13).

`OrchestrationRuntime` had TWO routing implementations. The public
`route_task` dispatched to `_route_semantic` / `_route_least_loaded` /
`_route_random` / `_route_round_robin`. The ID-returning `_route_task` carried
its own inline copy of all four.

The copies drifted, and the drift was invisible:

* `_route_task`'s SEMANTIC copy read `getattr(a2a_card, "capabilities", [])`.
  `A2AAgentCard` declares `primary_capabilities` / `secondary_capabilities` /
  `emerging_capabilities` and NO `capabilities`; for the dict card shape
  `getattr` never sees dict keys either. So the capability list was empty for
  BOTH shapes, the scoring loop never ran, the judge was invoked ZERO times,
  and every SEMANTIC route returned `available_agents[0]` — deterministic,
  unreasoned, silent.

* `_route_round_robin` (the LIVE one) indexed `agents[self._round_robin_index]`
  with no modulo on READ. The index is runtime-scoped and persists across
  calls while the candidate list is per-call, so any pool shrink — a
  deregistration, or the health monitor marking an agent UNHEALTHY — raised
  IndexError and aborted routing. The correct modulo-on-read guard existed
  ONLY in `_route_task`'s copy, i.e. only in the dead code.

So each implementation held the bug the other one fixed.

None of this was caught because `_route_task` has no production caller — its
only consumer is the #1981 regression suite, whose fixture returned
`SimpleNamespace(capabilities=[...])`, a shape no production path can emit. The
fixture had been shaped to the defect, so the guard on a closed CRITICAL was
asserting against code production never runs.

The fix deletes the duplicate: `_route_task` is now a thin ID-returning adapter
over the same helpers `route_task` uses. These tests pin that there is exactly
ONE implementation, so a future re-divergence fails here rather than silently.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from kaizen.core.base_agent import BaseAgent
from kaizen.nodes.ai.a2a import A2AAgentCard, Capability, CapabilityLevel

pytestmark = pytest.mark.regression


def _card(*names: str) -> A2AAgentCard:
    """A card in the shape `to_a2a_card()` actually produces."""
    return A2AAgentCard(
        agent_id="c",
        agent_name="c",
        agent_type="test",
        version="1.0.0",
        primary_capabilities=[
            Capability(
                name=n,
                domain="test",
                level=CapabilityLevel.ADVANCED,
                description=n,
                keywords=[],
                examples=[],
            )
            for n in names
        ],
    )


def _agent(agent_id: str, card: object) -> Mock:
    agent = Mock(spec=BaseAgent)
    agent.agent_id = agent_id
    agent.to_a2a_card = Mock(return_value=card)
    return agent


async def _runtime(*agents):
    from kaizen_agents.patterns.runtime import (
        OrchestrationRuntime,
        OrchestrationRuntimeConfig,
    )

    runtime = OrchestrationRuntime(
        config=OrchestrationRuntimeConfig(enable_health_monitoring=False)
    )
    for a in agents:
        await runtime.register_agent(a)
    return runtime


class TestSemanticActuallyConsultsTheJudge:
    """The defect in one assertion: was the LLM asked at all?"""

    @pytest.mark.asyncio
    async def test_production_shaped_card_is_ranked_not_positional(self):
        from kaizen_agents.patterns.runtime import RoutingStrategy

        runtime = await _runtime(
            _agent("a1", _card("Code generation")),
            _agent("a2", _card("Data analysis")),
        )
        runtime.config.default_routing_strategy = RoutingStrategy.SEMANTIC

        calls: list[str] = []

        def judge(self, requirement, **_kw):
            calls.append(self.name)
            return 0.99 if self.name == "Data analysis" else 0.01

        with patch.object(Capability, "matches_requirement", judge):
            selected = await runtime._route_task("analyse the data", ["a1", "a2"])

        # The judge-invocation count is what makes this discriminating. Without
        # it, a fixture that happened to order the better agent first would pass
        # against the dead branch by luck — which is exactly how the previous
        # suite stayed green.
        assert calls, (
            "the capability judge was never invoked — SEMANTIC routing returned "
            "a positional pick without consulting the LLM at all"
        )
        assert selected == "a2", (
            f"ranked selection ignored: judge scored 'Data analysis' 0.99 vs "
            f"'Code generation' 0.01 but got {selected!r} "
            f"(judge saw {calls!r})"
        )


class TestNoCapabilityDataIsLoud:
    """The positional fallback under SEMANTIC must announce itself.

    Both neighbouring outcomes are loud — an all-degraded round raises, a
    partially-degraded one WARNs — while "nothing to rank on at all" returned a
    round-robin pick indistinguishable from a ranked result. Same silence, but
    reached without the judge ever being consulted.
    """

    @pytest.mark.asyncio
    async def test_warns_when_nothing_is_rankable(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        from kaizen_agents.patterns.runtime import RoutingStrategy

        # Real config, real registration — no hand-rolled stub. A stub is how
        # the previous version of this assertion silently missed the
        # `enable_semantic_routing` gate.
        runtime = await _runtime(
            _agent("a1", None),
            _agent("a2", None),
        )
        runtime.config.default_routing_strategy = RoutingStrategy.SEMANTIC

        with caplog.at_level(logging.WARNING):
            selected = await runtime._route_task("do the thing", ["a1", "a2"])

        assert selected in ("a1", "a2"), (
            "contract unchanged: a candidate is still returned; only the "
            "silence was the defect"
        )
        hits = [
            r
            for r in caplog.records
            if r.message == "route_semantic.no_capability_data"
        ]
        assert hits, (
            "SEMANTIC routing fell back to positional selection with no "
            "WARNING — the caller asked for ranking and got an arbitrary pick "
            "with no signal (zero-tolerance Rule 3)"
        )
        assert (
            "remedy" in hits[0].__dict__
        ), "WARNING does not tell the operator how to fix the registration"

    @pytest.mark.asyncio
    async def test_not_conflated_with_the_degraded_signal(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """`degraded` means the judge was consulted and failed; this key means
        it was never consulted. Emitting the former here would send triage to
        the LLM provider when the fault is agent registration."""
        import logging

        from kaizen_agents.patterns.runtime import RoutingStrategy

        runtime = await _runtime(_agent("a1", None), _agent("a2", None))
        runtime.config.default_routing_strategy = RoutingStrategy.SEMANTIC

        with caplog.at_level(logging.WARNING):
            await runtime._route_task("do the thing", ["a1", "a2"])

        assert not [
            r for r in caplog.records if r.message == "route_semantic.degraded"
        ], "emitted the degraded signal when nothing was ever scored"


class TestBothEntryPointsAgree:
    """The structural anti-drift invariant.

    This is the assertion the original defect lacked. Any future second
    implementation of a strategy fails HERE, at the point of divergence,
    instead of silently returning a different answer from the other door.

    SCOPE — the parity claim is bounded to ACTIVE candidates, deliberately.
    The two entry points do NOT share a candidate filter, and that difference
    is PRE-EXISTING and preserved on purpose:

      * `route_task` selects over ALL registered agents and, finding no ACTIVE
        ones, FALLS BACK to DEGRADED agents.
      * `_route_task` selects within an EXPLICIT `available_agents` subset the
        caller passed, and has never had that fallback — no ACTIVE candidate in
        the given subset returns None.

    Those are different contracts, not drift: one asks "route this anywhere",
    the other "route this among these". Collapsing them would silently widen
    `_route_task`'s candidate set beyond what its caller named — a worse defect
    than the one this suite exists for.

    So the fixtures below register only ACTIVE agents. If a future change makes
    the filters agree, extend this suite rather than assuming the parity claim
    already covered DEGRADED; it does not, and never asserted that it did.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("shape", ["object", "dict"])
    async def test_route_task_matches_public_route_task(self, shape: str) -> None:
        from kaizen_agents.patterns.runtime import RoutingStrategy

        def make(names):
            if shape == "object":
                return _card(*names)
            return {"agent_id": "c", "capabilities": list(names)}

        runtime = await _runtime(
            _agent("a1", make(["Code generation"])),
            _agent("a2", make(["Data analysis"])),
        )
        runtime.config.default_routing_strategy = RoutingStrategy.SEMANTIC

        def judge(self, requirement, **_kw):
            return 0.99 if self.name == "Data analysis" else 0.01

        def text_judge(*, text_a, text_b, config=None, correlation_id=None):
            return 0.99 if text_b == "Data analysis" else 0.01

        with (
            patch.object(Capability, "matches_requirement", judge),
            patch(
                "kaizen_agents.patterns.runtime.llm_text_similarity",
                side_effect=text_judge,
            ),
        ):
            via_private = await runtime._route_task("analyse the data", ["a1", "a2"])
            via_public = await runtime.route_task(
                "analyse the data", strategy=RoutingStrategy.SEMANTIC
            )

        assert via_public is not None
        assert via_private == via_public.agent_id, (
            f"the two routing entry points disagree on the same fixtures "
            f"({via_private!r} vs {via_public.agent_id!r}) — a strategy has "
            f"more than one implementation again"
        )


class TestRoundRobinSurvivesPoolShrink:
    """The production crash the dead code's guard would have prevented."""

    @pytest.mark.asyncio
    async def test_deregistration_between_routes_does_not_raise(self):
        from kaizen_agents.patterns.runtime import RoutingStrategy

        runtime = await _runtime(
            _agent("a0", {"agent_id": "a0"}),
            _agent("a1", {"agent_id": "a1"}),
            _agent("a2", {"agent_id": "a2"}),
        )
        runtime.config.default_routing_strategy = RoutingStrategy.ROUND_ROBIN

        ids = ["a0", "a1", "a2"]
        for _ in range(2):
            await runtime._route_task("t", ids)

        # Pool shrinks below the stored index. No forced state — a
        # deregistration or a health downgrade does exactly this.
        remaining = ["a0", "a1"]
        selected = await runtime._route_task("t", remaining)

        assert selected in remaining, (
            f"round-robin returned {selected!r}, which is not in the surviving "
            f"pool {remaining!r}"
        )

    @pytest.mark.asyncio
    async def test_helper_directly_survives_shrink(self):
        """Pin the helper itself, not only the path through `_route_task`.

        `_route_round_robin` is reachable from the PUBLIC `route_task` too, so
        asserting only via the adapter would leave the production entry point
        unguarded.
        """
        from kaizen_agents.patterns.runtime import OrchestrationRuntime

        runtime = OrchestrationRuntime.__new__(OrchestrationRuntime)
        runtime._round_robin_index = 0

        class _M:
            def __init__(self, a):
                self.agent = a

        agents = [("a0", _M("A0")), ("a1", _M("A1")), ("a2", _M("A2"))]
        for _ in range(2):
            await runtime._route_round_robin(agents)
        assert runtime._round_robin_index == 2

        # Previously: IndexError: list index out of range.
        result = await runtime._route_round_robin(agents[:2])
        assert result in ("A0", "A1")
