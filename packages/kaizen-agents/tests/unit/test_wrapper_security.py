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

from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kailash.trust.envelope import (
    AgentPosture,
    ConstraintEnvelope,
    OperationalConstraint,
)
from kaizen_agents.events import StreamBufferOverflow
from kaizen_agents.governed_agent import GovernanceRejectedError, L3GovernedAgent
from kaizen_agents.monitored_agent import MonitoredAgent
from kaizen_agents.streaming_agent import StreamingAgent
from kaizen_agents.wrapper_base import DuplicateWrapperError, WrapperBase


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
        # Ceiling is SUPERVISED, requested posture is DELEGATED
        envelope = _make_envelope(posture_ceiling="supervised")
        governed = L3GovernedAgent(
            agent,
            envelope,
            posture=AgentPosture.DELEGATED,
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
        envelope = _make_envelope(posture_ceiling="shared_planning")
        governed = L3GovernedAgent(
            agent,
            envelope,
            posture=AgentPosture.SHARED_PLANNING,
            mcp_servers=[],
        )

        assert governed.posture == AgentPosture.SHARED_PLANNING

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
        """Canonical stack order is accepted."""
        agent = _make_agent()
        envelope = _make_envelope()

        governed = L3GovernedAgent(agent, envelope, mcp_servers=[])
        monitored = MonitoredAgent(governed, mcp_servers=[])
        streaming = StreamingAgent(monitored, mcp_servers=[])

        # All wrappers constructed without error
        assert streaming.innermost is agent


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
