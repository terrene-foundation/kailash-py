# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""MockGovernedAgent -- deterministic testing without LLM.

The MockGovernedAgent runs a scripted sequence of tool actions through
full PACT governance enforcement. This enables integration testing of
governance rules without requiring an LLM backend.

Usage::

    @governed_tool("read", cost=0.0)
    def tool_read() -> str:
        return "read_result"

    @governed_tool("write", cost=10.0)
    def tool_write() -> str:
        return "write_result"

    mock = MockGovernedAgent(
        engine=engine,
        role_address="D1-R1-T1-R1",
        tools=[tool_read, tool_write],
        script=["read", "write", "read"],
    )
    results = mock.run()  # ["read_result", "write_result", "read_result"]

Governance is fully enforced: blocked actions raise GovernanceBlockedError,
held actions raise GovernanceHeldError. The script execution stops at the
first governance error (fail-fast).
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from pact.governance.config import TrustPostureLevel
from pact.governance.agent import PactGovernedAgent
from pact.governance.engine import GovernanceEngine

logger = logging.getLogger(__name__)

__all__ = ["MockGovernedAgent"]


class MockGovernedAgent:
    """Governed agent that executes tools deterministically without LLM.

    Wraps PactGovernedAgent with a scripted execution sequence.
    Tools are auto-registered from their @governed_tool metadata.

    Args:
        engine: The GovernanceEngine for verification.
        role_address: The D/T/R positional address for the agent.
        tools: List of @governed_tool decorated callables.
        script: Ordered list of action names to execute.
        posture: Trust posture level. Defaults to SUPERVISED.
    """

    def __init__(
        self,
        engine: GovernanceEngine,
        role_address: str,
        tools: list[Callable[..., Any]],
        script: list[str],
        posture: TrustPostureLevel = TrustPostureLevel.SUPERVISED,
    ) -> None:
        self._governed = PactGovernedAgent(
            engine=engine,
            role_address=role_address,
            posture=posture,
        )
        self._script = script
        self._tools: dict[str, Callable[..., Any]] = {}

        # Auto-register tools from their @governed_tool metadata
        for tool in tools:
            if hasattr(tool, "_governance_action"):
                action_name: str = tool._governance_action
                cost: float = getattr(tool, "_governance_cost", 0.0)
                resource: str | None = getattr(tool, "_governance_resource", None)
                self._governed.register_tool(
                    action_name,
                    cost=cost,
                    resource=resource,
                )
                self._tools[action_name] = tool
            else:
                logger.warning(
                    "Tool %r does not have @governed_tool metadata -- skipping",
                    tool,
                )

    def run(self) -> list[Any]:
        """Execute the scripted sequence through governance enforcement.

        Runs each action in the script in order. Actions whose tool name
        does not match any registered tool are silently skipped (the tool
        is simply not available in this agent's toolkit).

        Actions that ARE registered but violate governance will raise
        GovernanceBlockedError or GovernanceHeldError (fail-fast).

        Returns:
            List of results from each successfully executed tool.

        Raises:
            GovernanceBlockedError: If any action is blocked by governance.
            GovernanceHeldError: If any action is held for approval.
        """
        results: list[Any] = []
        for action in self._script:
            tool = self._tools.get(action)
            if tool is None:
                # Tool not in this agent's toolkit -- skip
                logger.debug(
                    "Action '%s' has no matching tool in MockGovernedAgent -- skipping",
                    action,
                )
                continue
            result = self._governed.execute_tool(action, _tool_fn=tool)
            results.append(result)
        return results
