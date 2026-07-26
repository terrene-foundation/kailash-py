# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests — #1981 second-order break at ``A2ACoordinatorNode.run()``.

#1981 made a degraded capability judgment fail LOUD:
``kaizen.llm.reasoning.llm_capability_match`` raises ``ReasoningDegradedError``
where it previously returned a fabricated ``0.0``, and
``A2ACoordinatorNode._find_best_agents_for_task`` re-raises an aggregate when
EVERY candidate card degraded (rather than emitting an all-zero ranking whose
"best" agent was decided by sort order).

That fix introduced a SECOND-ORDER break at the layer above it.
``A2ACoordinatorNode.run()`` is a Kailash node entry point whose docstring
promises::

    Raises:
        None - errors returned in result dictionary

and it contained ZERO ``try`` statements. Two of its dispatch branches reach
the new raise:

* ``action="delegate"``  -> ``_enhanced_delegate_task``  -> ``_find_best_agents_for_task``
* ``action="match_agents_to_task"`` -> ``_match_agents_to_task`` -> ``_find_best_agents_for_task``

so a total judge failure escaped ``run()`` and aborted the whole workflow
instead of returning a failed-step result the graph could route on.

What these tests pin
--------------------
1. Both raising branches return a result DICT instead of raising (the
   documented contract).
2. The degradation is NOT swallowed: the returned dict carries a dedicated
   ``degraded: True`` marker plus the error's ``helper`` / ``model`` /
   ``correlation_id``, and a WARN line is emitted. A degraded round therefore
   stays distinguishable from a genuine "no agent matched" — the same
   collision #1981 exists to eliminate, one layer up.
3. The catch is TYPED, not a blanket ``except Exception``: a non-degradation
   exception still propagates, so a genuine defect is never converted into a
   plausible-looking ``{"success": False}`` (``zero-tolerance.md`` Rule 3).
4. Non-regression: a partially-degraded round still succeeds and carries NO
   ``degraded`` marker.

Scoring is stubbed at ``kaizen.llm.reasoning.llm_capability_match`` so the
control flow is deterministic. These are STRUCTURAL assertions about the
error contract of a node's ``run()`` — no probe is required per
``probe-driven-verification.md`` Rule 3. The LLM's judgment is explicitly NOT
under test; the plumbing around its failure mode is.
"""

import logging

import pytest

from kaizen.llm.reasoning import ReasoningDegradedError
from kaizen.nodes.ai.a2a import (
    A2AAgentCard,
    A2ACoordinatorNode,
    A2ATask,
    Capability,
    CapabilityLevel,
    TaskState,
)

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _coordinator() -> A2ACoordinatorNode:
    node = A2ACoordinatorNode()
    node.agent_cards = {
        "eng": _card("eng", primary_capabilities=[_cap("python")]),
        "des": _card("des", primary_capabilities=[_cap("design")]),
    }
    node.registered_agents = {
        "eng": {"id": "eng", "skills": ["python"], "status": "available"},
        "des": {"id": "des", "skills": ["design"], "status": "available"},
    }
    return node


def _assignable_task() -> A2ATask:
    """A task that passes ``TaskValidator.validate_for_assignment``."""
    return A2ATask(
        name="api",
        description="build a python API",
        requirements=["build a python API"],
        state=TaskState.CREATED,
    )


def _degrade_judge(monkeypatch) -> None:
    """Every capability judgment degrades — the all-degraded #1981 round."""
    import kaizen.llm.reasoning as reasoning

    def _raise(**kwargs):
        raise ReasoningDegradedError(
            "llm_capability_match",
            model="test-model",
            correlation_id="cid-1981",
            error="JSON_PARSE_FAILED",
            raw_response="## Confidence Score\n\n**0.92**",
        )

    monkeypatch.setattr(reasoning, "llm_capability_match", _raise)


# ---------------------------------------------------------------------------
# 1. Both raising branches honour the documented dict contract
# ---------------------------------------------------------------------------


