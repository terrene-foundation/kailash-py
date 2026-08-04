# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests — #1981 second-order consumer breaks in kaizen-agents.

#1981 promoted a degraded capability judgment from a fabricated ``0.0`` to a
typed ``ReasoningDegradedError``. `test_issue_1981_degraded_judgment.py` pins
the four RAISING layers. This module pins the CONSUMERS of those layers — the
callers that never expected an exception and were left aborting mid-flight.

Three sites, each a distinct failure shape:

1. ``OrchestrationRuntime.execute_multi_agent_workflow`` published its
   ``WorkflowStatus`` into ``self.workflows`` BEFORE the routing loop, then
   called ``route_task`` — which now raises. On that path the method aborted
   AFTER mutating shared state, leaving a phantom registry entry that
   ``get_workflow_status()`` reported as perpetually in-flight
   (``total_tasks=N, completed=0, failed=0``) and that NOTHING could ever
   clear, because the caller never received the generated ``workflow_id``.

2. ``OrchestrationRuntime._route_task`` (SEMANTIC branch) called
   ``_score_capability`` with no handler, so the FIRST degraded capability
   aborted a documented ``-> str | None`` helper — while its
   ``_route_semantic`` sibling shrugged the identical failure off. Two
   routing helpers, same error, opposite behaviour.

3. ``UserFilteredAgentDiscovery.find_agents_for_user`` calls
   ``AgentRegistry.find_agents_by_capability``, which now raises when every
   candidate degrades. The escape was undocumented at a surface whose
   docstring promised a list.

The fixes deliberately do NOT swallow. #1981's whole point is that a degraded
judgment must stay distinguishable from a genuine no-match, so:

* the workflow records the degraded task with a ``degraded: True`` marker,
  distinct from the plain ``"No agents available"`` no-match, and honours the
  caller's ``error_handling`` policy exactly as the execution phase does;
* ``_route_task`` skips the degraded capability and raises only when NOTHING
  was scoreable, matching ``_route_semantic`` exactly;
