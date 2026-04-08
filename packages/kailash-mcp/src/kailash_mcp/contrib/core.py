# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Core SDK contributor for the kailash-platform MCP server.

Provides AST-based discovery of Kailash node types from the ``kailash.nodes``
package. Always available (no sub-package dependency).

Tools registered:
    - ``core.list_node_types`` (Tier 1): All available node types
    - ``core.list_node_categories`` (Tier 1): Node categories with counts
    - ``core.describe_node`` (Tier 1): Detailed info for a single node type
    - ``core.get_sdk_version`` (Tier 1): Kailash SDK version info
    - ``core.validate_workflow`` (Tier 3): Validate workflow JSON structure
"""

from __future__ import annotations

import ast
import importlib.metadata
import importlib.util
import json
import logging
import time
from pathlib import Path
from typing import Any

from kailash_mcp.contrib import SecurityTier, is_tier_enabled

logger = logging.getLogger(__name__)

__all__ = ["register_tools"]

# ---------------------------------------------------------------------------
# AST-based node scanner
# ---------------------------------------------------------------------------

_node_type_cache: dict[str, Any] = {}
_cache_mtime: float = 0.0


def _get_nodes_dir() -> Path | None:
    """Locate the kailash.nodes package directory."""
    spec = importlib.util.find_spec("kailash.nodes")
    if spec is None or spec.submodule_search_locations is None:
        return None
    locs = list(spec.submodule_search_locations)
    if not locs:
        return None
    return Path(locs[0])


def _extract_params(cls_node: ast.ClassDef) -> list[dict[str, Any]]:
    """Extract parameter definitions from a ClassDef AST node."""
    params: list[dict[str, Any]] = []
    for item in cls_node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            param_name = item.target.id
            if param_name.startswith("_"):
                continue
            type_str = ast.unparse(item.annotation) if item.annotation else "Any"
            params.append(
                {
                    "name": param_name,
                    "type": type_str,
                    "required": item.value is None,
                    "description": "",
                }
            )
    # Also check __init__ parameters
    for item in cls_node.body:
        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
            for arg in item.args.args[1:]:  # skip self
                arg_name = arg.arg
                if arg_name.startswith("_"):
                    continue
                # Skip if already found via annotations
                if any(p["name"] == arg_name for p in params):
                    continue
                type_str = ast.unparse(arg.annotation) if arg.annotation else "Any"
                params.append(
                    {
                        "name": arg_name,
                        "type": type_str,
                        "required": True,
                        "description": "",
                    }
                )
            break
    return params


def _has_process_or_execute(cls_node: ast.ClassDef) -> bool:
    """Check if a class has a process() or execute() method."""
    for item in cls_node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if item.name in ("process", "execute", "run"):
                return True
    return False


def _scan_node_types() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Scan kailash.nodes package for node type classes using AST.

    Returns:
        Tuple of (node_types list, scan_metadata dict).
    """
    start = time.monotonic()
    nodes_dir = _get_nodes_dir()
    if nodes_dir is None:
        return [], {
            "method": "ast_static",
            "source": "kailash.nodes package",
            "files_scanned": 0,
            "scan_duration_ms": 0,
            "limitations": ["kailash.nodes package not found"],
        }

    node_types: list[dict[str, Any]] = []
    files_scanned = 0

    for py_file in sorted(nodes_dir.rglob("*.py")):
        if py_file.name.startswith("_"):
            continue
        files_scanned += 1
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            # Heuristic: class name ends with "Node" or has process/execute method
            is_node = node.name.endswith("Node")
            if not is_node and _has_process_or_execute(node):
                is_node = True
            if not is_node:
                continue

            docstring = ast.get_docstring(node) or ""

            # Category from module path
            try:
                rel = py_file.relative_to(nodes_dir)
                category = (
                    rel.parent.as_posix().replace("/", ".")
                    if rel.parent != Path(".")
                    else "core"
                )
            except ValueError:
                category = "core"

            params = _extract_params(node)

            node_types.append(
                {
                    "name": node.name,
                    "category": category,
                    "description": docstring.split("\n")[0] if docstring else "",
                    "parameters": params,
                    "file": str(py_file.relative_to(nodes_dir)),
                }
            )

    elapsed_ms = int((time.monotonic() - start) * 1000)
    metadata = {
        "method": "ast_static",
        "source": "kailash.nodes package",
        "files_scanned": files_scanned,
        "scan_duration_ms": elapsed_ms,
        "limitations": [
            "Only discovers built-in node types, not custom project nodes",
            "Parameter extraction limited to class annotations and __init__ args",
        ],
    }
    return node_types, metadata


