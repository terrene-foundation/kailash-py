"""Built-in slash commands for kz CLI.

Each function follows the handler signature::

    def handler(args: str, **context) -> str | None

Context keys (provided by the agent loop when executing):

- ``config``: :class:`~kz.config.loader.KzConfig`
- ``conversation``: :class:`~kz.cli.loop.Conversation`
- ``usage``: :class:`~kz.cli.loop.UsageTracker`
- ``session_manager``: :class:`~kz.session.manager.SessionManager`
"""

from __future__ import annotations

import sys
from typing import Any, TYPE_CHECKING

from kaizen_agents.delegate.commands import CommandRegistry

if TYPE_CHECKING:
    from kaizen_agents.delegate.config.effort import EffortLevel


# ---------------------------------------------------------------------------
# Sentinel for /exit and /quit
# ---------------------------------------------------------------------------

EXIT_SIGNAL = "__KZ_EXIT__"


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _help_handler(args: str, **context: Any) -> str:
    """List all available slash commands."""
    registry: CommandRegistry | None = context.get("registry")
    if registry is None:
        return "No command registry available."

    lines = ["Available commands:", ""]
    for name, cmd in sorted(registry.commands.items()):
        alias_str = ""
        if cmd.aliases:
            alias_str = f" (aliases: {', '.join('/' + a for a in cmd.aliases)})"
        lines.append(f"  /{name:<12s} {cmd.description}{alias_str}")
    lines.append("")
    return "\n".join(lines)


def _exit_handler(args: str, **context: Any) -> str:
    """Exit the session."""
    return EXIT_SIGNAL


def _cost_handler(args: str, **context: Any) -> str:
    """Show token usage and estimated cost for the current session."""
    usage = context.get("usage")
    if usage is None:
        return "No usage data available."

    # Use CostModel for accurate per-model pricing instead of hardcoded rates.
    # Resolve model from config context; fall back to CostModel defaults.
    from kaizen_agents.governance.cost_model import CostModel

    config = context.get("config")
    model_name = getattr(config, "model", "") if config else ""

    cost_model: CostModel | None = context.get("cost_model")
    if cost_model is None:
        cost_model = CostModel()

    rates = cost_model.get_rate(model_name) if model_name else cost_model.get_rate("")

    prompt_cost = (usage.prompt_tokens / 1_000_000) * rates["prompt"]
    completion_cost = (usage.completion_tokens / 1_000_000) * rates["completion"]
    total_cost = prompt_cost + completion_cost

    model_display = model_name if model_name else "(unknown model)"
    lines = [
        "Session usage:",
        f"  Model:             {model_display}",
        f"  Prompt tokens:     {usage.prompt_tokens:>10,}",
        f"  Completion tokens: {usage.completion_tokens:>10,}",
        f"  Total tokens:      {usage.total_tokens:>10,}",
        f"  Turns:             {usage.turns:>10}",
        "",
        f"  Prompt rate:       ${rates['prompt']:>9.2f}/1M tokens",
        f"  Completion rate:   ${rates['completion']:>9.2f}/1M tokens",
        f"  Estimated cost:    ${total_cost:>9.4f}",
        "  (check provider dashboard for exact billing)",
    ]
    return "\n".join(lines)


def _model_handler(args: str, **context: Any) -> str:
    """Show or switch the current model."""
    config = context.get("config")
    if config is None:
        return "No configuration available."

    if not args:
        return f"Current model: {config.model}"

    new_model = args.strip()
    config.model = new_model
    return f"Model switched to: {new_model}"


def _effort_handler(args: str, **context: Any) -> str:
    """Show or switch the effort level."""
    from kaizen_agents.delegate.config.effort import EffortLevel

    config = context.get("config")
    if config is None:
        return "No configuration available."

    if not args:
        return f"Current effort level: {config.effort_level.value}"

    level_str = args.strip().lower()
    try:
        new_level = EffortLevel(level_str)
    except ValueError:
        valid = ", ".join(e.value for e in EffortLevel)
        return f"Invalid effort level: {level_str!r}. Valid levels: {valid}"

    # Apply the full effort preset (model, temperature, max_tokens)
    from kaizen_agents.delegate.config.effort import get_effort_preset

    preset = get_effort_preset(new_level)
    config.effort_level = new_level
    config.model = preset.model
    config.temperature = preset.temperature
    config.max_tokens = preset.max_tokens
    return (
        f"Effort level switched to: {new_level.value}\n"
        f"Model: {preset.model}, max_tokens: {preset.max_tokens}"
    )


