"""Glob tool — file pattern matching sorted by modification time."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kaizen.utils.credential_scrub import scrub_remote_error
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
        except (ValueError, NotImplementedError) as exc:
            # `NotImplementedError` IS caught, and it is not defensive padding:
            # `Path.glob` raises it — NOT a `ValueError` — for an absolute
            # pattern (`pathlib/_local.py`, "Non-relative patterns are
            # unsupported"), and `pattern` is model-supplied. A model asking
            # for `/etc/**/*.pem` therefore escaped this `except` entirely and
            # raised out of `execute()`, where the agent loop degrades it to a
            # bare "failed with NotImplementedError" — unactionable for the
            # model, and indistinguishable from a real defect in the tool.
            #
            # SCRUBBED with the REMOTE preset, not the conservative one, even
            # though the probes found NO echoing branch on CPython 3.13
            # (`TestProbedOperandEchoVerdicts`, `Path.glob` entries — recorded
            # as measured, so this is not claiming a leak that was not found).
            # Two reasons that do not depend on one:
            #   1. The branch set is VERSION-DEPENDENT — `Path.glob` raised
            #      ValueError for a misplaced `**` component through 3.12 and
            #      stopped in 3.13 — so an interpolating branch re-added
            #      upstream would leak silently under the conservative preset.
            #   2. The switch costs nothing here. The doctrine's named
            #      filesystem-path carve-out is justified by there being a PATH
            #      the agent needs; these messages carry a condition class
            #      ("Unacceptable pattern: PosixPath('.')", "embedded null
            #      character"), never one. With no diagnostic payload to
            #      protect, the doctrine's own tie-breaker decides it.
            return ToolResult.failure(
                f"Invalid glob pattern: {scrub_remote_error(exc)}"
            )

        # Filter to files only (exclude directories)
        files = [p for p in matches if p.is_file()]

        # Sort by modification time, newest first
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        if not files:
            return ToolResult.success("(no matches)")

        lines = [str(f) for f in files]
        return ToolResult.success("\n".join(lines))
