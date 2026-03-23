"""FileEdit tool — exact string replacement in files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kaizen_agents.delegate.tools.base import Tool, ToolResult


class FileEditTool(Tool):
    """Perform exact string replacement in a file.

    By default, *old_string* must appear exactly once in the file (uniqueness
    check).  Set ``replace_all=True`` to replace every occurrence.
    """

    @property
    def name(self) -> str:
        return "file_edit"

    @property
    def description(self) -> str:
        return "Replace an exact string in a file. Validates uniqueness unless replace_all is set."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["file_path", "old_string", "new_string"],
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to edit.",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact text to find and replace.",
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement text.",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "If true, replace all occurrences. Default false.",
                    "default": False,
                },
            },
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        file_path: str = kwargs["file_path"]
        old_string: str = kwargs["old_string"]
        new_string: str = kwargs["new_string"]
        replace_all: bool = kwargs.get("replace_all", False)

        path = Path(file_path)

        if not path.is_file():
            return ToolResult.failure(f"File not found: {file_path}")

        if old_string == new_string:
            return ToolResult.failure("old_string and new_string are identical; no change needed.")

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ToolResult.failure(f"Cannot read binary file as text: {file_path}")
        except PermissionError:
            return ToolResult.failure(f"Permission denied: {file_path}")
        except OSError as exc:
            return ToolResult.failure(f"Error reading file: {exc}")

        count = content.count(old_string)

        if count == 0:
            return ToolResult.failure(
                f"old_string not found in {file_path}. "
                "Verify the exact text including whitespace and indentation."
            )

        if not replace_all and count > 1:
            return ToolResult.failure(
                f"old_string appears {count} times in {file_path}. "
                "Provide more context to make the match unique, or set replace_all=True."
            )

        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            # Replace only the first (and only) occurrence
            new_content = content.replace(old_string, new_string, 1)

        try:
            path.write_text(new_content, encoding="utf-8")
        except PermissionError:
            return ToolResult.failure(f"Permission denied: {file_path}")
        except OSError as exc:
            return ToolResult.failure(f"Error writing file: {exc}")

        replacements = count if replace_all else 1
        return ToolResult.success(f"Replaced {replacements} occurrence(s) in {file_path}")
