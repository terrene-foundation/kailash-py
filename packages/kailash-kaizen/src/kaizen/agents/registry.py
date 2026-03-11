"""
Agent Registration System

Provides dual registration for Kaizen agents:
1. Agent API: For Agent(agent_type="...")
2. Core SDK: For WorkflowBuilder (auto-calls @register_node)

Usage:
    from kaizen.agents.registry import register_agent

    register_agent(
        name="react",
        agent_class=ReActAgent,
        description="Reasoning + Acting agent",
        category="specialized",
        tags=["reasoning", "tool-use"]
    )

    # Now available via both APIs:
    from kaizen import Agent
    agent = Agent(agent_type="react")  # Agent API

    # Also available in WorkflowBuilder
    from kailash.workflow.builder import WorkflowBuilder
    workflow = WorkflowBuilder()
    workflow.add_node("ReActAgent", "agent", {...})  # Core SDK

Part of ADR-020: Unified Agent API Architecture & Phase 1 Implementation
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Type

from kaizen.core.base_agent import BaseAgent

logger = logging.getLogger(__name__)


# =============================================================================
# Agent Type Registration Data Structure
# =============================================================================


@dataclass
class AgentRegistration:
    """
    Registration metadata for an agent.

    Stores all information needed to create an agent instance from a type string.
    """

    name: str
    """Agent type name (e.g., 'react', 'reflection', 'planning')"""

    agent_class: Type[BaseAgent]
    """Agent class to instantiate"""

    description: str
    """Human-readable description of agent capabilities"""

    default_strategy: Optional[Type] = None
    """Default execution strategy class (optional)"""

    preset_config: Dict[str, Any] = field(default_factory=dict)
    """Default configuration parameters"""

    factory: Optional[Callable] = None
    """Optional factory function for custom instantiation logic"""

    category: str = "general"
    """Agent category (specialized, autonomous, multimodal, enterprise)"""

    tags: list = field(default_factory=list)
    """Tags for discovery and filtering"""


# Backward compatibility alias
AgentTypeRegistration = AgentRegistration


# =============================================================================
# Global Agent Type Registry
# =============================================================================


_AGENT_REGISTRY: Dict[str, AgentRegistration] = {}
"""Global registry of agents"""

# Backward compatibility alias
_AGENT_TYPE_REGISTRY = _AGENT_REGISTRY


# =============================================================================
# Registration Functions
# =============================================================================


def register_agent(
    name: str,
    agent_class: Type[BaseAgent] = None,
    description: str = "",
    default_strategy: Type = None,
    preset_config: Dict[str, Any] = None,
    factory: Callable = None,
    category: str = "general",
    tags: list = None,
    override: bool = False,
) -> None:
    """
    Register agent with DUAL registration:
    1. Agent API: For Agent(agent_type="...")
    2. Core SDK: For WorkflowBuilder (auto-calls @register_node)

    This function automatically registers the agent with both Kaizen's Agent API
    and Kailash Core SDK's node registry, enabling seamless usage in both contexts.

    Args:
        name: Agent type name (lowercase, underscores for multi-word)
        agent_class: Agent class to instantiate (must extend BaseAgent)
        description: Human-readable description
        default_strategy: Default execution strategy class
        preset_config: Default configuration parameters
        factory: Optional factory function for custom instantiation
        category: Agent category - one of:
            - "specialized": Domain-specific single agents
            - "autonomous": Fully autonomous agents with planning
            - "multimodal": Multi-modal processing agents
            - "enterprise": Enterprise-grade agents (batch, approval, resilient)
        tags: Tags for discovery
        override: Allow overriding existing registration

    Raises:
        ValueError: If name already registered and override=False
        TypeError: If agent_class doesn't extend BaseAgent

    Example:
        >>> from kaizen.agents.specialized.react import ReActAgent
        >>> from kaizen.strategies.multi_cycle import MultiCycleStrategy
        >>>
        >>> register_agent(
        ...     name="react",
        ...     agent_class=ReActAgent,
        ...     description="Reasoning + Acting cycles",
        ...     default_strategy=MultiCycleStrategy,
        ...     preset_config={"max_cycles": 10},
        ...     category="specialized",
        ...     tags=["reasoning", "tool-use"],
        ... )
        >>>
        >>> # Now available via Agent API
        >>> from kaizen import Agent
        >>> agent = Agent(agent_type="react")
        >>>
        >>> # Also available in WorkflowBuilder
        >>> from kailash.workflow.builder import WorkflowBuilder
        >>> workflow = WorkflowBuilder()
        >>> workflow.add_node("ReActAgent", "agent", {})
    """
    # Validation
    if not name:
        raise ValueError("Agent type name cannot be empty")

    if name in _AGENT_REGISTRY and not override:
        raise ValueError(
            f"Agent '{name}' already registered. Use override=True to replace."
        )

    if agent_class and not issubclass(agent_class, BaseAgent):
        raise TypeError(
            f"Agent class must extend BaseAgent, got {agent_class.__name__}"
        )

    if not agent_class and not factory:
        raise ValueError("Must provide either agent_class or factory function")

    # Step 1: Agent API registration
    registration = AgentRegistration(
        name=name,
        agent_class=agent_class,
        description=description,
        default_strategy=default_strategy,
        preset_config=preset_config or {},
        factory=factory,
        category=category,
        tags=tags or [],
    )

    _AGENT_REGISTRY[name] = registration

    # Step 2: Auto-register with Core SDK (dual registration)
    if agent_class:  # Only if agent_class provided (not factory)
        try:
            from kailash.nodes.base import NodeRegistry

            # Register with Core SDK using NodeRegistry.register()
            # This makes the agent available as a WorkflowBuilder node
            NodeRegistry.register(agent_class, alias=agent_class.__name__)

            logger.info(
                f"✅ Dual registration complete for '{name}': "
                f"Agent API + Core SDK ({agent_class.__name__}, category: {category})"
            )
        except Exception as e:
            logger.warning(
                f"⚠️ Core SDK registration failed for '{name}': {e}. "
                f"Agent API registration still successful."
            )
    else:
        logger.info(
            f"Registered agent '{name}' (factory function, category: {category})"
        )


# Backward compatibility alias
register_agent_type = register_agent


def unregister_agent_type(name: str) -> None:
    """
    Unregister an agent type.

    Args:
        name: Agent type name to remove

    Raises:
        ValueError: If agent type not registered
    """
    if name not in _AGENT_TYPE_REGISTRY:
        raise ValueError(f"Agent type '{name}' not registered")

    del _AGENT_TYPE_REGISTRY[name]
    logger.info(f"Unregistered agent type '{name}'")


def get_agent_type_registration(name: str) -> AgentTypeRegistration:
    """
    Get registration metadata for an agent type.

    Args:
        name: Agent type name

    Returns:
        AgentTypeRegistration instance

    Raises:
        ValueError: If agent type not registered
    """
    if name not in _AGENT_TYPE_REGISTRY:
        raise ValueError(
            f"Unknown agent type '{name}'. "
            f"Available types: {list_agent_type_names()}"
        )

    return _AGENT_TYPE_REGISTRY[name]


def is_agent_type_registered(name: str) -> bool:
    """
    Check if agent type is registered.

    Args:
        name: Agent type name

    Returns:
        True if registered, False otherwise
    """
    return name in _AGENT_TYPE_REGISTRY


def list_agent_type_names() -> list:
    """
    Get list of registered agent type names.

    Returns:
        List of agent type names
    """
    return list(_AGENT_TYPE_REGISTRY.keys())


def list_agent_types(category: str = None) -> Dict[str, str]:
    """
    Get dictionary of agent types and descriptions.

    Args:
        category: Optional category filter

    Returns:
        Dict mapping agent type names to descriptions
    """
    types = {}
    for name, reg in _AGENT_TYPE_REGISTRY.items():
        if category is None or reg.category == category:
            types[name] = reg.description

    return types


def get_agent_types_by_tag(tag: str) -> list:
    """
    Get agent types with a specific tag.

    Args:
        tag: Tag to filter by

    Returns:
        List of agent type names with the tag
    """
    return [name for name, reg in _AGENT_TYPE_REGISTRY.items() if tag in reg.tags]


def get_agent_types_by_category(category: str) -> list:
    """
    Get agent types in a specific category.

    Args:
        category: Category to filter by

    Returns:
        List of agent type names in the category
    """
    return [
        name for name, reg in _AGENT_TYPE_REGISTRY.items() if reg.category == category
    ]


# =============================================================================
# Agent Creation from Registry
# =============================================================================


def create_agent_from_type(agent_type: str, model: str, **kwargs) -> BaseAgent:
    """
    Create agent instance from registered type.

    This is used by Agent.__init__() to instantiate the correct agent class
    based on the agent_type parameter.

    Args:
        agent_type: Registered agent type name
        model: LLM model name
        **kwargs: Additional configuration parameters

    Returns:
        BaseAgent instance

    Raises:
        ValueError: If agent type not registered

    Example:
        >>> agent = create_agent_from_type(
        ...     agent_type="react",
        ...     model="gpt-4",
        ...     max_cycles=5,
        ...     temperature=0.7,
        ... )
    """
    # Get registration
    registration = get_agent_type_registration(agent_type)

    # Merge preset config with kwargs
    config = {**registration.preset_config, **kwargs}
    config["model"] = model

    # Use factory if provided
    if registration.factory:
        logger.debug(f"Creating agent '{agent_type}' using factory function")
        return registration.factory(config=config)

    # Use agent class
    logger.debug(
        f"Creating agent '{agent_type}' "
        f"(class: {registration.agent_class.__name__})"
    )

    # Create config object if agent expects it
    # Most agents expect a domain-specific config object
    agent_instance = registration.agent_class(config=config)

    return agent_instance


# =============================================================================
# Decorator for Easy Registration
# =============================================================================


def agent_type(
    name: str,
    description: str = "",
    default_strategy: Type = None,
    preset_config: Dict[str, Any] = None,
    category: str = "general",
    tags: list = None,
):
    """
    Decorator for easy agent type registration.

    Args:
        name: Agent type name
        description: Human-readable description
        default_strategy: Default execution strategy
        preset_config: Default configuration
        category: Agent category
        tags: Tags for discovery

    Example:
        >>> from kaizen.agents.registry import agent_type
        >>> from kaizen.core.base_agent import BaseAgent
        >>>
        >>> @agent_type(
        ...     name="research",
        ...     description="Research agent with citation tracking",
        ...     category="specialized",
        ...     tags=["research", "citations"],
        ... )
        ... class ResearchAgent(BaseAgent):
        ...     def __init__(self, config):
        ...         super().__init__(config=config, signature=ResearchSignature())
    """

    def decorator(cls: Type[BaseAgent]):
        # Register the agent type
        register_agent_type(
            name=name,
            agent_class=cls,
            description=description,
            default_strategy=default_strategy,
            preset_config=preset_config,
            category=category,
            tags=tags,
        )
        return cls

    return decorator


# =============================================================================
# Utility Functions
# =============================================================================


def clear_registry():
    """
    Clear all registered agent types.

    WARNING: This is primarily for testing. Use with caution.
    """
    global _AGENT_TYPE_REGISTRY
    _AGENT_TYPE_REGISTRY = {}
    logger.warning("Cleared agent type registry")


def get_registry_info() -> dict:
    """
    Get information about the registry state.

    Returns:
        Dict with registry statistics and info
    """
    categories = {}
    tags = set()

    for reg in _AGENT_TYPE_REGISTRY.values():
        categories[reg.category] = categories.get(reg.category, 0) + 1
        tags.update(reg.tags)

    return {
        "total_types": len(_AGENT_TYPE_REGISTRY),
        "categories": categories,
        "unique_tags": len(tags),
        "all_tags": sorted(list(tags)),
    }


def print_registry_info():
    """Print human-readable registry information."""
    info = get_registry_info()

    print(f"\n{'='*70}")
    print("Agent Type Registry Info")
    print(f"{'='*70}")
    print(f"Total registered types: {info['total_types']}")
    print("\nBy category:")
    for category, count in sorted(info["categories"].items()):
        print(f"  {category}: {count}")
    print(f"\nUnique tags: {info['unique_tags']}")
    print(f"All tags: {', '.join(info['all_tags'])}")
    print(f"{'='*70}\n")
