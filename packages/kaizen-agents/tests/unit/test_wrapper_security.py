# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""HIGH 3.10: Wrapper security threat tests (spec sections 11.1-11.6).

Verifies that composition wrappers enforce security boundaries:
- Inner agent bypass prevention (11.1)
- Posture poisoning prevention (11.2)
- Shadow mode detection (11.3)
- Stacking attack prevention (11.4)
- Stream backpressure handling (11.5)
- Governance bypass documentation (11.6)
"""

from __future__ import annotations

from typing import Any

import pytest

from kailash.trust.envelope import (
    AgentPosture,
    ConstraintEnvelope,
    OperationalConstraint,
)
from kailash.trust.readonly_proxy import ReadOnlyProxyError
from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen_agents.events import StreamBufferOverflow
from kaizen_agents.governed_agent import (
    GovernanceRejectedError,
    L3GovernedAgent,
    _ProtectedInnerProxy,
)
from kaizen_agents.monitored_agent import MonitoredAgent
from kaizen_agents.streaming_agent import StreamingAgent
from kaizen_agents.wrapper_base import DuplicateWrapperError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubAgent(BaseAgent):
    """Minimal concrete agent for security tests."""

    def run(self, **inputs: Any) -> dict[str, Any]:
        return {"text": "stub-result"}

    async def run_async(self, **inputs: Any) -> dict[str, Any]:
        return {"text": "stub-result-async"}


def _make_agent(**overrides: Any) -> _StubAgent:
    config = BaseAgentConfig(**overrides)
    return _StubAgent(config=config, mcp_servers=[])


def _make_envelope(
    *,
    posture_ceiling: str | None = None,
    blocked_actions: tuple[str, ...] = (),
) -> ConstraintEnvelope:
    operational = None
    if blocked_actions:
        operational = OperationalConstraint(blocked_actions=blocked_actions)
    return ConstraintEnvelope(
        posture_ceiling=posture_ceiling,
        operational=operational,
    )


# ---------------------------------------------------------------------------
# 11.1: Wrapper bypass via inner
# ---------------------------------------------------------------------------


class TestWrapperBypassViaInner:
    """Spec 11.1: Accessing governed_agent.inner._inner must raise AttributeError."""

    def test_governed_inner_proxy_blocks_inner_access(self) -> None:
        """Accessing .inner._inner on L3GovernedAgent raises AttributeError."""
        agent = _make_agent()
        envelope = _make_envelope(posture_ceiling="delegated")
        governed = L3GovernedAgent(agent, envelope, mcp_servers=[])

        # .inner returns a _ProtectedInnerProxy, not the real agent
        proxy = governed.inner
        with pytest.raises(AttributeError, match="Direct access to _inner is blocked"):
            _ = proxy._inner  # noqa: B018 -- intentional attribute access

    def test_governed_inner_proxy_blocks_the_real_handle(self) -> None:
        """#2224 sibling: the proxy blocked ``_inner`` and leaked ``_real_inner``.

        ``__getattr__`` is a FALLBACK, consulted only when normal lookup FAILS.
        The real agent was stored as ``_real_inner``, a plain instance
        attribute, so ``proxy._real_inner.run()`` resolved normally, never
        reached the guard, and ran the agent ungoverned. The guard blocked the
        name the attacker was expected to try while leaving the actual handle
        open.

        Distinct from ``TestGovernanceBypassViaDirectRun`` below: that is the
        documented Python limitation and needs an explicit
        ``object.__getattribute__`` call. This was plain attribute access.
        """
        agent = _make_agent()
        envelope = _make_envelope(posture_ceiling="delegated")
        governed = L3GovernedAgent(agent, envelope, mcp_servers=[])
        proxy = governed.inner

        for handle in ("_real_inner", "_target", "__dict__"):
            with pytest.raises(AttributeError):
                getattr(proxy, handle)

    def test_governed_inner_proxy_denies_by_default(self) -> None:
        """A name on no list at all -- proves default-deny, not a blocklist."""
        agent = _make_agent()
        envelope = _make_envelope()
        governed = L3GovernedAgent(agent, envelope, mcp_servers=[])

        with pytest.raises(AttributeError, match="restricted"):
            governed.inner.never_heard_of_this  # noqa: B018

    def test_governed_inner_proxy_blocks_run(self) -> None:
        """Cannot call run() through the inner proxy."""
        agent = _make_agent()
        envelope = _make_envelope()
        governed = L3GovernedAgent(agent, envelope, mcp_servers=[])

        with pytest.raises(AttributeError, match="restricted"):
            governed.inner.run()

    def test_governed_inner_proxy_blocks_run_async(self) -> None:
        """Cannot call run_async() through the inner proxy."""
        agent = _make_agent()
        envelope = _make_envelope()
        governed = L3GovernedAgent(agent, envelope, mcp_servers=[])

        with pytest.raises(AttributeError, match="restricted"):
            governed.inner.run_async()

    def test_governed_inner_proxy_allows_safe_attrs(self) -> None:
        """Safe read-only attributes are accessible through the proxy."""
        agent = _make_agent()
        envelope = _make_envelope()
        governed = L3GovernedAgent(agent, envelope, mcp_servers=[])

        # These should not raise
        _ = governed.inner.config
        _ = governed.inner.signature
        _ = governed.inner.get_parameters

    def test_governed_inner_proxy_blocks_setattr(self) -> None:
        """Cannot modify attributes on the inner proxy."""
        agent = _make_agent()
        envelope = _make_envelope()
        governed = L3GovernedAgent(agent, envelope, mcp_servers=[])

        with pytest.raises(AttributeError, match="Cannot modify"):
            governed.inner.config = "hacked"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 11.2: Posture poisoning
# ---------------------------------------------------------------------------


class TestPosturePoisoning:
    """Spec 11.2: Cannot set posture higher than ceiling after construction."""

    def test_posture_clamped_to_ceiling(self) -> None:
        """Posture is clamped to the envelope ceiling at construction time."""
        agent = _make_agent()
        # Ceiling is SUPERVISED, requested posture is AUTONOMOUS (above)
        envelope = _make_envelope(posture_ceiling="supervised")
        governed = L3GovernedAgent(
            agent,
            envelope,
            posture=AgentPosture.AUTONOMOUS,
            mcp_servers=[],
        )

        # Posture should be clamped down to SUPERVISED
        assert governed.posture == AgentPosture.SUPERVISED

    def test_posture_below_ceiling_preserved(self) -> None:
        """Posture below the ceiling is preserved unchanged."""
        agent = _make_agent()
        envelope = _make_envelope(posture_ceiling="delegated")
        governed = L3GovernedAgent(
            agent,
            envelope,
            posture=AgentPosture.SUPERVISED,
            mcp_servers=[],
        )

        assert governed.posture == AgentPosture.SUPERVISED

    def test_posture_at_ceiling_preserved(self) -> None:
        """Posture exactly at the ceiling is preserved."""
        agent = _make_agent()
        envelope = _make_envelope(posture_ceiling="tool")
        governed = L3GovernedAgent(
            agent,
            envelope,
            posture=AgentPosture.TOOL,
            mcp_servers=[],
        )

        assert governed.posture == AgentPosture.TOOL

    def test_envelope_is_frozen_after_construction(self) -> None:
        """The constraint envelope is frozen (immutable) after construction."""
        agent = _make_agent()
        envelope = _make_envelope(posture_ceiling="supervised")
        governed = L3GovernedAgent(agent, envelope, mcp_servers=[])

        # ConstraintEnvelope is a frozen dataclass -- cannot mutate
        with pytest.raises(AttributeError):
            governed.envelope.posture_ceiling = "delegated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 11.3: Shadow mode detection
# ---------------------------------------------------------------------------


class TestShadowModeDetection:
    """Spec 11.3: A wrapper that doesn't call _inner is detectable via _inner_called."""

    def test_inner_called_flag_initially_false(self) -> None:
        """_inner_called is False before any execution."""
        agent = _make_agent()
        wrapper = MonitoredAgent(agent, mcp_servers=[])
        assert wrapper._inner_called is False

    def test_inner_called_flag_set_after_run(self) -> None:
        """_inner_called is True after run()."""
        agent = _make_agent()
        wrapper = MonitoredAgent(agent, mcp_servers=[])
        wrapper.run()
        assert wrapper._inner_called is True

    @pytest.mark.asyncio
    async def test_inner_called_flag_set_after_run_async(self) -> None:
        """_inner_called is True after run_async()."""
        agent = _make_agent()
        wrapper = MonitoredAgent(agent, mcp_servers=[])
        await wrapper.run_async()
        assert wrapper._inner_called is True

    def test_governance_rejection_does_not_set_inner_called(self) -> None:
        """_inner_called stays False when governance rejects the request."""
        agent = _make_agent()
        envelope = _make_envelope(blocked_actions=("dangerous_action",))
        governed = L3GovernedAgent(agent, envelope, mcp_servers=[])

        with pytest.raises(GovernanceRejectedError):
            governed.run(_action="dangerous_action")

        assert governed._inner_called is False


