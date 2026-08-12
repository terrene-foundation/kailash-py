"""
Rich Console Output Manager for Unified Agent API

Provides beautiful console output showing:
- Startup banner with active features
- Real-time execution progress
- Performance metrics summary

Part of ADR-020: Unified Agent API Architecture (Feature Discoverability)
"""

from typing import Any, Dict, Optional

from kaizen.agent_config import AgentConfig


class RichOutputManager:
    """
    Rich console output for agent startup and execution.

    Solves feature discoverability problem by showing all active features
    on agent startup.

    Example output:
        🤖 Kaizen Agent v0.5.0
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        Agent Type: react (Reasoning + Action)
        Model: gpt-4

        Active Features:
        ✅ Memory: Enabled (10 turns, buffer backend)
        ✅ Tools: 12 builtin tools registered
        ✅ Observability:
           • Distributed tracing (http://localhost:4317)
           • Prometheus metrics (serve on port 9090)
           • Structured logging (INFO level)
           • Audit trail (.kaizen/audit.jsonl)
        ✅ Checkpointing: Filesystem (.kaizen/checkpoints/)
        ✅ Streaming: Console output
        ✅ Control Protocol: CLI transport
        ✅ Cost Tracking: No limit
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """

    def __init__(self, enabled: bool = True):
        """
        Initialize rich output manager.

        Args:
            enabled: Whether rich output is enabled (default: True)
        """
        self.enabled = enabled

    def show_startup_banner(
        self,
        agent_type: str,
        config: AgentConfig,
        components: Dict[str, Any],
    ) -> None:
        """
        Show startup banner with active features.

        Args:
            agent_type: Agent type (simple, react, cot, etc.)
            config: Agent configuration
            components: Dictionary of created components
                {
                    "memory": Memory instance or None,
                    "mcp_servers": List of MCP server configs or None,
                    "hook_manager": HookManager or None,
                    "checkpoint_manager": CheckpointManager or None,
                    "control_protocol": ControlProtocol,
                }
        """
        if not self.enabled:
            return

        from kaizen import __version__

        # Get agent type description
        from kaizen.agent_types import get_agent_type_preset

        preset = get_agent_type_preset(agent_type)

        # Banner
        self._print_separator()
        print(f"🤖 Kaizen Agent v{__version__}")
        self._print_separator()
        print(f"Agent Type: {agent_type} ({preset.description})")
        print(f"Model: {config.model}")
        print("")
        print("Active Features:")

        # Memory
        self._show_memory_status(config, components.get("memory"))

        # Tools
        self._show_tools_status(config, components.get("mcp_servers"))

        # Observability
        self._show_observability_status(config, components.get("hook_manager"))

        # Checkpointing
        self._show_checkpointing_status(config, components.get("checkpoint_manager"))

        # Streaming
        self._show_streaming_status(config)

        # Control Protocol
        self._show_control_protocol_status(config, components.get("control_protocol"))

        # Cost Tracking
        self._show_cost_tracking_status(config)

        self._print_separator()
        print("")  # Extra newline for spacing

    def _show_memory_status(self, config: AgentConfig, memory: Any) -> None:
        """Show memory feature status."""
        if memory is not None:
            backend = config.memory_backend
            turns = config.memory_turns
            print(f"✅ Memory: Enabled ({turns} turns, {backend} backend)")
        else:
            print("⚪ Memory: Disabled")

    def _show_tools_status(self, config: AgentConfig, mcp_servers: Any) -> None:
        """Show tools feature status."""
        if (
            mcp_servers is not None
            and isinstance(mcp_servers, list)
            and len(mcp_servers) > 0
        ):
            # MCP servers are list of config dicts
            server_names = [s.get("name", "Unknown") for s in mcp_servers]

            # kaizen_builtin has 12 tools, others unknown
            tool_count = sum(
                12 if "kaizen_builtin" in name else 0 for name in server_names
            )

            if len(server_names) == 1:
                server_name = server_names[0]
                if config.tools == "all":
                    print(
                        f"✅ Tools: MCP server '{server_name}' ({tool_count} tools available)"
                    )
                else:
                    print(f"✅ Tools: MCP server '{server_name}'")
            else:
                servers_str = ", ".join(server_names)
                print(f"✅ Tools: {len(server_names)} MCP servers ({servers_str})")
        else:
            print("⚪ Tools: Disabled")

    # What each registered hook name means to a user, and where its output
    # goes. Keyed on `BaseHook.name`, which is what the manager reports.
    _OBSERVABILITY_LABELS = {
        "tracing_hook": lambda config: f"Distributed tracing ({config.tracing_endpoint})",
        "metrics_hook": lambda config: (
            f"Prometheus metrics (serve on port {config.metrics_port})"
        ),
        "logging_hook": lambda config: f"Structured logging ({config.log_level} level)",
        "audit_trail_hook": lambda config: f"Audit trail ({config.audit_log_path})",
    }

    def _show_observability_status(
        self, config: AgentConfig, hook_manager: Any
    ) -> None:
        """
        Show observability feature status.

        Rendered from the hooks ACTUALLY registered, never from the config
        flags. Reading the flags is how this banner came to announce four
        subsystems -- with endpoints and file paths -- that had registered
        nothing (#2084); a subsystem whose optional dependency is missing is
        still flagged True, so a flag-driven banner reports it as running.
        """
        if hook_manager is None:
            print("⚪ Observability: Disabled")
            return

        if config.has_custom_observability():
            # A caller-supplied manager holds whatever that caller registered;
            # naming subsystems here would be guessing.
            print("✅ Observability: custom hook manager")
            return

        registered = hook_manager.registered_hook_names()
        observability_items = [
            label(config)
            for name, label in self._OBSERVABILITY_LABELS.items()
            if name in registered
        ]

        if observability_items:
            print("✅ Observability:")
            for item in observability_items:
                print(f"   • {item}")
        else:
            print("⚪ Observability: Enabled but no subsystems could be installed")

    def _show_checkpointing_status(
        self, config: AgentConfig, checkpoint_manager: Any
    ) -> None:
        """Show checkpointing feature status."""
        if checkpoint_manager is not None:
            print(f"✅ Checkpointing: Filesystem ({config.checkpoint_path})")
        else:
            print("⚪ Checkpointing: Disabled")

    def _show_streaming_status(self, config: AgentConfig) -> None:
        """Show streaming feature status."""
        if config.streaming:
            output_type = config.stream_output.capitalize()
            print(f"✅ Streaming: {output_type} output")
        else:
            print("⚪ Streaming: Disabled")

    def _show_control_protocol_status(
        self, config: AgentConfig, control_protocol: Any
    ) -> None:
        """Show control protocol feature status."""
        transport = config.control_protocol.upper()
        print(f"✅ Control Protocol: {transport} transport")

    def _show_cost_tracking_status(self, config: AgentConfig) -> None:
        """Show cost tracking feature status."""
        if config.budget_limit_usd is not None:
            print(f"✅ Cost Tracking: ${config.budget_limit_usd} limit")
        else:
            print("✅ Cost Tracking: Enabled (no limit)")

    def _print_separator(self, char: str = "━", length: int = 70) -> None:
        """Print a separator line."""
        print(char * length)

    def show_execution_start(self, prompt: str) -> None:
        """
        Show execution start message.

        Args:
            prompt: User prompt
        """
        if not self.enabled:
            return

        print(f"\n💭 Processing: {prompt[:50]}{'...' if len(prompt) > 50 else ''}")

    def show_execution_progress(
        self, message: str, percentage: Optional[float] = None
    ) -> None:
        """
        Show execution progress.

        Args:
            message: Progress message
            percentage: Progress percentage (0-100) or None
        """
        if not self.enabled:
            return

        if percentage is not None:
            print(f"   ⏳ {message} ({percentage:.0f}%)")
        else:
            print(f"   ⏳ {message}")

    def show_execution_complete(
        self, duration_ms: float, cost_usd: Optional[float] = None
    ) -> None:
        """
        Show execution complete message with performance metrics.

        Args:
            duration_ms: Execution duration in milliseconds
            cost_usd: Cost in USD or None
        """
        if not self.enabled:
            return

        metrics = [f"Duration: {duration_ms:.1f}ms"]

        if cost_usd is not None:
            metrics.append(f"Cost: ${cost_usd:.4f}")

        print(f"   ✅ Complete ({', '.join(metrics)})\n")

    def show_error(self, error: Exception) -> None:
        """
        Show error message.

        The message is credential-scrubbed before printing. stdout and the
        logger routinely land in the same aggregator (containers, CI, Nexus),
        so printing ``str(error)`` raw here re-leaks exactly what the caller's
        ``sanitize_provider_error`` just redacted on the log surface — the
        sibling-surface failure ``rules/security.md`` § "Multi-Site Kwarg
        Plumbing" and ``rules/observability.md`` Rule 6.3 both name (masking
        only the log line is BLOCKED). Scrubbing at this sink rather than at
        the one caller keeps every future caller covered.

        Args:
            error: Exception that occurred
        """
        if not self.enabled:
            return

        # Function-local import: rich_output is constructed early in the agent
        # lifecycle and credential_scrub pulls in the pattern table. Matches
        # the sibling sanitize sites (strategies/multi_cycle.py).
        from kaizen.utils.credential_scrub import scrub_credentials

        error_type = type(error).__name__
        # `[REDACTED]` is the node-surface marker, matching the sanitized log
        # line emitted by the caller for the same exception.
        error_msg = scrub_credentials(str(error), placeholder="[REDACTED]")

        print(f"   ❌ Error: {error_type}: {error_msg}\n")

    def show_feature_info(self, feature_name: str, info: Dict[str, Any]) -> None:
        """
        Show detailed information about a feature.

        Args:
            feature_name: Feature name
            info: Dictionary with feature information
        """
        if not self.enabled:
            return

        print(f"\n📊 {feature_name} Information:")
        self._print_separator("-")

        for key, value in info.items():
            if isinstance(value, dict):
                print(f"{key}:")
                for subkey, subvalue in value.items():
                    print(f"  {subkey}: {subvalue}")
            elif isinstance(value, list):
                print(f"{key}: [{', '.join(str(v) for v in value)}]")
            else:
                print(f"{key}: {value}")

        self._print_separator("-")
        print("")

    def format_result(self, result: Dict[str, Any]) -> str:
        """
        Format agent result for display.

        Args:
            result: Agent execution result

        Returns:
            Formatted result string
        """
        if not self.enabled:
            return str(result)

        # Try to extract answer field
        if "answer" in result:
            return result["answer"]

        # Try to extract response field
        if "response" in result:
            return result["response"]

        # Try to extract result field
        if "result" in result:
            return str(result["result"])

        # Fallback to full result
        return str(result)

    def enable(self) -> None:
        """Enable rich output."""
        self.enabled = True

    def disable(self) -> None:
        """Disable rich output."""
        self.enabled = False

    def is_enabled(self) -> bool:
        """Check if rich output is enabled."""
        return self.enabled


# =============================================================================
# Global Rich Output Manager Instance
# =============================================================================

# Global instance for convenience
_global_rich_output = RichOutputManager()


def get_rich_output() -> RichOutputManager:
    """
    Get global rich output manager.

    Returns:
        Global RichOutputManager instance
    """
    return _global_rich_output


def enable_rich_output() -> None:
    """Enable rich console output globally."""
    _global_rich_output.enable()


def disable_rich_output() -> None:
    """Disable rich console output globally."""
    _global_rich_output.disable()


def is_rich_output_enabled() -> bool:
    """Check if rich output is enabled globally."""
    return _global_rich_output.is_enabled()
