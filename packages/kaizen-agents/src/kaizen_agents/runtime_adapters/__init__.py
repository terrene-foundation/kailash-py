"""
Runtime Adapter Implementations

Contains concrete implementations of RuntimeAdapter for different
autonomous agent runtimes.

Adapters:
- LocalKaizenAdapter: Native Kaizen implementation (works with ANY LLM)
- ClaudeCodeAdapter: Delegates to Claude Code SDK (lazy loaded)
- OpenAICodexAdapter: Delegates to OpenAI Responses API (lazy loaded)
- GeminiCLIAdapter: Delegates to Gemini CLI (lazy loaded)

Tool Mapping:
- MCPToolMapper: Kaizen -> MCP format (for Claude Code custom tools)
- OpenAIToolMapper: Validation and normalization for OpenAI
- GeminiToolMapper: Kaizen -> Gemini Function Declarations

Note: External adapters are implemented in separate files and lazily
loaded to avoid importing heavy dependencies when not needed.
"""

from kaizen_agents.runtime_adapters.kaizen_local import LocalKaizenAdapter

# Tool mapping infrastructure
from kaizen_agents.runtime_adapters.tool_mapping import (
    GeminiToolMapper,
    KaizenTool,
    MappedTool,
    MCPToolMapper,
    OpenAIToolMapper,
    ToolMapper,
    ToolMappingError,
)
from kaizen_agents.runtime_adapters.types import (
    AutonomousConfig,
    AutonomousPhase,
    ExecutionState,
    PermissionMode,
    PlanningStrategy,
)

__all__ = [
    # Types
    "AutonomousPhase",
    "AutonomousConfig",
    "ExecutionState",
    "PlanningStrategy",
    "PermissionMode",
    # Adapters
    "LocalKaizenAdapter",
    # Tool Mapping
    "ToolMapper",
    "ToolMappingError",
    "KaizenTool",
    "MappedTool",
    "MCPToolMapper",
    "OpenAIToolMapper",
    "GeminiToolMapper",
]

# External adapters are loaded lazily - import from specific modules when needed
# from kaizen_agents.runtime_adapters.claude_code import ClaudeCodeAdapter
# from kaizen_agents.runtime_adapters.openai_codex import OpenAICodexAdapter
# from kaizen_agents.runtime_adapters.gemini_cli import GeminiCLIAdapter
