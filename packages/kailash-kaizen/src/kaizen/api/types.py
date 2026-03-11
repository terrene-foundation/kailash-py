"""
Core Types for Unified Agent API

This module defines the fundamental types for the 3-axis agent capability system:
- ExecutionMode: How the agent processes requests
- MemoryDepth: What the agent remembers
- ToolAccess: What the agent can do

These types enable progressive configuration while maintaining type safety.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Set


class ExecutionMode(str, Enum):
    """
    Defines how the agent processes requests.

    Progression: SINGLE -> MULTI -> AUTONOMOUS

    Examples:
        # Simple Q&A
        agent = Agent(model="gpt-4", execution_mode="single")

        # Multi-turn conversation
        agent = Agent(model="gpt-4", execution_mode="multi")

        # Self-directed task completion
        agent = Agent(model="gpt-4", execution_mode="autonomous")
    """

    SINGLE = "single"
    """One response per request. No memory between calls.

    Best for: Simple Q&A, one-shot generation, stateless APIs.
    """

    MULTI = "multi"
    """Multi-turn conversation with memory.

    Best for: Chat applications, tutoring, customer support.
    Maintains conversation context across multiple exchanges.
    """

    AUTONOMOUS = "autonomous"
    """Self-directed task completion using TAOD loop.

    Best for: Complex tasks, code generation, research, analysis.
    Agent plans, executes tools, and iterates until task completion.
    """


class MemoryDepth(str, Enum):
    """
    Defines what the agent remembers between interactions.

    Progression: STATELESS -> SESSION -> PERSISTENT -> LEARNING

    Examples:
        # No memory
        agent = Agent(model="gpt-4", memory="stateless")

        # Session-only memory (default)
        agent = Agent(model="gpt-4", memory="session")

        # Cross-session persistence
        agent = Agent(model="gpt-4", memory="persistent", memory_path="./data/memory")

        # Pattern detection and learning
        agent = Agent(model="gpt-4", memory="learning")
    """

    STATELESS = "stateless"
    """No memory between interactions.

    Best for: One-shot tasks, privacy-sensitive applications, stateless APIs.
    Each request is independent with no conversation history.
    """

    SESSION = "session"
    """Memory within current session only.

    Best for: Chat applications, tutoring sessions, support tickets.
    Remembers context during the session but clears on session end.
    """

    PERSISTENT = "persistent"
    """Cross-session memory persistence.

    Best for: Personal assistants, long-running projects, user preferences.
    Maintains memory across sessions using storage backend.
    """

    LEARNING = "learning"
    """Pattern detection and adaptive learning.

    Best for: Personalization, preference learning, optimization.
    Analyzes patterns, extracts knowledge, and improves over time.
    """


class ToolAccess(str, Enum):
    """
    Defines what the agent can do with external tools.

    Progression: NONE -> READ_ONLY -> CONSTRAINED -> FULL

    Examples:
        # No tools
        agent = Agent(model="gpt-4", tool_access="none")

        # Read-only tools
        agent = Agent(model="gpt-4", tool_access="read_only")

        # Constrained tools (safe writes)
        agent = Agent(model="gpt-4", tool_access="constrained")

        # Full access (dangerous operations allowed)
        agent = Agent(model="gpt-4", tool_access="full")
    """

    NONE = "none"
    """No tool access. Pure language model interaction.

    Best for: Simple Q&A, content generation, chat.
    Agent cannot read files, make API calls, or execute code.
    """

    READ_ONLY = "read_only"
    """Read-only tools: Read, Glob, Grep, List, etc.

    Best for: Research, code review, documentation analysis.
    Agent can read and search but cannot modify anything.
    """

    CONSTRAINED = "constrained"
    """Read, Write, and limited execution with safety checks.

    Best for: Development assistance, automation with guardrails.
    Agent can modify files in safe directories, make HTTP requests.
    Dangerous operations require confirmation.
    """

    FULL = "full"
    """All tools including dangerous operations.

    Best for: Trusted autonomous agents, admin tasks, deployment.
    Agent has full system access. Use with caution.
    Requires explicit user acknowledgment.
    """


# Tool categories for access level mapping
READ_ONLY_TOOLS: Set[str] = frozenset(
    {
        "read",
        "glob",
        "grep",
        "list",
        "ls",
        "find",
        "search",
        "get",
        "fetch",
        "view",
        "show",
        "describe",
        "analyze",
    }
)

CONSTRAINED_TOOLS: Set[str] = frozenset(
    {
        # Read-only tools
        *READ_ONLY_TOOLS,
        # Safe write tools
        "write",
        "edit",
        "create",
        "mkdir",
        "copy",
        "move",
        # Safe network tools
        "http_get",
        "http_post",
        "api_call",
        # Safe execution
        "python",
        "node",
    }
)

DANGEROUS_TOOLS: Set[str] = frozenset(
    {
        "bash",
        "shell",
        "exec",
        "sudo",
        "rm",
        "delete",
        "format",
        "install",
        "uninstall",
        "deploy",
        "rollback",
    }
)


@dataclass
class AgentCapabilities:
    """
    Defines the complete capability profile for an agent.

    This is the 3-axis capability system:
    - execution_modes: How the agent processes requests
    - max_memory_depth: What the agent remembers
    - tool_access: What the agent can do

    Examples:
        # Minimal capabilities
        caps = AgentCapabilities()  # Single mode, stateless, no tools

        # Full capabilities
        caps = AgentCapabilities(
            execution_modes=[ExecutionMode.SINGLE, ExecutionMode.MULTI, ExecutionMode.AUTONOMOUS],
            max_memory_depth=MemoryDepth.LEARNING,
            tool_access=ToolAccess.FULL,
        )

        # Check capabilities
        if caps.can_execute(ExecutionMode.AUTONOMOUS):
            agent.run_autonomous(task)
    """

    # Execution capability axis
    execution_modes: List[ExecutionMode] = field(
        default_factory=lambda: [ExecutionMode.SINGLE]
    )
    """Supported execution modes. Default: SINGLE only."""

    # Memory capability axis
    max_memory_depth: MemoryDepth = field(default=MemoryDepth.STATELESS)
    """Maximum memory depth. Default: STATELESS."""

    # Tool capability axis
    tool_access: ToolAccess = field(default=ToolAccess.NONE)
    """Tool access level. Default: NONE."""

    # Tool restrictions
    allowed_tools: Optional[List[str]] = field(default=None)
    """If set, only these tools are allowed (whitelist)."""

    denied_tools: Optional[List[str]] = field(default=None)
    """If set, these tools are explicitly denied (blacklist)."""

    # Execution limits
    max_turns: int = field(default=50)
    """Maximum conversation turns (MULTI mode)."""

    max_cycles: int = field(default=100)
    """Maximum TAOD cycles (AUTONOMOUS mode)."""

    max_tool_calls: int = field(default=1000)
    """Maximum tool calls per session."""

    max_tokens_per_turn: int = field(default=8192)
    """Maximum tokens per turn."""

    # Timeout limits
    timeout_seconds: float = field(default=300.0)
    """Overall execution timeout in seconds."""

    tool_timeout_seconds: float = field(default=60.0)
    """Individual tool call timeout in seconds."""

    def can_execute(self, mode: ExecutionMode) -> bool:
        """
        Check if a specific execution mode is supported.

        Args:
            mode: The execution mode to check

        Returns:
            True if the mode is supported, False otherwise

        Example:
            if caps.can_execute(ExecutionMode.AUTONOMOUS):
                result = agent.run_autonomous(task)
        """
        return mode in self.execution_modes

    def can_use_tool(self, tool_name: str) -> bool:
        """
        Check if a specific tool can be used based on access level and restrictions.

        Args:
            tool_name: The tool name to check (case-insensitive)

        Returns:
            True if the tool can be used, False otherwise

        Example:
            if caps.can_use_tool("bash"):
                result = agent.execute_bash(command)
        """
        tool_lower = tool_name.lower()

        # Check explicit deny list first
        if self.denied_tools and tool_lower in [t.lower() for t in self.denied_tools]:
            return False

        # Check explicit allow list
        if self.allowed_tools is not None:
            return tool_lower in [t.lower() for t in self.allowed_tools]

        # Check based on access level
        if self.tool_access == ToolAccess.NONE:
            return False
        elif self.tool_access == ToolAccess.READ_ONLY:
            return tool_lower in READ_ONLY_TOOLS
        elif self.tool_access == ToolAccess.CONSTRAINED:
            return tool_lower in CONSTRAINED_TOOLS or tool_lower in READ_ONLY_TOOLS
        elif self.tool_access == ToolAccess.FULL:
            return True

        return False

    def get_available_tools(self) -> Set[str]:
        """
        Get the set of tools available at the current access level.

        Returns:
            Set of available tool names

        Example:
            tools = caps.get_available_tools()
            print(f"Available: {', '.join(tools)}")
        """
        if self.allowed_tools is not None:
            base_tools = set(self.allowed_tools)
        elif self.tool_access == ToolAccess.NONE:
            base_tools = set()
        elif self.tool_access == ToolAccess.READ_ONLY:
            base_tools = set(READ_ONLY_TOOLS)
        elif self.tool_access == ToolAccess.CONSTRAINED:
            base_tools = set(CONSTRAINED_TOOLS) | set(READ_ONLY_TOOLS)
        elif self.tool_access == ToolAccess.FULL:
            # Full access - return all known tools
            base_tools = (
                set(READ_ONLY_TOOLS) | set(CONSTRAINED_TOOLS) | set(DANGEROUS_TOOLS)
            )
        else:
            base_tools = set()

        # Remove denied tools
        if self.denied_tools:
            base_tools -= set(t.lower() for t in self.denied_tools)

        return base_tools

    def requires_confirmation(self, tool_name: str) -> bool:
        """
        Check if a tool requires user confirmation before execution.

        Args:
            tool_name: The tool name to check

        Returns:
            True if confirmation is required, False otherwise

        Example:
            if caps.requires_confirmation("bash"):
                confirmation = get_user_confirmation()
        """
        tool_lower = tool_name.lower()

        # Full access doesn't require confirmation
        if self.tool_access == ToolAccess.FULL:
            return False

        # Dangerous tools always require confirmation in constrained mode
        if self.tool_access == ToolAccess.CONSTRAINED:
            return tool_lower in DANGEROUS_TOOLS

        return False

    def to_dict(self) -> dict:
        """
        Serialize capabilities to a dictionary.

        Returns:
            Dictionary representation of capabilities
        """
        return {
            "execution_modes": [m.value for m in self.execution_modes],
            "max_memory_depth": self.max_memory_depth.value,
            "tool_access": self.tool_access.value,
            "allowed_tools": self.allowed_tools,
            "denied_tools": self.denied_tools,
            "max_turns": self.max_turns,
            "max_cycles": self.max_cycles,
            "max_tool_calls": self.max_tool_calls,
            "max_tokens_per_turn": self.max_tokens_per_turn,
            "timeout_seconds": self.timeout_seconds,
            "tool_timeout_seconds": self.tool_timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentCapabilities":
        """
        Create capabilities from a dictionary.

        Args:
            data: Dictionary with capability data

        Returns:
            AgentCapabilities instance
        """
        return cls(
            execution_modes=[
                ExecutionMode(m) for m in data.get("execution_modes", ["single"])
            ],
            max_memory_depth=MemoryDepth(data.get("max_memory_depth", "stateless")),
            tool_access=ToolAccess(data.get("tool_access", "none")),
            allowed_tools=data.get("allowed_tools"),
            denied_tools=data.get("denied_tools"),
            max_turns=data.get("max_turns", 50),
            max_cycles=data.get("max_cycles", 100),
            max_tool_calls=data.get("max_tool_calls", 1000),
            max_tokens_per_turn=data.get("max_tokens_per_turn", 8192),
            timeout_seconds=data.get("timeout_seconds", 300.0),
            tool_timeout_seconds=data.get("tool_timeout_seconds", 60.0),
        )

    def __str__(self) -> str:
        """Human-readable capability summary."""
        modes = ", ".join(m.value for m in self.execution_modes)
        return (
            f"AgentCapabilities("
            f"modes=[{modes}], "
            f"memory={self.max_memory_depth.value}, "
            f"tools={self.tool_access.value})"
        )
