# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
File Source Adapter — local file data source for the Data Fabric Engine.

Supports automatic parsing based on file extension (.json, .yaml, .csv, .xlsx)
and optional watchdog-based file change monitoring via a background daemon thread
bridged to the async event loop.

Security: file paths are resolved to absolute, ``..`` components are rejected,
and all access is confined to the file's parent directory (M4 resolution from
redteam report ``01-redteam``).

Watchdog integration follows RT-7: the observer thread uses
``asyncio.run_coroutine_threadsafe()`` to bridge filesystem events into the
async event loop.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from dataflow.adapters.source_adapter import BaseSourceAdapter
from dataflow.fabric.config import FileSourceConfig

logger = logging.getLogger(__name__)

__all__ = [
    "FileSourceAdapter",
]

# ---------------------------------------------------------------------------
# Supported file extensions → parser names
# ---------------------------------------------------------------------------

_EXTENSION_PARSERS: Dict[str, str] = {
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".csv": "csv",
    ".xlsx": "xlsx",
}


def _validate_file_path(raw_path: str, base_dir: Optional[Path] = None) -> Path:
    """Resolve and validate a file path.

    Security (M4):
    - Resolves to an absolute path via ``Path.resolve()``.
    - Rejects paths whose string representation contains ``..`` after resolution.
    - If *base_dir* is provided, ensures the resolved path is within it.

    Returns:
        The resolved ``Path``.

    Raises:
        ValueError: If the path is empty, contains ``..``, or escapes *base_dir*.
    """
    if not raw_path:
        raise ValueError("File path must not be empty")

    resolved = Path(raw_path).resolve()

    # After resolution ``..`` should be gone, but reject if still present
    # (defensive — protects against symlink tricks on some platforms).
    if ".." in resolved.parts:
        raise ValueError(
            f"File path must not contain '..' components after resolution: {resolved}"
        )

    if base_dir is not None:
        base_resolved = base_dir.resolve()
        try:
            resolved.relative_to(base_resolved)
        except ValueError:
            raise ValueError(
                f"File path '{resolved}' is outside the allowed base directory "
                f"'{base_resolved}'"
            ) from None

    return resolved


def _parse_json(raw: str) -> Any:
    """Parse a JSON string."""
    return json.loads(raw)


def _parse_yaml(raw: str) -> Any:
    """Parse a YAML string (lazy imports ``yaml``)."""
    try:
        import yaml
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required to parse YAML files. "
            "Install it with: pip install pyyaml"
        ) from exc
    return yaml.safe_load(raw)


def _parse_csv(raw: str) -> List[Dict[str, str]]:
    """Parse a CSV string into a list of dicts (via ``csv.DictReader``)."""
    reader = csv.DictReader(io.StringIO(raw))
    return list(reader)


def _parse_xlsx(path: Path) -> List[Dict[str, Any]]:
    """Parse an XLSX file into a list of dicts (lazy imports ``openpyxl``).

    Reads the first (active) sheet. The first row is treated as headers.
    """
    try:
        import openpyxl
    except ImportError as exc:
        raise ImportError(
            "openpyxl is required to parse .xlsx files. "
            "Install it with: pip install openpyxl"
        ) from exc

    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    try:
        ws = wb.active
        if ws is None:
            return []

        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 1:
            return []

        headers = [
            str(h) if h is not None else f"col_{i}" for i, h in enumerate(rows[0])
        ]
        result: List[Dict[str, Any]] = []
        for row in rows[1:]:
            record: Dict[str, Any] = {}
            for idx, value in enumerate(row):
                key = headers[idx] if idx < len(headers) else f"col_{idx}"
                record[key] = value
            result.append(record)
        return result
    finally:
        wb.close()


_TEXT_PARSERS: Dict[str, Any] = {
    "json": _parse_json,
    "yaml": _parse_yaml,
    "csv": _parse_csv,
}