# ---------------------------------------------------------------------------
# 11.4: Stacking attack
# ---------------------------------------------------------------------------


class TestStackingAttack:
    """Spec 11.4: Duplicate wrapper types are rejected."""

    def test_duplicate_wrapper_rejected(self) -> None:
        """Applying the same wrapper type twice raises DuplicateWrapperError."""
        agent = _make_agent()
        monitored = MonitoredAgent(agent, mcp_servers=[])

        with pytest.raises(DuplicateWrapperError, match="MonitoredAgent"):
            MonitoredAgent(monitored, mcp_servers=[])

    def test_duplicate_governed_rejected(self) -> None:
        """Applying L3GovernedAgent twice raises DuplicateWrapperError."""
        agent = _make_agent()
        envelope = _make_envelope()
        governed = L3GovernedAgent(agent, envelope, mcp_servers=[])

        with pytest.raises(DuplicateWrapperError, match="L3GovernedAgent"):
            L3GovernedAgent(governed, envelope, mcp_servers=[])

    def test_canonical_stack_order_enforced(self) -> None:
        """Wrappers applied out of canonical order are rejected."""
        agent = _make_agent()
        # Canonical: BaseAgent -> Governed -> Monitored -> Streaming
        # Applying Governed on top of Monitored violates the order
        monitored = MonitoredAgent(agent, mcp_servers=[])
        envelope = _make_envelope()

        from kaizen_agents.wrapper_base import WrapperOrderError

        with pytest.raises(WrapperOrderError, match="Cannot apply"):
            L3GovernedAgent(monitored, envelope, mcp_servers=[])

    def test_valid_stack_order_accepted(self) -> None:
        """Canonical stack order is accepted.

        This test previously closed with ``assert streaming.innermost is agent``
        -- using identity with the raw agent as a cheap proxy for "all three
        wrappers constructed without error". That assertion was ALSO, silently,
        the only thing in the suite pinning ``innermost``'s containment
        behaviour, and what it pinned was the bypass: reaching the raw agent
        past a governance wrapper (#2227 Route A). It now asserts what it was
        actually written to check -- that the stack builds -- and the
        containment contract is asserted explicitly in
        ``TestInnermostContainment`` below.
        """
        agent = _make_agent()
        envelope = _make_envelope()

        governed = L3GovernedAgent(agent, envelope, mcp_servers=[])
        monitored = MonitoredAgent(governed, mcp_servers=[])
        streaming = StreamingAgent(monitored, mcp_servers=[])

        # All wrappers constructed without error, in the canonical order.
        assert streaming.inner is monitored
        assert monitored.inner is governed
        assert governed.envelope is envelope


