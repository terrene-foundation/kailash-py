"""
Core Kaizen framework components.

This module contains the foundational classes and interfaces for the Kaizen framework:
- Framework initialization and management
- Base classes and interfaces
- Agent creation and management
- Token counting utilities
"""

from .agents import Agent, AgentManager
from .base_agent import BaseAgent
from .config import KaizenConfig, MemoryProvider, OptimizationEngine
from .structured_output import StructuredOutput

# PERFORMANCE OPTIMIZED: Use lightweight imports for <100ms startup
from .framework import Kaizen

# Specialist System (ADR-013)
from .kaizen_options import KaizenOptions
from .specialist_types import (
    ContextFile,
    SettingSource,
    SkillDefinition,
    SpecialistDefinition,
)

# Token counting utilities
from .token_counter import (
    TIKTOKEN_AVAILABLE,
    TokenCounter,
    count_tokens,
    get_token_counter,
)

# Signature primitives — re-exported here so the canonical Quick Start
# (`from kaizen.core import BaseAgent, Signature, InputField, OutputField`)
# documented in specs/kaizen-core.md §3 and rules/patterns.md § Kaizen
# resolves on a fresh install.
from kaizen.signatures import InputField, OutputField, Signature

__all__ = [
    "Kaizen",
    "MemoryProvider",
    "OptimizationEngine",
    "KaizenConfig",
    "Agent",
    "AgentManager",
    "BaseAgent",
    "StructuredOutput",
    # Signature primitives (re-exported from kaizen.signatures)
    "Signature",
    "InputField",
    "OutputField",
    # Specialist System (ADR-013)
    "KaizenOptions",
    "SpecialistDefinition",
    "SkillDefinition",
    "ContextFile",
    "SettingSource",
    # Token counting
    "TokenCounter",
    "get_token_counter",
    "count_tokens",
    "TIKTOKEN_AVAILABLE",
]
