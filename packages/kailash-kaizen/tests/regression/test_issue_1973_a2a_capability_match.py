"""Regression test — A2A capability matching raised TypeError on every task (#1973).

Two independent defects, both in ``kaizen/nodes/ai/a2a.py``:

**Defect 1 — unawaited coroutine multiplied by a float.**
``24dcc4bb5`` ("replace Jaccard + substring matching with LLM signatures")
converted ``Capability.matches_requirement`` from a sync ``def`` to an
``async def`` but did NOT update its only in-module caller,
``A2AAgentCard.calculate_match_score`` (a SYNCHRONOUS method), which multiplies
the result by a tier weight at three sites::

    cap.matches_requirement(requirement) * 1.0   # primary
    cap.matches_requirement(requirement) * 0.7   # secondary
    cap.matches_requirement(requirement) * 0.4   # emerging

An ``async def`` returns a coroutine, so each site raised
``TypeError: unsupported operand type(s) for *: 'coroutine' and 'float'``.
The sole non-definition call site is
``A2ACoordinatorNode._find_best_agents_for_task`` — so EVERY A2A task→agent
match with non-empty requirements raised, deterministically. The feature was
100% broken from ``24dcc4bb5`` until this fix.

The ``async def`` was itself the defect: ``matches_requirement`` delegates to
``kaizen.llm.reasoning.llm_capability_match``, which is a SYNC ``def``, and the
body contains ZERO ``await`` tokens. The fix restores the sync signature (the
LLM-first delegation from ``24dcc4bb5`` is preserved verbatim — only the
async-ness is reverted), so the three weight sites work as written and no
event loop is spawned on a Kailash node's sync ``run()`` path.

**Defect 2 — silent-swallow fallback.**
``_summarize_with_llm`` wrapped its LLM summarization branch in
``except Exception: pass`` before falling through to the simple summary. The
fallback is legitimate; the silence is not (``zero-tolerance.md`` Rule 3 — no
silent error hiding). The fix logs at WARN with the exception detail before
degrading.

These tests pin:

(a) ``_find_best_agents_for_task`` ranks agents for a task with NON-EMPTY
    requirements — the exact live path that raised;
(b) the three tier weights (1.0 / 0.7 / 0.4) survive and differentiate;
(c) ``matches_requirement`` is NOT a coroutine function (shape pin — the
    ``24dcc4bb5`` regression re-lands the moment this flips);
(d) the ``kaizen_agents`` sync/async bridges still propagate ``config`` and
    ``correlation_id`` to the now-sync matcher (guards the fix's own blast
    radius — the bridges dispatch on ``inspect.iscoroutinefunction``);
(e) the summarization fallback emits a WARN record instead of swallowing.

Scoring is stubbed at ``kaizen.llm.reasoning.llm_capability_match`` so the
arithmetic is deterministic. That is a STRUCTURAL assertion (tier-weight
arithmetic and coroutine-vs-float plumbing), not a semantic one — no probe is
required per ``probe-driven-verification.md`` Rule 3. The LLM's judgment is
explicitly NOT under test here; the wiring around it is.
"""

import inspect
import logging
import os

import pytest

from kaizen.nodes.ai.a2a import (
    A2AAgentCard,
    A2AAgentNode,
    A2ACoordinatorNode,
    A2ATask,
    Capability,
    CapabilityLevel,
)

pytestmark = pytest.mark.regression


def _cap(name: str) -> Capability:
    return Capability(
        name=name,
        domain="engineering",
        level=CapabilityLevel.EXPERT,
        description=f"can do {name}",
        keywords=[name],
    )


def _card(agent_id: str, **caps) -> A2AAgentCard:
    return A2AAgentCard(
        agent_id=agent_id,
        agent_name=agent_id.upper(),
        agent_type="worker",
        version="1.0.0",
        **caps,
    )


