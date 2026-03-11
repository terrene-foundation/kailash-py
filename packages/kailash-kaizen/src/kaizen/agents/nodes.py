"""
Kaizen Agents - Node Registration Module

making them discoverable to:
- Kailash WorkflowBuilder (SDK workflows)
- Kailash Studio (visual workflow composer)
- NodeRegistry.list_nodes() API

Architecture Decision:
    Kaizen agents ARE Kailash nodes (BaseAgent inherits from Node).
    No wrapper nodes needed - agents register themselves directly.

Usage:
    # Agents are automatically registered when kaizen is imported
    from kaizen.agents.nodes import KAIZEN_AGENTS

    # List all registered Kaizen agents
    for agent_name, metadata in KAIZEN_AGENTS.items():
        print(f"{agent_name}: {metadata['description']}")

    # Use in workflows
    from kailash.workflow.builder import WorkflowBuilder

    workflow = WorkflowBuilder()
    workflow.add_node("SimpleQAAgent", "qa", {
        "question": "What is Python?",
        "llm_provider": "ollama",
        "model": "llama2"
    })

Registered Agents:
    Specialized (11):
    1. SimpleQAAgent - Basic question answering with confidence scoring
    2. MemoryAgent - Conversational agent with multi-turn memory
    3. ChainOfThoughtAgent - Step-by-step reasoning with verification
    4. RAGResearchAgent - Retrieval-Augmented Generation with vector search
    5. CodeGenerationAgent - Multi-language code generation with tests
    6. ReActAgent - Reasoning + Acting agent with tool use
    7. BatchProcessingAgent - Concurrent high-throughput batch processing
    8. HumanApprovalAgent - Human-in-the-loop decision making
    9. ResilientAgent - Multi-model fallback for high availability
    10. StreamingChatAgent - Real-time token streaming
    11. SelfReflectionAgent - Iterative self-improvement

    Multi-Modal (3):
    12. VisionAgent - Multi-modal vision processing (image analysis, OCR)
    13. TranscriptionAgent - Audio transcription with Whisper
    14. MultiModalAgent - Unified multi-modal agent (vision + audio + text)

See Also:
    - KAIZEN_STUDIO_ARCHITECTURE.md - Integration design
    - KAIZEN_WORKFLOW_CHAINING_EXAMPLES.md - Usage patterns
    - KAIZEN_MEMORY_ARCHITECTURE.md - Memory management
"""

from kaizen.agents.multi_modal.multi_modal_agent import MultiModalAgent
from kaizen.agents.multi_modal.transcription_agent import TranscriptionAgent

# Multi-modal agents
from kaizen.agents.multi_modal.vision_agent import VisionAgent
from kaizen.agents.specialized.batch_processing import BatchProcessingAgent
from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent
from kaizen.agents.specialized.code_generation import CodeGenerationAgent
from kaizen.agents.specialized.human_approval import HumanApprovalAgent
from kaizen.agents.specialized.memory_agent import MemoryAgent
from kaizen.agents.specialized.rag_research import RAGResearchAgent
from kaizen.agents.specialized.react import ReActAgent
from kaizen.agents.specialized.resilient import ResilientAgent
from kaizen.agents.specialized.self_reflection import SelfReflectionAgent

# Specialized agents
from kaizen.agents.specialized.simple_qa import SimpleQAAgent
from kaizen.agents.specialized.streaming_chat import StreamingChatAgent