class TestInnermostContainment:
    """#2227 Route A: ``innermost`` must not walk past a governance wrapper.

    ``L3GovernedAgent`` overrides ``inner`` to return a ``_ProtectedInnerProxy``
    but ``innermost`` is defined on ``WrapperBase`` and walked the private
    ``_inner`` chain, so it returned the raw agent and
    ``governed.innermost.run(...)`` executed with no governance evaluation at
    all -- going AROUND the proxy rather than through it, which is why the
    #2224 proxy work could not close it.

    Both poles are asserted throughout: the attack must fail AND the legitimate
    use of ``innermost`` (resolving the base agent's config, which is what
    StreamingAgent needs it for) must keep working.
    """

    def test_innermost_returns_proxy_not_raw_agent(self) -> None:
        """Direct case: governed.innermost is the proxy, not the raw agent."""
        agent = _make_agent()
        governed = L3GovernedAgent(agent, _make_envelope(), mcp_servers=[])

        assert governed.innermost is not agent
        assert isinstance(governed.innermost, _ProtectedInnerProxy)

    def test_innermost_through_full_stack_stops_at_governance(self) -> None:
        """Stacked case: the walk starts outermost and must still stop.

        This is the case an override on ``L3GovernedAgent.innermost`` would
        NOT have fixed -- the walk begins at StreamingAgent and never consults
        an intermediate wrapper's own ``innermost``.
        """
        agent = _make_agent()
        governed = L3GovernedAgent(agent, _make_envelope(), mcp_servers=[])
        monitored = MonitoredAgent(governed, mcp_servers=[])
        streaming = StreamingAgent(monitored, mcp_servers=[])

        for wrapper in (streaming, monitored, governed):
            assert wrapper.innermost is not agent
            assert isinstance(wrapper.innermost, _ProtectedInnerProxy)

    def test_innermost_cannot_run_ungoverned(self) -> None:
        """The concrete bypass: innermost.run() must be denied."""
        agent = _make_agent()
        streaming = StreamingAgent(
            MonitoredAgent(
                L3GovernedAgent(agent, _make_envelope(), mcp_servers=[]),
                mcp_servers=[],
            ),
            mcp_servers=[],
        )

        with pytest.raises(ReadOnlyProxyError):
            streaming.innermost.run(query="bypass")
        with pytest.raises(ReadOnlyProxyError):
            streaming.innermost.run_async(query="bypass")

    def test_innermost_still_serves_legitimate_config_reads(self) -> None:
        """Opposite pole: the reason innermost exists must keep working.

        StreamingAgent resolves the model/sampling config from the innermost
        agent. Returning the proxy (rather than raising) is what keeps that
        working while denying execution.
        """
        agent = _make_agent()
        governed = L3GovernedAgent(agent, _make_envelope(), mcp_servers=[])

        assert governed.innermost.config is agent.config
        assert governed.innermost.signature is agent.signature
        assert governed.innermost.get_parameters() == agent.get_parameters()

    def test_ungoverned_stack_innermost_unchanged(self) -> None:
        """Opposite pole: with no governance wrapper, nothing changes.

        Without this, the fix would be indistinguishable from "innermost is
        broken for everyone".
        """
        agent = _make_agent()
        monitored = MonitoredAgent(agent, mcp_servers=[])
        streaming = StreamingAgent(monitored, mcp_servers=[])

        assert monitored.innermost is agent
        assert streaming.innermost is agent
        assert streaming.innermost.run(query="ok") is not None


