"""
ReActAgent - Production-Ready Reasoning + Acting Agent

Zero-config usage:
    from kaizen.agents import ReActAgent

    agent = ReActAgent()
    result = agent.run(task="Book a flight to Paris")
    print(result["thought"])
    print(result["action"])
    print(f"Confidence: {result['confidence']}")

Progressive configuration:
    agent = ReActAgent(
        llm_provider="openai",
        model="gpt-4",
        temperature=0.1,
        max_cycles=15,
        confidence_threshold=0.8,
        mcp_discovery_enabled=True
    )

Environment variable support:
    KAIZEN_LLM_PROVIDER=openai
    KAIZEN_MODEL=gpt-4
    KAIZEN_TEMPERATURE=0.1
    KAIZEN_MAX_TOKENS=1000
"""

import os
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Dict, List, Optional

from kailash.nodes.base import NodeMetadata
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature
from kaizen.strategies.multi_cycle import MultiCycleStrategy


class ActionType(Enum):
    """Types of actions the ReAct agent can take."""

    TOOL_USE = "tool_use"
    FINISH = "finish"
    CLARIFY = "clarify"


@dataclass
class ReActConfig:
    """
    Configuration for ReAct Agent.

    All parameters have sensible defaults and can be overridden via:
    1. Constructor arguments (highest priority)
    2. Environment variables (KAIZEN_*)
    3. Default values (lowest priority)
    """

    llm_provider: str = field(
        default_factory=lambda: os.getenv("KAIZEN_LLM_PROVIDER", "openai")
    )
    model: str = field(default_factory=lambda: os.getenv("KAIZEN_MODEL", "gpt-4"))
    temperature: float = field(
        default_factory=lambda: float(os.getenv("KAIZEN_TEMPERATURE", "0.1"))
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("KAIZEN_MAX_TOKENS", "1000"))
    )

    # ReAct-specific configuration
    max_cycles: int = 10
    confidence_threshold: float = 0.7
    mcp_discovery_enabled: bool = False  # Disabled by default (opt-in)
    enable_parallel_tools: bool = False
    timeout: int = 30
    max_retries: int = 3
    provider_config: Dict[str, Any] = field(default_factory=dict)


class ReActSignature(Signature):
    """
    ReAct signature for structured reasoning and acting pattern.

    Implements the Reason + Act + Observe cycle with structured I/O.

    ADR-013 Update: Added tool_calls field for objective convergence detection.
    This enables the `while(tool_call_exists)` pattern from Claude Code.
    """

    # Input fields
    task: str = InputField(desc="Task to solve using ReAct reasoning")
    context: str = InputField(desc="Previous context and observations", default="")
    available_tools: list = InputField(desc="Available MCP tools", default=[])
    previous_actions: list = InputField(desc="Previous actions taken", default=[])

    # Output fields - structured ReAct response
    thought: str = OutputField(desc="Current reasoning step")
    action: str = OutputField(desc="Action to take (tool_use, finish, clarify)")
    action_input: dict = OutputField(desc="Input parameters for the action")
    confidence: float = OutputField(desc="Confidence in the action (0.0-1.0)")
    need_tool: bool = OutputField(desc="Whether external tool is needed")
    tool_calls: list = OutputField(
        desc="List of tool calls to execute (empty list = converged)"
    )


