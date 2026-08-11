"""
Core Kaizen framework components.

This module contains the foundational classes and interfaces for the Kaizen framework:
- Framework initialization and management
- Base classes and interfaces
- Agent creation and management
- Token counting utilities
"""

# Signature primitives — re-exported here so the canonical Quick Start
# (`from kaizen.core import BaseAgent, Signature, InputField, OutputField`)
# documented in specs/kaizen-core.md §3 and rules/patterns.md § Kaizen
# resolves on a fresh install.
from kaizen.signatures import InputField, OutputField, Signature

from ._provider_env import detect_provider_from_env, resolve_agent_provider
from .agents import Agent, AgentManager
from .base_agent import BaseAgent
from .config import KaizenConfig, MemoryProvider, OptimizationEngine

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
from .structured_output import StructuredOutput

# Token counting utilities
from .token_counter import (
    TIKTOKEN_AVAILABLE,
    TokenCounter,
    count_tokens,
    get_token_counter,
)

__all__ = [
    # Provider resolution — the PUBLIC surface for "which provider should this
    # agent config use?" (#2022). Cross-package callers (kailash-ml,
    # kailash-dataflow) MUST use these rather than reaching into private
    # modules such as `kaizen.nodes._env_model`, which makes an undeclared
    # coupling the next kaizen refactor breaks silently.
    "resolve_agent_provider",
    "detect_provider_from_env",
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
