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
from urllib.parse import urlparse

from kaizen.agent_config import AgentConfig

logger = logging.getLogger(__name__)

# Default OTLP gRPC ingest port, matching TracingManager's own default. Used
# when `tracing_endpoint` carries no explicit port.
_DEFAULT_OTLP_GRPC_PORT = 4317

# Jaeger's web UI port. It accepts no OTLP traffic, so an endpoint pointed here
# drops every span. Called out by name because it was this SDK's own
# `tracing_endpoint` default for as long as nothing read the field -- anyone who
# pinned that value explicitly is exactly the population at risk.
_JAEGER_WEB_UI_PORT = 16686


@lru_cache(maxsize=None)
def _warn_observability_unavailable(subsystem: str, flag: str, detail: str) -> None:
    """
    Announce, once per process, that an enabled subsystem could not load.

    ``create_observability`` runs on every agent construction, so a per-call
    warning means a process building 100 agents emits 100 copies -- and a
    warning repeated on a hot path is one operators filter out, which turns the
    loud-warning remedy back into no remedy.

    ``lru_cache`` rather than an instance flag because ``SmartDefaultsManager``
    is constructed per agent; an instance flag would warn once per instance and
    leave the spam intact. Tests clear it via ``cache_clear()``.

    Args:
        subsystem: Human name of the subsystem ("metrics").
        flag: The AgentConfig field that requested it ("enable_metrics").
        detail: The underlying ImportError text, which already names the extra.
    """
    logger.warning(
        "%s is enabled (%s=True) but could not be loaded, so NOTHING will be "
        "recorded for it. %s Set %s=False to disable it deliberately and "
        "silence this warning.",
        subsystem.capitalize(),
        flag,
        detail,
        flag,
    )


@lru_cache(maxsize=None)
def _warn_audit_unwritable(path: str, detail: str) -> None:
    """Warn once that the audit trail could not be opened for writing."""
    logger.warning(
        "Compliance audit is enabled (enable_audit=True) but the audit trail "
        "at %r could not be opened, so NOTHING will be recorded: %s. Point "
        "audit_log_path at a writable location, or set enable_audit=False to "
        "disable it deliberately and silence this warning.",
        path,
        detail,
    )


@lru_cache(maxsize=None)
def _shared_tracing_manager(service_name: str, host: str, port: int):
    """
    One TracingManager per (service, endpoint), shared across agents.

    Each TracingManager builds its own TracerProvider and BatchSpanProcessor,
    and the processor runs a background export thread that nothing in the
    agent lifecycle shuts down. Constructing one per agent would leak a thread
    per agent; keying on the tuple that actually distinguishes destinations
    bounds it to the number of distinct destinations.
    """
    from kaizen.core.autonomy.observability.tracing_manager import TracingManager

    return TracingManager(
        service_name=service_name,
        jaeger_host=host,
        jaeger_port=port,
    )


def _parse_otlp_endpoint(endpoint: str) -> tuple[str, int]:
    """
    Split an OTLP endpoint into (host, port) for TracingManager.

    Accepts both URL form ("http://collector:4317") and bare "host:port".

    Args:
        endpoint: Value of AgentConfig.tracing_endpoint.

    Returns:
        (host, port) -- port falls back to the OTLP gRPC default.
    """
    parsed = urlparse(endpoint if "//" in endpoint else f"//{endpoint}")
    host = parsed.hostname or "localhost"
    port = parsed.port or _DEFAULT_OTLP_GRPC_PORT

    if port == _JAEGER_WEB_UI_PORT:
        # Exporting to the UI port fails at the socket, and OpenTelemetry's
        # batch processor drops spans on export failure -- so the operator sees
        # tracing "enabled" and an empty Jaeger. Say it once, by name.
        _warn_tracing_endpoint_is_web_ui(endpoint)

    return host, port