class TestProxyMemberReturnValueContainment:
    """#2227 HIGH-1: an allowlisted member must not RETURN a runnable handle.

    Gating the NAME and stripping the bound method's ``__self__`` is not enough:
    ``to_workflow_node`` was ``def to_workflow_node(self): return self``, so
    ``governed.inner.to_workflow_node()`` handed back the raw agent and
    ``.run()`` on it executed ungoverned -- and, through the innermost boundary
    the #2227 fix added, ``streaming.innermost.to_workflow_node().run(...)`` did
    too. Same class as #2226: an allowlisted member returns a live handle to the
    target. The prior ``__self__`` test never CALLED the member, so it missed
    this. These tests CALL every allowlisted member and assert the result is
    neither the raw agent nor runnable.
    """

    def test_to_workflow_node_is_not_reachable_through_the_proxy(self) -> None:
        """The removed member must now be DENIED, not merely stripped."""
        agent = _make_agent()
        governed = L3GovernedAgent(agent, _make_envelope(), mcp_servers=[])

        with pytest.raises(AttributeError):
            governed.inner.to_workflow_node()

    def test_to_workflow_is_not_reachable_through_the_proxy(self) -> None:
        """to_workflow builds an LLM-executing workflow with ungoverned threaded."""
        agent = _make_agent()
        governed = L3GovernedAgent(agent, _make_envelope(), mcp_servers=[])

        with pytest.raises(AttributeError):
            governed.inner.to_workflow()

    def test_to_workflow_node_bypass_via_innermost_is_closed(self) -> None:
        """The stacked route the #2227 innermost fix opened must also be closed."""
        agent = _make_agent()
        streaming = StreamingAgent(
            MonitoredAgent(
                L3GovernedAgent(agent, _make_envelope(), mcp_servers=[]),
                mcp_servers=[],
            ),
            mcp_servers=[],
        )

        with pytest.raises(AttributeError):
            streaming.innermost.to_workflow_node()

    def test_no_allowlisted_member_returns_a_live_agent_handle(self) -> None:
        """Anti-staleness: CALL every allowlisted member; none may return the
        raw agent or anything runnable.

        Walks ``_ProtectedInnerProxy._ALLOWED_ATTRS`` itself, so a NEW entry
        that returns a live handle fails here -- the gap the __self__-only test
        left open. ``config``/``signature`` are data; ``get_parameters`` returns
        a params dict; a member returning the raw agent, or an object exposing
        ``run``/``run_async``, is the escape hatch.
        """
        agent = _make_agent()
        governed = L3GovernedAgent(agent, _make_envelope(), mcp_servers=[])
        proxy = governed.inner

        leaks: list[str] = []
        for name in sorted(_ProtectedInnerProxy._ALLOWED_ATTRS):
            member = getattr(proxy, name)
            result = member() if callable(member) else member
            if result is agent:
                leaks.append(f"{name} -> returned the raw agent")
                continue
            # An LLM-executing / runnable artifact reachable from a read-only
            # proxy is the HIGH-1 class even when it is not the agent object.
            if hasattr(result, "run") and hasattr(result, "run_async"):
                leaks.append(f"{name} -> returned a runnable ({type(result).__name__})")

        assert leaks == [], (
            f"_ProtectedInnerProxy allowlisted members returning a live/runnable "
            f"handle to the ungoverned agent (#2227 HIGH-1): {leaks}"
        )


