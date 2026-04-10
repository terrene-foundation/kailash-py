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


class TestUnknownKwargsRejected:
    """SPEC-04 §10.2: Unknown kwargs MUST be rejected (no catch-all)."""

    def test_unknown_kwargs_raise_type_error(self) -> None:
        """Extra kwargs cause TypeError — the **kwargs catch-all is gone."""
        config = BaseAgentConfig()
        with pytest.raises(TypeError):
            _StubAgent(
                config=config,
                mcp_servers=[],
                unknown_param="value",
                another_param=42,
            )

    def test_known_kwargs_still_accepted(self) -> None:
        """Valid params continue to work."""
        config = BaseAgentConfig()
        agent = _StubAgent(config=config, mcp_servers=[])
        result = agent.run()
        assert result == {"text": "stub"}


# ---------------------------------------------------------------------------
# Extension point deprecation
# ---------------------------------------------------------------------------


class TestExtensionPointOverrides:
    """Subclass extension point overrides work via normal MRO."""

    def test_override_pre_execution_hook_works(self) -> None:
        """Subclass overriding _pre_execution_hook takes effect via MRO."""

        class _CustomAgent(BaseAgent):
            def _pre_execution_hook(self, inputs: Any) -> Any:
                inputs["custom"] = True
                return inputs

        agent = _CustomAgent(config=BaseAgentConfig(), mcp_servers=[])
        result = agent._pre_execution_hook({"key": "val"})
        assert result["custom"] is True

    def test_override_post_execution_hook_works(self) -> None:
        """Subclass overriding _post_execution_hook takes effect via MRO."""

        class _PostHookAgent(BaseAgent):
            def _post_execution_hook(self, result: Any) -> Any:
                result["hooked"] = True
                return result

        agent = _PostHookAgent(config=BaseAgentConfig(), mcp_servers=[])
        result = agent._post_execution_hook({"text": "ok"})
        assert result["hooked"] is True

    def test_override_handle_error_works(self) -> None:
        """Subclass overriding _handle_error takes effect via MRO."""

        class _ErrorAgent(BaseAgent):
            def _handle_error(self, error: Exception, context: Any) -> Any:
                return {"custom_error": str(error)}

        agent = _ErrorAgent(config=BaseAgentConfig(), mcp_servers=[])
        result = agent._handle_error(ValueError("test"), {})
        assert result["custom_error"] == "test"

    def test_no_override_uses_default(self) -> None:
        """Without override, the base implementation runs."""

        class _CleanAgent(BaseAgent):
            pass

        agent = _CleanAgent(config=BaseAgentConfig(), mcp_servers=[])
        result = agent._pre_execution_hook({"key": "val"})
        assert result["key"] == "val"

    def test_no_deprecation_warnings_on_subclass(self) -> None:
        """Subclassing with overrides should NOT emit deprecation warnings."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")

            class _Agent(BaseAgent):
                def _pre_execution_hook(self, inputs: Any) -> Any:
                    return inputs

        deprecation_warnings = [
            w
            for w in caught
            if issubclass(w.category, DeprecationWarning)
            and "extension point" in str(w.message).lower()
        ]
        assert len(deprecation_warnings) == 0