class FileSourceAdapter(BaseSourceAdapter):
    """Adapter for local file data sources.

    Reads local files with automatic extension-based parsing and optional
    watchdog-based change monitoring.

    Supports two modes:

    - **Single file**: ``config.path`` set — reads one specific file.
    - **Directory scanning**: ``config.directory`` + ``config.pattern`` set —
      scans for the latest matching file by name or mtime.

    Args:
        name: Unique source name.
        config: ``FileSourceConfig`` with path/directory, watch, and parser fields.
    """

    def __init__(self, name: str, config: FileSourceConfig, **kwargs: Any) -> None:
        super().__init__(name=name, **kwargs)
        self.config = config
        self._resolved_path: Optional[Path] = None
        self._base_dir: Optional[Path] = None
        self._watch_dir: Optional[Path] = None
        self._last_mtime: float = 0.0
        self._file_changed: bool = False
        self._observer: Any = None  # watchdog.observers.Observer
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def source_type(self) -> str:
        return "file"

    def supports_feature(self, feature: str) -> bool:
        supported = {"detect_change", "fetch", "fetch_pages", "write"}
        return feature in supported

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def _connect(self) -> None:
        """Resolve the file path, verify readability, and optionally start a watchdog."""
        self.config.validate()

        if self.config.directory:
            # Directory scanning mode
            self._watch_dir = Path(self.config.directory).resolve()
            if not self._watch_dir.is_dir():
                raise FileNotFoundError(
                    f"Source directory does not exist: {self._watch_dir}"
                )
            self._base_dir = self._watch_dir
            self._resolved_path = self._resolve_latest()
        else:
            # Single-file mode (original behaviour)
            self._base_dir = Path(self.config.path).resolve().parent
            self._resolved_path = _validate_file_path(self.config.path, self._base_dir)

            if not self._resolved_path.exists():
                raise FileNotFoundError(
                    f"Source file does not exist: {self._resolved_path}"
                )

        if not os.access(self._resolved_path, os.R_OK):
            raise PermissionError(f"Source file is not readable: {self._resolved_path}")

        # Capture initial mtime
        self._last_mtime = self._resolved_path.stat().st_mtime

        # Start watchdog if requested (RT-7 integration)
        if self.config.watch:
            self._loop = asyncio.get_running_loop()
            self._start_watchdog()

        logger.info(
            "FileSourceAdapter '%s' connected to '%s' (watch=%s, dir_mode=%s)",
            self.name,
            self._resolved_path,
            self.config.watch,
            self._watch_dir is not None,
        )

    async def _disconnect(self) -> None:
        """Stop the watchdog observer if running."""
        self._stop_watchdog()
        self._loop = None
        logger.info("FileSourceAdapter '%s' disconnected", self.name)

    # ------------------------------------------------------------------
    # Change detection
    # ------------------------------------------------------------------

    async def detect_change(self) -> bool:
        """Detect file changes via mtime comparison (sub-millisecond).

        In directory mode, re-scans the directory and checks whether the
        latest matching file has changed (different file selected, or the
        same file was modified).

        If the watchdog has signalled a change, this returns ``True``
        immediately and resets the flag.  Otherwise it stats the file and
        compares the modification time.
        """
        if self._resolved_path is None:
            raise RuntimeError(
                f"FileSourceAdapter '{self.name}' is not connected — "
                "call connect() first"
            )

        # Fast path: watchdog already detected a change
        if self._file_changed:
            self._file_changed = False
            if self._watch_dir is not None:
                try:
                    new_latest = self._resolve_latest()
                except FileNotFoundError:
                    return False
                if new_latest != self._resolved_path:
                    self._resolved_path = new_latest
                    self._last_mtime = new_latest.stat().st_mtime
                    return True
            self._last_mtime = self._resolved_path.stat().st_mtime
            return True

        # Directory mode: re-scan for new files
        if self._watch_dir is not None:
            try:
                new_latest = self._resolve_latest()
            except FileNotFoundError:
                return False
            if new_latest != self._resolved_path:
                self._resolved_path = new_latest
                self._last_mtime = new_latest.stat().st_mtime
                return True

        # Poll mtime on the current file
        try:
            current_mtime = self._resolved_path.stat().st_mtime
        except FileNotFoundError:
            logger.warning(
                "Source file '%s' no longer exists for adapter '%s'",
                self._resolved_path,
                self.name,
            )
            return False

        if current_mtime != self._last_mtime:
            self._last_mtime = current_mtime
            return True
        return False

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    async def fetch(
        self, path: str = "", params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Read and parse a file.

        Args:
            path: Optional file path override.  When empty, uses
                ``self.config.path``.
            params: Unused for file adapter; reserved for API consistency.

        Returns:
            Parsed file contents.  Format depends on the file extension
            (or the ``config.parser`` override):
            - ``.json`` -- deserialized JSON
            - ``.yaml`` / ``.yml`` -- deserialized YAML
            - ``.csv`` -- list of dicts
            - ``.xlsx`` -- list of dicts
            - other -- raw text string
        """
        target = self._resolve_target(path)
        parser_name = self._determine_parser(target)

        if parser_name == "xlsx":
            data = _parse_xlsx(target)
        else:
            raw = target.read_text(encoding="utf-8")
            text_parser = _TEXT_PARSERS.get(parser_name)
            if text_parser is not None:
                data = text_parser(raw)
            else:
                data = raw

        self._record_successful_data(path, data)
        return data

    # ------------------------------------------------------------------
    # Paginated fetch
    # ------------------------------------------------------------------

    async def fetch_pages(
        self, path: str = "", page_size: int = 100
    ) -> AsyncIterator[List[Any]]:
        """Yield data in pages.

        For CSV and XLSX files the rows are chunked into pages of
        *page_size*.  For all other formats the entire file content is
        yielded as a single page.
        """
        target = self._resolve_target(path)
        parser_name = self._determine_parser(target)

        if parser_name == "csv":
            raw = target.read_text(encoding="utf-8")
            reader = csv.DictReader(io.StringIO(raw))
            page: List[Any] = []
            for row in reader:
                page.append(row)
                if len(page) >= page_size:
                    yield page
                    page = []
            if page:
                yield page
        elif parser_name == "xlsx":
            all_rows = _parse_xlsx(target)
            for i in range(0, len(all_rows), page_size):
                yield all_rows[i : i + page_size]
        else:
            # Non-tabular formats: yield entire content as a single page
            data = await self.fetch(path)
            if isinstance(data, list):
                for i in range(0, len(data), page_size):
                    yield data[i : i + page_size]
            else:
                yield [data]

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def write(self, path: str, data: Any) -> Any:
        """Write data to a file.

        If *data* is a ``dict`` or ``list``, it is serialized as JSON.
        Otherwise it is written as a string.

        Args:
            path: Target file path.  When empty, uses ``self.config.path``.
            data: Data to write.

        Returns:
            A dict with write metadata (bytes written, path).
        """
        target = self._resolve_target(path)

        if isinstance(data, (dict, list)):
            content = json.dumps(data, indent=2, default=str, ensure_ascii=False)
        else:
            content = str(data)

        target.write_text(content, encoding="utf-8")

        bytes_written = len(content.encode("utf-8"))
        logger.info(
            "FileSourceAdapter '%s' wrote %d bytes to '%s'",
            self.name,
            bytes_written,
            target,
        )
        return {"path": str(target), "bytes_written": bytes_written}

    # ------------------------------------------------------------------
    # Watchdog integration (RT-7)
    # ------------------------------------------------------------------

    def _start_watchdog(self) -> None:
        """Start a watchdog observer on the file's directory.

        The watchdog runs in a daemon thread.  Filesystem events for the
        monitored file set ``self._file_changed = True`` via the async
        bridge described in RT-7.
        """
        if self._resolved_path is None or self._loop is None:
            return

        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            logger.warning(
                "watchdog is not installed — file watching disabled for '%s'. "
                "Install it with: pip install watchdog",
                self.name,
            )
            return

        adapter = self
        watched_name = self._resolved_path.name
        loop = self._loop

        class _FileChangeHandler(FileSystemEventHandler):
            """Watches for modifications or creations of the target file."""

            def on_modified(self, event: Any) -> None:
                if event.is_directory:
                    return
                if Path(event.src_path).name == watched_name:
                    self._signal_change()

            def on_created(self, event: Any) -> None:
                if event.is_directory:
                    return
                if Path(event.src_path).name == watched_name:
                    self._signal_change()

            def _signal_change(self) -> None:
                """Bridge the watchdog thread event into the async loop."""
                future = asyncio.run_coroutine_threadsafe(
                    adapter._on_file_changed(), loop
                )
                future.add_done_callback(
                    lambda f: (
                        f.exception()
                        and logger.error(
                            "File change callback error for '%s': %s",
                            adapter.name,
                            f.exception(),
                        )
                    )
                )

        observer = Observer()
        observer.daemon = True
        observer.schedule(
            _FileChangeHandler(),
            str(self._resolved_path.parent),
            recursive=False,
        )
        observer.start()
        self._observer = observer
        logger.debug(
            "Watchdog started for '%s' in directory '%s'",
            self._resolved_path.name,
            self._resolved_path.parent,
        )

    def _stop_watchdog(self) -> None:
        """Stop the watchdog observer if it is running."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None
            logger.debug("Watchdog stopped for adapter '%s'", self.name)

    async def _on_file_changed(self) -> None:
        """Called from the watchdog thread via ``run_coroutine_threadsafe``."""
        self._file_changed = True
        logger.debug("File change detected via watchdog for adapter '%s'", self.name)

    # ------------------------------------------------------------------
    # Directory scanning
    # ------------------------------------------------------------------

    def _resolve_latest(self) -> Path:
        """Find the latest file matching the configured glob pattern.

        Uses ``config.selection`` to choose between lexicographic ordering
        (``latest_name``) and modification time (``latest_mtime``).

        Returns:
            The resolved ``Path`` to the selected file.

        Raises:
            FileNotFoundError: If no files match the pattern.
        """
        if self._watch_dir is None:
            raise RuntimeError("_resolve_latest called outside directory mode")

        matches = sorted(self._watch_dir.glob(self.config.pattern))
        # Filter out directories — only regular files
        matches = [m for m in matches if m.is_file()]

        if not matches:
            raise FileNotFoundError(
                f"No files matching '{self.config.pattern}' " f"in {self._watch_dir}"
            )

        if self.config.selection == "latest_name":
            return matches[-1]  # Lexicographic sort -> latest date in name
        elif self.config.selection == "latest_mtime":
            return max(matches, key=lambda p: p.stat().st_mtime)
        else:
            # Validation in config.validate() prevents reaching here, but
            # defensive coding in case of direct construction.
            raise ValueError(f"Unknown selection strategy: {self.config.selection!r}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_target(self, path: str) -> Path:
        """Resolve *path* to an absolute ``Path``, falling back to config.

        Raises:
            RuntimeError: If the adapter has not been connected.
            ValueError: If the path fails security validation.
        """
        if path:
            return _validate_file_path(path, self._base_dir)

        if self._resolved_path is None:
            raise RuntimeError(
                f"FileSourceAdapter '{self.name}' is not connected — "
                "call connect() first"
            )
        return self._resolved_path

    def _determine_parser(self, target: Path) -> str:
        """Determine the parser to use for *target*.

        If ``config.parser`` is set, it overrides extension detection.
        """
        if self.config.parser:
            return self.config.parser
        return _EXTENSION_PARSERS.get(target.suffix.lower(), "text")
