"""
Kaizen Unified Agent API

This module provides the user-facing unified Agent API for Kaizen.
It offers progressive configuration from simple 2-line usage to expert mode.

Quick Start:
    from kaizen.api import Agent

    agent = Agent(model="gpt-4")
    result = agent.run("What is IRP?")
"""

from kaizen.api.agent import Agent
from kaizen.api.config import AgentConfig
from kaizen.api.presets import CapabilityPresets
from kaizen.api.result import AgentResult, ToolCallRecord
from kaizen.api.shortcuts import (
    resolve_memory_shortcut,
    resolve_runtime_shortcut,
    resolve_tool_access_shortcut,
)
from kaizen.api.types import AgentCapabilities, ExecutionMode, MemoryDepth, ToolAccess
from kaizen.api.validation import (
    ConfigurationError,
    validate_configuration,
    validate_model_runtime_compatibility,
)

__all__ = [
    # Core Types
    "ExecutionMode",
    "MemoryDepth",
    "ToolAccess",
    "AgentCapabilities",
    # Result
    "AgentResult",
    "ToolCallRecord",
    # Shortcuts
    "resolve_memory_shortcut",
    "resolve_runtime_shortcut",
    "resolve_tool_access_shortcut",
    # Validation
    "ConfigurationError",
    "validate_configuration",
    "validate_model_runtime_compatibility",
    # Presets
    "CapabilityPresets",
    # Config
    "AgentConfig",
    # Main Class
    "Agent",
]