class TestRunReturnsInsteadOfRaising:
    """The docstring promise: ``errors returned in result dictionary``."""

    def test_match_agents_to_task_returns_degraded_result(self, monkeypatch):
        """Pre-fix: ``_find_best_agents_for_task``'s aggregate error escaped
        ``run()`` uncaught and aborted the workflow."""
        _degrade_judge(monkeypatch)

        result = _coordinator().run(
            action="match_agents_to_task",
            requirements=["build a python API"],
            context={},
        )

        assert isinstance(result, dict), (
            "run() raised instead of returning; a Kailash node's run() "
            "documents `errors returned in result dictionary` and an escaping "
            "exception aborts the whole workflow"
        )
        assert result["success"] is False
        assert result["degraded"] is True, (
            "the degradation must be VISIBLE in the returned dict — a bare "
            "`success: False` is indistinguishable from a genuine no-match"
        )

    def test_delegate_returns_degraded_result(self, monkeypatch):
        """The second reachable branch: ``delegate`` -> enhanced delegation."""
        _degrade_judge(monkeypatch)

        node = _coordinator()
        task = _assignable_task()
        node.active_tasks = {task.task_id: task}

        result = node.run(action="delegate", task_id=task.task_id, context={})

        assert isinstance(result, dict)
        assert result["success"] is False
        assert result["degraded"] is True

    def test_degraded_result_keeps_the_cycle_metadata_contract(self, monkeypatch):
        """The degraded path must produce a WELL-FORMED node result, not a
        truncated one — the cycle-aware post-processing still runs."""
        _degrade_judge(monkeypatch)

        result = _coordinator().run(
            action="match_agents_to_task",
            requirements=["build a python API"],
            context={},
        )

        assert "cycle_info" in result, (
            "the degraded branch skipped the cycle-aware post-processing, so "
            "the caller gets a result shape no other branch produces"
        )
        assert result["cycle_info"]["iteration"] == 0


# ---------------------------------------------------------------------------
# 2. Not a silent swallow
# ---------------------------------------------------------------------------


class TestDegradationIsObservableAndTyped:
    def test_returned_dict_carries_the_error_identity(self, monkeypatch):
        _degrade_judge(monkeypatch)

        result = _coordinator().run(
            action="match_agents_to_task",
            requirements=["build a python API"],
            context={},
        )

        assert result["degraded_helper"] == "a2a.find_best_agents", (
            "the aggregate error's helper must survive into the result dict; "
            "without it the caller cannot tell WHICH layer degraded"
        )
        assert result["degraded_model"] == "test-model"
        assert result["correlation_id"], "no correlation_id to join with the log line"
        assert "degraded" in result["error"].lower() or "no usable score" in (
            result["error"].lower()
        )

    def test_warn_line_is_emitted(self, monkeypatch, caplog):
        _degrade_judge(monkeypatch)

        with caplog.at_level(logging.WARNING, logger="kaizen.nodes.ai.a2a"):
            _coordinator().run(
                action="match_agents_to_task",
                requirements=["build a python API"],
                context={},
            )

        assert any(
            r.getMessage() == "a2a.coordinator.run.degraded" for r in caplog.records
        ), (
            "run() converted the degradation into a result dict with no WARN "
            "line — that is the silent swallow zero-tolerance Rule 3 blocks"
        )

    def test_genuine_failure_carries_no_degraded_marker(self):
        """Distinguishability, the whole point of #1981: an ordinary failed
        action must NOT look like a degraded judgment."""
        result = _coordinator().run(action="totally-unknown-action", context={})

        assert result["success"] is False
        assert "degraded" not in result, (
            "a plain failure was marked `degraded`, collapsing exactly the "
            "distinction #1981 exists to preserve"
        )

    def test_non_degradation_exception_still_propagates(self, monkeypatch):
        """The catch MUST be typed. A blanket `except Exception` would convert
        a genuine defect into a plausible-looking `{"success": False}`."""
        import kaizen.llm.reasoning as reasoning

        def _boom(**kwargs):
            raise RuntimeError("provider client exploded")

        monkeypatch.setattr(reasoning, "llm_capability_match", _boom)

        with pytest.raises(RuntimeError, match="provider client exploded"):
            _coordinator().run(
                action="match_agents_to_task",
                requirements=["build a python API"],
                context={},
            )


# ---------------------------------------------------------------------------
# 3. Non-regression — a partial degradation is not a failed round
# ---------------------------------------------------------------------------


class TestPartialDegradationStillSucceeds:
    def test_partially_degraded_round_matches_and_is_not_marked_degraded(
        self, monkeypatch
    ):
        import kaizen.llm.reasoning as reasoning

        def _judge(*, capability_name, capability_description, requirement, **kw):
            if capability_name == "design":
                raise ReasoningDegradedError(
                    "llm_capability_match",
                    model="test-model",
                    correlation_id="cid-1981",
                    error="JSON_PARSE_FAILED",
                )
            return 1.0

        monkeypatch.setattr(reasoning, "llm_capability_match", _judge)

        result = _coordinator().run(
            action="match_agents_to_task",
            requirements=["build a python API"],
            context={},
        )

        assert result["success"] is True
        assert "degraded" not in result
        assert [m["agent_id"] for m in result["matched_agents"]] == ["eng"], (
            "the card that COULD be scored must still be returned; a partial "
            "degradation must not sink the whole round"
        )

    def test_healthy_round_is_unaffected(self, monkeypatch):
        import kaizen.llm.reasoning as reasoning

        monkeypatch.setattr(reasoning, "llm_capability_match", lambda **kw: 1.0)

        result = _coordinator().run(
            action="match_agents_to_task",
            requirements=["build a python API"],
            context={},
        )

        assert result["success"] is True
        assert "degraded" not in result
        assert len(result["matched_agents"]) == 2
