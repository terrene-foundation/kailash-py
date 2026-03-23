"""Base classes for the kz tool system."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """Outcome of a single tool execution."""

    output: str
    error: str = ""
    is_error: bool = False

    @classmethod
    def success(cls, output: str) -> ToolResult:
        return cls(output=output)

    @classmethod
    def failure(cls, error: str) -> ToolResult:
        return cls(output="", error=error, is_error=True)


class Tool(abc.ABC):
    """Abstract base class for all kz tools.

    Subclasses define *name*, *description*, *parameters_schema*, and
    implement the *execute* method.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique tool identifier."""

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """Human-readable description of what this tool does."""

    @property
    @abc.abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """JSON-Schema-style dict describing accepted parameters."""

    @abc.abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult:
        """Run the tool with the given keyword arguments.

        Returns a :class:`ToolResult`.
        """


@dataclass
class ToolRegistry:
    """Registry for tool lookup by name."""

    _tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        """Register a tool. Raises ValueError on duplicate names."""
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name!r}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Return the tool with *name*, or ``None``."""
        return self._tools.get(name)

    def get_or_raise(self, name: str) -> Tool:
        """Return the tool with *name*; raise KeyError if missing."""
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Unknown tool: {name!r}")
        return tool

    def list_tools(self) -> list[Tool]:
        """Return all registered tools in registration order."""
        return list(self._tools.values())

    @property
    def names(self) -> list[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())