@pytest.fixture
def perfect_match(monkeypatch):
    """Stub the LLM judge to a constant 1.0 so tier arithmetic is exact.

    ``Capability.matches_requirement`` imports ``llm_capability_match`` locally
    (inside the method body) to avoid an import cycle, so the name resolves
    from the module namespace at CALL time — patching the module attribute is
    what reaches it.
    """
    import kaizen.llm.reasoning as reasoning

    monkeypatch.setattr(reasoning, "llm_capability_match", lambda **kw: 1.0)


class TestMatchesRequirementIsSync:
    """Deliverable (c): the shape pin that keeps #1973 closed."""

    def test_matches_requirement_is_not_a_coroutine_function(self):
        # The load-bearing pin. calculate_match_score is sync and multiplies the
        # result by a float; an async def re-introduces the TypeError at three
        # sites and breaks every A2A match again.
        assert not inspect.iscoroutinefunction(Capability.matches_requirement), (
            "Capability.matches_requirement is an async def again — "
            "calculate_match_score multiplies its return by a tier weight and "
            "will raise TypeError on every A2A match (#1973 re-opened)."
        )

    def test_matches_requirement_body_awaits_nothing(self):
        # Corroborates WHY sync is correct: the body delegates to the sync
        # llm_capability_match and has nothing to await. If a future edit adds
        # a real await here, this fails and forces a deliberate re-think of the
        # whole sync call chain rather than a silent async flip.
        source = inspect.getsource(Capability.matches_requirement)
        assert "await " not in source, (
            "matches_requirement now awaits something — the sync contract with "
            "calculate_match_score / _find_best_agents_for_task must be "
            "re-designed deliberately, not flipped."
        )

    def test_matches_requirement_returns_a_float(self, perfect_match):
        score = _cap("python").matches_requirement("write a python script")
        assert isinstance(score, float)
        assert score == 1.0


class TestCalculateMatchScoreTierWeights:
    """Deliverable (b): the 1.0 / 0.7 / 0.4 tiers survive and differentiate."""

    @pytest.mark.parametrize(
        "tier_field,weight",
        [
            ("primary_capabilities", 1.0),
            ("secondary_capabilities", 0.7),
            ("emerging_capabilities", 0.4),
        ],
    )
    def test_each_tier_applies_its_weight(self, perfect_match, tier_field, weight):
        card = _card("a1", **{tier_field: [_cap("python")]})
        # A fresh card has success_rate == 0.0 and insight_quality_score == 0.0,
        # so performance_modifier == 0.0 and final == avg_score * 0.7.
        expected = (1.0 * weight) * 0.7
        assert card.calculate_match_score(["write python"]) == pytest.approx(expected)

    def test_tiers_are_strictly_ordered(self, perfect_match):
        primary = _card("p", primary_capabilities=[_cap("python")])
        secondary = _card("s", secondary_capabilities=[_cap("python")])
        emerging = _card("e", emerging_capabilities=[_cap("python")])
        req = ["write python"]
        assert (
            primary.calculate_match_score(req)
            > secondary.calculate_match_score(req)
            > emerging.calculate_match_score(req)
        )

    def test_best_tier_wins_when_capability_appears_in_several(self, perfect_match):
        # calculate_match_score takes max() across all tiers per requirement, so
        # a card holding the capability in every tier scores the primary weight.
        card = _card(
            "a1",
            primary_capabilities=[_cap("python")],
            secondary_capabilities=[_cap("python")],
            emerging_capabilities=[_cap("python")],
        )
        assert card.calculate_match_score(["write python"]) == pytest.approx(0.7)

    def test_no_requirements_short_circuits_to_neutral(self):
        # The one path that never touched a capability, so it worked even while
        # the rest was broken. Pinned so the fix does not disturb it.
        assert _card("a1").calculate_match_score([]) == 0.5