@lru_cache(maxsize=None)
def _warn_tracing_endpoint_is_web_ui(endpoint: str) -> None:
    """Warn once that tracing_endpoint points at the Jaeger UI, not OTLP ingest."""
    logger.warning(
        "tracing_endpoint=%r targets port %d, which is the Jaeger WEB UI and "
        "accepts no OTLP traffic -- every span will be dropped on export. Point "
        "it at the collector's OTLP gRPC ingest port instead (default %d).",
        endpoint,
        _JAEGER_WEB_UI_PORT,
        _DEFAULT_OTLP_GRPC_PORT,
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
        Create observability with smart defaults.

        Registers one hook per enabled subsystem on a fresh ``HookManager``:

        - ``enable_logging`` → ``LoggingHook`` (core dependencies only)
        - ``enable_audit`` → ``AuditTrailHook`` writing ``audit_log_path``
        - ``enable_metrics`` → ``MetricsHook`` (needs the ``observability`` extra)
        - ``enable_tracing`` → ``TracingHook`` (needs the ``observability`` extra)

        The two extra-dependent subsystems cannot be silently skipped: an
        enabled flag that installs nothing is the exact defect #2084 records,
        so a missing dependency produces a one-time warning naming the flag,
        the extra, and the way to turn it off deliberately.

        Args:
            config: Agent configuration

        Returns:
            HookManager with the enabled subsystems registered, or None when
            observability is entirely disabled or nothing could be installed.

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

        hook_manager = HookManager()
        enabled_systems = []

        # ---------------------------------------------------------------
        # Logging (structured). Core dependencies only, so this one always
        # installs.
        #
        # `include_data` is driven OFF by default (`log_payload_keys`), not
        # left at the class default of True. Since #2070 LoggingHook emits
        # payload KEY NAMES and counts rather than values -- but key names are
        # a bounded leak, not an absent one (`ssn`, `patient_diagnosis`,
        # `termination_reason` disclose schema and subject matter on their
        # own), and this hook runs on EVERY agent construction in every
        # downstream consumer. Wiring a previously dormant sink onto a
        # default-on path is a disclosure change; it gets the conservative
        # default and an explicit opt-in.
        # ---------------------------------------------------------------
        if config.enable_logging:
            from kaizen.core.autonomy.hooks.builtin.logging_hook import LoggingHook

            hook_manager.register_hook(
                LoggingHook(
                    log_level=config.log_level,
                    include_data=config.log_payload_keys,
                )
            )
            enabled_systems.append(f"structured logging ({config.log_level})")

        # ---------------------------------------------------------------
        # Audit (compliance). AuditTrailHook bridges the observability
        # AuditTrailManager -- which honours `audit_log_path` and needs only
        # anyio -- into the hook system. The sibling `AuditHook` is NOT used
        # here: it wraps the PostgreSQL-backed security AuditTrailProvider,
        # which a zero-config default path has no connection for.
        # ---------------------------------------------------------------
        if config.enable_audit:
            from kaizen.core.autonomy.hooks.builtin.audit_trail_hook import (
                AuditTrailHook,
            )
            from kaizen.core.autonomy.observability.audit import (
                AuditTrailManager,
                FileAuditStorage,
            )

            # No mkdir here: FileAuditStorage creates the directory AND pins it
            # owner-only. Pre-creating it at this site would hand it the default
            # umask mode and leave the tightening below with nothing to do.
            audit_path = Path(config.audit_log_path)

            # `audit_log_path` defaults to a RELATIVE path, so this opens a file
            # in whatever directory the process runs in -- which on a read-only
            # root filesystem (Kubernetes `readOnlyRootFilesystem`, distroless
            # images, Lambda's `/var/task`) raises. Before #2084 the whole
            # branch died on an ImportError that was caught, so the write was
            # unreachable; making the branch work made it reachable, and an
            # unguarded OSError here propagates straight out of `Agent()`
            # because `agent.py` calls this BEFORE its own try. A compliance
            # sink that cannot write must fail LOUDLY, not fail construction.
            try:
                storage = FileAuditStorage(str(audit_path))
            except OSError as exc:
                _warn_audit_unwritable(str(audit_path), f"{type(exc).__name__}: {exc}")
            else:
                hook_manager.register_hook(
                    AuditTrailHook(audit_manager=AuditTrailManager(storage=storage))
                )
                enabled_systems.append(f"audit trail ({audit_path})")

        # ---------------------------------------------------------------
        # Metrics (Prometheus). `metrics_port` is deliberately NOT consumed
        # here -- it configures MetricsEndpoint, which the operator starts;
        # binding a network listener on every agent construction is not
        # something a zero-config default may do.
        # ---------------------------------------------------------------
        if config.enable_metrics:
            try:
                from kaizen.core.autonomy.hooks.builtin import MetricsHook
            except ImportError as exc:
                _warn_observability_unavailable("metrics", "enable_metrics", str(exc))
            else:
                hook_manager.register_hook(MetricsHook())
                enabled_systems.append("Prometheus metrics")

        # ---------------------------------------------------------------
        # Tracing (OpenTelemetry → Jaeger).
        # ---------------------------------------------------------------
        if config.enable_tracing:
            try:
                from kaizen.core.autonomy.hooks.builtin import TracingHook
            except ImportError as exc:
                _warn_observability_unavailable("tracing", "enable_tracing", str(exc))
            else:
                host, port = _parse_otlp_endpoint(config.tracing_endpoint)
                hook_manager.register_hook(
                    TracingHook(
                        tracing_manager=_shared_tracing_manager(
                            f"kaizen-{config.agent_type}", host, port
                        )
                    )
                )
                enabled_systems.append(f"distributed tracing ({host}:{port})")

        if not enabled_systems:
            # Every enabled subsystem failed to install. Returning an empty
            # HookManager here is what made the original defect invisible: a
            # caller branching on a non-None manager ran its observability
            # path against zero hooks. Each failure has already warned above.
            self.logger.warning(
                "Observability was enabled but no subsystem could be "
                "installed; returning no hook manager."
            )
            return None

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
