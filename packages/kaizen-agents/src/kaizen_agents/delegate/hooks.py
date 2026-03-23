"""Hook manager for kz CLI.

Discovers and executes hook scripts from ``.kz/hooks/``.  Scripts are
matched by filename convention:

    ``<event>.<ext>``  or  ``<event>-<name>.<ext>``

where ``<event>`` is one of the :class:`HookEvent` values (case-insensitive,
hyphens normalised) and ``<ext>`` is ``.js`` (Node.js) or ``.py`` (Python).

Examples::

    .kz/hooks/pre-tool-use.js
    .kz/hooks/post-model-validate.py
    .kz/hooks/session-start.js

Execution protocol
------------------

1. The manager serialises the event payload as JSON.
2. The script is spawned as a subprocess (``node`` for ``.js``, ``python``
   for ``.py``).
3. The JSON payload is written to the script's **stdin**.
4. The script writes optional JSON to **stdout**.
5. Exit code determines outcome:
   - 0 = allow (proceed)
   - 1 = error (log warning, continue)
   - 2 = block (abort the operation)
"""

from __future__ import annotations

import asyncio
import enum
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class HookEvent(enum.Enum):
    """Lifecycle events that hooks can subscribe to."""

    PRE_TOOL_USE = "pre-tool-use"
    POST_TOOL_USE = "post-tool-use"
    PRE_MODEL = "pre-model"
    POST_MODEL = "post-model"
    SESSION_START = "session-start"
    SESSION_END = "session-end"


@dataclass
class HookResult:
    """Outcome of running a single hook script.

    Attributes
    ----------
    event:
        The event that triggered the hook.
    script:
        Path to the script that was executed.
    exit_code:
        Process exit code (0=allow, 1=error, 2=block).
    stdout:
        Parsed JSON from stdout, or ``None``.
    stderr:
        Raw stderr output (for diagnostics).
    allowed:
        ``True`` if exit_code == 0.
    blocked:
        ``True`` if exit_code == 2.
    error:
        ``True`` if exit_code == 1 (or any non-0/2 code).
    """

    event: HookEvent
    script: Path
    exit_code: int
    stdout: dict[str, Any] | None = None
    stderr: str = ""

    @property
    def allowed(self) -> bool:
        return self.exit_code == 0

    @property
    def blocked(self) -> bool:
        return self.exit_code == 2

    @property
    def error(self) -> bool:
        return self.exit_code != 0 and self.exit_code != 2


# Extension -> interpreter command
_INTERPRETERS: dict[str, list[str]] = {
    ".js": ["node"],
    ".py": [sys.executable or "python3"],
}


def _normalise_event_prefix(name: str) -> str:
    """Normalise a filename stem to a canonical event prefix.

    ``pre-tool-use``, ``pre_tool_use``, ``PreToolUse`` all become
    ``pre-tool-use``.
    """
    import re

    # Convert CamelCase to hyphenated
    name = re.sub(r"([a-z])([A-Z])", r"\1-\2", name)
    # Underscores to hyphens, lowercase
    return name.replace("_", "-").lower()