class TestFindBestAgentsForTask:
    """Deliverable (a): the live path that raised on every non-empty task."""

    def test_ranks_agents_for_a_task_with_requirements(self, monkeypatch):
        import kaizen.llm.reasoning as reasoning

        # Deterministic judge: score 1.0 only when the requirement names the
        # capability, else 0.0. Exercises real differentiation, not a constant.
        def judge(*, capability_name, capability_description, requirement, **kw):
            return 1.0 if capability_name in requirement else 0.0

        monkeypatch.setattr(reasoning, "llm_capability_match", judge)

        node = A2ACoordinatorNode()
        node.agent_cards = {
            "py": _card("py", primary_capabilities=[_cap("python")]),
            "sql": _card("sql", primary_capabilities=[_cap("sql")]),
            "rust": _card("rust", secondary_capabilities=[_cap("python")]),
        }
        task = A2ATask(description="ship a python module", requirements=["python"])

        matches = node._find_best_agents_for_task(task)

        assert [agent_id for agent_id, _ in matches] == ["py", "rust", "sql"], (
            f"ranking is {matches!r}; expected primary-python > secondary-python "
            "> non-matching-sql."
        )
        assert matches[0][1] == pytest.approx(0.7)  # primary tier
        assert matches[1][1] == pytest.approx(0.49)  # secondary tier (0.7 * 0.7)
        assert matches[2][1] == 0.0  # no matching capability

    def test_returns_floats_not_coroutines(self, perfect_match):
        # The raise site verbatim: every score must be arithmetic-ready.
        node = A2ACoordinatorNode()
        node.agent_cards = {"py": _card("py", primary_capabilities=[_cap("python")])}
        task = A2ATask(description="d", requirements=["python"])
        for _agent_id, score in node._find_best_agents_for_task(task):
            assert isinstance(score, float)


class TestReasoningBridgesPreserveConfigPropagation:
    """Deliverable (d): the sync flip must not silently drop judge config.

    Both ``kaizen_agents`` bridges dispatch on
    ``inspect.iscoroutinefunction(matcher)`` and previously passed ``config`` /
    ``correlation_id`` on the async branch ONLY. With ``matches_requirement``
    now sync, the sync branch MUST carry the same kwargs — otherwise the judge
    silently falls back to ``.env`` defaults instead of the host agent's model.
    """

    def test_score_capability_sync_propagates_config_and_correlation_id(
        self, monkeypatch
    ):
        pytest.importorskip("kaizen_agents")
        import kaizen.llm.reasoning as reasoning
        from kaizen_agents.patterns._reasoning_bridge import score_capability_sync

        seen = {}

        def judge(**kw):
            seen.update(kw)
            return 1.0

        monkeypatch.setattr(reasoning, "llm_capability_match", judge)

        from kaizen.core.base_agent import BaseAgentConfig

        config = BaseAgentConfig(llm_provider="mock", model="mock-model")
        score = score_capability_sync(
            _cap("python"),
            "write python",
            reasoning_config=config,
            correlation_id="cid-1973",
        )

        assert score == 1.0
        assert seen.get("config") is config, (
            "the reasoning config was dropped on the sync matcher branch; the "
            "judge model silently falls back to .env defaults."
        )
        assert seen.get("correlation_id") == "cid-1973"

    def test_runtime_score_capability_propagates_config_and_correlation_id(
        self, monkeypatch
    ):
        pytest.importorskip("kaizen_agents")
        import asyncio

        import kaizen.llm.reasoning as reasoning
        from kaizen_agents.patterns.runtime import OrchestrationRuntime

        seen = {}

        def judge(**kw):
            seen.update(kw)
            return 1.0

        monkeypatch.setattr(reasoning, "llm_capability_match", judge)

        from kaizen.core.base_agent import BaseAgentConfig

        config = BaseAgentConfig(llm_provider="mock", model="mock-model")
        runtime = OrchestrationRuntime()
        score = asyncio.run(
            runtime._score_capability(
                _cap("python"), "write python", config, agent_id="a1"
            )
        )

        assert score == 1.0
        assert seen.get("config") is config
        assert seen.get("correlation_id") == "route_a1"

    def test_legacy_single_arg_sync_mocks_still_score(self, monkeypatch):
        # The bridges' TypeError fallback exists for legacy mocks with a
        # single-positional matcher. Passing kwargs on the sync branch must not
        # break them.
        pytest.importorskip("kaizen_agents")
        from kaizen_agents.patterns._reasoning_bridge import score_capability_sync

        class LegacyCap:
            def matches_requirement(self, requirement: str) -> float:
                return 0.42

        assert score_capability_sync(LegacyCap(), "anything") == pytest.approx(0.42)


