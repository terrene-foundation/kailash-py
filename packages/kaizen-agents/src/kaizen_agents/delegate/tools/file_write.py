"""FileWrite tool — create or overwrite files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kaizen_agents.delegate.tools.base import Tool, ToolResult


class FileWriteTool(Tool):
    """Write content to a file, creating parent directories as needed.

    If the file already exists it is overwritten.
    """

    @property
    def name(self) -> str:
        return "file_write"

    @property
    def description(self) -> str:
        return "Create or overwrite a file with the given content."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["file_path", "content"],
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to write.",
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file.",
                },
            },
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        file_path: str = kwargs["file_path"]
        content: str = kwargs["content"]

        path = Path(file_path)

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except PermissionError:
            return ToolResult.failure(f"Permission denied: {file_path}")
        except OSError as exc:
            return ToolResult.failure(f"Error writing file: {exc}")

        return ToolResult.success(f"Wrote {len(content)} bytes to {file_path}")
