"""Tests for the slash command system.

Covers:
- CommandRegistry: registration, parsing, aliases, execution
- Built-in commands: /help, /exit, /cost, /model, /effort, /context,
  /clear, /plan, /compact, /save, /load, /sessions, /fork
"""

from __future__ import annotations

import pytest

from kaizen_agents.delegate.commands import CommandRegistry, SlashCommand
from kaizen_agents.delegate.builtins import (
    EXIT_SIGNAL,
    register_builtins,
    create_default_commands,
)
from kaizen_agents.delegate.loop import Conversation, UsageTracker
from kaizen_agents.delegate.config.loader import KzConfig
from kaizen_agents.delegate.config.effort import EffortLevel


# -----------------------------------------------------------------------
# CommandRegistry basics
# -----------------------------------------------------------------------


class TestCommandRegistry:
    """Test CommandRegistry registration, parsing, and dispatch."""

    def test_register_and_parse(self):
        reg = CommandRegistry()
        reg.register("ping", "Ping", handler=lambda args, **kw: "pong")

        result = reg.parse("/ping")
        assert result == ("ping", "")

    def test_parse_with_args(self):
        reg = CommandRegistry()
        reg.register("echo", "Echo text", handler=lambda args, **kw: args)

        result = reg.parse("/echo hello world")
        assert result == ("echo", "hello world")

    def test_parse_unknown_command_returns_none(self):
        reg = CommandRegistry()
        assert reg.parse("/unknown") is None

    def test_parse_non_command_returns_none(self):
        reg = CommandRegistry()
        reg.register("test", "Test", handler=lambda args, **kw: "ok")
        assert reg.parse("hello world") is None
        assert reg.parse("") is None
        assert reg.parse("not a /command") is None

    def test_alias_resolution(self):
        reg = CommandRegistry()
        reg.register("exit", "Exit", handler=lambda args, **kw: "bye", aliases=["q", "quit"])

        assert reg.parse("/exit") == ("exit", "")
        assert reg.parse("/q") == ("exit", "")
        assert reg.parse("/quit") == ("exit", "")

    def test_execute_calls_handler(self):
        reg = CommandRegistry()
        reg.register("greet", "Greet", handler=lambda args, **kw: f"Hello {args}")

        output = reg.execute("/greet Alice")
        assert output == "Hello Alice"

    def test_execute_non_command_returns_none(self):
        reg = CommandRegistry()
        assert reg.execute("just a message") is None

    def test_execute_passes_context(self):
        def handler(args, **context):
            return f"model={context.get('model')}"

        reg = CommandRegistry()
        reg.register("info", "Info", handler=handler)

        output = reg.execute("/info", model="gpt-4o")
        assert output == "model=gpt-4o"

    def test_is_command(self):
        reg = CommandRegistry()
        reg.register("help", "Help", handler=lambda args, **kw: "help text")

        assert reg.is_command("/help") is True
        assert reg.is_command("/help extra") is True
        assert reg.is_command("hello") is False
        assert reg.is_command("/unknown") is False

    def test_get_command(self):
        reg = CommandRegistry()
        reg.register("test", "Test command", handler=lambda args, **kw: None)

        cmd = reg.get_command("test")
        assert cmd is not None
        assert cmd.name == "test"
        assert cmd.description == "Test command"

        assert reg.get_command("nonexistent") is None

    def test_commands_property(self):
        reg = CommandRegistry()
        reg.register("a", "A", handler=lambda args, **kw: None)
        reg.register("b", "B", handler=lambda args, **kw: None)

        cmds = reg.commands
        assert "a" in cmds
        assert "b" in cmds
        assert len(cmds) == 2

    def test_case_insensitive_parsing(self):
        reg = CommandRegistry()
        reg.register("help", "Help", handler=lambda args, **kw: "ok")

        assert reg.parse("/HELP") == ("help", "")
        assert reg.parse("/Help") == ("help", "")

    def test_parse_leading_whitespace(self):
        reg = CommandRegistry()
        reg.register("test", "Test", handler=lambda args, **kw: "ok")

        result = reg.parse("  /test  args here  ")
        assert result == ("test", "args here")


# -----------------------------------------------------------------------
# Built-in commands
# -----------------------------------------------------------------------


