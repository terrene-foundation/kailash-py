from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Local file-based agent registry.

Stores agent manifests as JSON files in a directory on disk.
Default location: ``~/.kaizen/registry/``

All agent names are validated against ``[a-zA-Z0-9_-]+`` to prevent
path traversal and injection attacks.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = ["FileRegistry", "LocalRegistry"]

_VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_name(name: str) -> None:
    """Validate an agent name.

    Raises:
        ValueError: If the name is empty, contains whitespace, path separators,
            or other disallowed characters.
    """
    if not name or not _VALID_NAME_RE.match(name):
        raise ValueError(
            f"Invalid agent name: {name!r}. Must match [a-zA-Z0-9_-]+ "
            f"(no spaces, slashes, dots, or special characters)"
        )


def _atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* atomically via temp-file + fsync + replace.

    On POSIX the temp file is chmod'd to owner-read/write only (0o600).
    If any step fails, the temp file is cleaned up and the exception is
    re-raised so that a partial write never corrupts the target file.
    """
    import tempfile

    parent = path.parent
    fd, tmp_path = tempfile.mkstemp(dir=str(parent), suffix=".tmp")
    try:
        os.write(fd, content.encode("utf-8"))
        os.fsync(fd)
        os.close(fd)
        fd = -1
        if os.name != "nt":
            import stat

            os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp_path, str(path))
    except BaseException:
        if fd >= 0:
            os.close(fd)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


class FileRegistry:
    """File-based local agent registry.

    Stores agent manifests as JSON files in a directory.
    Default location: ``~/.kaizen/registry/``

    Args:
        registry_dir: Path to the registry directory.  If ``None``,
            defaults to ``~/.kaizen/registry/``.
    """

    def __init__(self, registry_dir: Optional[str] = None) -> None:
        if registry_dir is None:
            registry_dir = os.path.join(os.path.expanduser("~"), ".kaizen", "registry")
        self._dir = Path(registry_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def register(self, manifest_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Register an agent manifest.

        Persists the manifest as a JSON file named ``{name}.json``
        in the registry directory.

        Args:
            manifest_dict: Agent manifest data.  Must contain a ``"name"``
                key with a valid agent name.

        Returns:
            Dict with ``agent_name``, ``status``, ``mode``, and ``path`` keys.

        Raises:
            ValueError: If the agent name is invalid.
        """
        name = manifest_dict.get("name", "")
        _validate_name(name)
        path = self._dir / f"{name}.json"
        _atomic_write(path, json.dumps(manifest_dict, indent=2, default=str))
        logger.info("Registered agent %r at %s", name, path)
        return {
            "agent_name": name,
            "status": "registered",
            "mode": "local",
            "path": str(path),
        }

    def list_agents(self) -> List[Dict[str, Any]]:
        """List all registered agents.

        Returns:
            List of manifest dicts, sorted by filename.
        """
        agents: List[Dict[str, Any]] = []
        for path in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(path.read_text())
                agents.append(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read agent manifest %s: %s", path, exc)
        return agents

    def get_agent(self, name: str) -> Optional[Dict[str, Any]]:
        """Get an agent manifest by name.

        Args:
            name: Agent name.

        Returns:
            Manifest dict, or ``None`` if not found.

        Raises:
            ValueError: If the name is invalid.
        """
        _validate_name(name)
        path = self._dir / f"{name}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read agent manifest %s: %s", path, exc)
            return None

    def deregister(self, name: str) -> bool:
        """Remove an agent from the registry.

        Args:
            name: Agent name.

        Returns:
            ``True`` if the agent was found and removed; ``False`` otherwise.

        Raises:
            ValueError: If the name is invalid.
        """
        _validate_name(name)
        path = self._dir / f"{name}.json"
        if path.exists():
            path.unlink()
            logger.info("Deregistered agent %r", name)
            return True
        return False


# Backward-compatible alias -- existing code imports ``LocalRegistry``
LocalRegistry = FileRegistry
