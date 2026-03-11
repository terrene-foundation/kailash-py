"""
Unified Agent API for Kaizen Framework

Single entry point for all agent types with 3-layer architecture:
- Layer 1 (Zero-Config): Everything works with defaults
- Layer 2 (Configuration): agent_type and behavioral parameters
- Layer 3 (Expert Override): Custom implementations

Part of ADR-020: Unified Agent API Architecture

Example (Layer 1 - Zero-Config):
    >>> from kaizen import Agent
    >>> agent = Agent(model="gpt-4")
    >>> result = agent.run("What is AI?")

Example (Layer 2 - Configuration):
    >>> agent = Agent(
    ...     model="gpt-4",
    ...     agent_type="react",
    ...     memory_turns=20,
    ...     tools=["read_file", "http_get"],
    ...     budget_limit_usd=5.0,
    ... )

Example (Layer 3 - Expert Override):
    >>> agent = Agent(
    ...     model="gpt-4",
    ...     custom_memory=RedisMemory(),
    ...     custom_mcp_servers=[{"name": "custom", "command": "python", "args": ["-m", "my.mcp.server"]}],
    ... )
"""

import logging
import time
from typing import Any, Dict, List, Optional, Union

from kaizen.agent_config import AgentConfig
from kaizen.agent_types import get_agent_type_preset
from kaizen.rich_output import RichOutputManager
from kaizen.smart_defaults import SmartDefaultsManager

logger = logging.getLogger(__name__)