class TestBuiltinCommands:
    """Test each built-in slash command handler."""

    @pytest.fixture()
    def registry(self):
        return create_default_commands()

    @pytest.fixture()
    def conversation(self):
        conv = Conversation()
        conv.add_system("You are kz.")
        conv.add_user("Hello")
        conv.add_assistant("Hi there!")
        return conv

    @pytest.fixture()
    def usage(self):
        tracker = UsageTracker()
        tracker.prompt_tokens = 1500
        tracker.completion_tokens = 500
        tracker.total_tokens = 2000
        tracker.turns = 3
        return tracker

    @pytest.fixture()
    def config(self):
        return KzConfig(model="gpt-4o", effort_level=EffortLevel.MEDIUM)

    # -- /help --

    def test_help_lists_commands(self, registry):
        output = registry.execute("/help", registry=registry)
        assert output is not None
        assert "Available commands" in output
        assert "/help" in output
        assert "/exit" in output
        assert "/cost" in output

    def test_help_with_no_registry_context(self, registry):
        output = registry.execute("/help")
        assert output is not None
        assert "No command registry" in output

    # -- /exit and /quit --

    def test_exit_returns_signal(self, registry):
        output = registry.execute("/exit")
        assert output == EXIT_SIGNAL

    def test_quit_alias(self, registry):
        output = registry.execute("/quit")
        assert output == EXIT_SIGNAL

    def test_q_alias(self, registry):
        output = registry.execute("/q")
        assert output == EXIT_SIGNAL

    # -- /cost --

    def test_cost_shows_usage(self, registry, usage):
        output = registry.execute("/cost", usage=usage)
        assert output is not None
        assert "1,500" in output
        assert "500" in output
        assert "2,000" in output
        assert "$" in output

    def test_cost_no_usage(self, registry):
        output = registry.execute("/cost")
        assert output is not None
        assert "No usage data" in output

    # -- /model --

    def test_model_show_current(self, registry, config):
        output = registry.execute("/model", config=config)
        assert output is not None
        assert "gpt-4o" in output

    def test_model_switch(self, registry, config):
        output = registry.execute("/model o3", config=config)
        assert output is not None
        assert "o3" in output
        assert config.model == "o3"

    def test_model_no_config(self, registry):
        output = registry.execute("/model")
        assert output is not None
        assert "No configuration" in output

    # -- /effort --

    def test_effort_show_current(self, registry, config):
        output = registry.execute("/effort", config=config)
        assert output is not None
        assert "medium" in output

    def test_effort_switch(self, registry, config):
        output = registry.execute("/effort high", config=config)
        assert output is not None
        assert "high" in output
        assert config.effort_level == EffortLevel.HIGH

    def test_effort_invalid(self, registry, config):
        output = registry.execute("/effort ultra", config=config)
        assert output is not None
        assert "Invalid" in output

    # -- /context --

    def test_context_shows_stats(self, registry, conversation, config):
        output = registry.execute("/context", conversation=conversation, config=config)
        assert output is not None
        assert "Messages:" in output
        assert "system:" in output
        assert "user:" in output
        assert "assistant:" in output

    def test_context_no_conversation(self, registry):
        output = registry.execute("/context")
        assert output is not None
        assert "No conversation" in output

    # -- /clear --

    def test_clear_keeps_system_prompt(self, registry, conversation):
        assert len(conversation.messages) == 3  # system + user + assistant

        output = registry.execute("/clear", conversation=conversation)
        assert output is not None
        assert "cleared" in output.lower()

        # Only system message should remain
        assert len(conversation.messages) == 1
        assert conversation.messages[0]["role"] == "system"

    def test_clear_no_conversation(self, registry):
        output = registry.execute("/clear")
        assert output is not None
        assert "No conversation" in output

    # -- /plan --

    def test_plan_placeholder(self, registry):
        output = registry.execute("/plan build a web app")
        assert output is not None
        assert "not yet connected" in output.lower()
        assert "build a web app" in output

    def test_plan_no_args(self, registry):
        output = registry.execute("/plan")
        assert output is not None
        assert "Usage" in output

    # -- /compact --

    def test_compact_placeholder(self, registry, conversation):
        output = registry.execute("/compact", conversation=conversation)
        assert output is not None
        assert "messages" in output.lower()
        assert "not yet connected" in output.lower()

    def test_compact_no_conversation(self, registry):
        output = registry.execute("/compact")
        assert output is not None
        assert "No conversation" in output


# -----------------------------------------------------------------------
# create_default_commands()
# -----------------------------------------------------------------------


class TestCreateDefaultCommands:
    """Test the factory function."""

    def test_returns_populated_registry(self):
        reg = create_default_commands()
        assert isinstance(reg, CommandRegistry)

        # All expected commands present
        cmds = reg.commands
        expected = {
            "help",
            "exit",
            "cost",
            "model",
            "effort",
            "context",
            "clear",
            "plan",
            "compact",
            "save",
            "load",
            "sessions",
            "fork",
        }
        assert expected.issubset(set(cmds.keys()))

    def test_aliases_work(self):
        reg = create_default_commands()
        assert reg.parse("/quit") is not None
        assert reg.parse("/q") is not None
        assert reg.parse("/h") is not None
        assert reg.parse("/?") is not None