class ReActAgent(BaseAgent):
    """
    Production-ready ReAct (Reasoning + Acting) agent.

    Uses MultiCycleStrategy for iterative Reason → Act → Observe cycles.

    Features:
    - Zero-config with sensible defaults
    - Progressive configuration (override as needed)
    - Environment variable support
    - Multi-cycle execution (iterative reasoning)
    - Optional MCP tool discovery
    - Action types: TOOL_USE, FINISH, CLARIFY
    - Convergence detection (finish action or high confidence)
    - Confidence threshold validation
    - Built-in error handling and logging

    Usage:
        # Zero-config (easiest)
        agent = ReActAgent()
        result = agent.run(task="Book a flight to Paris")

        # With configuration
        agent = ReActAgent(
            llm_provider="openai",
            model="gpt-4",
            temperature=0.1,
            max_cycles=15,
            confidence_threshold=0.8,
            mcp_discovery_enabled=True
        )

        # View reasoning cycles
        result = agent.run(task="Calculate 15% tip on $42.50")
        print(result["thought"])  # Current reasoning
        print(result["action"])   # Action taken
        print(result["confidence"])
        print(f"Cycles used: {result['cycles_used']}/{result['total_cycles']}")

    Configuration:
        llm_provider: LLM provider (default: "openai", env: KAIZEN_LLM_PROVIDER)
        model: Model name (default: "gpt-4", env: KAIZEN_MODEL)
        temperature: Sampling temperature (default: 0.1, env: KAIZEN_TEMPERATURE)
        max_tokens: Maximum tokens (default: 1000, env: KAIZEN_MAX_TOKENS)
        max_cycles: Maximum reasoning cycles (default: 10)
        confidence_threshold: Minimum confidence to finish (default: 0.7)
        mcp_discovery_enabled: Enable MCP tool discovery (default: False, opt-in)
        enable_parallel_tools: Enable parallel tool execution (default: False)
        timeout: Request timeout seconds (default: 30)
        max_retries: Retry count on failure (default: 3)
        provider_config: Additional provider-specific config (default: {})

    Returns:
        Dict with keys:
        - thought: str - Current reasoning step
        - action: str - Action taken (tool_use, finish, clarify)
        - action_input: dict - Action parameters
        - confidence: float - Confidence score 0.0-1.0
        - need_tool: bool - Whether tool is needed
        - cycles_used: int - Number of cycles executed
        - total_cycles: int - Maximum cycles configured
        - error: str (optional) - Error code if validation fails
    """

    # Node metadata for Studio discovery
    metadata = NodeMetadata(
        name="ReActAgent",
        description="Reasoning + Acting agent with iterative problem-solving and tool use",
        version="1.0.0",
        tags={"ai", "kaizen", "react", "reasoning", "tool-use", "multi-cycle"},
    )

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_cycles: Optional[int] = None,
        confidence_threshold: Optional[float] = None,
        mcp_discovery_enabled: Optional[bool] = None,
        enable_parallel_tools: Optional[bool] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        provider_config: Optional[Dict[str, Any]] = None,
        config: Optional[ReActConfig] = None,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ):
        """
        Initialize ReAct agent with zero-config defaults.

        Args:
            llm_provider: Override default LLM provider
            model: Override default model
            temperature: Override default temperature
            max_tokens: Override default max tokens
            max_cycles: Override default max cycles
            confidence_threshold: Override default confidence threshold
            mcp_discovery_enabled: Enable MCP tool discovery (opt-in)
            enable_parallel_tools: Enable parallel tool execution
            timeout: Override default timeout
            max_retries: Override default retry attempts
            provider_config: Additional provider-specific configuration
            config: Full config object (overrides individual params)            mcp_servers: Optional MCP server configurations for tool discovery
        """
        # If config object provided, use it; otherwise build from parameters
        if config is None:
            config = ReActConfig()

            # Override defaults with provided parameters
            if llm_provider is not None:
                config = replace(config, llm_provider=llm_provider)
            if model is not None:
                config = replace(config, model=model)
            if temperature is not None:
                config = replace(config, temperature=temperature)
            if max_tokens is not None:
                config = replace(config, max_tokens=max_tokens)
            if max_cycles is not None:
                config = replace(config, max_cycles=max_cycles)
            if confidence_threshold is not None:
                config = replace(config, confidence_threshold=confidence_threshold)
            if mcp_discovery_enabled is not None:
                config = replace(config, mcp_discovery_enabled=mcp_discovery_enabled)
            if enable_parallel_tools is not None:
                config = replace(config, enable_parallel_tools=enable_parallel_tools)
            if timeout is not None:
                config = replace(config, timeout=timeout)
            if max_retries is not None:
                config = replace(config, max_retries=max_retries)
            if provider_config is not None:
                config = replace(config, provider_config=provider_config)

        # Merge timeout into provider_config
        if config.timeout and (
            not config.provider_config or "timeout" not in config.provider_config
        ):
            provider_cfg = (
                config.provider_config.copy() if config.provider_config else {}
            )
            provider_cfg["timeout"] = config.timeout
            config = replace(config, provider_config=provider_cfg)

        # CRITICAL: Initialize MultiCycleStrategy (NOT AsyncSingleShotStrategy)
        # ReAct is inherently iterative: Reason → Act → Observe cycles
        multi_cycle_strategy = MultiCycleStrategy(
            max_cycles=config.max_cycles, convergence_check=self._check_convergence
        )

        # Initialize BaseAgent with auto-config extraction
        super().__init__(
            config=config,
            signature=ReActSignature(),
            strategy=multi_cycle_strategy,  # CRITICAL: Use MultiCycleStrategy
            mcp_servers=mcp_servers,
            **kwargs,
        )

        self.react_config = config
        self.available_tools = []
        self.action_history = []

        # Discover MCP tools if enabled (opt-in feature)
        if config.mcp_discovery_enabled:
            self._discover_mcp_tools()

    def _discover_mcp_tools(self):
        """
        Discover available MCP tools (placeholder for actual MCP integration).

        In production, this would use actual MCP discovery protocol.
        For now, this initializes an empty list that can be populated.
        """
        # Placeholder for MCP tool discovery
        # In production, this would use MCP protocol to discover available tools
        self.available_tools = []

    def _check_convergence(self, result: Dict[str, Any]) -> bool:
        """
        Check if ReAct cycle should stop (convergence detection).

        ADR-013 Implementation: Objective convergence detection using tool_calls field.

        Convergence logic (priority order):
        1. OBJECTIVE (preferred): Check tool_calls field
           - tool_calls present and non-empty → NOT converged (continue)
           - tool_calls present but empty → CONVERGED (stop)
        2. SUBJECTIVE (fallback): Check action/confidence
           - action == "finish" → CONVERGED (stop)
           - confidence >= threshold → CONVERGED (stop)
        3. DEFAULT: CONVERGED (safe fallback)

        This implements Claude Code's `while(tool_call_exists)` pattern for
        autonomous agents - the most reliable convergence detection method.

        Args:
            result: Result from current cycle

        Returns:
            bool: True if should stop (converged), False if should continue

        Example (Objective):
            >>> result = {"tool_calls": [{"name": "search"}]}
            >>> should_stop = agent._check_convergence(result)
            >>> print(should_stop)
            False  # tool_calls present = not converged

            >>> result = {"tool_calls": []}
            >>> should_stop = agent._check_convergence(result)
            >>> print(should_stop)
            True  # empty tool_calls = converged

        Example (Subjective fallback):
            >>> result = {"action": "finish", "confidence": 0.8}
            >>> should_stop = agent._check_convergence(result)
            >>> print(should_stop)
            True

            >>> result = {"action": "tool_use", "confidence": 0.95}
            >>> should_stop = agent._check_convergence(result)
            >>> print(should_stop)
            True  # High confidence triggers convergence
        """
        # OBJECTIVE CONVERGENCE (PREFERRED) - ADR-013
        # Check if tool_calls field is present
        if "tool_calls" in result:
            tool_calls = result.get("tool_calls", [])

            # Validate tool_calls is a list (handle malformed data)
            if not isinstance(tool_calls, list):
                # Malformed data - fall through to subjective
                pass
            else:
                # Not converged if tool_calls present and non-empty
                if tool_calls:
                    return False

                # Converged if tool_calls present but empty
                return True

        # SUBJECTIVE FALLBACK (backward compatibility)
        # Stop if action is "finish"
        if result.get("action") == ActionType.FINISH.value:
            return True

        # Stop if confidence is high enough
        confidence = result.get("confidence", 0)
        if confidence >= self.react_config.confidence_threshold:
            return True

        # Check if we have action field with non-finish value (continue signal)
        if "action" in result and result.get("action") != ActionType.FINISH.value:
            # Explicit action to continue (tool_use, clarify)
            return False

        # DEFAULT: Safe fallback (converged)
        # When no clear signals, assume converged to prevent infinite loops
        return True

    def run(self, task: str, context: str = "", **kwargs) -> Dict[str, Any]:
        """
        Universal execution method for ReAct agent.

        Executes ReAct cycles (Reason → Act → Observe) iteratively until:
        - Action is "finish"
        - Confidence >= threshold
        - Max cycles reached

        Args:
            task: The task to solve
            context: Optional additional context
            **kwargs: Additional parameters passed to BaseAgent.run()

        Returns:
            Dictionary containing:
            - thought: Current reasoning step
            - action: Action taken (tool_use, finish, clarify)
            - action_input: Action parameters
            - confidence: Confidence score (0.0-1.0)
            - need_tool: Whether tool is needed
            - cycles_used: Number of cycles executed
            - total_cycles: Maximum cycles configured
            - error: Optional error code if validation fails

        Example:
            >>> agent = ReActAgent()
            >>> result = agent.run(task="Book a flight to Paris")
            >>> print(result["thought"])
            I need to search for available flights...
            >>> print(result["action"])
            tool_use
            >>> print(result["confidence"])
            0.85
            >>> print(f"Used {result['cycles_used']}/{result['total_cycles']} cycles")
            Used 3/10 cycles
        """
        # Input validation
        if not task or not task.strip():
            return {
                "error": "INVALID_INPUT",
                "thought": "No task provided",
                "action": ActionType.FINISH.value,
                "action_input": {},
                "confidence": 0.0,
                "need_tool": False,
                "cycles_used": 0,
                "total_cycles": self.react_config.max_cycles,
            }

        # Execute via BaseAgent with MultiCycleStrategy
        # The strategy handles multi-cycle execution automatically
        result = super().run(
            task=task.strip(),
            context=context.strip() if context else "",
            available_tools=self.available_tools,
            previous_actions=self.action_history,
            **kwargs,
        )

        # MultiCycleStrategy returns result with cycles_used and total_cycles
        # The result contains the final cycle's output
        return result


# Convenience function for quick usage
def solve(task: str, **kwargs) -> Dict[str, Any]:
    """
    Quick one-liner for solving tasks without creating an agent instance.

    Args:
        task: The task to solve
        **kwargs: Optional configuration (llm_provider, model, temperature, etc.)

    Returns:
        The full result dictionary

    Example:
        >>> from kaizen.agents.specialized.react import solve
        >>> result = solve("Book a flight to Paris")
        >>> print(result["thought"])
        I need to search for available flights...
        >>> print(result["action"])
        tool_use
    """
    agent = ReActAgent(**kwargs)
    return agent.run(task=task)