# Agent metadata for Studio integration
KAIZEN_AGENTS = {
    "SimpleQAAgent": {
        "class": SimpleQAAgent,
        "category": "AI Agents",
        "description": "Simple question answering agent with confidence scoring",
        "version": "1.0.0",
        "tags": ["ai", "kaizen", "qa", "simple", "question-answering"],
        "icon": "message-circle",
        "color": "#4F46E5",  # Indigo
    },
    "MemoryAgent": {
        "class": MemoryAgent,
        "category": "AI Agents",
        "description": "Conversational agent with multi-turn memory and session management",
        "version": "1.0.0",
        "tags": ["ai", "kaizen", "memory", "conversation", "session"],
        "icon": "brain",
        "color": "#7C3AED",  # Purple
    },
    "VisionAgent": {
        "class": VisionAgent,
        "category": "AI Agents",
        "description": "Multi-modal vision agent for image analysis, OCR, and visual Q&A",
        "version": "1.0.0",
        "tags": ["ai", "kaizen", "vision", "multi-modal", "image", "ocr"],
        "icon": "eye",
        "color": "#0891B2",  # Cyan
    },
    "ChainOfThoughtAgent": {
        "class": ChainOfThoughtAgent,
        "category": "AI Agents",
        "description": "Step-by-step reasoning agent with transparent thought process and verification",
        "version": "1.0.0",
        "tags": [
            "ai",
            "kaizen",
            "reasoning",
            "chain-of-thought",
            "verification",
            "step-by-step",
        ],
        "icon": "git-branch",
        "color": "#DC2626",  # Red
    },
    "RAGResearchAgent": {
        "class": RAGResearchAgent,
        "category": "AI Agents",
        "description": "Retrieval-Augmented Generation agent with semantic vector search and source attribution",
        "version": "1.0.0",
        "tags": [
            "ai",
            "kaizen",
            "rag",
            "research",
            "retrieval",
            "vector-search",
            "semantic",
        ],
        "icon": "search",
        "color": "#059669",  # Green
    },
    "CodeGenerationAgent": {
        "class": CodeGenerationAgent,
        "category": "AI Agents",
        "description": "Multi-language code generation with automatic tests and documentation",
        "version": "1.0.0",
        "tags": [
            "ai",
            "kaizen",
            "code-generation",
            "programming",
            "testing",
            "documentation",
        ],
        "icon": "code",
        "color": "#F59E0B",  # Amber
    },
    "ReActAgent": {
        "class": ReActAgent,
        "category": "AI Agents",
        "description": "Reasoning + Acting agent with iterative problem-solving and tool use",
        "version": "1.0.0",
        "tags": ["ai", "kaizen", "react", "reasoning", "tool-use", "multi-cycle"],
        "icon": "zap",
        "color": "#8B5CF6",  # Violet
    },
    "TranscriptionAgent": {
        "class": TranscriptionAgent,
        "category": "AI Agents",
        "description": "Multi-modal audio transcription agent with multi-language support using Whisper",
        "version": "1.0.0",
        "tags": [
            "ai",
            "kaizen",
            "audio",
            "transcription",
            "whisper",
            "speech-to-text",
            "multi-modal",
        ],
        "icon": "mic",
        "color": "#EA580C",  # Orange
    },
    "MultiModalAgent": {
        "class": MultiModalAgent,
        "category": "AI Agents",
        "description": "Unified multi-modal agent for vision, audio, and text processing with cost tracking",
        "version": "1.0.0",
        "tags": [
            "ai",
            "kaizen",
            "multi-modal",
            "vision",
            "audio",
            "unified",
            "cost-tracking",
        ],
        "icon": "layers",
        "color": "#06B6D4",  # Cyan
    },
    "BatchProcessingAgent": {
        "class": BatchProcessingAgent,
        "category": "AI Agents",
        "description": "Concurrent batch processing with high throughput and semaphore limiting",
        "version": "1.0.0",
        "tags": ["ai", "kaizen", "batch", "concurrent", "high-throughput", "parallel"],
        "icon": "database",
        "color": "#10B981",  # Emerald
    },
    "HumanApprovalAgent": {
        "class": HumanApprovalAgent,
        "category": "AI Agents",
        "description": "Human-in-the-loop decision making with approval callbacks and audit trails",
        "version": "1.0.0",
        "tags": ["ai", "kaizen", "human-in-loop", "approval", "compliance", "audit"],
        "icon": "user-check",
        "color": "#6366F1",  # Indigo
    },
    "ResilientAgent": {
        "class": ResilientAgent,
        "category": "AI Agents",
        "description": "Multi-model fallback for high availability and progressive degradation",
        "version": "1.0.0",
        "tags": [
            "ai",
            "kaizen",
            "fallback",
            "resilient",
            "high-availability",
            "redundancy",
        ],
        "icon": "shield",
        "color": "#EF4444",  # Red
    },
    "StreamingChatAgent": {
        "class": StreamingChatAgent,
        "category": "AI Agents",
        "description": "Real-time token-by-token streaming for interactive chat applications",
        "version": "1.0.0",
        "tags": ["ai", "kaizen", "streaming", "chat", "real-time", "interactive"],
        "icon": "message-square",
        "color": "#3B82F6",  # Blue
    },
    "SelfReflectionAgent": {
        "class": SelfReflectionAgent,
        "category": "AI Agents",
        "description": "Iterative self-improvement through reflection and quality convergence",
        "version": "1.0.0",
        "tags": [
            "ai",
            "kaizen",
            "reflection",
            "self-improvement",
            "quality",
            "iterative",
        ],
        "icon": "rotate-cw",
        "color": "#A855F7",  # Purple
    },
}


