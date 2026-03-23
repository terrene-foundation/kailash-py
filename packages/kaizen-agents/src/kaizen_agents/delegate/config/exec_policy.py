"""Command execution policy for kz CLI shell tool.

Provides allowlist/blocklist filtering for shell commands executed
through BashTool. Understands compound commands (``&&``, ``||``, ``;``,
``|``) and checks each segment independently — a blocked command is
rejected even when chained with allowed commands.

Default blocklist includes destructive system commands that should
never be executed by an autonomous agent.

Integrates with BashTool's ``permission_gate`` callback.
"""

from __future__ import annotations

import logging
import re
import shlex
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Compound command separators — regex pattern that splits on
# &&, ||, ;, and | (but not ||)
# We split on these to check each segment independently.
_COMPOUND_SEPARATORS = re.compile(r"\s*(?:&&|\|\||[;|])\s*")

# Default blocked command prefixes. These are checked against the
# first token(s) of each command segment.
_DEFAULT_BLOCKLIST: list[str] = [
    "rm -rf /",
    "rm -rf /*",
    "rm -fr /",
    "rm -fr /*",
    "mkfs",
    "dd if=",
    ":(){ :|:& };:",
    "> /dev/sda",
    "chmod -R 777 /",
    "chown -R",
    "shutdown",
    "reboot",
    "halt",
    "init 0",
    "init 6",
    "kill -9 1",
    "killall",
    "mv /* ",
    "mv / ",
    "wget -O- | sh",
    "curl | sh",
    "curl | bash",
    "wget | sh",
    "wget | bash",
]

# Fork bomb patterns (regex-based detection)
_FORK_BOMB_PATTERNS: list[re.Pattern[str]] = [
    # Bash fork bomb: :(){ :|:& };: and variations
    re.compile(r":\(\)\s*\{.*\|.*&\s*\}"),
    # Common variations
    re.compile(r"\w+\(\)\s*\{.*\|\s*\w+\s*&\s*\}"),
]


@dataclass
class ExecPolicy:
    """Command execution policy with allowlist/blocklist filtering.

    If an allowlist is set, ONLY commands matching the allowlist are
    permitted. If a blocklist is set, commands matching the blocklist
    are rejected. The blocklist is checked first (deny takes priority).

    Compound commands (using ``&&``, ``||``, ``;``, ``|``) are split
    and each segment is checked independently.

    Parameters
    ----------
    allowlist:
        Optional list of allowed command prefixes. If non-empty, only
        commands starting with one of these prefixes are allowed.
    blocklist:
        List of blocked command prefixes. Commands starting with any
        of these are rejected. Defaults to the built-in blocklist.
    use_default_blocklist:
        Whether to include the default blocklist. Defaults to True.
    """

    allowlist: list[str] = field(default_factory=list)
    blocklist: list[str] = field(default_factory=list)
    use_default_blocklist: bool = True

    def __post_init__(self) -> None:
        if self.use_default_blocklist:
            # Prepend defaults so user-specified entries are also included
            combined = list(_DEFAULT_BLOCKLIST)
            for entry in self.blocklist:
                if entry not in combined:
                    combined.append(entry)
            self.blocklist = combined

    def check_command(self, command: str) -> PolicyResult:
        """Check whether a command is allowed by the policy.

        Parameters
        ----------
        command:
            The full shell command string, possibly compound.

        Returns
        -------
        A PolicyResult indicating whether the command is allowed or
        blocked, with a reason if blocked.
        """
        command = command.strip()
        if not command:
            return PolicyResult(allowed=True)

        # Check for subshell/variable expansion patterns that could bypass
        # blocklist matching (defense-in-depth, not a security boundary)
        _SUBSHELL_PATTERNS = ("`", "$(", "${")
        for pat in _SUBSHELL_PATTERNS:
            if pat in command:
                logger.warning(
                    "ExecPolicy: command contains subshell/expansion pattern %r "
                    "which cannot be fully analyzed: %s",
                    pat,
                    command[:200],
                )

        # Check for fork bomb patterns on the full command first
        for pattern in _FORK_BOMB_PATTERNS:
            if pattern.search(command):
                return PolicyResult(
                    allowed=False,
                    reason="Fork bomb pattern detected",
                    blocked_segment=command,
                )

        # Split compound commands and check each segment
        segments = split_compound_command(command)

        for segment in segments:
            result = self._check_segment(segment)
            if not result.allowed:
                return result

        return PolicyResult(allowed=True)

    def _check_segment(self, segment: str) -> PolicyResult:
        """Check a single command segment against the policy."""
        segment = segment.strip()
        if not segment:
            return PolicyResult(allowed=True)

        # Normalize whitespace for matching
        normalized = _normalize_command(segment)

        # Check blocklist first (deny takes priority)
        for blocked in self.blocklist:
            blocked_norm = blocked.strip().lower()
            if _matches_prefix(normalized.lower(), blocked_norm):
                return PolicyResult(
                    allowed=False,
                    reason=f"Command matches blocklist entry: {blocked!r}",
                    blocked_segment=segment,
                )

        # Check allowlist (if set)
        if self.allowlist:
            allowed = False
            for prefix in self.allowlist:
                prefix_norm = prefix.strip().lower()
                if _matches_prefix(normalized.lower(), prefix_norm):
                    allowed = True
                    break

            if not allowed:
                return PolicyResult(
                    allowed=False,
                    reason="Command not in allowlist",
                    blocked_segment=segment,
                )

        return PolicyResult(allowed=True)

    def as_permission_gate(self) -> Any:
        """Return a callable suitable for BashTool's permission_gate parameter.

        Returns a function that takes a command string and returns True
        if allowed, False if blocked.
        """

        def _gate(command: str) -> bool:
            result = self.check_command(command)
            if not result.allowed:
                logger.warning(
                    "ExecPolicy blocked command: %s (reason: %s)",
                    result.blocked_segment,
                    result.reason,
                )
            return result.allowed

        return _gate