* discovery PROPAGATES (returning ``[]`` there would reinstate the very bug
  #1981 killed — ``[]`` reads as "no agent has this capability") after a WARN
  makes it triageable at that layer.

Scoring is stubbed at the reasoning helpers so control flow is deterministic.
These are STRUCTURAL assertions about error contracts and shared-state
mutation ordering — no probe is required per
``probe-driven-verification.md`` Rule 3.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from kaizen.core.base_agent import BaseAgent
from kaizen.llm.reasoning import ReasoningDegradedError
from kaizen.nodes.ai.a2a import A2AAgentCard, Capability, CapabilityLevel
from kaizen.signatures import InputField, OutputField, Signature

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _degraded(helper: str = "llm_text_similarity") -> ReasoningDegradedError:
    """The exact error shape the reasoning helpers raise on #1981."""
    return ReasoningDegradedError(
        helper,
        model="test-model",
        correlation_id="cid-1981",
        error="JSON_PARSE_FAILED",
        raw_response="the score is about 0.92",
    )


class _Sig(Signature):
    """Minimal signature (underscore prefix avoids pytest collection)."""

    task: str = InputField(description="Task description")
    result: str = OutputField(description="Task result")


class _Cfg:
    """Minimal non-BaseAgentConfig stub (underscore avoids collection)."""

    def __init__(self) -> None:
        self.llm_provider = "mock"
        self.model = "mock-model"


def _agent(agent_id: str, capabilities: list[str], *, card: object = None) -> Mock:
    agent = Mock(spec=BaseAgent)
    agent.agent_id = agent_id
    agent.config = _Cfg()
    agent.signature = _Sig()
    agent.run = AsyncMock(return_value={"result": "ok"})
    agent.to_a2a_card = Mock(
        return_value=(
            card
            if card is not None
            else {"agent_id": agent_id, "capabilities": capabilities}
        )
    )
    # ``_build_workflow_from_agents`` derives each agent's LLMAgentNode config
    # from ``agent.to_workflow()``. A bare ``Mock(spec=BaseAgent)`` auto-creates
    # that method, so ``.nodes.values()`` returned a Mock and the runtime died
    # with "'Mock' object is not iterable" BEFORE any assertion ran — meaning
    # the index-shift invariant these tests exist for was unverified, not
    # merely un-run.
    #
    # The stub mirrors the contract the runtime actually reads: exactly ONE
    # spec typed "LLMAgentNode", carrying a ``config`` dict it copies before
    # injecting the task's messages. Faithful to the shape, so the test
    # exercises the real code path rather than routing around it.
    agent.to_workflow = Mock(
        return_value=SimpleNamespace(
            nodes={
                f"{agent_id}_llm": {
                    "type": "LLMAgentNode",
                    "config": {"provider": None, "model": None},
                }
            }
        )
    )
    return agent


async def _runtime(*agents):
    from kaizen_agents.patterns.runtime import (
        OrchestrationRuntime,
        OrchestrationRuntimeConfig,
    )

    runtime = OrchestrationRuntime(
        config=OrchestrationRuntimeConfig(enable_health_monitoring=False)
    )
    for agent in agents:
        await runtime.register_agent(agent)
    return runtime


# ===========================================================================
# Site 1 — execute_multi_agent_workflow: abort AFTER mutating shared state
# ===========================================================================


class TestExecuteMultiAgentWorkflowStateInvariant:
    """INVARIANT: ``self.workflows`` only ever holds workflows whose ROUTING
    phase completed."""

    @pytest.mark.asyncio
    async def test_fail_fast_routing_degradation_leaves_no_phantom_workflow(self):
        """THE TEETH. Pre-fix the status object was published at line 987 and
        ``route_task`` raised at line 992 — the entry survived the abort with
        no owner and no way to reach it."""
        runtime = await _runtime(
            _agent("a1", ["Code generation"]), _agent("a2", ["Data analysis"])
        )

        with (
            patch(
                "kaizen_agents.patterns.runtime.llm_text_similarity",
                side_effect=lambda **kw: (_ for _ in ()).throw(_degraded()),
            ),
            pytest.raises(ReasoningDegradedError),
        ):
            await runtime.execute_multi_agent_workflow(
                tasks=["anything"],
                routing_strategy="semantic",
                error_handling="fail-fast",
            )

        assert runtime.workflows == {}, (
            "the routing phase aborted AFTER publishing the WorkflowStatus: "
            f"{list(runtime.workflows)!r} is a phantom entry that "
            "get_workflow_status() reports as perpetually in-flight and that "
            "no caller can ever clear (the workflow_id never left the method)"
        )

    @pytest.mark.asyncio
    async def test_phantom_entry_is_not_reachable_via_get_workflow_status(self):
        """The user-visible consequence of the invariant, asserted through the
        public observability surface rather than the private dict."""
        runtime = await _runtime(_agent("a1", ["Code generation"]))

        with (
            patch(
                "kaizen_agents.patterns.runtime.llm_text_similarity",
                side_effect=lambda **kw: (_ for _ in ()).throw(_degraded()),
            ),
            pytest.raises(ReasoningDegradedError),
        ):
            await runtime.execute_multi_agent_workflow(
                tasks=["anything"],
                routing_strategy="semantic",
                error_handling="fail-fast",
            )

        for workflow_id in list(runtime.workflows):
            status = await runtime.get_workflow_status(workflow_id)
            pytest.fail(
                f"an orphaned workflow is still queryable: {status!r} — it will "
                "never complete and never be cleared"
            )

    @pytest.mark.asyncio
    async def test_graceful_records_degraded_task_instead_of_aborting(self):
        """Default ``error_handling="graceful"`` MUST NOT abort the workflow
        for one degraded routing decision — the execution phase below already
        honours the same policy."""
        runtime = await _runtime(_agent("a1", ["Code generation"]))

        with patch(
            "kaizen_agents.patterns.runtime.llm_text_similarity",
            side_effect=lambda **kw: (_ for _ in ()).throw(_degraded()),
        ):
            result = await runtime.execute_multi_agent_workflow(
                tasks=["anything"],
                routing_strategy="semantic",
                error_handling="graceful",
            )

        assert result["failed_tasks"] == 1
        entry = result["results"][0]
        assert entry["status"] == "failed"
        assert entry["degraded"] is True, (
            "the degraded routing was recorded as an ordinary failure; a total "
            "judge failure and a genuine no-match must stay distinguishable"
        )
        assert entry["degraded_helper"] == "runtime.route_semantic"
        assert entry["correlation_id"]

    @pytest.mark.asyncio
    async def test_graceful_degradation_is_distinct_from_no_agents_available(self):
        """The no-match path must NOT acquire the degraded marker."""
        runtime = await _runtime()  # zero agents -> route_task returns None

        result = await runtime.execute_multi_agent_workflow(
            tasks=["anything"], error_handling="graceful"
        )

        entry = result["results"][0]
        assert entry["error"] == "No agents available"
        assert "degraded" not in entry, (
            "a genuine 'no agents' no-match was marked degraded, collapsing "
            "exactly the distinction #1981 preserves"
        )

    @pytest.mark.asyncio
    async def test_graceful_run_publishes_the_workflow_for_observability(self):
        """Non-regression: the entry IS published once routing completes, so
        ``get_workflow_status`` keeps working on the normal path."""
        runtime = await _runtime()

        result = await runtime.execute_multi_agent_workflow(
            tasks=["anything"], error_handling="graceful"
        )

        status = await runtime.get_workflow_status(result["workflow_id"])
        assert status is not None and status["total_tasks"] == 1

    @pytest.mark.asyncio
    async def test_degraded_task_does_not_shift_the_agent_to_task_mapping(self):
        """A task that fails to route must not slide a LATER task onto the
        wrong agent. Pre-fix ``assigned_tasks`` was rebuilt by index
        (``tasks[i] for i < len(selected_agents)``), so dropping task 0 handed
        task 0's text to task 1's agent."""
        runtime = await _runtime(_agent("a1", ["Data analysis"]))

        def side_effect(*, text_a, text_b, config=None, correlation_id=None):
            if text_a == "degrade-me":
                raise _degraded()
            return 0.9

        captured: dict[str, object] = {}

        async def _fake_execute(workflow, inputs=None):
            captured["workflow"] = workflow
            return ({"agent_0_a1": {"result": "ok"}}, "run-1")

        runtime._async_runtime = SimpleNamespace(execute_workflow_async=_fake_execute)

        with patch(
            "kaizen_agents.patterns.runtime.llm_text_similarity",
            side_effect=side_effect,
        ):
            result = await runtime.execute_multi_agent_workflow(
                tasks=["degrade-me", "ok-task"],
                routing_strategy="semantic",
                error_handling="graceful",
            )

        completed = [r for r in result["results"] if r["status"] == "completed"]
        assert len(completed) == 1
        assert completed[0]["task"] == "ok-task", (
            "the surviving agent was handed the DEGRADED task's text — the "
            f"index-rebuilt mapping slid by one (got {completed[0]['task']!r})"
        )


# ===========================================================================
# Site 2 — _route_task SEMANTIC branch
# ===========================================================================


def _object_card(*capabilities: str) -> A2AAgentCard:
    """A card in the shape PRODUCTION actually emits.

    This helper previously returned ``SimpleNamespace(capabilities=[...])``,
    with a docstring explaining that ``_route_task`` reads
    ``a2a_card.capabilities`` so the card "must be object-shaped ... to score
    at all". Both halves of that were an accommodation to a defect, not a
    description of production.

    ``A2AAgentCard`` declares ``primary_capabilities`` /
    ``secondary_capabilities`` / ``emerging_capabilities`` and NO
    ``capabilities`` field, and ``to_a2a_card()`` is its only producer — so no
    production path can emit a card carrying ``.capabilities``. The fixture had
    been shaped to the one attribute name the code under test happened to read,
    which is why these assertions passed while the branch scored nothing for
    every real card: the judge was invoked zero times and the positional
    fallback was returned.

    Using the real type is what makes this suite a guard rather than a
    tautology — see `instrument-discipline.md` MUST-2: a green test reports on
    the behaviour it NAMES only if it would red in that behaviour's absence.
    """
    return A2AAgentCard(
        agent_id="card",
        agent_name="card",
        agent_type="test",
        version="1.0.0",
        primary_capabilities=[
            Capability(
                name=c,
                domain="test",
                level=CapabilityLevel.ADVANCED,
                description=c,
                keywords=[],
                examples=[],
            )
            for c in capabilities
        ],
    )


class TestRouteTaskSemanticDegraded:
    @pytest.mark.asyncio
    async def test_partial_degradation_still_returns_the_scoring_agent(self):
        """Pre-fix the FIRST degraded capability escaped ``_route_task``
        uncaught, aborting a helper documented to return ``str | None``."""
        runtime = await _runtime(
            _agent("a1", [], card=_object_card("Code generation")),
            _agent("a2", [], card=_object_card("Data analysis")),
        )
        runtime.config.default_routing_strategy = "semantic"

        # Patch `Capability.matches_requirement`, NOT `llm_text_similarity`.
        # `_score_capability` dispatches on TYPE: real `Capability` dataclass
        # instances are scored through `matches_requirement`, and only PLAIN
        # STRING capabilities go through `llm_text_similarity`. The old fixture
        # held bare strings, so patching the string judge was sufficient — and
        # that is a second way these assertions were not exercising production,
        # which emits `Capability` objects and therefore the other judge
        # entirely.
        def _matches(self, requirement, **_kw):
            if self.name == "Code generation":
                raise _degraded()
            return 0.9

        with patch.object(Capability, "matches_requirement", _matches):
            selected = await runtime._route_task("analyse the data", ["a1", "a2"])

        assert selected == "a2", (
            "one degraded capability sank the whole helper; its "
            "`_route_semantic` sibling skips it and ranks the rest"
        )

    @pytest.mark.asyncio
    async def test_all_degraded_raises_an_aggregate_naming_this_helper(self):
        """Matching ``_route_semantic``: an entirely unscoreable round MUST
        raise rather than silently return the ``active_agents[0]`` fallback,
        which would hide a total judge failure behind a plausible pick."""
        runtime = await _runtime(
            _agent("a1", [], card=_object_card("Code generation")),
            _agent("a2", [], card=_object_card("Data analysis")),
        )
        runtime.config.default_routing_strategy = "semantic"

        def _all_degraded(self, requirement, **_kw):
            raise _degraded()

        with (
            patch.object(Capability, "matches_requirement", _all_degraded),
            pytest.raises(ReasoningDegradedError) as exc,
        ):
            await runtime._route_task("anything", ["a1", "a2"])

        # `runtime.route_semantic`, not `runtime.route_task_semantic`. The two
        # labels existed only because two implementations existed; `_route_task`
        # now delegates to `_route_semantic`, which owns this contract outright.
        # A distinct label here would be the duplication reasserting itself.
        assert exc.value.helper == "runtime.route_semantic"
        assert "a1" in exc.value.error and "a2" in exc.value.error

    @pytest.mark.asyncio
    async def test_genuine_all_zero_round_still_returns_the_fallback(self):
        """Non-regression: SCORED zeros are a genuine no-match and keep the
        documented fallback. Only degradation raises."""
        runtime = await _runtime(_agent("a1", [], card=_object_card("Code")))
        runtime.config.default_routing_strategy = "semantic"

        with patch.object(
            Capability, "matches_requirement", lambda self, requirement, **_kw: 0.0
        ):
            selected = await runtime._route_task("unrelated", ["a1"])

        assert selected == "a1"


# ===========================================================================
# Site 3 — UserFilteredAgentDiscovery.find_agents_for_user
# ===========================================================================


def _registry_agent(agent_id: str, capability: str) -> Mock:
    agent = Mock(spec=BaseAgent)
    agent.agent_id = agent_id
    agent.config = _Cfg()
    agent.signature = _Sig()
    agent.run = AsyncMock(return_value={"result": "ok"})
    agent._a2a_card = {"name": agent_id, "capability": capability}
    return agent


class TestDiscoveryCapabilityFilterDegraded:
    @pytest.mark.asyncio
    async def test_all_degraded_propagates_instead_of_returning_empty(self, caplog):
        """The registry raises so that ``[]`` cannot be read as "no agent has
        this capability". Discovery MUST NOT undo that one layer up."""
        from kaizen_agents.patterns.discovery import UserFilteredAgentDiscovery
        from kaizen_agents.patterns.registry import AgentRegistry

        registry = AgentRegistry()
        await registry.register_agent(_registry_agent("a1", "Code"), "rt")
        await registry.register_agent(_registry_agent("a2", "Data"), "rt")
        discovery = UserFilteredAgentDiscovery(registry)

        with (
            patch(
                "kaizen_agents.patterns.registry.llm_text_similarity",
                side_effect=lambda **kw: (_ for _ in ()).throw(_degraded()),
            ),
            caplog.at_level(logging.WARNING, logger="kaizen_agents.patterns.discovery"),
            pytest.raises(ReasoningDegradedError) as exc,
        ):
            await discovery.find_agents_for_user(
                user_id="u-1", organization_id="o-1", capability_filter="code"
            )

        assert exc.value.helper == "registry.find_agents_by_capability"
        assert any(
            r.getMessage() == "discovery.find_agents_for_user.degraded"
            for r in caplog.records
        ), (
            "the degradation passed through the discovery layer with no WARN — "
            "it must be triageable at THIS layer too (observability MUST Rule 3)"
        )

    @pytest.mark.asyncio
    async def test_partial_degradation_returns_the_scored_agents(self):
        """Non-regression: a partially-degraded lookup still resolves."""
        from kaizen_agents.patterns.discovery import UserFilteredAgentDiscovery
        from kaizen_agents.patterns.registry import AgentRegistry

        registry = AgentRegistry()
        await registry.register_agent(_registry_agent("a1", "Code"), "rt")
        await registry.register_agent(_registry_agent("a2", "Data"), "rt")
        discovery = UserFilteredAgentDiscovery(registry)

        def side_effect(*, text_a, text_b, config=None, correlation_id=None):
            if "Code" in str(text_b):
                raise _degraded()
            return 0.9

        with patch(
            "kaizen_agents.patterns.registry.llm_text_similarity",
            side_effect=side_effect,
        ):
            found = await discovery.find_agents_for_user(
                user_id="u-1", organization_id="o-1", capability_filter="anything"
            )

        assert [a.metadata.agent_id for a in found] == ["a2"]

    @pytest.mark.asyncio
    async def test_unfiltered_discovery_is_untouched(self):
        """Non-regression: no ``capability_filter`` means no LLM judge at all,
        so the degradation contract cannot fire on that path."""
        from kaizen_agents.patterns.discovery import UserFilteredAgentDiscovery
        from kaizen_agents.patterns.registry import AgentRegistry

        registry = AgentRegistry()
        await registry.register_agent(_registry_agent("a1", "Code"), "rt")
        discovery = UserFilteredAgentDiscovery(registry)

        found = await discovery.find_agents_for_user(
            user_id="u-1", organization_id="o-1"
        )

        assert [a.metadata.agent_id for a in found] == ["a1"]
