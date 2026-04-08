# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Nexus contributor for the kailash-platform MCP server.

Provides AST-based discovery of Nexus handler registrations using both
decorator and imperative call patterns.

Tools registered:
    - ``nexus.list_handlers`` (Tier 1)
    - ``nexus.list_channels`` (Tier 1)
    - ``nexus.scaffold_handler`` (Tier 2)
    - ``nexus.generate_tests`` (Tier 2)
    - ``nexus.validate_handler`` (Tier 3)
    - ``nexus.test_handler`` (Tier 4)
"""

from __future__ import annotations

import ast
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from kailash_mcp.contrib import SecurityTier, is_tier_enabled

logger = logging.getLogger(__name__)

__all__ = ["register_tools"]

_SKIP_DIRS = frozenset(
    {
        ".venv",
        "__pycache__",
        "node_modules",
        ".git",
        ".tox",
        "dist",
        "build",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".hg",
        ".svn",
    }
)

_VALID_HTTP_METHODS = frozenset(
    {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
)


# ---------------------------------------------------------------------------
# AST-based handler scanner
# ---------------------------------------------------------------------------


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


def _get_name(node: ast.expr) -> str | None:
    """Extract a simple name from an AST expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_handler_decorator(decorator: ast.expr) -> bool:
    """Check if a decorator looks like a handler registration."""
    name = None
    if isinstance(decorator, ast.Call):
        name = _get_name(decorator.func) if hasattr(decorator, "func") else None
    elif isinstance(decorator, ast.Attribute):
        name = decorator.attr
    elif isinstance(decorator, ast.Name):
        name = decorator.id

    if name is None:
        return False
    return name in ("handler", "route", "endpoint")


def _parse_add_handler_call(
    call_node: ast.Call, py_file: Path, project_root: Path
) -> dict[str, Any] | None:
    """Extract handler info from app.add_handler(...) call."""
    args = call_node.args
    if not args:
        return None

    name = None
    method = None
    path = None

    if isinstance(args[0], ast.Constant) and isinstance(args[0].value, str):
        name = args[0].value

    for arg in args[1:]:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            val = arg.value.upper()
            if val in _VALID_HTTP_METHODS:
                method = val
            elif arg.value.startswith("/"):
                path = arg.value

    for kw in call_node.keywords:
        if kw.arg == "method" and isinstance(kw.value, ast.Constant):
            method = str(kw.value.value).upper()
        elif kw.arg == "path" and isinstance(kw.value, ast.Constant):
            path = str(kw.value.value)

    if name:
        return {
            "name": name,
            "method": method,
            "path": path,
            "file": str(py_file.relative_to(project_root)),
            "line": call_node.lineno,
        }
    return None


def _parse_handler_decorator(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    decorator: ast.expr,
    py_file: Path,
    project_root: Path,
) -> dict[str, Any] | None:
    """Extract handler info from @handler(...) decorator."""
    method = None
    path = None

    if isinstance(decorator, ast.Call):
        for kw in decorator.keywords:
            if kw.arg == "method" and isinstance(kw.value, ast.Constant):
                method = str(kw.value.value).upper()
            elif kw.arg == "path" and isinstance(kw.value, ast.Constant):
                path = str(kw.value.value)
        # Also check positional args
        for arg in decorator.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                val = arg.value.upper()
                if val in _VALID_HTTP_METHODS:
                    method = val
                elif arg.value.startswith("/"):
                    path = arg.value

    return {
        "name": func_node.name,
        "method": method,
        "path": path,
        "file": str(py_file.relative_to(project_root)),
        "line": func_node.lineno,
    }