class HookManager:
    """Discover and execute hook scripts.

    Parameters
    ----------
    hooks_dir:
        Directory containing hook scripts.  Typically ``.kz/hooks/``.
    timeout:
        Maximum seconds a hook script may run before being killed.
    """

    def __init__(
        self,
        hooks_dir: Path | str,
        *,
        timeout: float = 10.0,
    ) -> None:
        self._dir = Path(hooks_dir)
        self._timeout = timeout
        self._hooks: dict[HookEvent, list[Path]] = {}
        self._discover()

    @property
    def hooks_dir(self) -> Path:
        return self._dir

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _discover(self) -> None:
        """Scan the hooks directory and index scripts by event."""
        self._hooks.clear()

        if not self._dir.is_dir():
            return

        for path in sorted(self._dir.iterdir()):
            if not path.is_file():
                continue
            if path.suffix not in _INTERPRETERS:
                continue

            stem = path.stem  # e.g. "pre-tool-use" or "pre-tool-use-validate"
            prefix = _normalise_event_prefix(stem.split("-", maxsplit=3)[:3] and stem)

            # Match against known events
            # We match the longest prefix that is a valid event
            matched_event: HookEvent | None = None
            for event in HookEvent:
                if prefix == event.value or prefix.startswith(event.value):
                    matched_event = event
                    break

            if matched_event is None:
                logger.debug("Skipping unrecognised hook file: %s", path.name)
                continue

            self._hooks.setdefault(matched_event, []).append(path)

        total = sum(len(v) for v in self._hooks.values())
        if total:
            logger.info("Discovered %d hook(s) in %s", total, self._dir)

    def refresh(self) -> None:
        """Re-scan the hooks directory."""
        self._discover()

    def get_hooks(self, event: HookEvent) -> list[Path]:
        """Return script paths registered for *event*."""
        return list(self._hooks.get(event, []))

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def run_hooks(
        self,
        event: HookEvent,
        payload: dict[str, Any],
    ) -> list[HookResult]:
        """Execute all hooks for *event* sequentially.

        Parameters
        ----------
        event:
            The lifecycle event.
        payload:
            JSON-serialisable dict sent to each hook's stdin.

        Returns
        -------
        List of :class:`HookResult`, one per script.  If any hook
        returns exit code 2 (block), remaining hooks are **not** executed.
        """
        scripts = self._hooks.get(event, [])
        if not scripts:
            return []

        results: list[HookResult] = []
        payload_bytes = json.dumps(payload, default=str).encode("utf-8")

        for script in scripts:
            result = await self._run_single(event, script, payload_bytes)
            results.append(result)

            if result.blocked:
                logger.warning("Hook BLOCKED by %s (event=%s)", script.name, event.value)
                break

            if result.error:
                logger.warning(
                    "Hook error in %s (event=%s, exit=%d): %s",
                    script.name,
                    event.value,
                    result.exit_code,
                    result.stderr[:500] if result.stderr else "(no stderr)",
                )

        return results

    async def _run_single(
        self,
        event: HookEvent,
        script: Path,
        payload_bytes: bytes,
    ) -> HookResult:
        """Run a single hook script as a subprocess.

        Parameters
        ----------
        event:
            The event being fired.
        script:
            Path to the script.
        payload_bytes:
            Pre-serialised JSON payload for stdin.

        Returns
        -------
        :class:`HookResult` with the outcome.
        """
        interpreter = _INTERPRETERS.get(script.suffix)
        if interpreter is None:
            return HookResult(
                event=event,
                script=script,
                exit_code=1,
                stderr=f"No interpreter for {script.suffix}",
            )

        cmd = interpreter + [str(script)]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "KZ_HOOK_EVENT": event.value},
            )

            stdout_raw, stderr_raw = await asyncio.wait_for(
                proc.communicate(input=payload_bytes),
                timeout=self._timeout,
            )

            exit_code = proc.returncode or 0
            stderr_str = stderr_raw.decode("utf-8", errors="replace") if stderr_raw else ""

            # Parse stdout JSON if present
            stdout_data: dict[str, Any] | None = None
            if stdout_raw and stdout_raw.strip():
                try:
                    stdout_data = json.loads(stdout_raw)
                except json.JSONDecodeError:
                    logger.debug(
                        "Hook %s stdout is not valid JSON: %s",
                        script.name,
                        stdout_raw[:200],
                    )

            return HookResult(
                event=event,
                script=script,
                exit_code=exit_code,
                stdout=stdout_data,
                stderr=stderr_str,
            )

        except asyncio.TimeoutError:
            logger.error("Hook %s timed out after %.1fs", script.name, self._timeout)
            # Attempt to kill the process
            try:
                proc.kill()  # type: ignore[possibly-undefined]
            except ProcessLookupError:
                pass
            return HookResult(
                event=event,
                script=script,
                exit_code=1,
                stderr=f"Timed out after {self._timeout}s",
            )

        except OSError as exc:
            logger.error("Failed to spawn hook %s: %s", script.name, exc)
            return HookResult(
                event=event,
                script=script,
                exit_code=1,
                stderr=str(exc),
            )
