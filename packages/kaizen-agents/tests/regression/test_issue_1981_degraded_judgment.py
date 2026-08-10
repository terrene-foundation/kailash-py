# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1981 — degraded LLM judgments in kaizen-agents.

`kaizen.llm.reasoning.llm_capability_match` / `llm_text_similarity` now raise
`ReasoningDegradedError` instead of returning a fabricated `0.0` when the
judge's structured output cannot be parsed. A fabricated zero is
indistinguishable from a genuine no-match, so every ranking layer that
consumed it silently degraded to an arbitrary order (#1981 AC-2: the
degradation MUST be distinguishable at the API surface, not only in logs).

These tests pin the kaizen-agents half of that contract at the four call
sites which previously either propagated the typed error out of a public
float-returning API with no handling at all (`llm_routing._score_one`), or
caught it in a generic `except Exception` and converted it straight back
into the `0.0` the fix exists to eliminate (`_reasoning_bridge`, `runtime`,
`registry`).

The reference implementation is `kaizen.nodes.ai.a2a` ::
`A2ACoordinatorNode._find_best_agents_for_task` — catch PER CANDIDATE,
continue ranking with the candidates that scored, and re-raise only when
EVERY candidate degraded, so a partial failure never sinks a round but an
all-degraded round never returns an arbitrary ranking.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest

from kaizen.core.base_agent import BaseAgent
from kaizen.llm.reasoning import ReasoningDegradedError
from kaizen.signatures import InputField, OutputField, Signature

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _degraded(helper: str = "llm_text_similarity") -> ReasoningDegradedError:
    """Build the exact error shape the reasoning helpers raise on #1981."""
    return ReasoningDegradedError(
        helper,
        model="test-model",
        correlation_id="cid-1981",
        error="JSON_PARSE_FAILED",
        raw_response="the score is about 0.92",
    )


class _Sig(Signature):
    """Minimal signature for the mocked agents (underscore avoids collection)."""

    task: str = InputField(description="Task description")
    result: str = OutputField(description="Task result")


class _Cfg:
    """Minimal non-BaseAgentConfig stub (underscore avoids collection)."""

    def __init__(self) -> None:
        self.llm_provider = "mock"
        self.model = "mock-model"


class _Cap:
    """Capability-shaped object whose matcher is scripted per test."""

    def __init__(self, name: str, score):
        self.name = name
        self.description = f"{name} capability"
        self._score = score

    def matches_requirement(self, requirement, *, config=None, correlation_id=None):
        if isinstance(self._score, Exception):
            raise self._score
        return self._score


# ===========================================================================
# Site 1 — kaizen_agents.patterns.llm_routing.LLMBased
# ===========================================================================


class TestLLMRoutingDegraded:
    """`_score_one` had NO try/except: a degraded judge propagated an
    uncaught error out of `score()` / `select_best()`, both of which
    previously returned a float / a candidate."""

    @pytest.mark.asyncio
    async def test_select_best_skips_degraded_candidate(self):
        """PARTIAL degradation MUST NOT sink the round.

        Pre-fix: the first candidate's `ReasoningDegradedError` escaped the
        ranking loop uncaught, so one bad judgment lost the whole selection
        even though a later candidate scored fine.
        """
        from kaizen_agents.patterns.llm_routing import LLMBased

        def side_effect(*, text_a, text_b, config=None, correlation_id=None):
            if text_b == "alpha":
                raise _degraded()
            return 0.9

        with patch(
            "kaizen_agents.patterns.llm_routing.llm_text_similarity",
            side_effect=side_effect,
        ):
            best = await LLMBased().select_best("rank these", ["alpha", "beta"])

        assert best == "beta", (
            "a single degraded candidate sank the whole ranking round; the "
            "a2a.py reference skips it and ranks the candidates that scored"
        )

    @pytest.mark.asyncio
    async def test_select_best_all_degraded_raises_aggregate(self):
        """ALL candidates degraded MUST surface as one aggregate error.

        Pre-fix the FIRST candidate's per-helper error escaped, so the caller
        could not tell "one judgment failed" from "no ranking exists at all".
        """
        from kaizen_agents.patterns.llm_routing import LLMBased

        with (
            patch(
                "kaizen_agents.patterns.llm_routing.llm_text_similarity",
                side_effect=lambda **kw: (_ for _ in ()).throw(_degraded()),
            ),
            pytest.raises(ReasoningDegradedError) as exc,
        ):
            await LLMBased().select_best("rank these", ["alpha", "beta"])

        assert exc.value.helper == "llm_routing.select_best", (
            "the all-degraded round must raise an AGGREGATE error naming the "
            f"ranking API, got helper={exc.value.helper!r} (the raw per-"
            "candidate error leaked through an unguarded loop)"
        )
        assert "alpha" in exc.value.error and "beta" in exc.value.error

    @pytest.mark.asyncio
    async def test_score_logs_degradation_before_propagating(self, caplog):
        """`score()` has no round to sink, so it propagates — but the
        degradation MUST be triageable at THIS layer too
        (`rules/observability.md` MUST Rule 3). Pre-fix the error passed
        through `_score_one` with zero handling and zero log line."""
        from kaizen_agents.patterns.llm_routing import LLMBased

        with (
            patch(
                "kaizen_agents.patterns.llm_routing.llm_capability_match",
                side_effect=lambda **kw: (_ for _ in ()).throw(
                    _degraded("llm_capability_match")
                ),
            ),
            caplog.at_level(logging.WARNING, logger="kaizen_agents"),
            pytest.raises(ReasoningDegradedError) as exc,
        ):
            await LLMBased().score("rank this", _Cap("alpha", 0.0))

        assert exc.value.helper == "llm_capability_match", (
            "score() must re-raise the ORIGINAL error (it carries model, "
            "correlation_id and raw_response), not a lossy re-wrap"
        )
        assert any(
            "llm_routing.score.degraded" in r.getMessage() for r in caplog.records
        ), "no WARN line was emitted at the routing layer for the degradation"


