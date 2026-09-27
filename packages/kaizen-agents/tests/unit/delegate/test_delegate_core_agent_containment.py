# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""#2227 Route C: ``Delegate.core_agent`` must not walk past a governance wrapper.

Route A (``WrapperBase.innermost``) and Route B (``PactEngine.governance_callback``)
were closed by the #2227 fix. ``Delegate.core_agent`` is a THIRD public accessor of
the same class, flagged but never measured by that lane because ``_loop_agent``
stacks differ from the hand-built governed stack.

Measured: it IS reachable. ``Delegate.__init__`` assigns
``self._loop_agent = L3GovernedAgent(self._loop_agent, envelope=...)`` when an
envelope is supplied, so ``core_agent``'s ``while hasattr(agent, "_inner")`` walk
started INSIDE the governed stack and handed back the raw ``_LoopAgent`` bridge::

    d = Delegate(model=..., envelope=env)
    d.wrapper_stack.run(_action=BLOCKED, prompt=...)   # GovernanceRejectedError
    d.core_agent.run(_action=BLOCKED, prompt=...)      # ran, envelope never consulted

The fix reuses the SAME contract Route A's fix introduced --
``WrapperBase._containment_boundary`` via ``WrapperBase.innermost`` -- rather than
adding a second traversal rule for the facade to keep in sync.
"""

from __future__ import annotations

from typing import Any

import pytest

from kailash.trust.envelope import ConstraintEnvelope, OperationalConstraint
from kailash.trust.readonly_proxy import ReadOnlyProxyError
from kaizen_agents.delegate.delegate import Delegate
from kaizen_agents.governed_agent import GovernanceRejectedError, _ProtectedInnerProxy

BLOCKED_ACTION = "delete_production_database"


class _FakeStreamEvent:
    def __init__(self, delta_text: str) -> None:
        self.event_type = "text_delta"
        self.delta_text = delta_text
        self.tool_calls = None
        self.usage = None
        self.finish_reason = None


class _FakeAdapter:
    """Records whether LLM egress was reached at all."""

    def __init__(self) -> None:
        self.calls: list[list[dict[str, Any]]] = []

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ):
        self.calls.append(messages)
        yield _FakeStreamEvent("ok")


def _blocking_envelope() -> ConstraintEnvelope:
    return ConstraintEnvelope(
        operational=OperationalConstraint(blocked_actions=(BLOCKED_ACTION,))
    )


@pytest.mark.regression
class TestCoreAgentContainment:
    """#2227 Route C -- the Delegate facade honours the containment boundary."""

    def test_subject_under_test_is_this_checkout(self) -> None:
        """Guard: the imported ``delegate`` must be THIS tree's, not another's.

        A bare ``pytest`` in a git worktree silently imports an installed or
        main-checkout copy, so a containment assertion can pass against code
        that never contained the fix -- a green that proves nothing. Compares
        repo-relative, so it holds in any checkout.
        """
        import pathlib

        from kaizen_agents.delegate import delegate as _delegate

        pkg_root = pathlib.Path(__file__).resolve().parents[3]  # kaizen-agents/
        subject = pathlib.Path(_delegate.__file__).resolve()
        assert subject.is_relative_to(pkg_root), (
            f"import leak: tests live under {pkg_root}, but delegate.py "
            f"resolved to {subject}"
        )

    def test_core_agent_stops_at_the_containment_boundary(self) -> None:
        """``core_agent`` must hand back the proxy, never the raw bridge."""
        d = Delegate(
            model="test-model", envelope=_blocking_envelope(), adapter=_FakeAdapter()
        )

        assert d._governed is not None, "envelope must put L3GovernedAgent in the stack"
        core = d.core_agent

        # The bypass, stated positively: core_agent used to BE the raw inner.
        assert core is not d._governed._inner
        assert isinstance(core, _ProtectedInnerProxy)
        # ...and it agrees with the sibling public accessor fixed in Route A.
        assert core is d.wrapper_stack.innermost

    def test_core_agent_cannot_execute_an_ungoverned_run(self) -> None:
        """The exact input the governed path REJECTS must not run via core_agent.

        This is the behavioural half. A structural type assertion alone would
        still pass if the proxy ever grew a runnable member.
        """
        adapter = _FakeAdapter()
        d = Delegate(model="test-model", envelope=_blocking_envelope(), adapter=adapter)

        # Control: the governed path genuinely refuses this input. Without this
        # the test below could pass against an inert envelope.
        with pytest.raises(GovernanceRejectedError):
            d.wrapper_stack.run(_action=BLOCKED_ACTION, prompt="do it")
        assert adapter.calls == [], "control: rejection must precede egress"

        # The route under test must not offer a way around that refusal.
        with pytest.raises((ReadOnlyProxyError, AttributeError)):
            d.core_agent.run(_action=BLOCKED_ACTION, prompt="do it")

        assert adapter.calls == [], "core_agent reached LLM egress ungoverned"

    def test_core_agent_proxy_denies_the_private_relink(self) -> None:
        """``core_agent._inner`` must not re-expose the raw agent (adversarial)."""
        d = Delegate(
            model="test-model", envelope=_blocking_envelope(), adapter=_FakeAdapter()
        )
        core = d.core_agent

        with pytest.raises((ReadOnlyProxyError, AttributeError)):
            _ = core._inner  # noqa: B018 -- intentional attribute access
        with pytest.raises((ReadOnlyProxyError, AttributeError)):
            _ = core.to_workflow_node()  # returns `self` -> a live raw handle

    def test_core_agent_stops_at_boundary_through_an_outer_wrapper(self) -> None:
        """Stacked case: a budget adds MonitoredAgent ABOVE the governed wrapper.

        The walk then starts one level higher, which is exactly the shape that
        defeated the issue's originally-prescribed ``innermost`` override.
        """
        d = Delegate(
            model="test-model",
            envelope=_blocking_envelope(),
            budget_usd=1.0,
            adapter=_FakeAdapter(),
        )
        if d._monitored is None:
            pytest.skip("MonitoredAgent unavailable (kaizen.providers.cost missing)")

        assert d.wrapper_stack is d._monitored
        assert isinstance(d.core_agent, _ProtectedInnerProxy)
        assert d.core_agent is d._governed._inner_proxy

    def test_ungoverned_delegate_still_exposes_the_loop_bridge(self) -> None:
        """No envelope => no boundary => documented behaviour is unchanged.

        Guards against over-fixing: the property's contract for an ungoverned
        Delegate is the ``_LoopAgent`` bridge, and callers depend on it.
        """
        d = Delegate(model="test-model", adapter=_FakeAdapter())

        assert d._governed is None
        core = d.core_agent
        assert not isinstance(core, _ProtectedInnerProxy)
        assert type(core).__name__ == "_LoopAgent"
        assert core is d.wrapper_stack