def _context_handler(args: str, **context: Any) -> str:
    """Show current context window usage."""
    conversation = context.get("conversation")
    config = context.get("config")

    if conversation is None:
        return "No conversation data available."

    # Approximate token count: ~4 chars per token (rough heuristic)
    import json

    raw = json.dumps(conversation.messages, default=str)
    estimated_tokens = len(raw) // 4
    max_tokens = config.max_tokens if config else 16384

    message_count = len(conversation.messages)
    system_count = sum(1 for m in conversation.messages if m.get("role") == "system")
    user_count = sum(1 for m in conversation.messages if m.get("role") == "user")
    assistant_count = sum(1 for m in conversation.messages if m.get("role") == "assistant")
    tool_count = sum(1 for m in conversation.messages if m.get("role") == "tool")

    lines = [
        "Context window:",
        f"  Messages:       {message_count}",
        f"    system:       {system_count}",
        f"    user:         {user_count}",
        f"    assistant:    {assistant_count}",
        f"    tool:         {tool_count}",
        f"  Est. input tokens: ~{estimated_tokens:,}",
        f"  Max output tokens: {max_tokens:,}",
    ]
    return "\n".join(lines)


def _clear_handler(args: str, **context: Any) -> str:
    """Clear conversation history, keeping the system prompt."""
    conversation = context.get("conversation")
    if conversation is None:
        return "No conversation to clear."

    # Preserve the system message
    system_msgs = [m for m in conversation.messages if m.get("role") == "system"]
    conversation.messages.clear()
    conversation.messages.extend(system_msgs)

    return "Conversation cleared. System prompt preserved."


def _plan_handler(args: str, **context: Any) -> str:
    """Trigger multi-agent planning via GovernedSupervisor.

    Behaviour depends on what is available in context:

    1. No args -> usage message.
    2. A ``supervisor`` with a ``last_result`` that contains a plan -> format it.
    3. A ``supervisor`` without a result -> show info about the configured supervisor.
    4. No supervisor -> show a plan preview with a configuration hint.
    """
    if not args:
        return "Usage: /plan <objective>"

    supervisor = context.get("supervisor")
    if supervisor is None:
        return _plan_preview(args, context)

    # If the caller provided a last_result with a plan, display it.
    last_result = context.get("last_result")
    if last_result is not None and hasattr(last_result, "plan") and last_result.plan:
        return _format_plan(last_result)

    return (
        f"Plan created for: {args}\n"
        f"Run the objective to see the execution plan.\n"
        f"Supervisor configured with model={getattr(supervisor, 'model', 'unknown')}"
    )


def _plan_preview(objective: str, context: dict[str, Any]) -> str:
    """Preview what a plan would look like without a supervisor.

    Called when ``/plan`` is invoked but no ``GovernedSupervisor`` is
    available in the context.  Shows the objective and a hint for how
    to wire up a real supervisor.
    """
    model = context.get("model", "unknown")
    return (
        f"Plan preview for: {objective}\n"
        f"Model: {model}\n"
        f"To execute this plan, configure a GovernedSupervisor first.\n"
        f"Example: supervisor = GovernedSupervisor(model='{model}', budget_usd=10.0)"
    )