# ===========================================================================
# Site 2 — kaizen_agents.patterns._reasoning_bridge
# ===========================================================================


class TestReasoningBridgeDegraded:
    """The bridge caught `Exception` and returned `0.0`, converting the typed
    degradation signal straight back into the fabricated zero #1981 exists to
    eliminate. Its documented intent — one LLM failure must not sink a whole
    selection round — is preserved by SKIPPING the degraded candidate."""

    def test_score_capability_sync_raises_instead_of_fabricating_zero(self):
        from kaizen_agents.patterns._reasoning_bridge import score_capability_sync

        with (
            patch(
                "kaizen_agents.patterns._reasoning_bridge.llm_text_similarity",
                side_effect=lambda **kw: (_ for _ in ()).throw(_degraded()),
            ),
            pytest.raises(ReasoningDegradedError),
        ):
            score_capability_sync("translation", "translate this")

    def test_score_capability_sync_still_zeroes_on_infrastructure_error(self):
        """Non-regression: a genuine infrastructure failure keeps the
        documented 0.0-with-WARN behaviour. Only the TYPED degradation
        signal is promoted."""
        from kaizen_agents.patterns._reasoning_bridge import score_capability_sync

        with patch(
            "kaizen_agents.patterns._reasoning_bridge.llm_text_similarity",
            side_effect=ConnectionError("provider unreachable"),
        ):
            assert score_capability_sync("translation", "translate this") == 0.0

    def test_score_capability_list_partial_degradation_returns_scored_max(self):
        caps = [_Cap("a", _degraded("llm_capability_match")), _Cap("b", 0.7)]
        from kaizen_agents.patterns._reasoning_bridge import score_capability_list_sync

        assert score_capability_list_sync(caps, "task") == pytest.approx(0.7)

    def test_score_capability_list_all_degraded_raises(self):
        """Pre-fix every capability degraded to 0.0 and the list returned
        0.0 — indistinguishable from "this agent matches nothing"."""
        caps = [
            _Cap("a", _degraded("llm_capability_match")),
            _Cap("b", _degraded("llm_capability_match")),
        ]
        from kaizen_agents.patterns._reasoning_bridge import score_capability_list_sync

        with pytest.raises(ReasoningDegradedError) as exc:
            score_capability_list_sync(caps, "task")
        assert exc.value.helper == "pattern.score_capability_list"

    def test_rank_agents_excludes_degraded_agent(self):
        """A degraded agent's fit is UNKNOWN, not zero: pre-fix it was ranked
        at 0.0 alongside genuine no-matches, so `scored.sort()` could place
        it anywhere among them."""
        from kaizen_agents.patterns._reasoning_bridge import (
            rank_agents_by_capability_sync,
        )

        good, bad = object(), object()
        cards = [
            (bad, Mock(primary_capabilities=[_Cap("x", _degraded())])),
            (good, Mock(primary_capabilities=[_Cap("y", 0.8)])),
        ]
        scored = rank_agents_by_capability_sync(cards, "task")

        assert [a for a, _ in scored] == [good], (
            "the degraded agent must be EXCLUDED from the ranking, not ranked "
            f"at a fabricated 0.0 (got {scored!r})"
        )

    def test_rank_agents_all_degraded_raises(self):
        from kaizen_agents.patterns._reasoning_bridge import (
            rank_agents_by_capability_sync,
        )

        cards = [
            (object(), Mock(primary_capabilities=[_Cap("x", _degraded())])),
            (object(), Mock(primary_capabilities=[_Cap("y", _degraded())])),
        ]
        with pytest.raises(ReasoningDegradedError) as exc:
            rank_agents_by_capability_sync(cards, "task")
        assert exc.value.helper == "pattern.rank_agents_by_capability"

    @pytest.mark.asyncio
    async def test_degradation_survives_the_running_loop_thread_boundary(self):
        """`_run_coroutine` dispatches through a ThreadPoolExecutor when a
        loop is already running (patterns called from async hosts). The typed
        signal MUST survive that boundary — if it did not, every async caller
        would silently take the generic-Exception path."""
        from kaizen_agents.patterns._reasoning_bridge import score_capability_sync

        with (
            patch(
                "kaizen_agents.patterns._reasoning_bridge.llm_text_similarity",
                side_effect=lambda **kw: (_ for _ in ()).throw(_degraded()),
            ),
            pytest.raises(ReasoningDegradedError),
        ):
            score_capability_sync("translation", "translate this")

    def test_rank_agents_keeps_capability_less_agent_at_zero(self):
        """Non-regression: an agent with NO capabilities is a genuine 0.0,
        not a degradation — it stays in the ranking."""
        from kaizen_agents.patterns._reasoning_bridge import (
            rank_agents_by_capability_sync,
        )

        empty = object()
        scored = rank_agents_by_capability_sync(
            [(empty, Mock(primary_capabilities=[]))], "task"
        )
        assert scored == [(empty, 0.0)]


