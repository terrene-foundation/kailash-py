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
from functools import lru_cache
from pathlib import Path

from kaizen.agent_config import AgentConfig
from kaizen.errors import ObservabilityNotImplemented

logger = logging.getLogger(__name__)

#: The four observability subsystems this module advertises and does NOT
#: implement: ``(config flag, human name, what it would have provided)``.
#: The hook classes imported by the old call site do not exist, and neither do
#: the handler methods it registered (``start_trace`` / ``end_trace`` /
#: ``record_start`` / ``record_end`` / ``log_start`` / ``log_end`` have zero
#: definitions anywhere in ``src/``). Tracking: #2084.
_UNIMPLEMENTED_OBSERVABILITY = (
    ("enable_tracing", "tracing", "distributed tracing via Jaeger"),
    ("enable_metrics", "metrics", "Prometheus metrics collection"),
    ("enable_logging", "logging", "structured JSON logging"),
    ("enable_audit", "audit", "compliance audit trails"),
)


@lru_cache(maxsize=None)
def _warn_observability_unimplemented(subsystems: tuple[str, ...]) -> None:
    """Emit the unimplemented-subsystem warning ONCE per process.

    ``create_observability`` runs on EVERY agent construction, so warning per
    call turns a real signal into log spam — and a spammed warning is a
    silenced one: operators filter it, and the loud-warning remedy quietly
    becomes no remedy at all.

    ``lru_cache`` rather than an instance flag, because
    ``SmartDefaultsManager`` is constructed per agent — an instance flag would
    warn once per instance and leave the spam intact. Keyed on the subsystem
    tuple so a genuinely different set still gets its own warning.

    Tests reset it with ``_warn_observability_unimplemented.cache_clear()``.
    """
    logger.warning(
        "Observability subsystems are NOT IMPLEMENTED and no hooks were "
        "registered: %s. These config flags are advertised but install "
        "nothing (tracking: #2084). Set them to False to silence this, or "
        "True to fail loudly instead.",
        ", ".join(subsystems),
    )


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
        Resolve observability configuration.

        NONE of the four advertised subsystems — tracing, metrics, logging,
        audit — is implemented (#2084). This method no longer pretends
        otherwise: it either returns a caller-supplied hook manager, raises for
        an explicit request it cannot satisfy, or warns and returns None.

        Args:
            config: Agent configuration

        Returns:
            The custom hook manager if one was supplied, otherwise None.

        Raises:
            ObservabilityNotImplemented: if any of the four flags was set to
                ``True`` explicitly. Left unset (``None``), they warn instead.

        Logic:
        - If custom_hook_manager provided → use it
        - If any subsystem explicitly requested → raise (none are implemented)
        - Otherwise → warn once and return None
        """
        # Layer 3: Custom hook manager override
        if config.has_custom_observability():
            self.logger.info("Using custom hook manager")
            return config.custom_hook_manager

        # NOT-IMPLEMENTED gate (#2084).
        #
        # This function used to import four hook classes that do not exist,
        # catch the resulting ImportError, log "not available, skipping", and
        # return an EMPTY HookManager — so all four flags reported success
        # while registering nothing. `enable_audit` is the sharp case:
        # compliance audit trails that silently record nothing are invisible
        # exactly when they matter.
        #
        # Deliberately NOT wrapped in try/except ImportError. The defect being
        # fixed IS a swallowed ImportError; reproducing that shape one layer
        # out would defeat the purpose.
        explicitly_requested = [
            (flag, subsystem, provides)
            for flag, subsystem, provides in _UNIMPLEMENTED_OBSERVABILITY
            if getattr(config, flag, None) is True
        ]
        if explicitly_requested:
            flag, subsystem, provides = explicitly_requested[0]
            raise ObservabilityNotImplemented(subsystem, flag, provides)

        # Left at default: the caller did not ask, so do not break them — but
        # do not stay quiet about advertising four features that do not exist.
        # ONE consolidated warning, not the four separate "not available,
        # skipping" lines this replaced: "not available" reads as a missing
        # optional dependency an operator could install, and there is nothing
        # to install.
        unset = [
            subsystem
            for flag, subsystem, _ in _UNIMPLEMENTED_OBSERVABILITY
            if getattr(config, flag, None) is None
        ]
        if unset:
            # ONCE per process, not once per construction — see the helper.
            _warn_observability_unimplemented(tuple(unset))

        self.logger.info("Observability disabled")
        return None

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
