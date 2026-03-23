"""Slash command registry for kz CLI.

Commands are slash-prefixed strings (``/help``, ``/cost``, etc.) that the
user types at the prompt.  The registry detects them, parses arguments, and
dispatches to the registered handler.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class SlashCommand:
    """A single registered slash command."""

    name: str
    description: str
    handler: Callable[..., str | None]
    aliases: list[str] = field(default_factory=list)


# Pattern: starts with /, followed by a word (or single special char like ?),
# then optional whitespace + args
_COMMAND_RE = re.compile(r"^/([a-zA-Z_?][a-zA-Z0-9_-]*)\s*(.*)?$", re.DOTALL)


class CommandRegistry:
    """Registry that maps ``/name`` strings to command handlers.

    Usage::

        reg = CommandRegistry()
        reg.register("help", "Show help", handler=my_help_fn)

        result = reg.parse("/help")
        # result == ("help", "")

        output = reg.execute("/help")
        # calls my_help_fn("") and returns the output string
    """

    def __init__(self) -> None:
        self._commands: dict[str, SlashCommand] = {}
        self._aliases: dict[str, str] = {}  # alias -> canonical name

    def register(
        self,
        name: str,
        description: str,
        handler: Callable[..., str | None],
        *,
        aliases: list[str] | None = None,
    ) -> None:
        """Register a slash command.

        Parameters
        ----------
        name:
            Canonical command name (without the leading ``/``).
        description:
            One-line description shown in ``/help``.
        handler:
            Callable that receives ``(args: str, **context)`` and returns
            an optional display string.  ``args`` is everything after the
            command name. ``context`` contains ``config``, ``conversation``,
            ``usage``, and ``session_manager`` when available.
        aliases:
            Alternative names for the command (e.g. ``["q"]`` for ``quit``).
        """
        cmd = SlashCommand(
            name=name,
            description=description,
            handler=handler,
            aliases=aliases or [],
        )
        self._commands[name] = cmd
        for alias in cmd.aliases:
            self._aliases[alias] = name

    def parse(self, user_input: str) -> tuple[str, str] | None:
        """Parse user input for a slash command.

        Parameters
        ----------
        user_input:
            Raw user input string.

        Returns
        -------
        ``(command_name, args)`` if the input starts with a registered
        command (or alias), otherwise ``None``.
        """
        match = _COMMAND_RE.match(user_input.strip())
        if match is None:
            return None

        name = match.group(1).lower()
        args = (match.group(2) or "").strip()

        # Resolve alias
        canonical = self._aliases.get(name, name)

        if canonical not in self._commands:
            return None

        return (canonical, args)

    def execute(self, user_input: str, **context: Any) -> str | None:
        """Parse and execute a slash command.

        Parameters
        ----------
        user_input:
            Raw user input.
        **context:
            Keyword arguments forwarded to the handler (``config``,
            ``conversation``, ``usage``, ``session_manager``, etc.).

        Returns
        -------
        The handler's return string, or ``None`` if the input is not a
        command.

        Raises
        ------
        KeyError:
            If the parsed command name is not registered (should not happen
            after a successful ``parse``).
        """
        parsed = self.parse(user_input)
        if parsed is None:
            return None

        name, args = parsed
        cmd = self._commands[name]
        return cmd.handler(args, **context)

    def get_command(self, name: str) -> SlashCommand | None:
        """Look up a command by canonical name."""
        return self._commands.get(name)

    @property
    def commands(self) -> dict[str, SlashCommand]:
        """All registered commands (canonical name -> SlashCommand)."""
        return dict(self._commands)

    def is_command(self, user_input: str) -> bool:
        """Return ``True`` if the input would be parsed as a slash command."""
        return self.parse(user_input) is not None
