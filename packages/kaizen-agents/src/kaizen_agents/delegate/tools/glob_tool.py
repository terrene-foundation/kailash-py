"""Glob tool — file pattern matching sorted by modification time."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kaizen.utils.credential_scrub import scrub_local_error
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
            # pattern ("Non-relative patterns are unsupported"), on every
            # CPython from 3.10 to 3.14. `pattern` is model-supplied, so a
            # model asking for `/etc/**/*.pem` escaped this `except` entirely
            # and raised out of `execute()`, where the agent loop degrades it
            # to a bare "failed with NotImplementedError" — unactionable for
            # the model, and indistinguishable from a real defect in the tool.
            #
            # LOCAL preset, and that is the PROBED verdict rather than an
            # inherited assumption. `pattern` is model-supplied, so this site
            # passes doctrine Test 1 (raised in-process) and the whole question
            # is Test 2 — does any branch carry the operand? Probed per branch
            # on CPython 3.10 / 3.11 / 3.12 / 3.13 / 3.14: NO branch echoes a
            # credential-bearing pattern on any of them. The one raise that
            # interpolates at all ("Unacceptable pattern: {p!r}") is reachable
            # ONLY when the pattern normalizes to no tail components — `""`,
            # `"."`, `"./"` — none of which can carry a credential; every other
            # message is a condition class ("Non-relative patterns are
            # unsupported", "embedded null character in path").
            #
            # Recorded because the branch set genuinely CHURNS and the probes,
            # not this comment, are what will catch it: the misplaced-`**`
            # ValueError exists on 3.10-3.12 and is gone on 3.13+, and the NUL
            # branch raises ValueError ONLY on 3.13. So the verdict is pinned
            # in `TestProbedOperandEchoVerdicts`, which reads the REAL messages
            # and returns the other answer if a future CPython starts echoing —
            # at which point this classification is re-derived, not assumed.
            return ToolResult.failure(f"Invalid glob pattern: {scrub_local_error(exc)}")

        # Filter to files only (exclude directories)
        files = [p for p in matches if p.is_file()]

        # Sort by modification time, newest first
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        if not files:
            return ToolResult.success("(no matches)")

        lines = [str(f) for f in files]
        return ToolResult.success("\n".join(lines))