# ---------------------------------------------------------------------------
# 11.5: Stream backpressure
# ---------------------------------------------------------------------------


class TestStreamBackpressure:
    """Spec 11.5: Buffer overflow is properly handled and reported."""

    @pytest.mark.asyncio
    async def test_buffer_overflow_emits_event(self) -> None:
        """When buffer overflows, a StreamBufferOverflow event is emitted."""

        class _VerboseAgent(BaseAgent):
            """Agent that returns many tool calls to trigger buffer overflow."""

            def run(self, **inputs: Any) -> dict[str, Any]:
                return {"text": "verbose"}

            async def run_async(self, **inputs: Any) -> dict[str, Any]:
                # Return enough tool_calls to exceed buffer_size=2
                return {
                    "text": "result",
                    "tool_calls": [
                        {"id": f"call_{i}", "function": {"name": f"tool_{i}"}}
                        for i in range(10)
                    ],
                }

        agent = _VerboseAgent(config=BaseAgentConfig(), mcp_servers=[])
        # Very small buffer to trigger overflow during batch fallback
        streaming = StreamingAgent(agent, buffer_size=2, mcp_servers=[])

        events = []
        async for event in streaming.run_stream():
            events.append(event)

        overflow_events = [e for e in events if isinstance(e, StreamBufferOverflow)]
        assert len(overflow_events) >= 1
        assert overflow_events[0].dropped_count > 0

    def test_stream_buffer_overflow_event_fields(self) -> None:
        """StreamBufferOverflow event carries dropped_count and oldest_timestamp."""
        event = StreamBufferOverflow(dropped_count=5, oldest_timestamp=123.456)
        assert event.dropped_count == 5
        assert event.oldest_timestamp == 123.456
        assert event.event_type == "stream_buffer_overflow"


