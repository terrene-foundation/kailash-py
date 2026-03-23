"""Session management for kz CLI.

Sessions are persisted as JSON files under ``<root>/.kz/sessions/``.  Each
file contains the conversation messages, usage statistics, a config
snapshot, and metadata (timestamp, turn count).
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from kaizen_agents.delegate.loop import Conversation, UsageTracker
    from kaizen_agents.delegate.config.loader import KzConfig

logger = logging.getLogger(__name__)


class SessionManager:
    """Manage saved sessions on disk.

    Parameters
    ----------
    sessions_dir:
        Directory where session JSON files are stored.  Defaults to
        ``.kz/sessions/`` under the project root.
    """

    def __init__(self, sessions_dir: Path | str) -> None:
        self._dir = Path(sessions_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def sessions_dir(self) -> Path:
        """Path to the sessions directory."""
        return self._dir

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_session(
        self,
        name: str,
        conversation: Conversation | None = None,
        usage: UsageTracker | None = None,
        config: KzConfig | None = None,
    ) -> Path:
        """Persist the current session state to disk.

        Parameters
        ----------
        name:
            Session name (used as the filename stem).
        conversation:
            The conversation to save.
        usage:
            Token usage tracker to save.
        config:
            Config snapshot to include.

        Returns
        -------
        Path to the written JSON file.
        """
        now = datetime.now(timezone.utc).isoformat()

        messages = conversation.messages if conversation else []
        user_turns = sum(1 for m in messages if m.get("role") == "user")

        data: dict[str, Any] = {
            "name": name,
            "timestamp": now,
            "turn_count": user_turns,
            "message_count": len(messages),
            "messages": messages,
            "usage": {
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0,
                "turns": usage.turns if usage else 0,
            },
            "config": {
                "model": config.model if config else None,
                "effort_level": config.effort_level.value if config else None,
                "max_turns": config.max_turns if config else None,
                "max_tokens": config.max_tokens if config else None,
                "temperature": config.temperature if config else None,
            },
        }

        path = self._session_path(name)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        logger.info("Session saved: %s", path)
        return path

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load_session(self, name: str) -> dict[str, Any] | None:
        """Load a session from disk.

        Parameters
        ----------
        name:
            Session name.

        Returns
        -------
        The parsed session dict, or ``None`` if the session file does not
        exist.
        """
        path = self._session_path(name)
        if not path.is_file():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load session %s: %s", name, exc)
            return None

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all saved sessions with metadata.

        Returns
        -------
        A list of dicts with ``name``, ``timestamp``, ``turn_count``,
        and ``message_count`` keys.  Sorted by timestamp descending
        (newest first).
        """
        sessions: list[dict[str, Any]] = []

        for path in self._dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                sessions.append(
                    {
                        "name": data.get("name", path.stem),
                        "timestamp": data.get("timestamp", "unknown"),
                        "turn_count": data.get("turn_count", 0),
                        "message_count": data.get("message_count", 0),
                    }
                )
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping unreadable session file %s: %s", path, exc)

        sessions.sort(key=lambda s: s["timestamp"], reverse=True)
        return sessions

    # ------------------------------------------------------------------
    # Fork
    # ------------------------------------------------------------------

    def fork_session(self, source_name: str, new_name: str) -> Path | None:
        """Copy an existing session as a new session.

        Parameters
        ----------
        source_name:
            Name of the session to copy from.
        new_name:
            Name for the forked session.

        Returns
        -------
        Path to the new session file, or ``None`` if the source does not
        exist.
        """
        source_path = self._session_path(source_name)
        if not source_path.is_file():
            return None

        dest_path = self._session_path(new_name)
        shutil.copy2(source_path, dest_path)

        # Update the name and timestamp in the forked file
        try:
            data = json.loads(dest_path.read_text(encoding="utf-8"))
            data["name"] = new_name
            data["timestamp"] = datetime.now(timezone.utc).isoformat()
            dest_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to update forked session metadata: %s", exc)

        logger.info("Session forked: %s -> %s", source_name, new_name)
        return dest_path

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_session(self, name: str) -> bool:
        """Delete a saved session.

        Parameters
        ----------
        name:
            Session name to delete.

        Returns
        -------
        ``True`` if the file was deleted, ``False`` if it did not exist.
        """
        path = self._session_path(name)
        if not path.is_file():
            return False

        path.unlink()
        logger.info("Session deleted: %s", name)
        return True

    # ------------------------------------------------------------------
    # Auto-save
    # ------------------------------------------------------------------

    def auto_save(
        self,
        conversation: Conversation | None = None,
        usage: UsageTracker | None = None,
        config: KzConfig | None = None,
    ) -> Path:
        """Auto-save the current session as ``_auto``.

        Called after each turn to provide crash recovery.

        Returns
        -------
        Path to the auto-save file.
        """
        return self.save_session(
            name="_auto",
            conversation=conversation,
            usage=usage,
            config=config,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _session_path(self, name: str) -> Path:
        """Resolve a session name to a file path.

        Sanitizes the name to prevent path traversal.
        """
        # Allowlist-based sanitization: keep only safe characters
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        if not safe_name or safe_name.startswith(("-", ".")):
            safe_name = "_" + safe_name
        return self._dir / f"{safe_name}.json"
