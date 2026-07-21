---
name: mcp-contributor-pattern
description: "How to write a kailash-mcp framework contributor module. Use when asking 'mcp contributor', 'register tools', 'add framework to mcp', 'new mcp contributor', or 'extend kailash-mcp'."
---

# MCP Contributor Pattern

How to add a new framework contributor to the kailash-mcp platform server. Each contributor is a Python module that registers namespace-prefixed tools on the shared FastMCP server.

> **Skill Metadata**
> Category: `mcp`
> Priority: `MEDIUM`
> SDK Version: `0.9.25+`
> Related Skills: [`mcp-platform-overview`](mcp-platform-overview.md), [`mcp-security-tiers`](mcp-security-tiers.md), [`mcp-tool-catalog`](mcp-tool-catalog.md)
> Related Subagents: `mcp-platform-specialist` (contributor implementation, testing)

## Contributor Contract

Every contributor module MUST implement this function:

```python
def register_tools(server: FastMCP, project_root: Path, namespace: str) -> None:
    """Register framework-specific MCP tools.

    All tool names MUST start with '{namespace}.' prefix.
    This function MUST be synchronous and non-blocking.
    Do NOT perform network calls or heavy computation during registration.
    """
```

**Why synchronous?** The platform server calls `register_tools` sequentially during startup. Async registration would complicate error handling and make startup order non-deterministic.

**Why non-blocking?** Heavy computation during registration delays server startup for all frameworks, not just the slow one. Defer expensive work to tool call time.

## Step-by-Step: Writing a New Contributor

### Step 1: Create the Module

Create `kailash/mcp/contrib/<framework>.py`:

```python
# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""<Framework> contributor for the kailash-platform MCP server.

Provides <discovery method> of <what it discovers>.

Tools registered:
    - ``<namespace>.list_<things>`` (Tier 1): List all <things>
    - ``<namespace>.describe_<thing>`` (Tier 1): Describe a specific <thing>
    - ``<namespace>.scaffold_<thing>`` (Tier 2): Generate <thing> code
    - ``<namespace>.validate_<thing>`` (Tier 3): Validate <thing> definition
"""

from __future__ import annotations

import ast
import logging
import time
from pathlib import Path
from typing import Any

from kailash.mcp.contrib import SecurityTier, is_tier_enabled

logger = logging.getLogger(__name__)

__all__ = ["register_tools"]
```

### Step 2: Implement the Scanner

Use AST-based static analysis to discover project artifacts. The scanner function is shared between the tool and the `platform.platform_map` aggregator.

```python
_SKIP_DIRS = frozenset(
    {".venv", "__pycache__", "node_modules", ".git", ".tox",
     "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
)


def _iter_python_files(root: Path) -> list[Path]:
    """Iterate Python files, skipping non-project directories."""
    files: list[Path] = []

    def _walk(directory: Path) -> None:
        try:
            entries = sorted(directory.iterdir())
        except (OSError, PermissionError):
            return
        for child in entries:
            if child.is_dir():
                if child.name in _SKIP_DIRS or child.name.startswith("."):
                    continue
                _walk(child)
            elif child.suffix == ".py":
                files.append(child)

    _walk(root)
    return files


def _scan_things(project_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Scan project for <things> using AST analysis.

    Returns:
        Tuple of (things list, scan_metadata dict).
    """
    start = time.monotonic()
    py_files = _iter_python_files(project_root)
    things: list[dict[str, Any]] = []

    for py_file in py_files:
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            # Detection heuristic goes here
            pass

    elapsed_ms = int((time.monotonic() - start) * 1000)
    metadata = {
        "method": "ast_static",
        "files_scanned": len(py_files),
        "scan_duration_ms": elapsed_ms,
        "limitations": [
            "Dynamic registration not detected",
            "Only scans project_root, not installed packages",
        ],
    }
    return things, metadata
```

**Why return scan_metadata?** Every tool response includes metadata about how results were obtained and what limitations apply. This lets MCP clients (and the humans reading responses) understand the confidence level.

### Step 3: Register Tools by Tier

```python
def register_tools(server: Any, project_root: Path, namespace: str) -> None:
    """Register <Framework> tools on the MCP server."""
    _cache: dict[str, Any] = {}

    def _get_things() -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Cached scanner -- re-scans only when called, not at registration."""
        if "things" not in _cache:
            things, meta = _scan_things(project_root)
            _cache["things"] = things
            _cache["metadata"] = meta
        return _cache["things"], _cache["metadata"]

    # --- Tier 1: Introspection (always registered) ---

    @server.tool(name=f"{namespace}.list_things")
    async def list_things() -> dict:
        """List all <things> found in this project."""
        things, metadata = _get_things()
        return {
            "things": [{"name": t["name"], "file": t["file"]} for t in things],
            "total": len(things),
            "scan_metadata": metadata,
        }

    @server.tool(name=f"{namespace}.describe_thing")
    async def describe_thing(thing_name: str) -> dict:
        """Describe a specific <thing> with details.

        Args:
            thing_name: The name of the thing to describe.
        """
        things, metadata = _get_things()
        for t in things:
            if t["name"] == thing_name:
                return {**t, "scan_metadata": metadata}
        return {
            "error": f"'{thing_name}' not found",
            "available": sorted(t["name"] for t in things),
            "scan_metadata": metadata,
        }

    # --- Tier 2: Scaffolding (always registered) ---

    @server.tool(name=f"{namespace}.scaffold_thing")
    async def scaffold_thing(name: str, spec: str) -> dict:
        """Generate a <thing> definition.

        Args:
            name: Name for the new thing.
            spec: Specification string.
        """
        code = f"# Generated {name}\n"
        try:
            ast.parse(code)
        except SyntaxError as exc:
            return {"error": f"Generated code has syntax error: {exc}"}
        return {"file_path": f"things/{name.lower()}.py", "code": code}

    # --- Tier 3: Validation (gated by env var) ---

    if is_tier_enabled(SecurityTier.VALIDATION):

        @server.tool(name=f"{namespace}.validate_thing")
        async def validate_thing(thing_name: str) -> dict:
            """Validate a <thing> definition.

            Args:
                thing_name: The name to validate.
            """
            things, metadata = _get_things()
            errors: list[str] = []
            warnings: list[str] = []
            # Validation logic here
            return {
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
                "scan_metadata": metadata,
            }

    # --- Tier 4: Execution (gated, disabled by default) ---

    if is_tier_enabled(SecurityTier.EXECUTION):

        @server.tool(name=f"{namespace}.test_thing")
        async def test_thing(thing_name: str) -> dict:
            """Execute a <thing> in an isolated subprocess.

            Args:
                thing_name: The thing to execute.
            """
            # Always run in subprocess, never import user code directly
            return {"result": "executed", "duration_ms": 0}
```

