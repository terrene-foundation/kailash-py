"""Grep tool — regex content search across files."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from kaizen_agents.delegate.tools.base import Tool, ToolResult


class GrepTool(Tool):
    """Search file contents using regex patterns.

    Supports three output modes:

    * ``files_with_matches`` (default) — file paths only
    * ``content`` — matching lines with optional context
    * ``count`` — match counts per file
    """

    @property
    def name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return "Search file contents using regex patterns."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["pattern"],
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regular expression pattern to search for.",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search. Defaults to cwd.",
                },
                "glob": {
                    "type": "string",
                    "description": "Glob filter for file names (e.g. '*.py').",
                },
                "output_mode": {
                    "type": "string",
                    "enum": ["content", "files_with_matches", "count"],
                    "description": "Output format. Default: files_with_matches.",
                },
                "case_insensitive": {
                    "type": "boolean",
                    "description": "Case-insensitive search. Default false.",
                },
                "context": {
                    "type": "integer",
                    "description": "Lines of context before and after each match (content mode).",
                },
                "head_limit": {
                    "type": "integer",
                    "description": "Limit output to first N entries.",
                },
            },
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        pattern_str: str = kwargs["pattern"]
        search_path: str | None = kwargs.get("path")
        glob_filter: str | None = kwargs.get("glob")
        output_mode: str = kwargs.get("output_mode", "files_with_matches")
        case_insensitive: bool = kwargs.get("case_insensitive", False)
        context_lines: int = kwargs.get("context", 0)
        head_limit: int = kwargs.get("head_limit", 0)

        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex = re.compile(pattern_str, flags)
        except re.error as exc:
            return ToolResult.failure(f"Invalid regex: {exc}")

        base = Path(search_path) if search_path else Path.cwd()

        # Collect files to search
        if base.is_file():
            files = [base]
        elif base.is_dir():
            files = _collect_files(base, glob_filter)
        else:
            return ToolResult.failure(f"Path not found: {base}")

        if output_mode == "files_with_matches":
            return self._files_with_matches(files, regex, head_limit)
        elif output_mode == "count":
            return self._count_mode(files, regex, head_limit)
        elif output_mode == "content":
            return self._content_mode(files, regex, context_lines, head_limit)
        else:
            return ToolResult.failure(f"Unknown output_mode: {output_mode!r}")

    # ------------------------------------------------------------------
    # Output mode implementations
    # ------------------------------------------------------------------

    @staticmethod
    def _files_with_matches(
        files: list[Path], regex: re.Pattern[str], head_limit: int
    ) -> ToolResult:
        matched: list[str] = []
        for fp in files:
            content = _safe_read(fp)
            if content is not None and regex.search(content):
                matched.append(str(fp))
                if head_limit > 0 and len(matched) >= head_limit:
                    break
        if not matched:
            return ToolResult.success("(no matches)")
        return ToolResult.success("\n".join(matched))

    @staticmethod
    def _count_mode(files: list[Path], regex: re.Pattern[str], head_limit: int) -> ToolResult:
        results: list[str] = []
        for fp in files:
            content = _safe_read(fp)
            if content is None:
                continue
            count = len(regex.findall(content))
            if count > 0:
                results.append(f"{fp}:{count}")
                if head_limit > 0 and len(results) >= head_limit:
                    break
        if not results:
            return ToolResult.success("(no matches)")
        return ToolResult.success("\n".join(results))

    @staticmethod
    def _content_mode(
        files: list[Path],
        regex: re.Pattern[str],
        context_lines: int,
        head_limit: int,
    ) -> ToolResult:
        output_parts: list[str] = []
        entry_count = 0

        for fp in files:
            content = _safe_read(fp)
            if content is None:
                continue
            lines = content.splitlines()
            match_indices: list[int] = []
            for idx, line in enumerate(lines):
                if regex.search(line):
                    match_indices.append(idx)

            if not match_indices:
                continue

            # Build output for this file
            file_parts: list[str] = []
            shown: set[int] = set()
            for midx in match_indices:
                start = max(0, midx - context_lines)
                end = min(len(lines), midx + context_lines + 1)
                for i in range(start, end):
                    if i not in shown:
                        shown.add(i)
                        prefix = ">" if i == midx else " "
                        file_parts.append(f"{fp}:{i + 1}:{prefix} {lines[i]}")
                        entry_count += 1

                if head_limit > 0 and entry_count >= head_limit:
                    break
            output_parts.extend(file_parts)
            if head_limit > 0 and entry_count >= head_limit:
                break

        if not output_parts:
            return ToolResult.success("(no matches)")
        return ToolResult.success("\n".join(output_parts))


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

# Binary-looking extensions we skip to avoid decode errors
_BINARY_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".ico",
        ".webp",
        ".pdf",
        ".zip",
        ".gz",
        ".tar",
        ".bz2",
        ".xz",
        ".7z",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".o",
        ".a",
        ".pyc",
        ".pyo",
        ".class",
        ".wasm",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".eot",
        ".mp3",
        ".mp4",
        ".avi",
        ".mov",
        ".mkv",
        ".flac",
        ".ogg",
        ".sqlite",
        ".db",
    }
)


def _collect_files(directory: Path, glob_filter: str | None) -> list[Path]:
    """Walk a directory and return all text-file candidates."""
    files: list[Path] = []
    if glob_filter:
        # Use the glob as a recursive pattern under the directory
        pattern = glob_filter if "**" in glob_filter or "/" in glob_filter else f"**/{glob_filter}"
        for p in directory.glob(pattern):
            if p.is_file() and p.suffix.lower() not in _BINARY_EXTENSIONS:
                files.append(p)
    else:
        for root, _dirs, filenames in os.walk(directory):
            root_path = Path(root)
            # Skip hidden directories and common noise
            parts = root_path.relative_to(directory).parts
            if any(
                part.startswith(".") or part == "node_modules" or part == "__pycache__"
                for part in parts
            ):
                continue
            for fn in filenames:
                fp = root_path / fn
                if fp.suffix.lower() not in _BINARY_EXTENSIONS and not fn.startswith("."):
                    files.append(fp)
    return sorted(files)


def _safe_read(path: Path) -> str | None:
    """Read a file as UTF-8, returning ``None`` on decode or permission errors."""
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError, OSError):
        return None