# Export all agents for convenience
__all__ = [
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
    "VisionAgent",
    "TranscriptionAgent",
    "MultiModalAgent",
    "KAIZEN_AGENTS",
]


def get_agent_class(agent_name: str):
    """
    Get agent class by name.

    Args:
        agent_name: Name of the agent (e.g., "SimpleQAAgent")

    Returns:
        Agent class or None if not found

    Example:
        >>> agent_cls = get_agent_class("SimpleQAAgent")
        >>> agent = agent_cls()
    """
    return KAIZEN_AGENTS.get(agent_name, {}).get("class")


def list_agents():
    """
    List all registered Kaizen agents with metadata.

    Returns:
        Dict mapping agent names to metadata

    Example:
        >>> agents = list_agents()
        >>> for name, info in agents.items():
        ...     print(f"{name}: {info['description']}")
        SimpleQAAgent: Simple question answering agent...
        MemoryAgent: Conversational agent with multi-turn memory...
    """
    return KAIZEN_AGENTS.copy()


def get_agent_count() -> int:
    """
    Get total count of registered Kaizen agents.

    Returns:
        Number of registered agents

    Example:
        >>> count = get_agent_count()
        >>> print(f"Registered agents: {count}")
        Registered agents: 14
    """
    return len(KAIZEN_AGENTS)


def register_agents_with_node_registry():
    """
    Register Kaizen agents with the Core SDK NodeRegistry.

    This enables Kaizen agents to be used in Kailash workflows
    via WorkflowBuilder.add_node() and discovered via NodeRegistry.list_nodes().

    Agent names follow the convention: {AgentName}Node
    (e.g., SimpleQAAgent -> SimpleQAAgentNode)

    Example:
        >>> from kailash.nodes import NodeRegistry
        >>> register_agents_with_node_registry()
        >>> 'SimpleQAAgentNode' in NodeRegistry.list_nodes()
        True
    """
    try:
        from kailash.nodes import NodeRegistry
        from kailash.nodes.base import Node
    except ImportError:
        # Core SDK not available - skip registration
        return

    for agent_name, metadata in KAIZEN_AGENTS.items():
        node_name = f"{agent_name}Node"
        agent_class = metadata.get("class")

        # Skip if not a valid class
        if agent_class is None or not isinstance(agent_class, type):
            continue

        # Skip if not a Node subclass (Kaizen agents inherit from Node)
        try:
            if not issubclass(agent_class, Node):
                continue
        except TypeError:
            # issubclass failed - skip
            continue

        try:
            # register(node_class, alias=None) - class first, then optional alias
            NodeRegistry.register(agent_class, alias=node_name)
        except (ValueError, KeyError, TypeError):
            # Already registered or registration failed - skip
            pass


# Auto-register agents when module is imported
register_agents_with_node_registry()