### Step 4: Register in the Platform Server

Add the contributor to `FRAMEWORK_CONTRIBUTORS` in `kailash/mcp/platform_server.py`:

```python
FRAMEWORK_CONTRIBUTORS: list[tuple[str, str]] = [
    # ... existing contributors ...
    ("kailash.mcp.contrib.myframework", "myframework"),
]
```

**Why this ordering matters:** Contributors are registered in list order. If your contributor depends on another (e.g., to cross-reference models), place it after the dependency.

### Step 5: Expose Scanner for platform_map

If `platform.platform_map` should include your framework's data, expose a scanner function that the platform contributor can import:

```python
# Make _scan_things importable (used by platform.platform_map)
# The function name must match what platform.py imports via _safe_import_scanner
```

The platform contributor uses `_safe_import_scanner` to dynamically load scanner functions, so failures are handled gracefully.

## Naming Conventions

| Pattern                 | Example                   | Purpose                   |
| ----------------------- | ------------------------- | ------------------------- |
| `{ns}.list_{things}`    | `dataflow.list_models`    | List all discovered items |
| `{ns}.describe_{thing}` | `kaizen.describe_agent`   | Detailed single-item info |
| `{ns}.scaffold_{thing}` | `nexus.scaffold_handler`  | Generate code from spec   |
| `{ns}.generate_tests`   | `dataflow.generate_tests` | Generate test scaffolds   |
| `{ns}.validate_{thing}` | `dataflow.validate_model` | Check correctness         |
| `{ns}.test_{thing}`     | `nexus.test_handler`      | Execute in subprocess     |
| `{ns}.query_{aspect}`   | `dataflow.query_schema`   | Project-level metadata    |

**Why consistent naming?** MCP clients can predict tool names without listing them. An agent knows that `<framework>.list_<things>` will exist for any registered framework.

## Testing Checklist

### Unit Tests

```python
def test_scanner_finds_decorated_classes(tmp_path):
    """Scanner detects @framework.thing decorated classes."""
    (tmp_path / "app.py").write_text("""
from framework import thing

@thing
class MyThing:
    name: str
""")
    results, meta = _scan_things(tmp_path)
    assert len(results) == 1
    assert results[0]["name"] == "MyThing"


def test_scanner_skips_venv(tmp_path):
    """Scanner ignores .venv directories."""
    venv = tmp_path / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "thing.py").write_text("class ShouldNotFind: pass")
    results, _ = _scan_things(tmp_path)
    assert len(results) == 0


def test_scanner_handles_syntax_errors(tmp_path):
    """Scanner skips files with syntax errors."""
    (tmp_path / "bad.py").write_text("def broken(")
    results, _ = _scan_things(tmp_path)
    assert len(results) == 0
```

### Integration Tests

```python
async def test_tools_registered_with_namespace(tmp_path):
    """All tools have correct namespace prefix."""
    server = FastMCP("test")
    register_tools(server, tmp_path, "myframework")
    tool_names = _get_tool_names(server)
    for name in tool_names:
        assert name.startswith("myframework."), f"Tool {name} missing namespace prefix"


async def test_list_returns_scan_metadata():
    """Every tool response includes scan_metadata."""
    server = FastMCP("test")
    register_tools(server, Path("/tmp"), "myframework")
    # Call the list tool and verify scan_metadata is present
```

### End-to-End Tests

```python
async def test_full_server_starts_with_contributor():
    """Platform server includes contributor's tools."""
    server = create_platform_server(project_root=Path("/tmp"))
    tool_names = _get_tool_names(server)
    assert any(name.startswith("myframework.") for name in tool_names)
```

## Common Mistakes

| Mistake                             | Consequence                                     | Fix                                          |
| ----------------------------------- | ----------------------------------------------- | -------------------------------------------- |
| Missing namespace prefix            | Platform server logs warning, tools may collide | Always use `f"{namespace}.tool_name"`        |
| Importing user code at registration | Side effects during startup                     | Use AST scanning, defer imports to tool call |
| Network calls in `register_tools`   | Slow or failed startup                          | Defer to tool call time, cache results       |
| Synchronous blocking in async tools | Blocks the event loop                           | Use `asyncio.to_thread` for heavy compute    |
| No `scan_metadata` in response      | Clients can't assess result quality             | Always include method, limitations           |

## When to Escalate to Subagent

Use `mcp-platform-specialist` when:

- Implementing cross-framework scanning in `platform_map`
- Adding Tier 4 execution tools with subprocess isolation
- Debugging namespace validation warnings
- Implementing caching strategies for large projects

<!-- Trigger Keywords: mcp contributor, register tools, add framework to mcp, new mcp contributor, extend kailash-mcp, contributor pattern, framework contributor, mcp plugin -->
