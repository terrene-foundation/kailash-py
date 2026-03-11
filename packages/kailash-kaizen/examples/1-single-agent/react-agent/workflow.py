"""
ReAct Agent - Refactored with BaseAgent + MultiCycleStrategy

Demonstrates iterative reasoning and acting with BaseAgent + MultiCycleStrategy:
- 598 lines → ~150 lines (75% reduction)
- Signature-based ReAct pattern
- Multi-cycle execution with tool integration
- Built-in error handling, logging, performance tracking via mixins
- Enterprise-grade with minimal code
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

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
    """Configuration for ReAct agent behavior."""

    max_cycles: int = 10
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.1
    confidence_threshold: float = 0.7
    mcp_discovery_enabled: bool = True
    enable_parallel_tools: bool = False
    timeout: int = 30
    max_retries: int = 3
    provider_config: Dict[str, Any] = field(default_factory=dict)


class ReActSignature(Signature):
    """
    Signature for ReAct reasoning and acting pattern.

    Each cycle produces thought, action, and optionally uses tools.
    """

    # Input fields
    task: str = InputField(desc="The task to solve")
    context: str = InputField(desc="Previous context and observations", default="")
    available_tools: list = InputField(desc="List of available MCP tools", default=[])
    previous_actions: list = InputField(desc="Previous actions taken", default=[])

    # Output fields - structured ReAct response
    thought: str = OutputField(desc="Current reasoning step")
    action: str = OutputField(desc="Action to take (tool_use, finish, clarify)")
    action_input: dict = OutputField(desc="Input parameters for the action")
    confidence: float = OutputField(desc="Confidence in the action (0.0-1.0)")
    need_tool: bool = OutputField(desc="Whether external tool is needed")


class KaizenReActAgent(BaseAgent):
    """
    ReAct Agent using BaseAgent architecture with MultiCycleStrategy.

    Inherits from BaseAgent:
    - Signature-based structured ReAct reasoning
    - Multi-cycle execution via MultiCycleStrategy
    - Error handling (ErrorHandlingMixin)
    - Performance tracking (PerformanceMixin)
    - Structured logging (LoggingMixin)
    - Workflow generation for Core SDK integration
    """

    def __init__(self, config: ReActConfig):
        """Initialize ReAct agent with BaseAgent infrastructure and MultiCycleStrategy."""
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        # Initialize BaseAgent with MultiCycleStrategy (ReAct is inherently multi-cycle)
        multi_cycle_strategy = MultiCycleStrategy(
            max_cycles=config.max_cycles, convergence_check=self._check_convergence
        )

        super().__init__(
            config=config, signature=ReActSignature(), strategy=multi_cycle_strategy
        )

        self.react_config = config
        self.available_tools = []
        self.action_history = []

        # Discover MCP tools if enabled
        if config.mcp_discovery_enabled:
            self._discover_mcp_tools()

    def _discover_mcp_tools(self):
        """Discover available MCP tools (placeholder for actual MCP integration)."""
        # In production, this would use actual MCP discovery
        # For now, this is a placeholder
        self.available_tools = [
            {"name": "calculator", "description": "Perform mathematical calculations"},
            {"name": "web_search", "description": "Search the web for information"},
            {"name": "file_reader", "description": "Read files from the filesystem"},
        ]

    def _check_convergence(self, cycle_results: List[Dict[str, Any]]) -> bool:
        """
        Check if the agent has converged (finished its task).

        Args:
            cycle_results: Results from all previous cycles

        Returns:
            bool: True if agent has finished, False if more cycles needed
        """
        if not cycle_results:
            return False

        last_result = cycle_results[-1]

        # Check if action is FINISH
        if last_result.get("action") == ActionType.FINISH.value:
            return True

        # Check if confidence is high enough
        if last_result.get("confidence", 0) >= self.react_config.confidence_threshold:
            return True

        return False

    def _process_cycle(self, inputs: Dict[str, Any], cycle_num: int) -> Dict[str, Any]:
        """
        Process a single ReAct cycle.

        This is called by MultiCycleStrategy for each iteration.
        It adds cycle-specific context and lets the strategy execute the workflow.

        Args:
            inputs: Current cycle inputs
            cycle_num: Current cycle number

        Returns:
            Dict[str, Any]: Enhanced inputs for this cycle
        """
        # Add cycle context to inputs
        cycle_inputs = inputs.copy()
        cycle_inputs["cycle_num"] = cycle_num
        cycle_inputs["available_tools"] = self.available_tools
        cycle_inputs["previous_actions"] = self.action_history

        # Return enhanced inputs - strategy will execute workflow
        # The strategy will handle execution and call this for each cycle
        return cycle_inputs

    def solve(self, task: str, context: str = "") -> Dict[str, Any]:
        """
        Solve a task using ReAct reasoning and acting pattern.

        Args:
            task: The task to solve
            context: Optional additional context

        Returns:
            Dict containing final answer, thought, action, and metadata
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
            }

        # Execute via MultiCycleStrategy
        # The strategy handles the multi-cycle execution automatically
        result = self.run(task=task.strip(), context=context.strip() if context else "")

        # MultiCycleStrategy returns result with cycles_used and total_cycles
        # The result contains the final cycle's output
        return result