class TestReasoningHelpersDoNotReportDegradedAsOk:
    """Third defect, found by walking the fix against a LIVE provider.

    With #1973's plumbing fixed, a real ``_find_best_agents_for_task`` call
    returned ``[('eng', 0.0), ('des', 0.0)]`` — every agent tied at zero. The
    LLM had actually reasoned correctly and emitted a 0.92 confidence score,
    but the provider returned prose and structured-output parsing failed, so
    the agent result was ``{'response': '<prose>', 'error': 'JSON_PARSE_FAILED'}``
    with NO ``match_score``. ``_coerce_float(None)`` yields 0.0, and the helper
    logged ``llm_capability_match.ok`` — reporting a fabricated zero as a
    successful match (``zero-tolerance.md`` Rule 3), and CACHING it so the
    transient failure became permanent for the process.

    #1981 SUPERSEDED the RETURN half of this contract: a degraded judgment now
    raises ``ReasoningDegradedError`` instead of returning a fabricated 0.0. A
    WARN line is not reachable by a caller, so 0.0 stayed indistinguishable
    from a genuine no-match and ranking stayed arbitrary — the very defect the
    paragraph above describes.

    What this class still pins is the OBSERVABILITY half: the degradation is
    loud (a ``*.degraded`` WARN carrying the underlying error) and is NOT
    cached, so a transient failure never becomes permanent for the process.
    Those assertions are the teeth of this class and are unchanged. The return
    contract now lives in ``test_issue_1981_reasoning_structured_output.py``.
    """

    @pytest.fixture
    def _clear_cache(self):
        from kaizen.llm.reasoning import _CACHE

        _CACHE._match_results.clear()
        _CACHE._similarity_results.clear()
        yield
        _CACHE._match_results.clear()
        _CACHE._similarity_results.clear()

    def _stub_agent(self, monkeypatch, getter_name, payload):
        import kaizen.llm.reasoning as reasoning

        class _Agent:
            def run(self, **kwargs):
                return payload

        monkeypatch.setattr(reasoning, getter_name, lambda cfg: _Agent())
        from kaizen.core.base_agent import BaseAgentConfig

        return BaseAgentConfig(llm_provider="mock", model="mock-model")

    def test_unparseable_capability_response_warns_and_is_not_cached(
        self, monkeypatch, caplog, _clear_cache
    ):
        from kaizen.llm.reasoning import (
            _CACHE,
            ReasoningDegradedError,
            llm_capability_match,
        )

        config = self._stub_agent(
            monkeypatch,
            "get_capability_match_agent",
            {
                "response": "## Confidence Score\n\n**0.92**",
                "error": "JSON_PARSE_FAILED",
            },
        )

        with caplog.at_level(logging.WARNING, logger="kaizen.llm.reasoning"):
            # #1981: the degradation is RAISED, not returned as a fake 0.0.
            with pytest.raises(ReasoningDegradedError):
                llm_capability_match(
                    capability_name="python",
                    capability_description="writes python",
                    requirement="build an API",
                    config=config,
                )

        degraded = [
            r
            for r in caplog.records
            if r.getMessage() == "llm_capability_match.degraded"
        ]
        assert degraded, (
            "the judge returned no match_score and the helper reported success — "
            "every capability silently ties at 0.0 and ranking becomes arbitrary."
        )
        assert getattr(degraded[0], "error", "") == "JSON_PARSE_FAILED"
        assert not _CACHE._match_results, (
            "a parse failure was cached; the transient degradation would pin 0.0 "
            "for this key for the rest of the process."
        )

    def test_missing_score_key_is_also_treated_as_degraded(
        self, monkeypatch, caplog, _clear_cache
    ):
        from kaizen.llm.reasoning import ReasoningDegradedError, llm_capability_match

        # No explicit "error" key — just an absent match_score. Still degraded.
        config = self._stub_agent(
            monkeypatch, "get_capability_match_agent", {"response": "some prose"}
        )
        with caplog.at_level(logging.WARNING, logger="kaizen.llm.reasoning"):
            # #1981: an absent match_score raises rather than fabricating 0.0.
            with pytest.raises(ReasoningDegradedError):
                llm_capability_match(
                    capability_name="python",
                    capability_description="writes python",
                    requirement="build an API",
                    config=config,
                )
        assert [
            r
            for r in caplog.records
            if r.getMessage() == "llm_capability_match.degraded"
        ]

    def test_valid_capability_response_still_caches_and_logs_ok(
        self, monkeypatch, caplog, _clear_cache
    ):
        from kaizen.llm.reasoning import _CACHE, llm_capability_match

        config = self._stub_agent(
            monkeypatch,
            "get_capability_match_agent",
            {"match_score": 0.92, "matches": True},
        )
        with caplog.at_level(logging.WARNING, logger="kaizen.llm.reasoning"):
            score = llm_capability_match(
                capability_name="python",
                capability_description="writes python",
                requirement="build an API",
                config=config,
            )

        assert score == pytest.approx(0.92)
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert _CACHE._match_results, "a valid result must still be cached"

    def test_similarity_sibling_has_the_same_guard(
        self, monkeypatch, caplog, _clear_cache
    ):
        # Multi-site parity: the two helpers share one failure shape and must
        # not drift (security.md § Multi-Site Kwarg Plumbing).
        from kaizen.llm.reasoning import (
            _CACHE,
            ReasoningDegradedError,
            llm_text_similarity,
        )

        config = self._stub_agent(
            monkeypatch, "get_text_similarity_agent", {"error": "JSON_PARSE_FAILED"}
        )
        with caplog.at_level(logging.WARNING, logger="kaizen.llm.reasoning"):
            # #1981: sibling parity — the similarity helper raises too.
            with pytest.raises(ReasoningDegradedError):
                llm_text_similarity(text_a="a", text_b="b", config=config)

        assert [
            r
            for r in caplog.records
            if r.getMessage() == "llm_text_similarity.degraded"
        ]
        assert not _CACHE._similarity_results


