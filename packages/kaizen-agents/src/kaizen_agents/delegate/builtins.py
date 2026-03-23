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

    # Rough cost estimates (USD per 1M tokens) — these are approximate
    # and vary by model.  The user can check their provider dashboard
    # for exact billing.
    prompt_cost_per_m = 2.50
    completion_cost_per_m = 10.00

    prompt_cost = (usage.prompt_tokens / 1_000_000) * prompt_cost_per_m
    completion_cost = (usage.completion_tokens / 1_000_000) * completion_cost_per_m
    total_cost = prompt_cost + completion_cost

    lines = [
        "Session usage:",
        f"  Prompt tokens:     {usage.prompt_tokens:>10,}",
        f"  Completion tokens: {usage.completion_tokens:>10,}",
        f"  Total tokens:      {usage.total_tokens:>10,}",
        f"  Turns:             {usage.turns:>10}",
        "",
        f"  Estimated cost:    ${total_cost:>9.4f}",
        "  (approximate — check provider dashboard for exact billing)",
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

    config.effort_level = new_level
    return f"Effort level switched to: {new_level.value}"


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
        f"  Est. tokens:    ~{estimated_tokens:,}",
        f"  Max tokens:     {max_tokens:,}",
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
    """Trigger multi-agent planning via PlanMonitor."""
    if not args:
        return "Usage: /plan <objective>"

    return f"Plan mode not yet connected. Objective received: {args}"


def _compact_handler(args: str, **context: Any) -> str:
    """Manually trigger context compaction."""
    conversation = context.get("conversation")
    if conversation is None:
        return "No conversation to compact."

    import json

    raw = json.dumps(conversation.messages, default=str)
    estimated_tokens = len(raw) // 4
    message_count = len(conversation.messages)

    return (
        f"Conversation length: {message_count} messages, ~{estimated_tokens:,} tokens.\n"
        "Context compaction not yet connected."
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
    registry.register("plan", "Trigger multi-agent planning", _plan_handler)
    registry.register("compact", "Summarize conversation length", _compact_handler)
    registry.register("save", "Save current session (/save <name>)", _save_handler)
    registry.register("load", "Load a saved session (/load <name>)", _load_handler)
    registry.register("sessions", "List saved sessions", _sessions_handler)
    registry.register("fork", "Fork current session (/fork <name>)", _fork_handler)


def create_default_commands() -> CommandRegistry:
    """Create a CommandRegistry pre-loaded with all built-in commands."""
    registry = CommandRegistry()
    register_builtins(registry)
    return registry
