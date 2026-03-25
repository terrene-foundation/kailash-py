"""
Kaizen Unified Agent API

This module provides the user-facing unified Agent API for Kaizen.
It offers progressive configuration from simple 2-line usage to expert mode.

Quick Start:
    from kaizen_agents.api import Agent

    agent = Agent(model="gpt-4")
    result = agent.run("What is IRP?")
"""

from kaizen_agents.api.agent import Agent
from kaizen_agents.api.config import AgentConfig
from kaizen_agents.api.presets import CapabilityPresets
from kaizen_agents.api.result import AgentResult, ToolCallRecord
from kaizen_agents.api.shortcuts import (
    resolve_memory_shortcut,
    resolve_runtime_shortcut,
    resolve_tool_access_shortcut,
)
from kaizen_agents.api.types import AgentCapabilities, ExecutionMode, MemoryDepth, ToolAccess
from kaizen_agents.api.validation import (
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
