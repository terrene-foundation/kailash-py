"""Non-interactive print mode for the kz CLI.

Executes a single prompt and writes the result to stdout, then exits.
Supports plain text output and JSON output modes.
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from typing import Any

from kaizen_agents.delegate.config.loader import KzConfig
from kaizen_agents.delegate.loop import AgentLoop, ToolRegistry


@dataclass
class PrintResult:
    """Result of a single print-mode execution."""

    result: str = ""
    is_error: bool = False
    error_message: str = ""
    tools_used: list[str] = field(default_factory=list)
    tokens: dict[str, int] = field(default_factory=dict)
    cost: float = 0.0


class PrintRunner:
    """Runs a single prompt in non-interactive mode.

    Parameters
    ----------
    config:
        Resolved kz configuration.
    tools:
        Tool registry for the agent.
    client:
        Optional AsyncOpenAI client override (for testing).
    max_turns:
        Override the config max_turns for this run.
    """

    def __init__(
        self,
        config: KzConfig,
        tools: ToolRegistry,
        *,
        client: Any = None,
        max_turns: int | None = None,
    ) -> None:
        if max_turns is not None:
            config = KzConfig(
                model=config.model,
                provider=config.provider,
                effort_level=config.effort_level,
                max_turns=max_turns,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                tools_allow=config.tools_allow,
                tools_deny=config.tools_deny,
                ignore_patterns=config.ignore_patterns,
                loaded_from=config.loaded_from,
            )
        self._config = config
        self._loop = AgentLoop(config=config, tools=tools, client=client)

    async def run(self, prompt: str) -> PrintResult:
        """Run a single prompt and return the result.

        Parameters
        ----------
        prompt:
            The user's prompt.

        Returns
        -------
        PrintResult with the response text and metadata.
        """
        if not prompt or not prompt.strip():
            return PrintResult(is_error=True, error_message="Empty prompt")

        try:
            full_text = ""
            async for chunk in self._loop.run_turn(prompt):
                full_text += chunk
        except Exception as exc:
            return PrintResult(is_error=True, error_message=str(exc))

        tools_used = self._extract_tools_used()
        usage = self._loop.usage

        return PrintResult(
            result=full_text,
            tools_used=tools_used,
            tokens={
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            },
        )

    def _extract_tools_used(self) -> list[str]:
        """Extract unique tool names from the conversation history."""
        seen: list[str] = []
        seen_set: set[str] = set()
        for msg in self._loop.conversation.messages:
            if msg.get("role") == "assistant":
                for tc in msg.get("tool_calls", []):
                    name = tc.get("function", {}).get("name", "")
                    if name and name not in seen_set:
                        seen.append(name)
                        seen_set.add(name)
        return seen

    def format_text(self, result: PrintResult) -> str:
        """Format a PrintResult as plain text."""
        if result.is_error:
            return f"Error: {result.error_message}\n"
        text = result.result
        if not text.endswith("\n"):
            text += "\n"
        return text

    def format_json(self, result: PrintResult) -> str:
        """Format a PrintResult as JSON."""
        data: dict[str, Any] = {
            "result": result.result,
            "tools_used": result.tools_used,
            "tokens": result.tokens,
            "cost": result.cost,
        }
        if result.is_error:
            data["error"] = result.error_message
        return json.dumps(data)


def read_prompt(cli_arg: str | None) -> str | None:
    """Read the prompt from CLI arg or stdin.

    Parameters
    ----------
    cli_arg:
        If provided, use this as the prompt.

    Returns
    -------
    The prompt string, or None if no input is available.
    """
    if cli_arg is not None:
        return cli_arg

    if sys.stdin.isatty():
        return None

    content = sys.stdin.read().strip()
    return content if content else None


async def run_print_mode(
    config: KzConfig,
    tools: ToolRegistry,
    prompt: str,
    *,
    json_output: bool = False,
    client: Any = None,
) -> int:
    """Run print mode and write output to stdout.

    Parameters
    ----------
    config:
        Resolved kz configuration.
    tools:
        Tool registry.
    prompt:
        The user's prompt.
    json_output:
        If True, output JSON instead of plain text.
    client:
        Optional AsyncOpenAI client override.

    Returns
    -------
    Exit code: 0 for success, 1 for error.
    """
    runner = PrintRunner(config=config, tools=tools, client=client)
    result = await runner.run(prompt)

    if json_output:
        sys.stdout.write(runner.format_json(result) + "\n")
    else:
        sys.stdout.write(runner.format_text(result))

    return 1 if result.is_error else 0