def _format_plan(result: Any) -> str:
    """Format a SupervisorResult plan as ASCII for terminal display.

    Renders each node with a status icon, its description, and (for
    completed/failed/held nodes) a one-line detail.  Finishes with a
    summary line showing completion counts.
    """
    from kaizen_agents.types import PlanNodeState

    plan = result.plan
    lines = [f"Plan ({len(plan.nodes)} nodes):"]

    status_icons = {
        PlanNodeState.COMPLETED: "[done]",
        PlanNodeState.FAILED: "[FAIL]",
        PlanNodeState.HELD: "[HELD]",
        PlanNodeState.RUNNING: "[....]",
        PlanNodeState.PENDING: "[    ]",
        PlanNodeState.READY: "[    ]",
        PlanNodeState.SKIPPED: "[skip]",
    }

    for node_id, node in plan.nodes.items():
        icon = status_icons.get(node.state, "[????]")
        desc = node.agent_spec.description if node.agent_spec else node_id
        lines.append(f"  {icon} {node_id}: {desc}")

        if node.state == PlanNodeState.COMPLETED and node.output:
            preview = str(node.output)[:80]
            lines.append(f"           -> {preview}")
        elif node.state == PlanNodeState.FAILED and node.error:
            lines.append(f"           !! {node.error}")
        elif node.state == PlanNodeState.HELD:
            lines.append(f"           ** Awaiting approval")

    # Summary
    total = len(plan.nodes)
    done = sum(1 for n in plan.nodes.values() if n.state == PlanNodeState.COMPLETED)
    failed = sum(1 for n in plan.nodes.values() if n.state == PlanNodeState.FAILED)
    held = sum(1 for n in plan.nodes.values() if n.state == PlanNodeState.HELD)

    lines.append(f"\n{done}/{total} completed, {failed} failed, {held} held")
    lines.append(f"{'SUCCESS' if result.success else 'INCOMPLETE'}")

    return "\n".join(lines)


def _compact_handler(args: str, **context: Any) -> str:
    """Manually trigger context compaction.

    Prunes older messages and replaces them with a compact summary while
    preserving the system prompt and the most recent turn pairs.
    """
    conversation = context.get("conversation")
    if conversation is None:
        return "No conversation to compact."

    result = conversation.compact()

    if result.before_count == result.after_count:
        return (
            f"Conversation has {result.before_count} messages "
            f"(~{result.before_tokens:,} tokens) -- nothing to compact."
        )

    return (
        f"Compacted: {result.before_count} -> {result.after_count} messages, "
        f"~{result.before_tokens:,} -> ~{result.after_tokens:,} tokens "
        f"({result.reduction_pct:.0f}% reduction)"
    )


# ---------------------------------------------------------------------------
# Session commands (delegate to SessionManager)
# ---------------------------------------------------------------------------


def _save_handler(args: str, **context: Any) -> str:
    """Save the current session."""
    session_manager = context.get("session_manager")
    if session_manager is None:
        return "Session manager not available."

    name = args.strip() if args.strip() else None
    if not name:
        return "Usage: /save <name>"

    conversation = context.get("conversation")
    usage = context.get("usage")
    config = context.get("config")

    path = session_manager.save_session(
        name=name,
        conversation=conversation,
        usage=usage,
        config=config,
    )
    return f"Session saved: {path}"


def _load_handler(args: str, **context: Any) -> str:
    """Load a saved session."""
    session_manager = context.get("session_manager")
    if session_manager is None:
        return "Session manager not available."

    name = args.strip() if args.strip() else None
    if not name:
        return "Usage: /load <name>"

    result = session_manager.load_session(name)
    if result is None:
        return f"Session not found: {name}"

    # Unpack and apply to current context
    conversation = context.get("conversation")
    usage = context.get("usage")

    if conversation is not None and result.get("messages"):
        conversation.messages.clear()
        conversation.messages.extend(result["messages"])

    if usage is not None and result.get("usage"):
        u = result["usage"]
        usage.prompt_tokens = u.get("prompt_tokens", 0)
        usage.completion_tokens = u.get("completion_tokens", 0)
        usage.total_tokens = u.get("total_tokens", 0)
        usage.turns = u.get("turns", 0)

    turn_count = len([m for m in result.get("messages", []) if m.get("role") == "user"])
    return f"Session loaded: {name} ({turn_count} user turns)"


