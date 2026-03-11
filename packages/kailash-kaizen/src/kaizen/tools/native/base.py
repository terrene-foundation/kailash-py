"""
Base Tool Infrastructure for Native Tools

Provides the abstract base class and result types for Kaizen native tools.
Native tools are designed for direct execution within LocalKaizenAdapter,
supporting the Think-Act-Observe-Decide autonomous loop.

Key Difference from MCP Tools:
- MCP tools: Used by BaseAgent for LLM tool calling (external access)
- Native tools: Used by LocalKaizenAdapter for autonomous execution (internal)

Design Principles:
- Async-first: All tools use async/await for consistency
- Type-safe: Full type hints and validation
- Error-wrapped: All exceptions wrapped in NativeToolResult
- Schema-ready: Tools generate LLM-compatible schemas
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kaizen.tools.types import DangerLevel, ToolCategory


@dataclass
class NativeToolResult:
    """
    Standardized result from native tool execution.

    Designed for use in autonomous agent loops where tools are called
    programmatically, not through LLM tool calling.

    Attributes:
        success: Whether the tool execution succeeded
        output: The tool output (any type - string, dict, list, etc.)
        error: Error message if execution failed
        metadata: Additional execution metadata (timing, stats, etc.)

    Example:
        >>> result = NativeToolResult(
        ...     success=True,
        ...     output="File contents here...",
        ...     metadata={"bytes_read": 1024, "lines": 50}
        ... )
        >>>
        >>> # Error result
        >>> result = NativeToolResult(
        ...     success=False,
        ...     output="",
        ...     error="File not found: /path/to/file.txt"
        ... )
    """

    success: bool
    output: Any
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_success(cls, output: Any, **metadata) -> "NativeToolResult":
        """Create a successful result."""
        return cls(success=True, output=output, metadata=metadata)

    @classmethod
    def from_error(cls, error: str, **metadata) -> "NativeToolResult":
        """Create an error result."""
        return cls(success=False, output="", error=error, metadata=metadata)

    @classmethod
    def from_exception(cls, exception: Exception) -> "NativeToolResult":
        """Create result from an exception."""
        return cls(
            success=False,
            output="",
            error=str(exception),
            metadata={"exception_type": type(exception).__name__},
        )


class BaseTool(ABC):
    """
    Abstract base class for all native tools.

    Native tools are designed for direct programmatic execution within
    the LocalKaizenAdapter's autonomous loop. Each tool must define:

    - name: Unique identifier for the tool
    - description: Human-readable description for LLM understanding
    - danger_level: Safety classification for approval workflows
    - execute(): Async method that performs the tool's action
    - get_schema(): Returns LLM-compatible parameter schema

    Design Requirements:
    1. All tools MUST be async (for consistency with Kaizen architecture)
    2. All tools MUST return NativeToolResult (never raise for normal errors)
    3. All tools MUST validate inputs before execution
    4. All tools MUST handle their own exceptions

    Example:
        >>> class MyTool(BaseTool):
        ...     name = "my_tool"
        ...     description = "Does something useful"
        ...     danger_level = DangerLevel.SAFE
        ...     category = ToolCategory.CUSTOM
        ...
        ...     async def execute(self, param1: str) -> NativeToolResult:
        ...         try:
        ...             result = do_something(param1)
        ...             return NativeToolResult.from_success(result)
        ...         except Exception as e:
        ...             return NativeToolResult.from_exception(e)
        ...
        ...     def get_schema(self) -> Dict[str, Any]:
        ...         return {
        ...             "type": "object",
        ...             "properties": {
        ...                 "param1": {"type": "string", "description": "Parameter 1"}
        ...             },
        ...             "required": ["param1"]
        ...         }
    """

    # Class attributes - must be overridden by subclasses
    name: str = ""
    description: str = ""
    danger_level: DangerLevel = DangerLevel.SAFE
    category: ToolCategory = ToolCategory.CUSTOM

    def __init__(self):
        """Initialize the tool and validate configuration."""
        if not self.name:
            raise ValueError(f"{self.__class__.__name__} must define 'name' attribute")
        if not self.description:
            raise ValueError(
                f"{self.__class__.__name__} must define 'description' attribute"
            )

    @abstractmethod
    async def execute(self, **kwargs) -> NativeToolResult:
        """
        Execute the tool with the given parameters.

        Args:
            **kwargs: Tool-specific parameters

        Returns:
            NativeToolResult with success/failure and output

        Note:
            Implementations should NOT raise exceptions for normal failures.
            Instead, return NativeToolResult.from_error() or NativeToolResult.from_exception().
            Only truly unexpected errors (bugs) should raise.
        """
        pass

    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """
        Get JSON Schema for tool parameters.

        Returns:
            JSON Schema dict compatible with OpenAI function calling format:
            {
                "type": "object",
                "properties": {
                    "param_name": {
                        "type": "string",
                        "description": "Parameter description"
                    }
                },
                "required": ["param_name"]
            }
        """
        pass

    def get_full_schema(self) -> Dict[str, Any]:
        """
        Get complete tool schema for LLM function calling.

        Returns:
            Complete schema including name, description, and parameters:
            {
                "type": "function",
                "function": {
                    "name": "tool_name",
                    "description": "Tool description",
                    "parameters": {...schema...}
                }
            }
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.get_schema(),
            },
        }

    def is_safe(self) -> bool:
        """Check if tool is safe (no approval required)."""
        return self.danger_level in (DangerLevel.SAFE, DangerLevel.LOW)

    def requires_approval(self, threshold: DangerLevel = DangerLevel.MEDIUM) -> bool:
        """
        Check if tool requires approval at given threshold.

        Args:
            threshold: Minimum danger level that requires approval

        Returns:
            True if tool's danger level >= threshold
        """
        danger_order = [
            DangerLevel.SAFE,
            DangerLevel.LOW,
            DangerLevel.MEDIUM,
            DangerLevel.HIGH,
            DangerLevel.CRITICAL,
        ]
        tool_index = danger_order.index(self.danger_level)
        threshold_index = danger_order.index(threshold)
        return tool_index >= threshold_index

    async def execute_with_timing(self, **kwargs) -> NativeToolResult:
        """
        Execute tool and add timing metadata.

        Wraps execute() to add execution_time_ms to metadata.
        """
        start_time = time.perf_counter()
        result = await self.execute(**kwargs)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        result.metadata["execution_time_ms"] = round(elapsed_ms, 2)
        return result

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"name={self.name!r}, "
            f"danger_level={self.danger_level.value!r})"
        )