class TestSummarizeFallbackIsNotSilent:
    """Deliverable (e): the LLM-summary failure logs at WARN before degrading."""

    def test_llm_failure_emits_warning_and_still_falls_back(self, monkeypatch, caplog):
        from kaizen.nodes.ai.llm_agent import LLMAgentNode

        def boom(self, **kwargs):
            raise RuntimeError("provider exploded")

        monkeypatch.setattr(LLMAgentNode, "run", boom)

        node = A2AAgentNode()
        # Any non-"mock", non-None provider enters the LLM branch; the patched
        # run() raises before either value reaches a provider, so no real model
        # name is needed (env-models.md — never hardcode a provider model).
        node._current_provider = "openai"
        node._current_model = os.environ.get("KAIZEN_DEFAULT_MODEL", "test-model")
        shared_context = [
            {"agent_id": "a1", "content": "found a leak", "importance": 0.9, "tags": []}
        ]

        with caplog.at_level(logging.WARNING, logger="kaizen.nodes.ai.a2a"):
            summary = node._summarize_with_llm(shared_context)

        # The fallback itself is legitimate — it must still produce a summary.
        assert summary.startswith("Recent insights:")
        assert "a1" in summary

        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warnings, (
            "LLM summarization failed and the node fell back SILENTLY — "
            "zero-tolerance.md Rule 3 (no silent error hiding). Expected a WARN "
            "record naming the failure before the degraded path is taken."
        )
        record = warnings[0]
        assert record.getMessage() == "a2a.summarize.llm_failed"
        # Asserted on the STRUCTURED field, not caplog.text: observability.md
        # MUST NOT § "Unstructured f-string messages" requires the detail to
        # travel as a queryable field, so it is absent from the rendered text
        # by design.
        assert getattr(record, "error", "") == "provider exploded", (
            "the WARN record does not carry the underlying exception detail, so "
            "the failure is unactionable from logs alone."
        )
        assert getattr(record, "error_type", "") == "RuntimeError"

    def test_handler_survives_failure_before_model_is_bound(self, caplog):
        # Review finding on the defect-2 fix itself: `provider` and `model` were
        # bound INSIDE the try but referenced by the except handler, so a raise
        # between `try:` and the second assignment left `model` unbound and the
        # handler raised UnboundLocalError — converting the silent swallow into
        # a crash, strictly worse than the bug being fixed.
        #
        # This is the narrow, real window: `provider` binds, then `model` raises.
        class _RaisingModelNode(A2AAgentNode):
            @property
            def _current_model(self):
                raise RuntimeError("model attribute access exploded")

        node = _RaisingModelNode()
        node._current_provider = "openai"
        shared_context = [
            {"agent_id": "a3", "content": "partial bind", "importance": 0.7, "tags": []}
        ]

        with caplog.at_level(logging.WARNING, logger="kaizen.nodes.ai.a2a"):
            summary = node._summarize_with_llm(shared_context)

        assert summary.startswith("Recent insights:")
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warnings, (
            "the except handler raised instead of logging — `model` was unbound "
            "when the handler referenced it (UnboundLocalError)."
        )
        assert getattr(warnings[0], "error", "") == "model attribute access exploded"
        # `provider` bound before the raise, so its real value is reported.
        assert getattr(warnings[0], "provider", "<missing>") == "openai"

    def test_handler_survives_failure_before_provider_is_bound(self, caplog):
        # Widest case: the FIRST assignment raises, so both names are unbound.
        # This is the latent trap — the next person to add a statement between
        # `try:` and the assignments silently breaks the error path.
        class _RaisingProviderNode(A2AAgentNode):
            @property
            def _current_provider(self):
                raise RuntimeError("provider attribute access exploded")

        node = _RaisingProviderNode()
        shared_context = [
            {"agent_id": "a4", "content": "no bind", "importance": 0.6, "tags": []}
        ]

        with caplog.at_level(logging.WARNING, logger="kaizen.nodes.ai.a2a"):
            summary = node._summarize_with_llm(shared_context)

        assert summary.startswith("Recent insights:")
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warnings, (
            "the except handler raised instead of logging — neither `provider` "
            "nor `model` was bound when the handler referenced them."
        )
        assert getattr(warnings[0], "error", "") == "provider attribute access exploded"
        # Neither name was ever assigned a real value; the handler must still
        # report them (as None), not crash.
        assert getattr(warnings[0], "provider", "<missing>") is None
        assert getattr(warnings[0], "model", "<missing>") is None

    def test_mock_provider_still_skips_the_llm_branch_without_warning(self, caplog):
        # Behavior preservation: provider "mock"/None never enters the LLM
        # branch, so the honest simple-summary path must stay warning-free.
        node = A2AAgentNode()
        node._current_provider = "mock"
        shared_context = [
            {"agent_id": "a2", "content": "steady state", "importance": 0.5, "tags": []}
        ]

        with caplog.at_level(logging.WARNING, logger="kaizen.nodes.ai.a2a"):
            summary = node._summarize_with_llm(shared_context)

        assert summary.startswith("Recent insights:")
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
