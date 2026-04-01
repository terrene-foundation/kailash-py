# FastMCP Reference Model: TrustPlane MCP Server

**Source**: `src/kailash/trust/plane/mcp_server.py` (302 lines)

## Architecture Overview

The TrustPlane MCP server is the only production-quality FastMCP implementation in the codebase. It demonstrates every pattern the platform server needs to adopt.

## FastMCP Instance Creation

```python
from mcp.server import FastMCP

mcp = FastMCP(
    "TrustPlane",
    instructions=(
        "TrustPlane provides trust gating for AI operations. "
        "Before performing actions that modify files, create content, "
        "or make decisions, call trust_check to verify the action is "
        "allowed by the constraint envelope. Record significant "
        "decisions with trust_record for audit trail."
    ),
)
```

Key patterns:

- Module-level `mcp` instance (NOT wrapped in a class)
- `instructions` parameter tells AI assistants how to use the server
- Server name is descriptive and stable

## Tool Registration Pattern

```python
@mcp.tool(
    name="trust_check",
    description=(
        "Check whether a proposed action is allowed by the constraint "
        "envelope. Returns a verdict: AUTO_APPROVED, FLAGGED, HELD, "
        "or BLOCKED. Call this BEFORE performing actions that modify "
        "files, create content, or make decisions."
    ),
)
async def trust_check(
    action: str,
    resource: str = "",
    decision_type: str = "",
) -> dict:
    """Gate: can I do this?"""
    ...
```

Key patterns:

- `@mcp.tool(name=..., description=...)` decorator
- All tools are `async`
- Return type is `dict` (JSON-serializable)
- Description is detailed and action-oriented (tells the AI WHEN to call it)
- Parameters use simple Python types with defaults
- Short docstring for internal reference; `description` for MCP clients

## Thread-Safe Caching (Double-Checked Locking)

```python
_project: TrustProject | None = None
_manifest_mtime: float = 0.0
_project_lock = threading.Lock()

async def _get_project() -> TrustProject:
    global _project, _manifest_mtime

    manifest_path = TRUST_DIR / "manifest.json"
    try:
        current_mtime = manifest_path.stat().st_mtime
    except FileNotFoundError:
        current_mtime = 0.0

    # Fast path: no lock
    cached = _project
    if cached is not None and current_mtime == _manifest_mtime:
        return cached

    # Slow path: acquire lock
    with _project_lock:
        if _project is not None and current_mtime == _manifest_mtime:
            return _project

        loaded = await TrustProject.load(TRUST_DIR)
        _project = loaded
        _manifest_mtime = current_mtime
        return _project
```

Key patterns:

- Module-level globals with `threading.Lock`
- Double-checked locking: fast path avoids lock contention
- File mtime comparison for change detection (no watchdog dependency)
- Lock protects both `_project` and `_manifest_mtime` atomically
- `async` function can hold a sync lock briefly (just assignment, no I/O inside lock)

## File-Watching Strategy

The server does NOT use `watchdog` or `watchfiles`. Instead:

1. Each tool call checks `manifest_path.stat().st_mtime`
2. If mtime changed, reload under lock
3. This is simple, dependency-free, and sufficient for config files

For the platform server: same pattern works for `pyproject.toml` changes. No need for a file-watcher dependency.

## CLI Entry Point

```python
def main():
    import argparse
    parser = argparse.ArgumentParser(description="TrustPlane MCP Server")
    parser.add_argument(
        "--trust-dir",
        default=os.environ.get("TRUSTPLANE_DIR", "./trust-plane"),
        help="Path to trust plane directory",
    )
    args = parser.parse_args()
    global TRUST_DIR
    TRUST_DIR = Path(args.trust_dir)
    mcp.run()
```

Registered in `pyproject.toml`:

```toml
[project.scripts]
trustplane-mcp = "kailash.trust.plane.mcp_server:main"
```

Key patterns:

- `mcp.run()` handles stdio/SSE transport automatically
- CLI arg -> environment variable -> default fallback chain
- `global` assignment before `mcp.run()` ensures tools see the correct config
- `argparse` (no Click dependency)

## Test Support Pattern

```python
def _set_project(project: TrustProject) -> None:
    """Set the cached project under the lock (for testing)."""
    global _project, _manifest_mtime
    manifest_path = TRUST_DIR / "manifest.json"
    try:
        mtime = manifest_path.stat().st_mtime
    except FileNotFoundError:
        mtime = 0.0
    with _project_lock:
        _project = project
        _manifest_mtime = mtime

def _reset_project() -> None:
    """Clear cached project and mtime under the lock (for testing)."""
    global _project, _manifest_mtime
    with _project_lock:
        _project = None
        _manifest_mtime = 0.0
```

Key patterns:

- Explicit test injection functions (prefix `_` to mark as internal)
- Reset function for test isolation
- Lock acquired even in test helpers

## Patterns to Replicate for Platform Server

1. **Module-level FastMCP instance** — `mcp = FastMCP("kailash-platform", instructions="...")`
2. **Tool decorator with detailed descriptions** — Tell AI when and why to call each tool
3. **Double-checked locking for cached state** — Framework registries should be cached
4. **File mtime for change detection** — Check `pyproject.toml` mtime for framework version changes
5. **CLI with argparse** — `--project-root`, `--transport`, `--port`
6. **Test injection helpers** — `_set_registries()`, `_reset_registries()`
7. **Error handling returns dict, not exceptions** — MCP tools should return error info in the response, not raise

## What NOT to Replicate

- `global TRUST_DIR` mutation — use a config object or pass `project_root` to tools
- Single-purpose server — platform server needs the contributor plugin system
- Module-level tool definitions — contributors register tools dynamically
