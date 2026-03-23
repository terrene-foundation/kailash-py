"""FileRead tool — read file contents with line numbers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kaizen_agents.delegate.tools.base import Tool, ToolResult


class FileReadTool(Tool):
    """Read a file and return its contents with ``cat -n`` style line numbers.

    Supports *offset* (1-based line to start from) and *limit* (max lines to
    return) for efficient reading of large files.
    """

    @property
    def name(self) -> str:
        return "file_read"

    @property
    def description(self) -> str:
        return "Read a file from the filesystem with line numbers."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["file_path"],
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to read.",
                },
                "offset": {
                    "type": "integer",
                    "description": "1-based line number to start reading from.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to return.",
                },
            },
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        file_path: str = kwargs["file_path"]
        offset: int = kwargs.get("offset", 1)
        limit: int | None = kwargs.get("limit")

        path = Path(file_path)
        if not path.is_file():
            return ToolResult.failure(f"File not found: {file_path}")

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ToolResult.failure(f"Cannot read binary file as text: {file_path}")
        except PermissionError:
            return ToolResult.failure(f"Permission denied: {file_path}")
        except OSError as exc:
            return ToolResult.failure(f"Error reading file: {exc}")

        lines = text.splitlines(keepends=True)
        total_lines = len(lines)

        # Apply offset (1-based)
        start_idx = max(0, offset - 1)
        selected = lines[start_idx:]

        # Apply limit
        if limit is not None and limit > 0:
            selected = selected[:limit]

        # Format with line numbers (cat -n style)
        numbered: list[str] = []
        for i, line in enumerate(selected, start=start_idx + 1):
            # Right-align line number to 6 chars, tab, then content
            numbered.append(f"{i:>6}\t{line.rstrip()}")

        output = "\n".join(numbered)
        if not output and total_lines == 0:
            output = "(empty file)"

        return ToolResult.success(output)
