"""
Capability Presets for Unified Agent API

This module provides pre-configured capability combinations for common use cases.
Presets are the recommended starting point for most users.
"""

from typing import Any, Dict, Optional

from kaizen.api.types import AgentCapabilities, ExecutionMode, MemoryDepth, ToolAccess


class CapabilityPresets:
    """
    Pre-configured capability combinations for common agent use cases.

    Use presets to quickly configure agents for specific tasks without
    needing to understand all configuration options.

    Examples:
        # Simple Q&A assistant
        config = CapabilityPresets.qa_assistant()
        agent = Agent(model="gpt-4", **config)

        # Developer assistant with full capabilities
        config = CapabilityPresets.developer()
        agent = Agent(model="claude-3-opus", **config)

        # Custom preset with overrides
        config = CapabilityPresets.researcher(max_cycles=100)
        agent = Agent(model="gpt-4", **config)
    """

    @staticmethod
    def qa_assistant(
        model: str = "gpt-4",
        **overrides,
    ) -> Dict[str, Any]:
        """
        Simple Q&A assistant configuration.

        Best for: Simple question answering, explanations, definitions.
        - Single-shot execution
        - Stateless memory (no conversation history)
        - No tool access

        Args:
            model: Model to use (default: gpt-4)
            **overrides: Override any configuration values

        Returns:
            Configuration dictionary for Agent constructor

        Example:
            agent = Agent(**CapabilityPresets.qa_assistant())
            result = agent.run("What is IRP?")
        """
        config = {
            "model": model,
            "execution_mode": "single",
            "memory": "stateless",
            "tool_access": "none",
            "max_cycles": 1,
            "timeout_seconds": 60.0,
        }
        config.update(overrides)
        return config

    @staticmethod
    def tutor(
        model: str = "gpt-4",
        max_turns: int = 50,
        **overrides,
    ) -> Dict[str, Any]:
        """
        Educational tutor configuration.

        Best for: Teaching, tutoring, guided learning, explanations.
        - Multi-turn conversation
        - Session memory (remembers context)
        - No tool access (pure dialogue)

        Args:
            model: Model to use (default: gpt-4)
            max_turns: Maximum conversation turns (default: 50)
            **overrides: Override any configuration values

        Returns:
            Configuration dictionary for Agent constructor

        Example:
            agent = Agent(**CapabilityPresets.tutor())
            result = agent.chat("Teach me about recursion")
            result = agent.chat("Can you give me an example?")
        """
        config = {
            "model": model,
            "execution_mode": "multi",
            "memory": "session",
            "tool_access": "none",
            "max_turns": max_turns,
            "timeout_seconds": 300.0,
        }
        config.update(overrides)
        return config

    @staticmethod
    def researcher(
        model: str = "gpt-4",
        max_cycles: int = 50,
        **overrides,
    ) -> Dict[str, Any]:
        """
        Autonomous researcher configuration.

        Best for: Research, investigation, analysis, code review.
        - Autonomous execution (TAOD loop)
        - Session memory
        - Read-only tool access (safe exploration)

        Args:
            model: Model to use (default: gpt-4)
            max_cycles: Maximum TAOD cycles (default: 50)
            **overrides: Override any configuration values

        Returns:
            Configuration dictionary for Agent constructor

        Example:
            agent = Agent(**CapabilityPresets.researcher())
            result = agent.run("Analyze the authentication module and identify security issues")
        """
        config = {
            "model": model,
            "execution_mode": "autonomous",
            "memory": "session",
            "tool_access": "read_only",
            "max_cycles": max_cycles,
            "timeout_seconds": 600.0,
        }
        config.update(overrides)
        return config

    @staticmethod
    def developer(
        model: str = "gpt-4",
        max_cycles: int = 100,
        **overrides,
    ) -> Dict[str, Any]:
        """
        Full-capability developer assistant configuration.

        Best for: Code generation, debugging, implementation, refactoring.
        - Autonomous execution (TAOD loop)
        - Session memory
        - Constrained tool access (read, write, safe execution)

        Args:
            model: Model to use (default: gpt-4)
            max_cycles: Maximum TAOD cycles (default: 100)
            **overrides: Override any configuration values

        Returns:
            Configuration dictionary for Agent constructor

        Example:
            agent = Agent(**CapabilityPresets.developer())
            result = agent.run("Implement a REST API endpoint for user authentication")
        """
        config = {
            "model": model,
            "execution_mode": "autonomous",
            "memory": "session",
            "tool_access": "constrained",
            "max_cycles": max_cycles,
            "timeout_seconds": 900.0,  # 15 minutes for complex tasks
        }
        config.update(overrides)
        return config

    @staticmethod
    def admin(
        model: str = "gpt-4",
        max_cycles: int = 100,
        **overrides,
    ) -> Dict[str, Any]:
        """
        Administrative agent with full tool access.

        Best for: System administration, deployment, automation.
        - Autonomous execution (TAOD loop)
        - Persistent memory
        - Full tool access (including dangerous operations)

        ⚠️ WARNING: This preset allows dangerous operations.
        Only use with trusted models and proper access controls.

        Args:
            model: Model to use (default: gpt-4)
            max_cycles: Maximum TAOD cycles (default: 100)
            **overrides: Override any configuration values

        Returns:
            Configuration dictionary for Agent constructor

        Example:
            agent = Agent(**CapabilityPresets.admin())
            result = agent.run("Deploy the new version to staging")
        """
        config = {
            "model": model,
            "execution_mode": "autonomous",
            "memory": "persistent",
            "tool_access": "full",
            "max_cycles": max_cycles,
            "timeout_seconds": 1800.0,  # 30 minutes for admin tasks
        }
        config.update(overrides)
        return config

    @staticmethod
    def chat_assistant(
        model: str = "gpt-4",
        max_turns: int = 100,
        memory_path: Optional[str] = None,
        **overrides,
    ) -> Dict[str, Any]:
        """
        Conversational chat assistant with persistent memory.

        Best for: Personal assistants, support agents, long-running conversations.
        - Multi-turn conversation
        - Persistent memory (remembers across sessions)
        - No tool access (pure dialogue)

        Args:
            model: Model to use (default: gpt-4)
            max_turns: Maximum conversation turns (default: 100)
            memory_path: Path for persistent memory storage
            **overrides: Override any configuration values

        Returns:
            Configuration dictionary for Agent constructor

        Example:
            agent = Agent(**CapabilityPresets.chat_assistant(memory_path="./data/chat"))
            result = agent.chat("Remember that my favorite color is blue")
            # Later session...
            result = agent.chat("What's my favorite color?")  # Remembers!
        """
        config = {
            "model": model,
            "execution_mode": "multi",
            "memory": "persistent",
            "memory_path": memory_path or "./data/chat_memory",
            "tool_access": "none",
            "max_turns": max_turns,
            "timeout_seconds": 300.0,
        }
        config.update(overrides)
        return config

    @staticmethod
    def data_analyst(
        model: str = "gpt-4",
        max_cycles: int = 50,
        **overrides,
    ) -> Dict[str, Any]:
        """
        Data analysis agent configuration.

        Best for: Data analysis, visualization, report generation.
        - Autonomous execution
        - Session memory
        - Constrained tools (read, write, python execution)

        Args:
            model: Model to use (default: gpt-4)
            max_cycles: Maximum TAOD cycles (default: 50)
            **overrides: Override any configuration values

        Returns:
            Configuration dictionary for Agent constructor

        Example:
            agent = Agent(**CapabilityPresets.data_analyst())
            result = agent.run("Analyze sales.csv and create a summary report")
        """
        config = {
            "model": model,
            "execution_mode": "autonomous",
            "memory": "session",
            "tool_access": "constrained",
            "allowed_tools": [
                "read",
                "glob",
                "grep",
                "list",
                "write",
                "python",
            ],
            "max_cycles": max_cycles,
            "timeout_seconds": 600.0,
        }
        config.update(overrides)
        return config

    @staticmethod
    def code_reviewer(
        model: str = "claude-3-opus",  # Claude excels at code review
        max_cycles: int = 30,
        **overrides,
    ) -> Dict[str, Any]:
        """
        Code review agent configuration.

        Best for: Code review, security analysis, best practices.
        - Autonomous execution
        - Session memory
        - Read-only access (safe code exploration)

        Args:
            model: Model to use (default: claude-3-opus)
            max_cycles: Maximum TAOD cycles (default: 30)
            **overrides: Override any configuration values

        Returns:
            Configuration dictionary for Agent constructor

        Example:
            agent = Agent(**CapabilityPresets.code_reviewer())
            result = agent.run("Review the authentication module for security issues")
        """
        config = {
            "model": model,
            "execution_mode": "autonomous",
            "memory": "session",
            "tool_access": "read_only",
            "max_cycles": max_cycles,
            "timeout_seconds": 600.0,
        }
        config.update(overrides)
        return config

    @staticmethod
    def custom(
        execution_mode: str = "single",
        memory: str = "stateless",
        tool_access: str = "none",
        **overrides,
    ) -> Dict[str, Any]:
        """
        Create a custom preset with specified capabilities.

        Use this when the predefined presets don't match your needs.

        Args:
            execution_mode: Execution mode ("single", "multi", "autonomous")
            memory: Memory type ("stateless", "session", "persistent", "learning")
            tool_access: Tool access level ("none", "read_only", "constrained", "full")
            **overrides: Additional configuration values

        Returns:
            Configuration dictionary for Agent constructor

        Example:
            config = CapabilityPresets.custom(
                execution_mode="autonomous",
                memory="persistent",
                tool_access="constrained",
                max_cycles=75,
                timeout_seconds=1200.0,
            )
            agent = Agent(model="gpt-4", **config)
        """
        config = {
            "execution_mode": execution_mode,
            "memory": memory,
            "tool_access": tool_access,
        }
        config.update(overrides)
        return config

    @classmethod
    def list_presets(cls) -> Dict[str, str]:
        """
        List all available presets with descriptions.

        Returns:
            Dictionary of preset names to descriptions
        """
        return {
            "qa_assistant": "Simple Q&A, no memory or tools",
            "tutor": "Educational assistant with conversation memory",
            "researcher": "Autonomous research with read-only tools",
            "developer": "Full development capabilities with constrained tools",
            "admin": "Administrative agent with full tool access (dangerous)",
            "chat_assistant": "Conversational assistant with persistent memory",
            "data_analyst": "Data analysis with constrained tools",
            "code_reviewer": "Code review with read-only access",
            "custom": "Build your own preset",
        }

    @classmethod
    def get_preset(cls, name: str, **kwargs) -> Dict[str, Any]:
        """
        Get a preset by name.

        Args:
            name: Preset name
            **kwargs: Override values

        Returns:
            Configuration dictionary

        Raises:
            ValueError: If preset name is not recognized

        Example:
            config = CapabilityPresets.get_preset("developer", max_cycles=200)
        """
        presets = {
            "qa_assistant": cls.qa_assistant,
            "tutor": cls.tutor,
            "researcher": cls.researcher,
            "developer": cls.developer,
            "admin": cls.admin,
            "chat_assistant": cls.chat_assistant,
            "data_analyst": cls.data_analyst,
            "code_reviewer": cls.code_reviewer,
            "custom": cls.custom,
        }

        if name not in presets:
            valid = ", ".join(presets.keys())
            raise ValueError(f"Unknown preset: '{name}'. Valid presets: {valid}")

        return presets[name](**kwargs)


# Convenience function for quick preset access
def preset(name: str, **kwargs) -> Dict[str, Any]:
    """
    Quick access to capability presets.

    Args:
        name: Preset name
        **kwargs: Override values

    Returns:
        Configuration dictionary

    Example:
        agent = Agent(**preset("developer", model="claude-3-opus"))
    """
    return CapabilityPresets.get_preset(name, **kwargs)
