"""
Register Builtin Agents with Registry

Automatically registers all builtin Kaizen agents with the agent type registry
so they can be used with Agent(agent_type="...").

This module is imported by agents/__init__.py to ensure all builtin agents
are registered on import.

Part of ADR-020: Unified Agent API Architecture
"""

# Import autonomous agents
from kaizen.agents.autonomous.base import BaseAutonomousAgent
from kaizen.agents.autonomous.claude_code import ClaudeCodeAgent
from kaizen.agents.autonomous.codex import CodexAgent

# Import multi-agent coordination pattern (document extraction agent is internal-only)
from kaizen.agents.multi_modal.document_extraction_agent import DocumentExtractionAgent
from kaizen.agents.multi_modal.multi_modal_agent import MultiModalAgent
from kaizen.agents.multi_modal.transcription_agent import TranscriptionAgent

# Import multi-modal agents
from kaizen.agents.multi_modal.vision_agent import VisionAgent
from kaizen.agents.registry import register_agent
from kaizen.agents.specialized.batch_processing import BatchProcessingAgent
from kaizen.agents.specialized.chain_of_thought import ChainOfThoughtAgent
from kaizen.agents.specialized.code_generation import CodeGenerationAgent
from kaizen.agents.specialized.human_approval import HumanApprovalAgent
from kaizen.agents.specialized.memory_agent import MemoryAgent
from kaizen.agents.specialized.rag_research import RAGResearchAgent
from kaizen.agents.specialized.react import ReActAgent
from kaizen.agents.specialized.resilient import ResilientAgent
from kaizen.agents.specialized.self_reflection import SelfReflectionAgent

# Import all builtin agent classes
from kaizen.agents.specialized.simple_qa import SimpleQAAgent
from kaizen.agents.specialized.streaming_chat import StreamingChatAgent

# =============================================================================
# Register Specialized Agents
# =============================================================================


def register_builtin_agents():
    """
    Register all builtin agents with the registry.

    This function is called automatically when importing kaizen.agents,
    making all builtin agents available for use with Agent(agent_type="...").
    """

    # =============================================================================
    # Specialized Agents
    # =============================================================================

    # Simple QA Agent
    register_agent(
        name="simple",
        agent_class=SimpleQAAgent,
        description="Direct question-answering with no special processing",
        category="specialized",
        tags=["qa", "simple", "basic"],
    )

    # ReAct Agent
    register_agent(
        name="react",
        agent_class=ReActAgent,
        description="Reasoning + Action cycles with tool calling",
        category="specialized",
        tags=["reasoning", "tool-use", "iterative"],
    )

    # Chain of Thought Agent
    register_agent(
        name="cot",
        agent_class=ChainOfThoughtAgent,
        description="Chain of thought step-by-step reasoning",
        category="specialized",
        tags=["reasoning", "step-by-step", "analysis"],
    )

    # RAG Research Agent
    register_agent(
        name="rag",
        agent_class=RAGResearchAgent,
        description="Retrieval-Augmented Generation with document retrieval",
        category="specialized",
        tags=["rag", "retrieval", "research", "knowledge"],
    )

    # Memory Agent
    register_agent(
        name="memory",
        agent_class=MemoryAgent,
        description="Agent with enhanced memory and context tracking",
        category="specialized",
        tags=["memory", "context", "stateful"],
    )

    # Code Generation Agent
    register_agent(
        name="code",
        agent_class=CodeGenerationAgent,
        description="Code generation and programming assistance",
        category="specialized",
        tags=["code", "programming", "generation"],
    )

    # Self-Reflection Agent
    register_agent(
        name="reflection",
        agent_class=SelfReflectionAgent,
        description="Self-reflecting agent with iterative improvement",
        category="specialized",
        tags=["reflection", "improvement", "iterative"],
    )

    # Streaming Chat Agent
    register_agent(
        name="streaming",
        agent_class=StreamingChatAgent,
        description="Real-time streaming chat responses",
        category="specialized",
        tags=["streaming", "chat", "real-time"],
    )

    # =============================================================================
    # Enterprise Agents
    # =============================================================================

    # Batch Processing Agent
    register_agent(
        name="batch",
        agent_class=BatchProcessingAgent,
        description="High-throughput batch processing",
        category="enterprise",
        tags=["batch", "throughput", "concurrent"],
    )

    # Human Approval Agent
    register_agent(
        name="approval",
        agent_class=HumanApprovalAgent,
        description="Human-in-the-loop with approval workflow",
        category="enterprise",
        tags=["human-in-loop", "approval", "compliance"],
    )

    # Resilient Agent
    register_agent(
        name="resilient",
        agent_class=ResilientAgent,
        description="Fault-tolerant agent with retry and fallback",
        category="enterprise",
        tags=["resilient", "fault-tolerant", "retry"],
    )

    # =============================================================================
    # Multi-Modal Agents
    # =============================================================================

    # Vision Agent
    register_agent(
        name="vision",
        agent_class=VisionAgent,
        description="Vision processing with image analysis",
        category="multimodal",
        tags=["vision", "image", "ocr", "analysis"],
    )

    # Transcription Agent (Audio)
    register_agent(
        name="audio",
        agent_class=TranscriptionAgent,
        description="Audio transcription with speech-to-text",
        category="multimodal",
        tags=["audio", "transcription", "speech"],
    )

    # Multi-Modal Agent
    register_agent(
        name="multimodal",
        agent_class=MultiModalAgent,
        description="Multi-modal processing (vision + audio + text)",
        category="multimodal",
        tags=["multimodal", "vision", "audio", "text"],
    )

    # Document Extraction Agent (internal use, opt-in via VisionAgent/MultiModalAgent)
    register_agent(
        name="document_extraction",
        agent_class=DocumentExtractionAgent,
        description="Document extraction with RAG chunking (PDF, DOCX, TXT)",
        category="multimodal",
        tags=["document", "extraction", "rag", "pdf"],
    )

    # =============================================================================
    # Autonomous Agents
    # =============================================================================

    # Base Autonomous Agent
    register_agent(
        name="autonomous",
        agent_class=BaseAutonomousAgent,
        description="Autonomous agent with planning and execution",
        category="autonomous",
        tags=["autonomous", "planning", "execution"],
    )

    # Claude Code Agent
    register_agent(
        name="claude_code",
        agent_class=ClaudeCodeAgent,
        description="Autonomous coding agent based on Claude Code patterns",
        category="autonomous",
        tags=["autonomous", "coding", "claude"],
    )

    # Codex Agent
    register_agent(
        name="codex",
        agent_class=CodexAgent,
        description="Autonomous code generation agent",
        category="autonomous",
        tags=["autonomous", "codegen", "openai"],
    )


# =============================================================================
# Auto-Registration on Import
# =============================================================================

# Automatically register all builtin agents when this module is imported
register_builtin_agents()
