# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""HIGH 4.8: BaseAgent security tests.

Verifies:
- Deferred MCP with mcp_servers=[] does not auto-connect
- Legacy/unknown kwargs don't crash BaseAgent.__init__
- Overriding deprecated extension points emits DeprecationWarning
"""

from __future__ import annotations

import warnings
from typing import Any

import pytest

from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubAgent(BaseAgent):
    """Minimal concrete agent for security tests."""

    def run(self, **inputs: Any) -> dict[str, Any]:
        return {"text": "stub"}

    async def run_async(self, **inputs: Any) -> dict[str, Any]:
        return {"text": "stub-async"}


# ---------------------------------------------------------------------------
# Deferred MCP: mcp_servers=[] prevents auto-connect
# ---------------------------------------------------------------------------


class TestDeferredMcpNoAutoConnect:
    """mcp_servers=[] must prevent any MCP auto-connection."""

    def test_empty_mcp_servers_list_no_autoconnect(self) -> None:
        """BaseAgent with mcp_servers=[] does not auto-connect to MCP servers."""
        config = BaseAgentConfig()
        agent = _StubAgent(config=config, mcp_servers=[])

        # mcp_servers=[] means no MCP connections configured
        mcp_servers = getattr(agent, "_mcp_servers", None)

        # The agent should have an empty list, not None (which triggers auto)
        assert mcp_servers is not None
        assert len(mcp_servers) == 0

    def test_mcp_servers_none_is_different_from_empty(self) -> None:
        """mcp_servers=None and mcp_servers=[] are semantically different.

        None = auto-connect to builtin MCP servers (if configured).
        [] = explicitly disable MCP.
        """
        config = BaseAgentConfig()

        agent_none = _StubAgent(config=config, mcp_servers=None)
        agent_empty = _StubAgent(config=config, mcp_servers=[])

        # Both should be constructable without error
        assert agent_none is not None
        assert agent_empty is not None

        # The empty list agent should have no MCP servers
        empty_servers = getattr(agent_empty, "_mcp_servers", None)
        assert empty_servers is not None
        assert len(empty_servers) == 0


# ---------------------------------------------------------------------------
# Legacy/unknown kwargs
# ---------------------------------------------------------------------------


class TestLegacyKwargsIgnored:
    """Unknown kwargs passed to BaseAgent.__init__ should not crash."""

    def test_unknown_kwargs_accepted(self) -> None:
        """Extra kwargs are passed through to Node.__init__ without crashing."""
        config = BaseAgentConfig()
        # These unknown kwargs should be absorbed by **kwargs -> Node.__init__
        agent = _StubAgent(
            config=config,
            mcp_servers=[],
            unknown_param="value",
            another_param=42,
        )
        assert agent is not None

    def test_agent_functional_with_extra_kwargs(self) -> None:
        """Agent still works correctly even with extra kwargs."""
        config = BaseAgentConfig()
        agent = _StubAgent(
            config=config,
            mcp_servers=[],
            legacy_flag=True,
        )
        result = agent.run()
        assert result == {"text": "stub"}


# ---------------------------------------------------------------------------
# Extension point deprecation
# ---------------------------------------------------------------------------


class TestExtensionShadowDeprecated:
    """Overriding deprecated extension points must emit DeprecationWarning."""

    def test_override_pre_execution_hook_warns(self) -> None:
        """Subclass overriding _pre_execution_hook emits DeprecationWarning."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")

            class _CustomAgent(BaseAgent):
                def _pre_execution_hook(self, **kwargs: Any) -> None:
                    pass

                def run(self, **inputs: Any) -> dict[str, Any]:
                    return {"text": "custom"}

                async def run_async(self, **inputs: Any) -> dict[str, Any]:
                    return {"text": "custom-async"}

        deprecation_warnings = [
            w for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) >= 1
        assert "_pre_execution_hook" in str(deprecation_warnings[0].message)
        assert "deprecated" in str(deprecation_warnings[0].message).lower()

    def test_override_post_execution_hook_warns(self) -> None:
        """Subclass overriding _post_execution_hook emits DeprecationWarning."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")

            class _PostHookAgent(BaseAgent):
                def _post_execution_hook(self, result: Any, **kwargs: Any) -> Any:
                    return result

                def run(self, **inputs: Any) -> dict[str, Any]:
                    return {"text": "post"}

                async def run_async(self, **inputs: Any) -> dict[str, Any]:
                    return {"text": "post-async"}

        deprecation_warnings = [
            w for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) >= 1
        assert "_post_execution_hook" in str(deprecation_warnings[0].message)

    def test_override_handle_error_warns(self) -> None:
        """Subclass overriding _handle_error emits DeprecationWarning."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")

            class _ErrorAgent(BaseAgent):
                def _handle_error(self, error: Exception, **kwargs: Any) -> Any:
                    return {"error": str(error)}

                def run(self, **inputs: Any) -> dict[str, Any]:
                    return {"text": "err"}

                async def run_async(self, **inputs: Any) -> dict[str, Any]:
                    return {"text": "err-async"}

        deprecation_warnings = [
            w for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) >= 1
        assert "_handle_error" in str(deprecation_warnings[0].message)

    def test_no_override_no_warning(self) -> None:
        """Subclass that does NOT override extension points emits no warning."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")

            class _CleanAgent(BaseAgent):
                def run(self, **inputs: Any) -> dict[str, Any]:
                    return {"text": "clean"}

                async def run_async(self, **inputs: Any) -> dict[str, Any]:
                    return {"text": "clean-async"}

        deprecation_warnings = [
            w
            for w in caught
            if issubclass(w.category, DeprecationWarning)
            and "extension point" in str(w.message).lower()
        ]
        assert len(deprecation_warnings) == 0