class Agent:
    """
    Unified agent API with smart defaults and progressive disclosure.

    Replaces 16 specialized agent classes with single unified interface.
    Implements 3-layer architecture:
    - Layer 1: Zero-config (everything works by default)
    - Layer 2: Configuration (agent_type, behavioral params)
    - Layer 3: Expert override (custom implementations)

    This class provides the user-facing API and delegates to BaseAgent
    for execution.

    Example (Zero-Config):
        >>> agent = Agent(model="gpt-4")
        >>> result = agent.run("What is AI?")

    Example (Configuration):
        >>> agent = Agent(
        ...     model="gpt-4",
        ...     agent_type="react",
        ...     memory_turns=20,
        ... )

    Example (Expert Override):
        >>> agent = Agent(
        ...     model="gpt-4",
        ...     custom_memory=RedisMemory(),
        ... )
    """

    def __init__(
        self,
        model: str,
        llm_provider: Optional[str] = None,
        # =====================================================================
        # LAYER 2: Configuration Parameters
        # =====================================================================
        agent_type: str = "simple",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        # Memory
        memory_turns: Optional[int] = 10,
        memory_backend: str = "buffer",
        # Tools
        tools: Union[str, List[str], None] = "all",
        # Observability
        enable_tracing: bool = True,
        enable_metrics: bool = True,
        enable_logging: bool = True,
        enable_audit: bool = True,
        # Checkpointing
        enable_checkpointing: bool = True,
        checkpoint_path: str = ".kaizen/checkpoints",
        # Streaming
        streaming: bool = True,
        stream_output: str = "console",
        # Control Protocol
        control_protocol: str = "cli",
        # Error Handling
        max_retries: int = 3,
        # Cost Tracking
        budget_limit_usd: Optional[float] = None,
        # =====================================================================
        # LAYER 3: Expert Overrides
        # =====================================================================
        custom_memory=None,
        custom_mcp_servers=None,
        custom_hook_manager=None,
        custom_checkpoint_manager=None,
        custom_control_protocol=None,
        # =====================================================================
        # ADVANCED: Additional Configuration
        # =====================================================================
        instructions: Optional[str] = None,
        signature=None,
        session_id: Optional[str] = None,
        show_startup_banner: bool = True,
        **kwargs,
    ):
        """
        Initialize unified agent with smart defaults.

        Args:
            model: LLM model name (e.g., "gpt-4", "claude-3")
            llm_provider: LLM provider (openai, anthropic, azure, ollama, mock).
                Auto-detected from model name if not specified.

            # Layer 2: Configuration
            agent_type: Agent behavior preset (simple, react, cot, rag, autonomous, vision, audio)
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate

            memory_turns: Number of conversation turns to remember (default: 10, None = disabled)
            memory_backend: Memory backend type (buffer, semantic, persistent)

            tools: Tools to enable ("all", list, or None)

            enable_tracing: Enable Jaeger distributed tracing
            enable_metrics: Enable Prometheus metrics
            enable_logging: Enable structured JSON logging
            enable_audit: Enable compliance audit trails

            enable_checkpointing: Enable automatic checkpointing
            checkpoint_path: Checkpoint storage directory

            streaming: Enable streaming output
            stream_output: Streaming destination (console, http, none)

            control_protocol: Control protocol transport (cli, http, stdio, memory)

            max_retries: Maximum retries on error

            budget_limit_usd: Maximum cost in USD (None = unlimited)

            # Layer 3: Expert Overrides
            custom_memory: Custom memory implementation
            custom_mcp_servers: Custom MCP server configurations
            custom_hook_manager: Custom hook manager
            custom_checkpoint_manager: Custom checkpoint manager
            custom_control_protocol: Custom control protocol

            # Advanced
            instructions: System instructions for the agent
            signature: Custom signature (overrides agent_type default)
            session_id: Session ID for memory continuity
            show_startup_banner: Show rich startup banner (default: True)
        """
        self.logger = logging.getLogger(f"{__name__}.Agent")

        # Step 1: Create configuration
        self.config = AgentConfig(
            model=model,
            llm_provider=llm_provider,
            agent_type=agent_type,
            temperature=temperature,
            max_tokens=max_tokens,
            memory_turns=memory_turns,
            memory_backend=memory_backend,
            tools=tools,
            enable_tracing=enable_tracing,
            enable_metrics=enable_metrics,
            enable_logging=enable_logging,
            enable_audit=enable_audit,
            enable_checkpointing=enable_checkpointing,
            checkpoint_path=checkpoint_path,
            streaming=streaming,
            stream_output=stream_output,
            control_protocol=control_protocol,
            max_retries=max_retries,
            budget_limit_usd=budget_limit_usd,
            custom_memory=custom_memory,
            custom_mcp_servers=custom_mcp_servers,
            custom_hook_manager=custom_hook_manager,
            custom_checkpoint_manager=custom_checkpoint_manager,
            custom_control_protocol=custom_control_protocol,
            instructions=instructions,
            signature=signature,
            session_id=session_id,
        )

        # Step 2: Get agent type preset
        self.preset = get_agent_type_preset(agent_type)
        self.logger.info(f"Agent type: {agent_type} ({self.preset.description})")

        # Step 3: Create components with smart defaults
        defaults_manager = SmartDefaultsManager()

        self.memory = defaults_manager.create_memory(self.config)
        self.mcp_servers = defaults_manager.create_tools(self.config)
        self.hook_manager = defaults_manager.create_observability(self.config)
        self.checkpoint_manager = defaults_manager.create_checkpointing(self.config)
        self.control_protocol = defaults_manager.create_control_protocol(self.config)

        # Step 4: Show startup banner (feature discoverability)
        self.rich_output = RichOutputManager(enabled=streaming)

        if show_startup_banner:
            self.rich_output.show_startup_banner(
                agent_type=agent_type,
                config=self.config,
                components={
                    "memory": self.memory,
                    "mcp_servers": self.mcp_servers,
                    "hook_manager": self.hook_manager,
                    "checkpoint_manager": self.checkpoint_manager,
                    "control_protocol": self.control_protocol,
                },
            )

        # Step 5: Initialize BaseAgent (execution engine)
        # NOTE: This is a placeholder. In full implementation, this would
        # delegate to BaseAgent for actual execution.
        self.base_agent = None
        self._initialize_base_agent()

        self.logger.info(f"Agent initialized: {self.config}")

    def _initialize_base_agent(self):
        """
        Initialize BaseAgent for execution.

        This is where we delegate to the actual BaseAgent implementation.
        """
        try:
            from kaizen.core.base_agent import BaseAgent

            # Use preset signature if not provided
            signature = self.config.signature or self.preset.signature

            # Create BaseAgent with all configured components
            self.base_agent = BaseAgent(
                config=self._convert_to_base_agent_config(),
                signature=signature,
                memory=self.memory,
                mcp_servers=self.mcp_servers,
                hook_manager=self.hook_manager,
                checkpoint_manager=self.checkpoint_manager,
                # control_protocol=self.control_protocol,  # TODO: Add when BaseAgent supports it
            )

            self.logger.info("BaseAgent initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize BaseAgent: {e}")
            self.logger.warning("Agent will operate in limited mode")

    def _convert_to_base_agent_config(self) -> dict:
        """
        Convert AgentConfig to BaseAgent-compatible configuration.

        Returns:
            Configuration dictionary for BaseAgent
        """
        return {
            "llm_provider": self.config.llm_provider,
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

    # =========================================================================
    # Primary Execution Method
    # =========================================================================

    def run(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Universal execution method for all agent types.

        This is the primary method users call to execute the agent,
        regardless of agent type.

        Args:
            prompt: Input prompt/question/task
            **kwargs: Additional parameters for specific agent types

        Returns:
            dict: Agent execution result

        Example:
            >>> agent = Agent(model="gpt-4")
            >>> result = agent.run("What is AI?")
            >>> print(result["answer"])

        Example (with session):
            >>> result1 = agent.run("My name is Alice", session_id="user123")
            >>> result2 = agent.run("What's my name?", session_id="user123")
            >>> # Returns: "Your name is Alice"
        """
        start_time = time.time()

        try:
            # Show execution start
            self.rich_output.show_execution_start(prompt)

            # Execute via BaseAgent - required for actual execution
            if self.base_agent:
                result = self.base_agent.run(prompt=prompt, **kwargs)
            else:
                # CRITICAL: Do not silently return mock data in production
                # This would cause users to receive fake responses
                import os

                if os.environ.get("KAIZEN_ALLOW_MOCK", "").lower() == "true":
                    self.logger.warning(
                        "BaseAgent not configured - using mock execution. "
                        "Set KAIZEN_ALLOW_MOCK=false or configure a provider to disable."
                    )
                    result = self._mock_execution(prompt, **kwargs)
                else:
                    raise RuntimeError(
                        "BaseAgent not configured. Cannot execute without a configured "
                        "AI provider. Please configure a provider (e.g., OpenAI, Anthropic, "
                        "Ollama) or set KAIZEN_ALLOW_MOCK=true for development/testing."
                    )

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Show execution complete
            cost = result.get("cost_usd", None)
            self.rich_output.show_execution_complete(duration_ms, cost)

            return result

        except Exception as e:
            self.logger.error(f"Execution failed: {e}", exc_info=True)
            self.rich_output.show_error(e)
            raise

    def _mock_execution(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Mock execution for development/testing.

        Used when BaseAgent is not available.

        Args:
            prompt: Input prompt
            **kwargs: Additional parameters

        Returns:
            Mock result
        """
        return {
            "answer": f"Mock response to: {prompt[:50]}...",
            "success": True,
            "mock": True,
        }

    # =========================================================================
    # Convenience Methods (Backward Compatibility)
    # =========================================================================

    def ask(self, question: str, **kwargs) -> Dict[str, Any]:
        """
        Ask a question (backward compatibility with SimpleQAAgent).

        Args:
            question: Question to ask
            **kwargs: Additional parameters

        Returns:
            Agent result

        Note:
            This is a convenience method. Use .run() for consistency.
        """
        return self.run(prompt=question, **kwargs)

    def analyze(self, image: str, question: str, **kwargs) -> Dict[str, Any]:
        """
        Analyze an image (backward compatibility with VisionAgent).

        Args:
            image: Image file path
            question: Question about the image
            **kwargs: Additional parameters

        Returns:
            Agent result

        Note:
            Only works with agent_type="vision".
            This is a convenience method. Use .run() for consistency.
        """
        if self.config.agent_type != "vision":
            raise ValueError(
                f"analyze() only works with agent_type='vision', "
                f"got '{self.config.agent_type}'"
            )

        return self.run(prompt=question, image=image, **kwargs)

    # =========================================================================
    # Feature Information Methods
    # =========================================================================

    def get_enabled_features(self) -> List[str]:
        """
        Get list of enabled features.

        Returns:
            List of enabled feature names
        """
        return self.config.get_enabled_features()

    def show_features(self) -> None:
        """
        Show all enabled features with details.
        """
        features_info = {
            "Agent Type": f"{self.config.agent_type} ({self.preset.description})",
            "Model": self.config.model,
            "Enabled Features": self.get_enabled_features(),
        }

        if self.memory:
            features_info["Memory"] = {
                "Type": self.config.memory_backend,
                "Turns": self.config.memory_turns,
            }

        if self.mcp_servers:
            # MCP servers info
            features_info["MCP Servers"] = {
                "Count": len(self.mcp_servers),
                "Servers": [s.get("name", "Unknown") for s in self.mcp_servers],
            }

        self.rich_output.show_feature_info("Agent Configuration", features_info)

    def get_config(self) -> AgentConfig:
        """
        Get agent configuration.

        Returns:
            AgentConfig instance
        """
        return self.config

    def get_stats(self) -> Dict[str, Any]:
        """
        Get agent statistics.

        Returns:
            Dictionary with agent statistics
        """
        return {
            "agent_type": self.config.agent_type,
            "model": self.config.model,
            "enabled_features": self.get_enabled_features(),
            "has_base_agent": self.base_agent is not None,
        }

    def __repr__(self) -> str:
        """String representation."""
        features = ", ".join(self.get_enabled_features()[:3])
        if len(self.get_enabled_features()) > 3:
            features += "..."

        return (
            f"Agent(model={self.config.model}, "
            f"agent_type={self.config.agent_type}, "
            f"features=[{features}])"
        )