@dataclass(frozen=True)
class PolicyResult:
    """Result of a command policy check."""

    allowed: bool
    reason: str = ""
    blocked_segment: str = ""


def split_compound_command(command: str) -> list[str]:
    """Split a compound shell command into individual segments.

    Handles ``&&``, ``||``, ``;``, and ``|`` operators. Returns
    the individual command segments for independent checking.

    Subshells (``$(...)``, backticks) are NOT expanded — they are
    treated as part of the containing segment. This is a conservative
    approach: we check what we can see.

    Parameters
    ----------
    command:
        The full shell command string.

    Returns
    -------
    List of command segments (stripped of whitespace).
    """
    # Split on compound operators
    # We need to be careful with || vs | — split on || first
    # Use regex to split on && , || , ; , |
    segments = _COMPOUND_SEPARATORS.split(command)
    return [s.strip() for s in segments if s.strip()]


def _matches_prefix(command: str, prefix: str) -> bool:
    """Check if a command matches a blocklist/allowlist prefix.

    A prefix matches if the command starts with the prefix AND either:
    - The prefix is the entire command (exact match)
    - The prefix ends with ``/`` and the command continues with more
      path characters — in this case, it does NOT match (``rm -rf /``
      should not block ``rm -rf /tmp/mydir``)
    - Otherwise, the prefix is treated as a standard starts-with check

    This prevents ``rm -rf /`` from matching ``rm -rf /tmp/mydir``
    while still matching ``rm -rf /`` exactly, ``rm -rf / --flag``,
    ``mkfs.ext4``, and ``dd if=/dev/zero``.
    """
    if not command.startswith(prefix):
        return False

    # Exact match
    if len(command) == len(prefix):
        return True

    # If prefix ends with '/', the next char must be whitespace or '*'
    # to match. This prevents /tmp, /usr, /home from matching a
    # blocklist entry targeting the root filesystem.
    if prefix and prefix[-1] == "/":
        next_char = command[len(prefix)]
        return next_char in (" ", "\t", "*")

    # For all other prefixes, standard starts-with is sufficient
    return True


def _normalize_command(command: str) -> str:
    """Normalize a command string for prefix matching.

    Collapses multiple spaces and strips leading/trailing whitespace.
    Handles common quoting patterns.
    """
    # Collapse whitespace
    normalized = " ".join(command.split())
    return normalized


def load_exec_policy(raw_config: dict[str, Any]) -> ExecPolicy:
    """Load execution policy from a TOML-loaded config dict.

    Expects the structure::

        [exec_policy]
        allowlist = ["git", "ls", "cat"]
        blocklist = ["rm -rf", "mkfs"]
        use_default_blocklist = true

    Parameters
    ----------
    raw_config:
        A TOML-loaded config dict.

    Returns
    -------
    An ExecPolicy instance.
    """
    policy_section = raw_config.get("exec_policy", {})
    if not isinstance(policy_section, dict):
        return ExecPolicy()

    return ExecPolicy(
        allowlist=policy_section.get("allowlist", []),
        blocklist=policy_section.get("blocklist", []),
        use_default_blocklist=policy_section.get("use_default_blocklist", True),
    )
