"""
Smart Defaults Manager for Unified Agent API

Automatically initializes all production features with sensible defaults:
- Memory: BufferMemory with configured turns
- Tools: MCP server configurations for builtin tools
- Observability: Jaeger + Prometheus + logs + audit
- Checkpointing: Filesystem storage
- Control Protocol: CLI transport

Part of ADR-020: Unified Agent API Architecture (Layer 1: Zero-Config)
"""

import logging
from pathlib import Path

from kaizen.agent_config import AgentConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Smart Defaults Manager
# =============================================================================


class SmartDefaultsManager:
    """
    Create production-ready defaults for all agent components.

    This manager implements Layer 1 (Zero-Config) of the unified Agent API.
    It automatically initializes all features with sensible defaults, allowing
    users to get started with zero configuration.

    Example:
        >>> manager = SmartDefaultsManager()
        >>> config = AgentConfig(model="gpt-4")
        >>> memory = manager.create_memory(config)
        >>> tools = manager.create_tools(config)
        >>> observability = manager.create_observability(config)
    """

    def __init__(self):
        """Initialize smart defaults manager."""
        self.logger = logging.getLogger(__name__)

    # =========================================================================
    # Memory Creation
    # =========================================================================

    def create_memory(self, config: AgentConfig):
        """
        Create memory with smart defaults.

        Args:
            config: Agent configuration

        Returns:
            Memory instance (BufferMemory, SemanticMemory, or None)

        Logic:
        - If custom_memory provided → use it
        - If memory_turns is None → no memory
        - If memory_backend == "buffer" → BufferMemory
        - If memory_backend == "semantic" → SemanticMemory
        - If memory_backend == "persistent" → DataFlow-backed memory
        """
        # Layer 3: Custom memory override
        if config.has_custom_memory():
            self.logger.info("Using custom memory implementation")
            return config.custom_memory

        # No memory if memory_turns is None
        if config.memory_turns is None:
            self.logger.info("Memory disabled (memory_turns=None)")
            return None

        # Layer 1: Smart defaults based on backend
        if config.memory_backend == "buffer":
            from kaizen.memory import BufferMemory

            memory = BufferMemory(max_turns=config.memory_turns)
            self.logger.info(f"Created BufferMemory ({config.memory_turns} turns)")
            return memory

        elif config.memory_backend == "semantic":
            from kaizen.memory import SemanticMemory

            memory = SemanticMemory(max_turns=config.memory_turns)
            self.logger.info(f"Created SemanticMemory ({config.memory_turns} turns)")
            return memory

        elif config.memory_backend == "persistent":
            from kaizen.memory import PersistentBufferMemory

            memory = PersistentBufferMemory(
                max_turns=config.memory_turns,
                session_id=config.session_id or "default",
            )
            self.logger.info(
                f"Created PersistentBufferMemory ({config.memory_turns} turns)"
            )
            return memory

        else:
            # Fallback to buffer memory
            from kaizen.memory import BufferMemory

            memory = BufferMemory(max_turns=config.memory_turns)
            self.logger.warning(
                f"Unknown memory backend '{config.memory_backend}', "
                f"falling back to BufferMemory"
            )
            return memory

    # =========================================================================
    # MCP Server Configuration Creation
    # =========================================================================

    def create_tools(self, config: AgentConfig):
        """
        Create MCP server configurations with smart defaults.

        Args:
            config: Agent configuration

        Returns:
            List of MCP server configurations or None

        Logic:
        - If custom_mcp_servers provided → use it
        - If tools is None → no MCP servers
        - If tools == "all" or list → kaizen_builtin MCP server

        Note: The kaizen_builtin MCP server includes all 12 builtin tools:
        - File (5): read_file, write_file, delete_file, list_directory, file_exists
        - HTTP (4): http_get, http_post, http_put, http_delete
        - Bash (1): bash_command
        - Web (2): fetch_url, extract_links
        """
        # Layer 3: Custom MCP servers override
        if (
            hasattr(config, "custom_mcp_servers")
            and config.custom_mcp_servers is not None
        ):
            self.logger.info("Using custom MCP servers")
            return config.custom_mcp_servers

        # No MCP servers if tools is None
        if config.tools is None:
            self.logger.info("Tools disabled (tools=None)")
            return None

        # Layer 1: Smart defaults - kaizen_builtin MCP server
        if config.tools == "all" or isinstance(config.tools, list):
            mcp_servers = [
                {
                    "name": "kaizen_builtin",
                    "command": "python",
                    "args": ["-m", "kaizen.mcp.builtin_server"],
                    "transport": "stdio",
                }
            ]
            self.logger.info("Configured kaizen_builtin MCP server (12 tools)")
            return mcp_servers

        return None

    # =========================================================================
    # Observability Creation (Hooks System)
    # =========================================================================

    def create_observability(self, config: AgentConfig):
        """
        Create observability with smart defaults.

        Sets up:
        - Tracing: Jaeger distributed tracing
        - Metrics: Prometheus metrics collection
        - Logging: Structured JSON logging
        - Audit: Compliance audit trails

        Args:
            config: Agent configuration

        Returns:
            HookManager with observability hooks or None

        Logic:
        - If custom_hook_manager provided → use it
        - If all observability disabled → no hooks
        - Otherwise → create HookManager with enabled subsystems
        """
        # Layer 3: Custom hook manager override
        if config.has_custom_observability():
            self.logger.info("Using custom hook manager")
            return config.custom_hook_manager

        # No observability if all disabled
        if not config.is_observability_enabled():
            self.logger.info("Observability disabled")
            return None

        # Layer 1: Smart defaults
        from kaizen.core.autonomy.hooks import HookManager
        from kaizen.core.autonomy.hooks.types import HookEvent

        hook_manager = HookManager()
        enabled_systems = []

        # Tracing (Jaeger)
        if config.enable_tracing:
            try:
                from kaizen.core.autonomy.observability.tracing import TracingHook

                tracing_hook = TracingHook(endpoint=config.tracing_endpoint)
                hook_manager.register(
                    HookEvent.PRE_AGENT_LOOP, tracing_hook.start_trace
                )
                hook_manager.register(HookEvent.POST_AGENT_LOOP, tracing_hook.end_trace)
                enabled_systems.append("Jaeger tracing")
            except ImportError:
                self.logger.warning("Tracing hook not available, skipping")

        # Metrics (Prometheus)
        if config.enable_metrics:
            try:
                from kaizen.core.autonomy.observability.metrics import MetricsHook

                metrics_hook = MetricsHook(port=config.metrics_port)
                hook_manager.register(
                    HookEvent.PRE_AGENT_LOOP, metrics_hook.record_start
                )
                hook_manager.register(
                    HookEvent.POST_AGENT_LOOP, metrics_hook.record_end
                )
                enabled_systems.append(
                    f"Prometheus metrics (port {config.metrics_port})"
                )
            except ImportError:
                self.logger.warning("Metrics hook not available, skipping")

        # Logging (Structured JSON)
        if config.enable_logging:
            try:
                from kaizen.core.autonomy.observability.logging import LoggingHook

                logging_hook = LoggingHook(level=config.log_level)
                hook_manager.register(HookEvent.PRE_AGENT_LOOP, logging_hook.log_start)
                hook_manager.register(HookEvent.POST_AGENT_LOOP, logging_hook.log_end)
                enabled_systems.append(f"Structured logging ({config.log_level})")
            except ImportError:
                self.logger.warning("Logging hook not available, skipping")

        # Audit (Compliance)
        if config.enable_audit:
            try:
                from kaizen.core.autonomy.observability.audit import AuditHook

                # Ensure audit log directory exists
                audit_path = Path(config.audit_log_path)
                audit_path.parent.mkdir(parents=True, exist_ok=True)

                audit_hook = AuditHook(path=config.audit_log_path)
                hook_manager.register(HookEvent.PRE_AGENT_LOOP, audit_hook.record_start)
                hook_manager.register(HookEvent.POST_AGENT_LOOP, audit_hook.record_end)
                enabled_systems.append("Audit trails")
            except ImportError:
                self.logger.warning("Audit hook not available, skipping")

        if enabled_systems:
            self.logger.info(f"Enabled observability: {', '.join(enabled_systems)}")

        return hook_manager

    # =========================================================================
    # Checkpointing Creation
    # =========================================================================

    def create_checkpointing(self, config: AgentConfig):
        """
        Create checkpointing with smart defaults.

        Args:
            config: Agent configuration

        Returns:
            CheckpointManager instance or None

        Logic:
        - If custom_checkpoint_manager provided → use it
        - If enable_checkpointing is False → no checkpointing
        - Otherwise → FilesystemStorage with configured path
        """
        # Layer 3: Custom checkpoint manager override
        if config.has_custom_checkpointing():
            self.logger.info("Using custom checkpoint manager")
            return config.custom_checkpoint_manager

        # No checkpointing if disabled
        if not config.enable_checkpointing:
            self.logger.info("Checkpointing disabled")
            return None

        # Layer 1: Smart defaults (filesystem storage)
        try:
            from kaizen.memory.checkpoint import CheckpointManager, FilesystemStorage

            # Ensure checkpoint directory exists
            checkpoint_path = Path(config.checkpoint_path)
            checkpoint_path.mkdir(parents=True, exist_ok=True)

            storage = FilesystemStorage(config.checkpoint_path)
            checkpoint_manager = CheckpointManager(storage)

            self.logger.info(
                f"Created checkpointing (filesystem: {config.checkpoint_path})"
            )

            return checkpoint_manager

        except ImportError:
            self.logger.warning(
                "Checkpoint module not available, disabling checkpointing"
            )
            return None

    # =========================================================================
    # Control Protocol Creation
    # =========================================================================

    def create_control_protocol(self, config: AgentConfig):
        """
        Create control protocol with smart defaults.

        Args:
            config: Agent configuration

        Returns:
            ControlProtocol instance

        Logic:
        - If custom_control_protocol provided → use it
        - If control_protocol == "cli" → CLITransport
        - If control_protocol == "http" → HTTPTransport
        - If control_protocol == "stdio" → StdioTransport
        - If control_protocol == "memory" → MemoryTransport (testing)
        """
        # Layer 3: Custom control protocol override
        if config.has_custom_control_protocol():
            self.logger.info("Using custom control protocol")
            return config.custom_control_protocol

        # Layer 1: Smart defaults based on transport
        from kaizen.core.autonomy.control import ControlProtocol

        if config.control_protocol == "cli":
            from kaizen.core.autonomy.control.transports import CLITransport

            protocol = ControlProtocol(CLITransport())
            self.logger.info("Created control protocol (CLI transport)")

        elif config.control_protocol == "http":
            from kaizen.core.autonomy.control.transports import HTTPTransport

            protocol = ControlProtocol(HTTPTransport(port=8080))
            self.logger.info("Created control protocol (HTTP transport, port 8080)")

        elif config.control_protocol == "stdio":
            from kaizen.core.autonomy.control.transports import StdioTransport

            protocol = ControlProtocol(StdioTransport())
            self.logger.info("Created control protocol (stdio transport)")

        elif config.control_protocol == "memory":
            from kaizen.core.autonomy.control.transports import MemoryTransport

            protocol = ControlProtocol(MemoryTransport())
            self.logger.info("Created control protocol (memory transport)")

        else:
            # Fallback to CLI
            from kaizen.core.autonomy.control.transports import CLITransport

            protocol = ControlProtocol(CLITransport())
            self.logger.warning(
                f"Unknown control protocol '{config.control_protocol}', "
                f"falling back to CLI"
            )

        return protocol

    # =========================================================================
    # All Components Creation (Convenience Method)
    # =========================================================================

    def create_all_components(self, config: AgentConfig) -> dict:
        """
        Create all components with smart defaults.

        This is a convenience method that creates all agent components
        in one call.

        Args:
            config: Agent configuration

        Returns:
            Dictionary with all components:
            {
                "memory": Memory instance or None,
                "mcp_servers": List of MCP server configs or None,
                "hook_manager": HookManager instance or None,
                "checkpoint_manager": CheckpointManager instance or None,
                "control_protocol": ControlProtocol instance,
            }

        Example:
            >>> manager = SmartDefaultsManager()
            >>> config = AgentConfig(model="gpt-4")
            >>> components = manager.create_all_components(config)
            >>> agent = Agent(config=config, **components)
        """
        self.logger.info("Creating all components with smart defaults")

        components = {
            "memory": self.create_memory(config),
            "mcp_servers": self.create_tools(config),
            "hook_manager": self.create_observability(config),
            "checkpoint_manager": self.create_checkpointing(config),
            "control_protocol": self.create_control_protocol(config),
        }

        # Log summary
        enabled = [k for k, v in components.items() if v is not None]
        disabled = [k for k, v in components.items() if v is None]

        self.logger.info(f"Enabled components: {', '.join(enabled)}")
        if disabled:
            self.logger.info(f"Disabled components: {', '.join(disabled)}")

        return components