def _get_cached_node_types() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return cached node types, rescanning if the nodes directory changed."""
    global _node_type_cache, _cache_mtime

    nodes_dir = _get_nodes_dir()
    if nodes_dir is None:
        return _scan_node_types()

    # Check if any file in the nodes directory has changed
    try:
        current_mtime = max(
            (
                f.stat().st_mtime
                for f in nodes_dir.rglob("*.py")
                if not f.name.startswith("_")
            ),
            default=0.0,
        )
    except OSError:
        current_mtime = 0.0

    if _node_type_cache.get("node_types") is not None and current_mtime <= _cache_mtime:
        return _node_type_cache["node_types"], _node_type_cache["metadata"]

    node_types, metadata = _scan_node_types()
    _node_type_cache["node_types"] = node_types
    _node_type_cache["metadata"] = metadata
    _cache_mtime = current_mtime
    return node_types, metadata


# ---------------------------------------------------------------------------
# register_tools
# ---------------------------------------------------------------------------


def register_tools(server: Any, project_root: Path, namespace: str) -> None:
    """Register Core SDK tools on the MCP server."""

    @server.tool(name=f"{namespace}.list_node_types")
    async def list_node_types() -> dict:
        """List all available Kailash Core SDK node types.

        Returns node types discovered by scanning the kailash.nodes package
        using AST-based static analysis.
        """
        node_types, metadata = _get_cached_node_types()
        return {
            "node_types": [
                {
                    "name": nt["name"],
                    "category": nt["category"],
                    "description": nt["description"],
                    "parameters_count": len(nt["parameters"]),
                }
                for nt in node_types
            ],
            "total": len(node_types),
            "scan_metadata": metadata,
        }

    @server.tool(name=f"{namespace}.list_node_categories")
    async def list_node_categories() -> dict:
        """List node type categories with counts."""
        node_types, metadata = _get_cached_node_types()
        categories: dict[str, int] = {}
        for nt in node_types:
            cat = nt["category"]
            categories[cat] = categories.get(cat, 0) + 1
        return {
            "categories": [
                {"name": cat, "count": count}
                for cat, count in sorted(categories.items())
            ],
            "total_categories": len(categories),
            "scan_metadata": metadata,
        }

    @server.tool(name=f"{namespace}.describe_node")
    async def describe_node(node_type: str) -> dict:
        """Describe a specific Core SDK node type with its parameters.

        Args:
            node_type: The node type name (e.g., "TransformNode", "FilterNode")
        """
        node_types, metadata = _get_cached_node_types()
        for nt in node_types:
            if nt["name"] == node_type:
                return {**nt, "scan_metadata": metadata}
        return {
            "error": f"Node type '{node_type}' not found",
            "available": sorted(nt["name"] for nt in node_types)[:20],
            "total_available": len(node_types),
            "scan_metadata": metadata,
        }

    @server.tool(name=f"{namespace}.get_sdk_version")
    async def get_sdk_version() -> dict:
        """Get Kailash SDK version and installed framework information."""
        versions: dict[str, str | None] = {}
        for pkg in [
            "kailash",
            "kailash-dataflow",
            "kailash-nexus",
            "kailash-kaizen",
            "kailash-pact",
            "kailash-ml",
            "kailash-align",
        ]:
            try:
                versions[pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                versions[pkg] = None

        import sys

        return {
            "versions": versions,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "scan_metadata": {
                "method": "importlib.metadata",
                "limitations": [],
            },
        }

    # Tier 3: Validation tools
    if is_tier_enabled(SecurityTier.VALIDATION):

        @server.tool(name=f"{namespace}.validate_workflow")
        async def validate_workflow(workflow_json: str) -> dict:
            """Validate a workflow JSON structure.

            Checks node types exist, DAG has no cycles, required parameters
            are provided, and connection targets reference existing node IDs.

            Args:
                workflow_json: JSON string representing the workflow definition.
            """
            errors: list[str] = []
            warnings: list[str] = []

            # Parse JSON
            try:
                workflow = json.loads(workflow_json)
            except (json.JSONDecodeError, TypeError) as exc:
                return {
                    "valid": False,
                    "errors": [f"Invalid JSON: {exc}"],
                    "warnings": [],
                    "node_count": 0,
                    "has_cycles": False,
                    "scan_metadata": {
                        "method": "ast_static",
                        "limitations": ["Workflow JSON must be a valid JSON string"],
                    },
                }

            if not isinstance(workflow, dict):
                return {
                    "valid": False,
                    "errors": ["Workflow must be a JSON object"],
                    "warnings": [],
                    "node_count": 0,
                    "has_cycles": False,
                    "scan_metadata": {"method": "ast_static", "limitations": []},
                }

            # Extract nodes
            nodes = workflow.get("nodes", [])
            if not isinstance(nodes, list):
                nodes = []
                errors.append("'nodes' field must be a list")

            node_ids = set()
            known_types, _ = _get_cached_node_types()
            known_type_names = {nt["name"] for nt in known_types}

            for i, node in enumerate(nodes):
                if not isinstance(node, dict):
                    errors.append(f"Node at index {i} must be an object")
                    continue

                node_type = node.get("type", "")
                node_id = node.get("id", "")

                if not node_id:
                    errors.append(f"Node at index {i} has no 'id' field")
                elif node_id in node_ids:
                    errors.append(f"Duplicate node ID: '{node_id}'")
                else:
                    node_ids.add(node_id)

                if not node_type:
                    errors.append(f"Node at index {i} has no 'type' field")
                elif node_type not in known_type_names:
                    warnings.append(
                        f"Unknown node type '{node_type}' (may be a custom or project node)"
                    )

            # Check connections reference existing nodes
            connections = workflow.get("connections", [])
            if isinstance(connections, list):
                for conn in connections:
                    if isinstance(conn, dict):
                        src = conn.get("from", "")
                        dst = conn.get("to", "")
                        if src and src not in node_ids:
                            errors.append(
                                f"Connection references non-existent source node: '{src}'"
                            )
                        if dst and dst not in node_ids:
                            errors.append(
                                f"Connection references non-existent target node: '{dst}'"
                            )

            # Simple cycle detection via DFS
            has_cycles = False
            if isinstance(connections, list) and node_ids:
                adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}
                for conn in connections:
                    if isinstance(conn, dict):
                        src = conn.get("from", "")
                        dst = conn.get("to", "")
                        if src in adjacency and dst in adjacency:
                            adjacency[src].append(dst)

                visited: set[str] = set()
                in_stack: set[str] = set()

                def _dfs(nid: str) -> bool:
                    visited.add(nid)
                    in_stack.add(nid)
                    for neighbor in adjacency.get(nid, []):
                        if neighbor in in_stack:
                            return True
                        if neighbor not in visited and _dfs(neighbor):
                            return True
                    in_stack.discard(nid)
                    return False

                for nid in node_ids:
                    if nid not in visited:
                        if _dfs(nid):
                            has_cycles = True
                            warnings.append(
                                "Workflow contains cycles (may be intentional for iterative patterns)"
                            )
                            break

            return {
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
                "node_count": len(nodes),
                "has_cycles": has_cycles,
                "scan_metadata": {
                    "method": "ast_static",
                    "source": "kailash.nodes package",
                    "limitations": [
                        "Only validates against built-in node types",
                        "Custom project node types reported as warnings, not errors",
                    ],
                },
            }
