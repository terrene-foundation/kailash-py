# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Mtime-based resource cache for MCP platform discovery (MCP-507).

Caches computed MCP resource data (platform maps, model lists, etc.) and
invalidates when source files change. Thread-safe for concurrent MCP access.

The cache watches a project directory for file modifications. When any
Python file's mtime changes, cached resources are invalidated and rebuilt
on the next access.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

__all__ = ["ResourceCache"]

# Directories to skip when scanning for mtime changes
_SKIP_DIRS = frozenset(
    {
        "__pycache__",
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)


class ResourceCache:
    """Mtime-based cache for MCP resource builders.

    Watches a project directory for file changes. When any Python file's
    mtime changes, cached data is invalidated and rebuilt on the next
    ``get_or_refresh()`` call.

    Thread-safe: concurrent calls to ``get_or_refresh()`` are serialized
    via a lock. The builder runs at most once per invalidation cycle.

    Args:
        project_path: Root directory to watch for file changes.
        extensions: File extensions to monitor (default: .py files).
    """

    def __init__(
        self,
        project_path: Path | str,
        extensions: tuple[str, ...] = (".py",),
    ) -> None:
        self._project_path = Path(project_path)
        self._extensions = extensions
        self._lock = threading.Lock()
        self._cache: dict[str, Any] = {}
        self._last_mtime: float = 0.0

    def get_or_refresh(
        self,
        uri: str,
        builder: Callable[[], Any],
    ) -> Any:
        """Get cached data or rebuild if source files changed.

        Args:
            uri: Cache key (typically an MCP resource URI).
            builder: Callable that produces the data to cache.

        Returns:
            Cached or freshly built data.
        """
        with self._lock:
            current_mtime = self._scan_max_mtime()
            if current_mtime != self._last_mtime:
                # Source files changed — invalidate everything
                self._cache.clear()
                self._last_mtime = current_mtime

            if uri not in self._cache:
                self._cache[uri] = builder()

            return self._cache[uri]

    def invalidate(self, uri: str | None = None) -> None:
        """Invalidate cached data.

        Args:
            uri: Specific URI to invalidate. If None, invalidates all.
        """
        with self._lock:
            if uri is None:
                self._cache.clear()
                self._last_mtime = 0.0  # Force rescan on next access
            else:
                self._cache.pop(uri, None)

    def _scan_max_mtime(self) -> float:
        """Scan project directory for the latest mtime among tracked files.

        Skips hidden directories and __pycache__.
        """
        max_mtime = 0.0
        if not self._project_path.is_dir():
            return max_mtime

        for root, dirs, files in os.walk(self._project_path):
            # Prune hidden dirs and __pycache__ in-place
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _SKIP_DIRS]
            for f in files:
                if any(f.endswith(ext) for ext in self._extensions):
                    try:
                        mtime = os.path.getmtime(os.path.join(root, f))
                        if mtime > max_mtime:
                            max_mtime = mtime
                    except OSError:
                        pass

        return max_mtime
