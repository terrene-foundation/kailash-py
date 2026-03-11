"""
Agent Type Presets for Unified Agent API

Defines preset configurations for different agent behaviors:
- simple: Direct Q&A
- react: Reasoning + Action cycles
- cot: Chain of thought reasoning
- rag: Retrieval-augmented generation
- autonomous: Full autonomous agent
- vision: Vision processing
- audio: Audio transcription

Part of ADR-020: Unified Agent API Architecture
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from kaizen.signatures import InputField, OutputField, Signature

# =============================================================================
# Agent Type Preset Dataclass
# =============================================================================


@dataclass
class AgentTypePreset:
    """
    Preset configuration for an agent type.

    Defines the strategy, signature, and default configuration for each
    agent type pattern.
    """

    agent_type: str
    """Agent type identifier"""

    description: str
    """Human-readable description"""

    strategy: str
    """Execution strategy class name"""

    signature: Signature
    """Default signature for this agent type"""

    enable_tools: bool = False
    """Whether tools are enabled by default"""

    enable_memory: bool = True
    """Whether memory is enabled by default"""

    max_iterations: Optional[int] = None
    """Maximum iterations for iterative patterns (react, autonomous)"""

    show_reasoning: bool = False
    """Whether to show reasoning steps (cot)"""

    enable_planning: bool = False
    """Whether to enable planning phase (autonomous)"""

    enable_multimodal: bool = False
    """Whether to enable multimodal processing (vision, audio)"""

    retrieval_backend: Optional[str] = None
    """Retrieval backend for RAG agents"""

    additional_config: Dict[str, Any] = None
    """Additional type-specific configuration"""

    def __post_init__(self):
        """Post-initialization."""
        if self.additional_config is None:
            self.additional_config = {}


# =============================================================================
# Signature Definitions for Each Agent Type
# =============================================================================


class SimpleQASignature(Signature):
    """Simple question-answering signature."""

    prompt: str = InputField(description="User input or question")
    answer: str = OutputField(description="Agent response")


class ChainOfThoughtSignature(Signature):
    """Chain of thought reasoning signature."""

    prompt: str = InputField(description="Problem or question to solve")
    reasoning: str = OutputField(description="Step-by-step reasoning process")
    answer: str = OutputField(description="Final answer")


class ReActSignature(Signature):
    """ReAct (Reasoning + Action) signature."""

    prompt: str = InputField(description="Task or question")
    thought: str = OutputField(description="Reasoning about what to do")
    action: str = OutputField(description="Action to take")
    observation: str = OutputField(description="Result of the action")
    answer: str = OutputField(description="Final answer")


class RAGSignature(Signature):
    """Retrieval-Augmented Generation signature."""

    query: str = InputField(description="User query")
    retrieved_context: str = OutputField(description="Retrieved relevant information")
    answer: str = OutputField(description="Answer based on retrieved context")


class AutonomousSignature(Signature):
    """Autonomous agent signature with planning."""

    task: str = InputField(description="High-level task to accomplish")
    plan: str = OutputField(description="Multi-step plan")
    execution: str = OutputField(description="Execution log")
    result: str = OutputField(description="Task result")


class VisionSignature(Signature):
    """Vision processing signature."""

    image: str = InputField(description="Image file path or URL")
    question: str = InputField(description="Question about the image")
    answer: str = OutputField(description="Analysis of the image")


class AudioSignature(Signature):
    """Audio transcription signature."""

    audio: str = InputField(description="Audio file path or URL")
    language: str = InputField(description="Language code (optional)", default="en")
    transcription: str = OutputField(description="Transcribed text")


# =============================================================================
# Agent Type Preset Registry
# =============================================================================


AGENT_TYPE_PRESETS: Dict[str, AgentTypePreset] = {
    "simple": AgentTypePreset(
        agent_type="simple",
        description="Direct question-answering with no special processing",
        strategy="AsyncSingleShotStrategy",
        signature=SimpleQASignature(),
        enable_tools=False,
        enable_memory=True,
        show_reasoning=False,
        additional_config={
            "use_case": "Simple questions, quick answers",
            "best_for": "Basic Q&A, information lookup, simple tasks",
        },
    ),
    "react": AgentTypePreset(
        agent_type="react",
        description="Reasoning + Action cycles with tool calling",
        strategy="ReActStrategy",
        signature=ReActSignature(),
        enable_tools=True,
        enable_memory=True,
        max_iterations=10,
        show_reasoning=True,
        additional_config={
            "use_case": "Tasks requiring tools and multi-step reasoning",
            "best_for": "File operations, API calls, complex workflows",
        },
    ),
    "cot": AgentTypePreset(
        agent_type="cot",
        description="Chain of thought step-by-step reasoning",
        strategy="ChainOfThoughtStrategy",
        signature=ChainOfThoughtSignature(),
        enable_tools=False,
        enable_memory=True,
        show_reasoning=True,
        additional_config={
            "use_case": "Complex reasoning and problem solving",
            "best_for": "Math problems, logic puzzles, step-by-step analysis",
        },
    ),
    "rag": AgentTypePreset(
        agent_type="rag",
        description="Retrieval-Augmented Generation with document retrieval",
        strategy="RAGStrategy",
        signature=RAGSignature(),
        enable_tools=True,
        enable_memory=True,
        retrieval_backend="semantic",
        additional_config={
            "use_case": "Knowledge-intensive tasks with document retrieval",
            "best_for": "Research, documentation search, knowledge base queries",
        },
    ),
    "autonomous": AgentTypePreset(
        agent_type="autonomous",
        description="Full autonomous agent with planning and execution",
        strategy="AutonomousStrategy",
        signature=AutonomousSignature(),
        enable_tools=True,
        enable_memory=True,
        enable_planning=True,
        max_iterations=20,
        show_reasoning=True,
        additional_config={
            "use_case": "Complex multi-step tasks requiring autonomous execution",
            "best_for": "Project planning, data analysis workflows, complex automation",
        },
    ),
    "vision": AgentTypePreset(
        agent_type="vision",
        description="Vision processing with image analysis",
        strategy="VisionStrategy",
        signature=VisionSignature(),
        enable_tools=False,
        enable_memory=True,
        enable_multimodal=True,
        additional_config={
            "use_case": "Image analysis and understanding",
            "best_for": "OCR, image Q&A, visual content analysis",
        },
    ),
    "audio": AgentTypePreset(
        agent_type="audio",
        description="Audio transcription with speech-to-text",
        strategy="AudioStrategy",
        signature=AudioSignature(),
        enable_tools=False,
        enable_memory=True,
        enable_multimodal=True,
        additional_config={
            "use_case": "Audio transcription and speech processing",
            "best_for": "Transcription, voice commands, audio analysis",
        },
    ),
}


# =============================================================================
# Helper Functions
# =============================================================================


def get_agent_type_preset(agent_type: str) -> AgentTypePreset:
    """
    Get preset configuration for an agent type.

    Args:
        agent_type: Agent type identifier

    Returns:
        AgentTypePreset configuration

    Raises:
        ValueError: If agent type is not recognized

    Example:
        >>> preset = get_agent_type_preset("react")
        >>> print(preset.description)
        'Reasoning + Action cycles with tool calling'
    """
    if agent_type not in AGENT_TYPE_PRESETS:
        available_types = ", ".join(AGENT_TYPE_PRESETS.keys())
        raise ValueError(
            f"Unknown agent type: {agent_type}. " f"Available types: {available_types}"
        )

    return AGENT_TYPE_PRESETS[agent_type]


def list_agent_types() -> Dict[str, str]:
    """
    List all available agent types with descriptions.

    Returns:
        Dictionary mapping agent_type to description

    Example:
        >>> types = list_agent_types()
        >>> for agent_type, description in types.items():
        ...     print(f"{agent_type}: {description}")
        simple: Direct question-answering with no special processing
        react: Reasoning + Action cycles with tool calling
        ...
    """
    return {
        agent_type: preset.description
        for agent_type, preset in AGENT_TYPE_PRESETS.items()
    }


def validate_agent_type(agent_type: str) -> bool:
    """
    Validate if an agent type exists.

    Args:
        agent_type: Agent type to validate

    Returns:
        True if valid, False otherwise

    Example:
        >>> validate_agent_type("react")
        True
        >>> validate_agent_type("invalid")
        False
    """
    return agent_type in AGENT_TYPE_PRESETS


def get_preset_config(agent_type: str) -> Dict[str, Any]:
    """
    Get preset configuration as dictionary.

    Args:
        agent_type: Agent type identifier

    Returns:
        Configuration dictionary

    Example:
        >>> config = get_preset_config("react")
        >>> print(config["enable_tools"])
        True
        >>> print(config["max_iterations"])
        10
    """
    preset = get_agent_type_preset(agent_type)

    return {
        "agent_type": preset.agent_type,
        "description": preset.description,
        "strategy": preset.strategy,
        "enable_tools": preset.enable_tools,
        "enable_memory": preset.enable_memory,
        "max_iterations": preset.max_iterations,
        "show_reasoning": preset.show_reasoning,
        "enable_planning": preset.enable_planning,
        "enable_multimodal": preset.enable_multimodal,
        "retrieval_backend": preset.retrieval_backend,
        **preset.additional_config,
    }


def print_agent_type_info(agent_type: str) -> None:
    """
    Print detailed information about an agent type.

    Args:
        agent_type: Agent type identifier

    Example:
        >>> print_agent_type_info("react")
        Agent Type: react
        Description: Reasoning + Action cycles with tool calling
        Strategy: ReActStrategy
        Tools Enabled: True
        Memory Enabled: True
        Max Iterations: 10
        Use Case: Tasks requiring tools and multi-step reasoning
        Best For: File operations, API calls, complex workflows
    """
    preset = get_agent_type_preset(agent_type)

    print(f"Agent Type: {preset.agent_type}")
    print(f"Description: {preset.description}")
    print(f"Strategy: {preset.strategy}")
    print(f"Tools Enabled: {preset.enable_tools}")
    print(f"Memory Enabled: {preset.enable_memory}")

    if preset.max_iterations:
        print(f"Max Iterations: {preset.max_iterations}")

    if preset.show_reasoning:
        print(f"Show Reasoning: {preset.show_reasoning}")

    if preset.enable_planning:
        print(f"Planning Enabled: {preset.enable_planning}")

    if preset.enable_multimodal:
        print(f"Multimodal: {preset.enable_multimodal}")

    if preset.retrieval_backend:
        print(f"Retrieval Backend: {preset.retrieval_backend}")

    print(f"Use Case: {preset.additional_config.get('use_case', 'N/A')}")
    print(f"Best For: {preset.additional_config.get('best_for', 'N/A')}")


# =============================================================================
# CLI Helper (for debugging)
# =============================================================================


if __name__ == "__main__":
    print("Available Agent Types:")
    print("=" * 70)

    for agent_type, description in list_agent_types().items():
        print(f"\n{agent_type.upper()}")
        print("-" * 70)
        print_agent_type_info(agent_type)