# ===========================================================================
# Site 3 — kaizen_agents.patterns.runtime.OrchestrationRuntime
# ===========================================================================


def _runtime_agent(agent_id: str, capabilities: list[str]) -> Mock:
    agent = Mock(spec=BaseAgent)
    agent.agent_id = agent_id
    agent.config = _Cfg()
    agent.signature = _Sig()
    agent.run = AsyncMock(return_value={"result": "ok"})
    agent.to_a2a_card = Mock(
        return_value={"agent_id": agent_id, "capabilities": capabilities}
    )
    return agent


class TestRuntimeSemanticRoutingDegraded:
    @pytest.mark.asyncio
    async def test_all_degraded_raises_instead_of_round_robin(self):
        """Pre-fix every capability scored a fabricated 0.0, `best_agent`
        stayed None, and `_route_semantic` fell through to ROUND ROBIN —
        hiding a total judge failure behind a plausible-looking assignment."""
        from kaizen_agents.patterns.runtime import (
            OrchestrationRuntime,
            OrchestrationRuntimeConfig,
            RoutingStrategy,
        )

        runtime = OrchestrationRuntime(config=OrchestrationRuntimeConfig())
        await runtime.register_agent(_runtime_agent("a1", ["Code generation"]))
        await runtime.register_agent(_runtime_agent("a2", ["Data analysis"]))

        with (
            patch(
                "kaizen_agents.patterns.runtime.llm_text_similarity",
                side_effect=lambda **kw: (_ for _ in ()).throw(_degraded()),
            ),
            pytest.raises(ReasoningDegradedError) as exc,
        ):
            await runtime.route_task("anything", strategy=RoutingStrategy.SEMANTIC)

        assert exc.value.helper == "runtime.route_semantic"

    @pytest.mark.asyncio
    async def test_partial_degradation_still_routes_to_scoring_agent(self):
        from kaizen_agents.patterns.runtime import (
            OrchestrationRuntime,
            OrchestrationRuntimeConfig,
            RoutingStrategy,
        )

        runtime = OrchestrationRuntime(config=OrchestrationRuntimeConfig())
        await runtime.register_agent(_runtime_agent("a1", ["Code generation"]))
        await runtime.register_agent(_runtime_agent("a2", ["Data analysis"]))

        def side_effect(*, text_a, text_b, config=None, correlation_id=None):
            if text_b == "Code generation":
                raise _degraded()
            return 0.9

        with patch(
            "kaizen_agents.patterns.runtime.llm_text_similarity",
            side_effect=side_effect,
        ):
            selected = await runtime.route_task(
                "analyse the data", strategy=RoutingStrategy.SEMANTIC
            )

        assert selected is not None and selected.agent_id == "a2"

    @pytest.mark.asyncio
    async def test_one_agent_fully_degraded_does_not_raise_when_another_scored(self):
        """A per-AGENT degradation is not a per-ROUND one: as long as some
        capability somewhere was scored, the round stands and only a WARN is
        emitted. Guards against over-raising from the aggregate check."""
        from kaizen_agents.patterns.runtime import (
            OrchestrationRuntime,
            OrchestrationRuntimeConfig,
            RoutingStrategy,
        )

        runtime = OrchestrationRuntime(config=OrchestrationRuntimeConfig())
        await runtime.register_agent(_runtime_agent("a1", ["Code generation"]))
        await runtime.register_agent(_runtime_agent("a2", ["Data analysis"]))

        def side_effect(*, text_a, text_b, config=None, correlation_id=None):
            if text_b == "Code generation":
                raise _degraded()
            return 0.0  # genuine no-match, but SCORED

        with patch(
            "kaizen_agents.patterns.runtime.llm_text_similarity",
            side_effect=side_effect,
        ):
            selected = await runtime.route_task(
                "unrelated", strategy=RoutingStrategy.SEMANTIC
            )

        assert selected is not None, "a partially-degraded round must not raise"

    @pytest.mark.asyncio
    async def test_genuine_no_match_still_falls_back_to_round_robin(self):
        """Non-regression: an all-zero (but SCORED) round keeps the
        documented round-robin fallback. Only degradation raises."""
        from kaizen_agents.patterns.runtime import (
            OrchestrationRuntime,
            OrchestrationRuntimeConfig,
            RoutingStrategy,
        )

        runtime = OrchestrationRuntime(config=OrchestrationRuntimeConfig())
        await runtime.register_agent(_runtime_agent("a1", ["Code generation"]))

        with patch(
            "kaizen_agents.patterns.runtime.llm_text_similarity",
            return_value=0.0,
        ):
            selected = await runtime.route_task(
                "unrelated", strategy=RoutingStrategy.SEMANTIC
            )

        assert selected is not None and selected.agent_id == "a1"