def _sessions_handler(args: str, **context: Any) -> str:
    """List saved sessions."""
    session_manager = context.get("session_manager")
    if session_manager is None:
        return "Session manager not available."

    sessions = session_manager.list_sessions()
    if not sessions:
        return "No saved sessions."

    lines = ["Saved sessions:", ""]
    for info in sessions:
        lines.append(
            f"  {info['name']:<20s}  {info['timestamp']}  "
            f"({info['turn_count']} turns, {info['message_count']} messages)"
        )
    lines.append("")
    return "\n".join(lines)


def _fork_handler(args: str, **context: Any) -> str:
    """Fork the current session into a new saved session."""
    session_manager = context.get("session_manager")
    if session_manager is None:
        return "Session manager not available."

    name = args.strip() if args.strip() else None
    if not name:
        return "Usage: /fork <name>"

    # First auto-save the current state, then fork from auto
    conversation = context.get("conversation")
    usage = context.get("usage")
    config = context.get("config")

    session_manager.save_session(
        name="_current",
        conversation=conversation,
        usage=usage,
        config=config,
    )
    path = session_manager.fork_session("_current", name)
    if path is None:
        return "Failed to fork session."

    return f"Session forked as: {name}"


def _holds_handler(args: str, **context: Any) -> str:
    """List currently held governance actions awaiting approval."""
    supervisor = context.get("supervisor")
    if supervisor is None:
        return "No supervisor configured."

    held = supervisor.held_nodes
    if not held:
        return "No held actions."

    lines = ["Held actions awaiting approval:", ""]
    for node_id, record in held.items():
        lines.append(f"  [{node_id}] {record.reason}")
        lines.append(f"    held at: {record.held_at.isoformat()}")
    lines.append("")
    lines.append("Use /approve <node_id> or /reject <node_id> to resolve.")
    return "\n".join(lines)


def _approve_handler(args: str, **context: Any) -> str:
    """Approve a held governance action."""
    supervisor = context.get("supervisor")
    if supervisor is None:
        return "No supervisor configured."

    node_id = args.strip() if args else ""
    if not node_id:
        return "Usage: /approve <node_id>"

    try:
        supervisor.resolve_hold(node_id, approved=True)
        return f"Approved: {node_id}"
    except ValueError as exc:
        return str(exc)


def _reject_handler(args: str, **context: Any) -> str:
    """Reject a held governance action."""
    supervisor = context.get("supervisor")
    if supervisor is None:
        return "No supervisor configured."

    node_id = args.strip() if args else ""
    if not node_id:
        return "Usage: /reject <node_id>"

    try:
        supervisor.resolve_hold(node_id, approved=False)
        return f"Rejected: {node_id}"
    except ValueError as exc:
        return str(exc)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_builtins(registry: CommandRegistry) -> None:
    """Register all built-in commands on *registry*."""
    registry.register("help", "List all available commands", _help_handler, aliases=["h", "?"])
    registry.register("exit", "Exit the session", _exit_handler, aliases=["quit", "q"])
    registry.register("cost", "Show token usage and estimated cost", _cost_handler)
    registry.register("model", "Show or switch the current model", _model_handler)
    registry.register("effort", "Show or switch effort level (low/medium/high)", _effort_handler)
    registry.register("context", "Show context window usage", _context_handler)
    registry.register("clear", "Clear conversation history (keep system prompt)", _clear_handler)
    registry.register("plan", "Execute governed multi-agent planning", _plan_handler)
    registry.register("compact", "Compact conversation by pruning older messages", _compact_handler)
    registry.register("save", "Save current session (/save <name>)", _save_handler)
    registry.register("load", "Load a saved session (/load <name>)", _load_handler)
    registry.register("sessions", "List saved sessions", _sessions_handler)
    registry.register("fork", "Fork current session (/fork <name>)", _fork_handler)
    registry.register("holds", "List held governance actions", _holds_handler)
    registry.register("approve", "Approve a held action (/approve <node_id>)", _approve_handler)
    registry.register("reject", "Reject a held action (/reject <node_id>)", _reject_handler)


def create_default_commands() -> CommandRegistry:
    """Create a CommandRegistry pre-loaded with all built-in commands."""
    registry = CommandRegistry()
    register_builtins(registry)
    return registry