def _scan_handlers(project_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Scan project for Nexus handler registrations via AST."""
    start = time.monotonic()
    py_files = _iter_python_files(project_root)
    handlers: list[dict[str, Any]] = []

    for py_file in py_files:
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            # Pattern 1: app.add_handler(...) or app.register(...)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in ("add_handler", "register"):
                    handler = _parse_add_handler_call(node, py_file, project_root)
                    if handler:
                        handlers.append(handler)

            # Pattern 2: @handler decorator on function def
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if _is_handler_decorator(dec):
                        handler = _parse_handler_decorator(
                            node, dec, py_file, project_root
                        )
                        if handler:
                            handlers.append(handler)

    elapsed_ms = int((time.monotonic() - start) * 1000)
    metadata = {
        "method": "ast_static",
        "files_scanned": len(py_files),
        "scan_duration_ms": elapsed_ms,
        "limitations": [
            "Imperative handler registration in conditional branches may be missed",
            "Handler functions passed by reference from external modules not detected",
            "Only scans project_root, not installed packages",
        ],
    }
    return handlers, metadata


# ---------------------------------------------------------------------------
# AST enrichment helpers
# ---------------------------------------------------------------------------


def _enrich_handler_descriptions(
    handlers: list[dict[str, Any]], project_root: Path
) -> None:
    """Enrich AST-discovered handlers with docstrings from source."""
    for handler in handlers:
        filepath = handler.get("file")
        func_name = handler.get("name")
        if not filepath or not func_name:
            continue
        full_path = project_root / filepath
        if not full_path.exists():
            continue
        try:
            source = full_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name == func_name:
                        docstring = ast.get_docstring(node)
                        if docstring:
                            handler["description"] = docstring.split("\n")[0]
                        break
        except Exception:
            continue
        # Default empty fields for consistency
        handler.setdefault("description", "")
        handler.setdefault("channel", "http")
        handler.setdefault("middleware", [])


def _detect_channels(project_root: Path) -> list[dict[str, Any]]:
    """Detect Nexus channels from source code patterns."""
    channels: list[dict[str, Any]] = []
    seen: set[str] = set()
    py_files = _iter_python_files(project_root)

    for filepath in py_files:
        try:
            source = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # Detect Nexus(api_port=...) or .start(port=...)
        if "Nexus(" in source or "nexus" in source.lower():
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func_name = ""
                    if isinstance(node.func, ast.Name):
                        func_name = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        func_name = node.func.attr
                    if func_name == "Nexus":
                        for kw in node.keywords:
                            if kw.arg == "api_port" and "http" not in seen:
                                port = (
                                    kw.value.value
                                    if isinstance(kw.value, ast.Constant)
                                    else "dynamic"
                                )
                                channels.append({"type": "http", "port": port})
                                seen.add("http")
                    if func_name == "start":
                        if "http" not in seen:
                            channels.append({"type": "http", "port": "default"})
                            seen.add("http")
    # Check for MCP and CLI patterns
    for filepath in py_files:
        try:
            source = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "FastMCP" in source or "mcp_server" in source:
            if "mcp" not in seen:
                channels.append({"type": "mcp", "transport": "stdio"})
                seen.add("mcp")
        if "add_command" in source or "cli" in source.lower():
            if "cli" not in seen:
                channels.append({"type": "cli"})
                seen.add("cli")
    return channels


def _scan_event_subscriptions(project_root: Path) -> list[dict[str, Any]]:
    """Scan for EventBus subscriptions via AST."""
    events: list[dict[str, Any]] = []
    py_files = _iter_python_files(project_root)

    for filepath in py_files:
        try:
            source = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "subscribe" not in source and "on_model_change" not in source:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        rel_path = str(filepath.relative_to(project_root))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func_name = ""
            if isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            if func_name == "subscribe" and node.args:
                # event_bus.subscribe("event_type", callback)
                if isinstance(node.args[0], ast.Constant) and isinstance(
                    node.args[0].value, str
                ):
                    events.append(
                        {
                            "event_type": node.args[0].value,
                            "file": rel_path,
                            "line": node.lineno,
                        }
                    )
            elif func_name == "on_model_change" and node.args:
                # db.on_model_change("User", callback)
                if isinstance(node.args[0], ast.Constant) and isinstance(
                    node.args[0].value, str
                ):
                    events.append(
                        {
                            "event_type": f"dataflow.{node.args[0].value}.*",
                            "file": rel_path,
                            "line": node.lineno,
                        }
                    )
    return events


# ---------------------------------------------------------------------------
# Subprocess execution (Tier 4)
# ---------------------------------------------------------------------------


def _execute_in_subprocess(
    script: str, project_root: Path, timeout: int = 30
) -> dict[str, Any]:
    """Run a Python script in an isolated subprocess."""
    start = time.monotonic()
    env = {**dict(os.environ), "PYTHONPATH": str(project_root)}
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(project_root),
            env=env,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if result.returncode != 0:
            return {
                "errors": [
                    result.stderr.strip()
                    or f"Process exited with code {result.returncode}"
                ],
                "duration_ms": elapsed_ms,
            }
        try:
            output = json.loads(result.stdout)
        except json.JSONDecodeError:
            output = {"raw_output": result.stdout.strip()}
        output["duration_ms"] = elapsed_ms
        return output
    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "errors": [f"Execution timed out after {timeout}s"],
            "duration_ms": elapsed_ms,
        }


# ---------------------------------------------------------------------------
# register_tools
# ---------------------------------------------------------------------------


def register_tools(server: Any, project_root: Path, namespace: str) -> None:
    """Register Nexus tools on the MCP server."""
    _cache: dict[str, Any] = {}

    def _get_handlers() -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if "handlers" not in _cache:
            handlers, meta = _scan_handlers(project_root)
            _cache["handlers"] = handlers
            _cache["metadata"] = meta
        return _cache["handlers"], _cache["metadata"]

    @server.tool(name=f"{namespace}.list_handlers")
    async def list_handlers() -> dict:
        """List all Nexus handlers found in this project.

        Uses AST-based static analysis with docstring enrichment.
        Runtime introspection is intentionally NOT used at Tier 1
        because importing project modules executes arbitrary code.
        """
        handlers, metadata = _get_handlers()
        # Enrich with docstring descriptions (AST-only, no imports).
        _enrich_handler_descriptions(handlers, project_root)
        return {
            "handlers": handlers,
            "total": len(handlers),
            "scan_metadata": metadata,
        }

    @server.tool(name=f"{namespace}.list_channels")
    async def list_channels() -> dict:
        """List configured Nexus channels detected in this project.

        Scans for Nexus instantiation patterns and port/channel
        configuration in source code.
        """
        channels = _detect_channels(project_root)
        return {
            "channels": channels,
            "total": len(channels),
            "scan_metadata": {
                "method": "ast_static",
                "note": "Detected from Nexus() constructor args and start() calls",
            },
        }

    @server.tool(name=f"{namespace}.list_events")
    async def list_events() -> dict:
        """List EventBus event subscriptions found in this project.

        Scans for event_bus.subscribe() and on_model_change() calls
        using AST-based static analysis.
        """
        events = _scan_event_subscriptions(project_root)
        return {
            "events": events,
            "total": len(events),
            "scan_metadata": {"method": "ast_static"},
        }

    @server.tool(name=f"{namespace}.scaffold_handler")
    async def scaffold_handler(
        name: str, method: str, path: str, description: str = ""
    ) -> dict:
        """Generate a Nexus handler definition with test code.

        Args:
            name: Handler function name (e.g., "create_user")
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            path: URL path (e.g., "/api/users")
            description: Optional description of what the handler does
        """
        method_upper = method.upper()
        if method_upper not in _VALID_HTTP_METHODS:
            return {
                "error": f"Invalid HTTP method: {method}",
                "valid_methods": sorted(_VALID_HTTP_METHODS),
            }
        if not path.startswith("/"):
            return {"error": "Path must start with '/'"}

        desc = description or f"{method_upper} {path}"

        code = f'''"""{desc}"""
from nexus import handler


@handler(method="{method_upper}", path="{path}")
async def {name}(request):
    """Handle {method_upper} {path}."""
    data = request.json() if request.body else {{}}
    # Process the request
    return {{"status": "ok", "data": data}}
'''

        test_code = f'''"""Tests for {name} handler."""
import pytest


class Test{name.title().replace("_", "")}:
    """Tests for the {name} handler."""

    async def test_{name}_success(self):
        """Happy path: valid request returns success."""
        # Arrange
        request_data = {{"key": "value"}}

        # Act (replace with actual handler invocation)
        result = {{"status": "ok", "data": request_data}}

        # Assert
        assert result["status"] == "ok"

    async def test_{name}_invalid_input(self):
        """Error path: invalid input returns error."""
        # Test with invalid/missing required fields
        pass

    async def test_{name}_error_handling(self):
        """Error path: handler error is handled gracefully."""
        pass
'''

        try:
            ast.parse(code)
            ast.parse(test_code)
        except SyntaxError as exc:
            return {"error": f"Generated code has syntax error: {exc}"}

        return {
            "file_path": f"handlers/{name}.py",
            "code": code,
            "tests_path": f"tests/test_{name}.py",
            "tests_code": test_code,
            "scan_metadata": {"method": "template_generation", "limitations": []},
        }

    # Tier 2: Test generation
    @server.tool(name=f"{namespace}.generate_tests")
    async def generate_tests(handler_name: str) -> dict:
        """Generate pytest test scaffolds for a Nexus handler.

        Args:
            handler_name: The handler function name to generate tests for.
        """
        handlers, metadata = _get_handlers()
        handler = None
        for h in handlers:
            if h["name"] == handler_name:
                handler = h
                break
        if handler is None:
            return {
                "error": f"Handler '{handler_name}' not found",
                "available": sorted(h["name"] for h in handlers),
                "scan_metadata": metadata,
            }

        method = handler.get("method", "POST")
        path = handler.get("path", "/")
        class_name = handler_name.title().replace("_", "")

        test_code = f'''"""Tests for {handler_name} handler."""
import pytest


class Test{class_name}:
    """Tests for the {handler_name} handler ({method} {path})."""

    async def test_{handler_name}_success(self):
        """Happy path: valid {method} {path} returns success."""
        request_data = {{"key": "value"}}
        # TODO: Replace with actual handler invocation
        result = {{"status": "ok"}}
        assert result["status"] == "ok"

    async def test_{handler_name}_invalid_input(self):
        """Error path: invalid input returns error response."""
        # TODO: Test with invalid/missing required fields
        pass

    async def test_{handler_name}_error_handling(self):
        """Error path: handler errors are handled gracefully."""
        pass
'''

        try:
            ast.parse(test_code)
        except SyntaxError:
            pass

        return {
            "test_code": test_code,
            "test_path": f"tests/test_{handler_name}.py",
            "imports": ["pytest"],
            "scan_metadata": {"method": "template_generation", "limitations": []},
        }

    # Tier 3: Validation
    if is_tier_enabled(SecurityTier.VALIDATION):

        @server.tool(name=f"{namespace}.validate_handler")
        async def validate_handler(handler_name: str) -> dict:
            """Validate a Nexus handler definition.

            Args:
                handler_name: The handler function name to validate.
            """
            handlers, metadata = _get_handlers()
            handler = None
            for h in handlers:
                if h["name"] == handler_name:
                    handler = h
                    break
            if handler is None:
                return {
                    "valid": False,
                    "errors": [f"Handler '{handler_name}' not found"],
                    "warnings": [],
                    "handler_name": handler_name,
                    "scan_metadata": metadata,
                }

            errors: list[str] = []
            warnings: list[str] = []

            if not handler.get("method"):
                warnings.append("No HTTP method specified")
            if not handler.get("path"):
                warnings.append("No URL path specified")

            return {
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
                "handler_name": handler_name,
                "scan_metadata": metadata,
            }

    # Tier 4: Execution tools
    if is_tier_enabled(SecurityTier.EXECUTION):

        @server.tool(name=f"{namespace}.test_handler")
        async def test_handler(handler_name: str, input_data: str = "{}") -> dict:
            """Execute a Nexus handler in an isolated subprocess (Tier 4).

            Args:
                handler_name: The handler to execute.
                input_data: JSON string of input data for the handler.
            """
            handlers, metadata = _get_handlers()
            handler = None
            for h in handlers:
                if h["name"] == handler_name:
                    handler = h
                    break
            if handler is None:
                return {
                    "errors": [f"Handler '{handler_name}' not found"],
                    "available": sorted(h["name"] for h in handlers),
                    "scan_metadata": metadata,
                }

            handler_file = handler.get("file", "")
            module_path = handler_file.replace("/", ".").replace(".py", "")

            # Security: never interpolate user input into Python source.
            # Pass input_data, module_path, and handler_name via env vars
            # to prevent code injection.
            import base64 as _b64

            encoded_input = _b64.b64encode(input_data.encode()).decode()
            encoded_module = _b64.b64encode(module_path.encode()).decode()
            encoded_handler = _b64.b64encode(handler_name.encode()).decode()

            script = """
import json, sys, os, base64
sys.path.insert(0, '.')
try:
    module_path = base64.b64decode(os.environ['_HANDLER_MODULE']).decode()
    handler_name = base64.b64decode(os.environ['_HANDLER_NAME']).decode()
    input_str = base64.b64decode(os.environ['_HANDLER_INPUT']).decode()
    mod = __import__(module_path, fromlist=[handler_name])
    handler_fn = getattr(mod, handler_name)
    input_data = json.loads(input_str)
    import asyncio
    result = asyncio.run(handler_fn(input_data))
    print(json.dumps({"result": str(result), "status_code": 200}))
except Exception as e:
    print(json.dumps({"errors": [str(e)], "status_code": 500}))
"""
            # Inject values via environment, not string interpolation.
            start = time.monotonic()
            env = {
                **dict(os.environ),
                "PYTHONPATH": str(project_root),
                "_HANDLER_MODULE": encoded_module,
                "_HANDLER_NAME": encoded_handler,
                "_HANDLER_INPUT": encoded_input,
            }
            try:
                result = subprocess.run(
                    [sys.executable, "-c", script],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=str(project_root),
                    env=env,
                )
                elapsed_ms = int((time.monotonic() - start) * 1000)
                if result.returncode != 0:
                    return {
                        "errors": [
                            result.stderr.strip()
                            or f"Process exited with code {result.returncode}"
                        ],
                        "duration_ms": elapsed_ms,
                    }
                try:
                    output = json.loads(result.stdout)
                except json.JSONDecodeError:
                    output = {"raw_output": result.stdout.strip()}
                output["duration_ms"] = elapsed_ms
                return output
            except subprocess.TimeoutExpired:
                elapsed_ms = int((time.monotonic() - start) * 1000)
                return {
                    "errors": ["Execution timed out after 30s"],
                    "duration_ms": elapsed_ms,
                }