# ===========================================================================
# Site 4 — kaizen_agents.patterns.registry.AgentRegistry
# ===========================================================================


def _registry_agent(agent_id: str, capability: str) -> Mock:
    agent = Mock(spec=BaseAgent)
    agent.agent_id = agent_id
    agent.config = _Cfg()
    agent.signature = _Sig()
    agent.run = AsyncMock(return_value={"result": "ok"})
    agent._a2a_card = {"name": agent_id, "capability": capability}
    return agent


class TestRegistryCapabilityLookupDegraded:
    @pytest.mark.asyncio
    async def test_all_degraded_raises_instead_of_empty_list(self):
        """Pre-fix every score fell back to 0.0, `best_score > 0` was never
        true, and the lookup returned `[]` — read by every caller as "no
        agent has this capability" rather than "the judge could not tell"."""
        from kaizen_agents.patterns.registry import AgentRegistry

        registry = AgentRegistry()
        await registry.register_agent(_registry_agent("a1", "Code"), "rt")
        await registry.register_agent(_registry_agent("a2", "Data"), "rt")

        with (
            patch(
                "kaizen_agents.patterns.registry.llm_text_similarity",
                side_effect=lambda **kw: (_ for _ in ()).throw(_degraded()),
            ),
            pytest.raises(ReasoningDegradedError) as exc,
        ):
            await registry.find_agents_by_capability("code")

        assert exc.value.helper == "registry.find_agents_by_capability"

    @pytest.mark.asyncio
    async def test_partial_degradation_warns_and_returns_scored_agents(self, caplog):
        from kaizen_agents.patterns.registry import AgentRegistry

        registry = AgentRegistry()
        await registry.register_agent(_registry_agent("a1", "Code"), "rt")
        await registry.register_agent(_registry_agent("a2", "Data"), "rt")

        def side_effect(*, text_a, text_b, config=None, correlation_id=None):
            if "Code" in str(text_b):
                raise _degraded()
            return 0.9

        with (
            patch(
                "kaizen_agents.patterns.registry.llm_text_similarity",
                side_effect=side_effect,
            ),
            caplog.at_level(logging.WARNING, logger="kaizen_agents"),
        ):
            found = await registry.find_agents_by_capability("anything")

        assert [m.agent_id for m in found] == ["a2"]
        assert any(
            "degraded" in r.getMessage() for r in caplog.records
        ), "the partially-degraded lookup emitted no WARN naming the degradation"


# ===========================================================================
# Pattern call sites — the four patterns consuming the bridge
# ===========================================================================


