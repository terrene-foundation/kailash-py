"""
Kaizen - Advanced AI agent framework built on Kailash SDK

This package provides signature-based programming, enterprise memory systems,
auto-optimization, and enhanced AI agent capabilities built on top of the
proven Kailash SDK infrastructure.
"""

__version__ = "2.1.1"
__author__ = "Terrene Foundation"
__license__ = "Apache-2.0"

# UNIFIED AGENT API (ADR-020) - Primary user-facing agent
from kaizen.agent import Agent  # NEW: Unified Agent with 3-layer architecture

# Import nodes module to trigger agent registration
# This makes Kaizen agents discoverable to WorkflowBuilder and Studio
from kaizen.agents import nodes as _agent_nodes  # noqa: F401

# Core framework components
from kaizen.core.agents import (  # Legacy agent for internal use; noqa: F401 - Re-exported for backward compatibility
    Agent as CoreAgent,
)
from kaizen.core.agents import AgentManager
from kaizen.core.config import KaizenConfig, _global_config_manager

# PERFORMANCE OPTIMIZED: Core framework exports for <100ms import
from kaizen.core.framework import Kaizen

# Signature classes (Option 3: DSPy-inspired)
from kaizen.signatures import InputField, OutputField, Signature

# Backward compatibility alias
Framework = Kaizen


# Global configuration convenience functions
def configure(**kwargs):
    """
    Configure Kaizen framework globally.

    This provides a convenient way to set framework-wide configuration
    that will be applied to new Kaizen instances unless explicitly overridden.

    Args:
        **kwargs: Configuration parameters

    Examples:
        >>> import kaizen
        >>> kaizen.configure(
        ...     signature_programming_enabled=True,
        ...     mcp_integration_enabled=True,
        ...     multi_agent_coordination=True,
        ...     transparency_enabled=True
        ... )
        >>> agent = kaizen.create_agent("processor")  # Uses global config
    """
    _global_config_manager.configure(**kwargs)


def load_config_from_env(prefix: str = "KAIZEN_"):
    """
    Load configuration from environment variables.

    Args:
        prefix: Environment variable prefix (default: "KAIZEN_")

    Returns:
        Dict of loaded configuration

    Examples:
        >>> import os
        >>> os.environ["KAIZEN_SIGNATURE_PROGRAMMING_ENABLED"] = "true"
        >>> config = kaizen.load_config_from_env()
        >>> print(config["signature_programming_enabled"])  # True
    """
    return _global_config_manager.load_from_env(prefix)


def load_config_from_file(file_path: str):
    """
    Load configuration from file (YAML, JSON, or TOML).

    Args:
        file_path: Path to configuration file

    Returns:
        Dict of loaded configuration

    Examples:
        >>> config = kaizen.load_config_from_file("kaizen.yaml")
        >>> kaizen.configure(**config)
    """
    return _global_config_manager.load_from_file(file_path)


def auto_discover_config():
    """
    Auto-discover and load configuration files from standard locations.

    Searches for kaizen.{toml,yaml,yml,json} in:
    - Current directory
    - ~/.config/kaizen/
    - ~/.kaizen/
    - /etc/kaizen/

    Returns:
        Path of loaded config file or None if not found

    Examples:
        >>> config_file = kaizen.auto_discover_config()
        >>> if config_file:
        ...     print(f"Loaded config from: {config_file}")
    """
    return _global_config_manager.auto_discover_config_files()


def create_agent(name: str = None, config: dict = None, **kwargs):
    """
    Create an agent with resolved global configuration.

    This is a convenience function that creates a Kaizen instance with
    resolved configuration (environment, files, global) and then creates
    an agent.

    Args:
        name: Agent name
        config: Explicit agent configuration (overrides global config)
        **kwargs: Additional agent parameters

    Returns:
        Agent instance

    Examples:
        >>> kaizen.configure(signature_programming_enabled=True)
        >>> agent = kaizen.create_agent("processor", {"model": "gpt-4"})
    """
    # Create Kaizen instance with resolved configuration
    kaizen_config = _global_config_manager.create_kaizen_config()
    framework = Kaizen(config=kaizen_config)

    # Create agent
    return framework.create_agent(agent_id=name, config=config, **kwargs)


def get_resolved_config(explicit_config: dict = None) -> dict:
    """
    Get the current resolved configuration.

    Shows the final configuration after applying precedence rules:
    1. File configuration (lowest priority)
    2. Environment variables
    3. Global configuration (kaizen.configure())
    4. Explicit parameters (highest priority)

    Args:
        explicit_config: Optional explicit configuration to merge

    Returns:
        Dict of resolved configuration

    Examples:
        >>> kaizen.configure(debug=True)
        >>> config = kaizen.get_resolved_config()
        >>> print(config["debug"])  # True
    """
    return _global_config_manager.resolve_config(explicit_config)


def clear_global_config():
    """
    Clear all global configuration.

    Useful for testing or resetting configuration state.

    Examples:
        >>> kaizen.configure(debug=True)
        >>> kaizen.clear_global_config()
        >>> config = kaizen.get_resolved_config()
        >>> print(config.get("debug", False))  # False
    """
    _global_config_manager.clear()


# Google A2A (Agent-to-Agent) Components - Re-export from Kailash SDK
# Full Google A2A protocol support for multi-agent systems
try:
    from kaizen.nodes.ai.a2a import (  # Agent Cards and Capabilities; Task Management; Factory Functions
        A2AAgentCard,
        A2ATask,
        Capability,
        CapabilityLevel,
        CollaborationStyle,
        Insight,
        InsightType,
        PerformanceMetrics,
        ResourceRequirements,
        TaskIteration,
        TaskPriority,
        TaskState,
        TaskValidator,
        create_coding_agent_card,
        create_implementation_task,
        create_qa_agent_card,
        create_research_agent_card,
        create_research_task,
        create_validation_task,
    )

    _a2a_available = True
except ImportError:
    _a2a_available = False

# Convenience imports for common usage
__all__ = [
    "__version__",
    "__author__",
    "__license__",
    "Kaizen",
    "Framework",  # Backward compatibility
    "KaizenConfig",
    "Agent",
    "AgentManager",
    # Signature classes (Option 3)
    "Signature",
    "InputField",
    "OutputField",
    # Global configuration functions
    "configure",
    "load_config_from_env",
    "load_config_from_file",
    "auto_discover_config",
    "create_agent",
    "get_resolved_config",
    "clear_global_config",
]

# Add A2A components to __all__ if available
if _a2a_available:
    __all__.extend(
        [
            # Agent Cards and Capabilities
            "A2AAgentCard",
            "Capability",
            "CapabilityLevel",
            "CollaborationStyle",
            "PerformanceMetrics",
            "ResourceRequirements",
            # Task Management
            "A2ATask",
            "TaskState",
            "TaskPriority",
            "TaskValidator",
            "Insight",
            "InsightType",
            "TaskIteration",
            # Factory Functions
            "create_research_agent_card",
            "create_coding_agent_card",
            "create_qa_agent_card",
            "create_research_task",
            "create_implementation_task",
            "create_validation_task",
        ]
    )

# Package metadata
__pkg_info__ = {
    "name": "kailash-kaizen",
    "version": __version__,
    "description": "Advanced AI agent framework built on Kailash SDK",
    "url": "https://github.com/terrene-foundation/kailash-py",
    "license": __license__,
}
