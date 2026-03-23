"""Glob tool — file pattern matching sorted by modification time."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kaizen_agents.delegate.tools.base import Tool, ToolResult


class GlobTool(Tool):
    """Find files matching a glob pattern, sorted by modification time (newest first)."""

    @property
    def name(self) -> str:
        return "glob"

    @property
    def description(self) -> str:
        return "Find files matching a glob pattern, sorted by modification time."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["pattern"],
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g. '**/*.py', 'src/**/*.ts').",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in. Defaults to cwd.",
                },
            },
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        pattern: str = kwargs["pattern"]
        search_path: str | None = kwargs.get("path")

        base = Path(search_path) if search_path else Path.cwd()

        if not base.is_dir():
            return ToolResult.failure(f"Directory not found: {base}")

        try:
            matches = list(base.glob(pattern))
        except ValueError as exc:
            return ToolResult.failure(f"Invalid glob pattern: {exc}")

        # Filter to files only (exclude directories)
        files = [p for p in matches if p.is_file()]

        # Sort by modification time, newest first
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        if not files:
            return ToolResult.success("(no matches)")

        lines = [str(f) for f in files]
        return ToolResult.success("\n".join(lines))
