"""
Kaizen Specialized Agents - Production-Ready Agent Library

This module provides production-ready, importable agents that can be used
directly without copy-pasting example code.

Usage:
    from kaizen.agents import SimpleQAAgent, ReActAgent, RAGResearchAgent

    # Zero-config usage (sensible defaults)
    agent = SimpleQAAgent()
    result = agent.ask("What is AI?")

    # Progressive configuration (override as needed)
    agent = SimpleQAAgent(llm_provider="openai", model="gpt-4")

    # Batch processing for high throughput
    from kaizen.agents import BatchProcessingAgent
    batch_agent = BatchProcessingAgent(max_concurrent=20)

    # Human-in-the-loop for compliance
    from kaizen.agents import HumanApprovalAgent
    approval_agent = HumanApprovalAgent(approval_callback=my_callback)

Creating Custom Agents:
    See examples/guides/creating-custom-agents/ for tutorials on:
    - Extending BaseAgent
    - Creating domain-specific agents
    - Implementing custom strategies
"""

# IMPORTANT: Auto-register all builtin agents with the registry
# This enables Agent(agent_type="simple"), Agent(agent_type="react"), etc.
from kaizen.agents import register_builtin  # noqa: F401
from kaizen.agents.multi_modal.multi_modal_agent import (
    MultiModalAgent,
    MultiModalConfig,
)
from kaizen.agents.multi_modal.transcription_agent import (
    TranscriptionAgent,
    TranscriptionAgentConfig,
)

# Multi-modal agents
from kaizen.agents.multi_modal.vision_agent import VisionAgent, VisionAgentConfig

# Registry functions for agent type registration and discovery
from kaizen.agents.registry import register_agent_type  # Backward compatibility alias
from kaizen.agents.registry import (
    create_agent_from_type,
    get_agent_type_registration,
    get_agent_types_by_category,
    get_agent_types_by_tag,
    get_registry_info,
    is_agent_type_registered,
    list_agent_type_names,
    list_agent_types,
    register_agent,
    unregister_agent_type,
)
from kaizen.agents.specialized.batch_processing import BatchProcessingAgent
from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent
from kaizen.agents.specialized.code_generation import CodeGenerationAgent
from kaizen.agents.specialized.human_approval import HumanApprovalAgent
from kaizen.agents.specialized.memory_agent import MemoryAgent
from kaizen.agents.specialized.rag_research import RAGResearchAgent
from kaizen.agents.specialized.react import ReActAgent
from kaizen.agents.specialized.resilient import ResilientAgent
from kaizen.agents.specialized.self_reflection import SelfReflectionAgent

# Specialized agents (single-purpose, ready-to-use)
from kaizen.agents.specialized.simple_qa import SimpleQAAgent
from kaizen.agents.specialized.streaming_chat import StreamingChatAgent

__all__ = [
    # Specialized (11 production agents)
    "SimpleQAAgent",
    "MemoryAgent",
    "ChainOfThoughtAgent",
    "RAGResearchAgent",
    "CodeGenerationAgent",
    "ReActAgent",
    "BatchProcessingAgent",
    "HumanApprovalAgent",
    "ResilientAgent",
    "StreamingChatAgent",
    "SelfReflectionAgent",
    # Multi-modal (3 agents)
    "VisionAgent",
    "VisionAgentConfig",
    "TranscriptionAgent",
    "TranscriptionAgentConfig",
    "MultiModalAgent",
    "MultiModalConfig",
    # Registry functions (Phase 1)
    "register_agent",
    "register_agent_type",  # Backward compatibility
    "get_agent_type_registration",
    "list_agent_type_names",
    "list_agent_types",
    "is_agent_type_registered",
    "unregister_agent_type",
    "get_agent_types_by_category",
    "get_agent_types_by_tag",
    "get_registry_info",
    "create_agent_from_type",
]