def _pattern_agent(agent_id: str) -> Mock:
    agent = Mock(spec=BaseAgent)
    agent.agent_id = agent_id
    agent.config = _Cfg()
    agent.to_a2a_card = Mock(
        return_value={"agent_id": agent_id, "capabilities": [f"{agent_id} skill"]}
    )
    return agent


def _run_degraded_selection(module_path, call):
    """Invoke `call` with the module's ranking helper raising the aggregate
    degradation error, capturing WARN records from the kaizen_agents tree."""
    caplog_records: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record):
            caplog_records.append(record)

    root = logging.getLogger("kaizen_agents")
    handler = _Collector(level=logging.WARNING)
    root.addHandler(handler)
    previous_level, root.level = root.level, logging.WARNING
    try:
        with patch(
            f"{module_path}.rank_agents_by_capability_sync",
            side_effect=lambda *a, **kw: (_ for _ in ()).throw(
                ReasoningDegradedError(
                    "pattern.rank_agents_by_capability",
                    model="test-model",
                    correlation_id="cid-1981",
                    error="the capability judge degraded for all 2 candidate agent(s)",
                )
            ),
        ):
            result = call()
    finally:
        root.removeHandler(handler)
        root.level = previous_level
    return result, caplog_records


class TestPatternCallSitesDegraded:
    """Each pattern consuming `rank_agents_by_capability_sync` wraps it in a
    broad `except Exception: pass` that falls through to a round-robin /
    first-agent fallback. That generic handler swallows the typed degradation
    signal SILENTLY — the "hide a total judge failure behind a plausible-
    looking assignment" failure (`rules/zero-tolerance.md` Rule 3).

    The documented fallback is preserved (a pattern's `run()` is a public sync
    contract that must not start raising), but the degradation MUST be
    observable: a typed handler logs it before falling through.
    """

    def test_meta_controller_logs_degradation_before_fallback(self):
        from kaizen_agents.patterns.patterns.meta_controller import (
            MetaControllerPipeline,
        )

        agents = [_pattern_agent("a1"), _pattern_agent("a2")]
        pipeline = MetaControllerPipeline(agents=agents)
        selected, records = _run_degraded_selection(
            "kaizen_agents.patterns.patterns.meta_controller",
            lambda: pipeline._select_agent_via_a2a("task"),
        )

        assert selected is agents[0], "documented fallback must be preserved"
        assert any("degraded" in r.getMessage() for r in records), (
            "the total-judge-failure signal was swallowed silently by the "
            "generic `except Exception` — no WARN identifies the degradation"
        )

    def test_ensemble_logs_degradation_before_fallback(self):
        from kaizen_agents.patterns.patterns.ensemble import EnsemblePipeline

        agents = [_pattern_agent("a1"), _pattern_agent("a2")]
        pipeline = EnsemblePipeline(agents=agents, synthesizer=_pattern_agent("syn"))
        selected, records = _run_degraded_selection(
            "kaizen_agents.patterns.patterns.ensemble",
            lambda: pipeline._discover_agents_via_a2a("task"),
        )

        assert selected == agents[: pipeline.top_k]
        assert any("degraded" in r.getMessage() for r in records)

    def test_blackboard_logs_degradation_before_fallback(self):
        from kaizen_agents.patterns.patterns.blackboard import BlackboardPipeline

        specialists = [_pattern_agent("s1"), _pattern_agent("s2")]
        pipeline = BlackboardPipeline(
            specialists=specialists, controller=_pattern_agent("ctl")
        )
        selected, records = _run_degraded_selection(
            "kaizen_agents.patterns.patterns.blackboard",
            lambda: pipeline._select_specialist_via_a2a("needed"),
        )

        assert selected is None, "documented no-match fallback must be preserved"
        assert any("degraded" in r.getMessage() for r in records)

    def test_supervisor_worker_logs_degradation_before_fallback(self):
        from kaizen_agents.patterns.patterns.supervisor_worker import SupervisorAgent

        workers = [_pattern_agent("w1"), _pattern_agent("w2")]
        # Duck-typed host: `select_worker_for_task` reads only these two
        # attributes on the A2A branch, and constructing a real SupervisorAgent
        # would stand up an LLM-backed BaseAgent for a pure selection test.
        host = Mock(spec=["a2a_coordinator", "config"])
        host.a2a_coordinator = "capability_matching"
        host.config = None

        selected, records = _run_degraded_selection(
            "kaizen_agents.patterns.patterns.supervisor_worker",
            lambda: SupervisorAgent.select_worker_for_task(host, "task", workers),
        )

        assert selected is workers[0], "documented round-robin fallback preserved"
        assert any("degraded" in r.getMessage() for r in records)