# ---------------------------------------------------------------------------
# 11.6: Governance bypass via direct run
# ---------------------------------------------------------------------------


class TestGovernanceBypassViaDirectRun:
    """Spec 11.6: Document Python limitation on object.__getattribute__ bypass.

    This is a documented Python language limitation: any Python wrapper can
    be bypassed via object.__getattribute__. The L3GovernedAgent's
    _ProtectedInnerProxy mitigates the .inner._inner path but cannot prevent
    direct CPython introspection.
    """

    def test_object_getattribute_bypass_documented(self) -> None:
        """Demonstrate that object.__getattribute__ can reach _inner.

        This test documents the Python limitation. The governed agent
        protects the .inner property path but cannot block CPython-level
        attribute resolution on the wrapper itself.
        """
        agent = _make_agent()
        envelope = _make_envelope(blocked_actions=("forbidden",))
        governed = L3GovernedAgent(agent, envelope, mcp_servers=[])

        # The governed wrapper stores _inner as an instance attribute
        # for WrapperBase. object.__getattribute__ bypasses @property.
        raw_inner = object.__getattribute__(governed, "_inner")

        # This IS the raw inner agent (not the proxy)
        assert isinstance(raw_inner, BaseAgent)

        # Calling run() on it bypasses governance -- documented limitation
        result = raw_inner.run()
        assert result == {"text": "stub-result"}


class TestProxiesDoNotHandBackTheirTarget:
    """#2224 redteam: gating attribute NAMES is not enough.

    ``getattr(target, "allowed_method")`` returns a BOUND method, and
    ``__self__`` is the target -- so an allowlisted method leaked the agent in
    two plain attribute reads, without touching a single denied name.
    """

    def test_protected_inner_proxy_returns_no_bound_method(self) -> None:
        agent = _make_agent()
        envelope = _make_envelope()
        governed = L3GovernedAgent(agent, envelope, mcp_servers=[])
        proxy = governed.inner

        for name in sorted(_ProtectedInnerProxy._ALLOWED_ATTRS):
            member = getattr(proxy, name)
            assert (
                getattr(member, "__self__", None) is not agent
            ), f"'{name}' hands back the raw agent via __self__"

    def test_protected_inner_proxy_slot_is_sealed(self) -> None:
        from kailash.trust.readonly_proxy import ReadOnlyProxyError

        agent = _make_agent()
        envelope = _make_envelope()
        governed = L3GovernedAgent(agent, envelope, mcp_servers=[])
        proxy = governed.inner

        sealed = super(_ProtectedInnerProxy, proxy)._target
        assert sealed is not agent
        with pytest.raises(ReadOnlyProxyError):
            sealed("not-the-token")

    def test_protected_inner_proxy_cannot_be_reinitialised(self) -> None:
        agent = _make_agent()
        envelope = _make_envelope()
        governed = L3GovernedAgent(agent, envelope, mcp_servers=[])
        proxy = governed.inner

        with pytest.raises(AttributeError, match="already initialised"):
            type(proxy).__init__(proxy, agent)
