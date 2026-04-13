# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Platform contributor for the kailash-platform MCP server.

Provides the ``platform.platform_map`` tool -- a single-call cross-framework
graph of the entire project. Aggregates discovery results from all framework
contributors. Always available (no sub-package dependency).

Tools registered:
    - ``platform.platform_map`` (Tier 1): Full cross-framework project graph
    - ``platform.project_info`` (Tier 1): Project metadata
    - ``platform.discover_tools`` (Tier 1): Unified tool discovery across frameworks
    - ``platform.discover_resources`` (Tier 1): Unified resource discovery
    - ``platform.get_platform_info`` (Tier 1): Platform metadata and capabilities
"""

from __future__ import annotations

import importlib.metadata
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["register_tools"]

# Skip directories when scanning project files
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_project_info(project_root: Path) -> dict[str, Any]:
    """Extract project metadata from pyproject.toml or directory name."""
    project_name = project_root.name
    toml_path = project_root / "pyproject.toml"
    if toml_path.exists():
        try:
            content = toml_path.read_text(encoding="utf-8")
            # Simple TOML parsing for project name (avoids tomllib dependency)
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("name") and "=" in stripped:
                    _, _, val = stripped.partition("=")
                    val = val.strip().strip('"').strip("'")
                    if val:
                        project_name = val
                    break
        except OSError:
            pass

    kailash_version = None
    try:
        kailash_version = importlib.metadata.version("kailash")
    except importlib.metadata.PackageNotFoundError:
        pass

    return {
        "name": project_name,
        "root": str(project_root),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "kailash_version": kailash_version,
    }


def _get_framework_versions() -> dict[str, dict[str, Any]]:
    """Detect which Kailash frameworks are installed and their versions."""
    frameworks: dict[str, dict[str, Any]] = {}
    pkg_map = {
        "core": "kailash",
        "dataflow": "kailash-dataflow",
        "nexus": "kailash-nexus",
        "kaizen": "kailash-kaizen",
        "pact": "kailash-pact",
        "trust": "kailash",  # trust is part of core
        "ml": "kailash-ml",
        "align": "kailash-align",
    }
    for fw, pkg in pkg_map.items():
        try:
            version = importlib.metadata.version(pkg)
            frameworks[fw] = {"installed": True, "version": version}
        except importlib.metadata.PackageNotFoundError:
            frameworks[fw] = {"installed": False}
    return frameworks


def _iter_python_files(root: Path) -> list[Path]:
    """Iterate Python files in a project, skipping non-project directories."""
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


def _safe_import_scanner(module_name: str, func_name: str) -> Any:
    """Try to import a scanner function from a contributor module."""
    try:
        mod = __import__(module_name, fromlist=[func_name])
        return getattr(mod, func_name, None)
    except (ImportError, AttributeError):
        return None


def _detect_model_handler_connections(
    models: list[dict[str, Any]],
    handlers: list[dict[str, Any]],
    project_root: Path,
) -> list[dict[str, Any]]:
    """Detect model-to-handler connections via generated node name matching."""
    connections: list[dict[str, Any]] = []
    for model in models:
        model_name = model.get("name", "")
        generated_names = [
            f"Create{model_name}",
            f"Read{model_name}",
            f"Update{model_name}",
            f"Delete{model_name}",
            f"List{model_name}",
            f"Upsert{model_name}",
            f"Count{model_name}",
        ]
        for handler in handlers:
            handler_file = project_root / handler.get("file", "")
            if not handler_file.exists():
                continue
            try:
                source = handler_file.read_text(encoding="utf-8")
            except OSError:
                continue
            for gen_name in generated_names:
                if gen_name in source:
                    connections.append(
                        {
                            "from": model_name,
                            "to": handler.get("name", ""),
                            "type": "model_to_handler",
                            "via": gen_name,
                        }
                    )
                    break  # One connection per model-handler pair
    return connections


def _detect_agent_tool_connections(
    agents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Detect agent-to-tool connections from agent tool lists."""
    connections: list[dict[str, Any]] = []
    for agent in agents:
        tools = agent.get("tools") or []
        for tool_name in tools:
            connections.append(
                {
                    "from": agent.get("name", ""),
                    "to": tool_name,
                    "type": "agent_to_tool",
                }
            )
    return connections


def _detect_model_agent_connections(
    models: list[dict[str, Any]],
    agents: list[dict[str, Any]],
    project_root: Path,
) -> list[dict[str, Any]]:
    """Detect model-to-agent connections via generated node name references."""
    connections: list[dict[str, Any]] = []
    for model in models:
        model_name = model.get("name", "")
        generated_names = [
            f"Create{model_name}",
            f"Read{model_name}",
            f"Update{model_name}",
            f"Delete{model_name}",
            f"List{model_name}",
        ]
        for agent in agents:
            agent_file = project_root / agent.get("file", "")
            if not agent_file.exists():
                continue
            try:
                source = agent_file.read_text(encoding="utf-8")
            except OSError:
                continue
            for gen_name in generated_names:
                if gen_name in source:
                    connections.append(
                        {
                            "from": model_name,
                            "to": agent.get("name", ""),
                            "type": "model_to_agent",
                            "via": gen_name,
                        }
                    )
                    break
    return connections


def _get_trust_summary(project_root: Path) -> dict[str, Any]:
    """Get a lightweight trust-plane summary for the platform map."""
    trust_dir = project_root / "trust-plane"
    if not trust_dir.exists():
        return {"installed": False, "trust_dir_exists": False}
    return {
        "installed": True,
        "trust_dir_exists": True,
        "trust_dir": str(trust_dir),
    }


def _build_platform_map(project_root: Path) -> dict[str, Any]:
    """Build the full platform map data structure.

    This is the core logic shared by the platform.platform_map tool
    and the kailash://platform-map resource.
    """
    start = time.monotonic()

    models: list[dict[str, Any]] = []
    handlers: list[dict[str, Any]] = []
    agents: list[dict[str, Any]] = []
    channels: list[dict[str, Any]] = []
    total_files = 0

    scan_models = _safe_import_scanner("kailash_mcp.contrib.dataflow", "_scan_models")
    if scan_models is not None:
        try:
            result = scan_models(project_root)
            if isinstance(result, tuple):
                models, meta = result
                total_files += meta.get("files_scanned", 0)
            elif isinstance(result, list):
                models = result
        except Exception as exc:
            logger.debug("DataFlow scan failed: %s", exc)

    scan_handlers = _safe_import_scanner("kailash_mcp.contrib.nexus", "_scan_handlers")
    if scan_handlers is not None:
        try:
            result = scan_handlers(project_root)
            if isinstance(result, tuple):
                handlers, meta = result
                total_files += meta.get("files_scanned", 0)
            elif isinstance(result, list):
                handlers = result
        except Exception as exc:
            logger.debug("Nexus scan failed: %s", exc)

    scan_agents = _safe_import_scanner("kailash_mcp.contrib.kaizen", "_scan_agents")
    if scan_agents is not None:
        try:
            result = scan_agents(project_root)
            if isinstance(result, tuple):
                agents, meta = result
                total_files += meta.get("files_scanned", 0)
            elif isinstance(result, list):
                agents = result
        except Exception as exc:
            logger.debug("Kaizen scan failed: %s", exc)

    connections: list[dict[str, Any]] = []
    connections.extend(
        _detect_model_handler_connections(models, handlers, project_root)
    )
    connections.extend(_detect_agent_tool_connections(agents))
    connections.extend(_detect_model_agent_connections(models, agents, project_root))

    trust_summary = _get_trust_summary(project_root)

    elapsed_ms = int((time.monotonic() - start) * 1000)

    frameworks_scanned: list[str] = []
    if models or scan_models is not None:
        frameworks_scanned.append("dataflow")
    if handlers or scan_handlers is not None:
        frameworks_scanned.append("nexus")
    if agents or scan_agents is not None:
        frameworks_scanned.append("kaizen")

    return {
        "project": _get_project_info(project_root),
        "frameworks": _get_framework_versions(),
        "models": [
            {
                "name": m.get("name"),
                "fields_count": m.get("fields_count", 0),
                "file": m.get("file"),
            }
            for m in models
        ],
        "handlers": [
            {
                "name": h.get("name"),
                "method": h.get("method"),
                "path": h.get("path"),
                "file": h.get("file"),
            }
            for h in handlers
        ],
        "agents": [
            {"name": a.get("name"), "type": a.get("type"), "file": a.get("file")}
            for a in agents
        ],
        "channels": channels,
        "connections": connections,
        "trust": trust_summary,
        "scan_metadata": {
            "method": "ast_static",
            "frameworks_scanned": frameworks_scanned,
            "total_files_scanned": total_files,
            "scan_duration_ms": elapsed_ms,
            "limitations": [
                "Cross-framework connections detected via deterministic naming only",
                "Custom node names in handlers not detected as model connections",
                "Dynamic model/handler/agent registration not detected",
                "External packages not scanned",
            ],
        },
    }


# ---------------------------------------------------------------------------
# register_tools
# ---------------------------------------------------------------------------


def register_tools(server: Any, project_root: Path, namespace: str) -> None:
    """Register Platform tools and MCP resources on the server."""

    @server.tool(name=f"{namespace}.platform_map")
    async def platform_map(filter: str = "") -> dict:
        """Return a complete cross-framework map of this Kailash project.

        A single call that shows all models, handlers, agents, channels,
        and the connections between them. Use this for project overview.

        Args:
            filter: Optional JSON string to filter output (reserved for future use).
        """
        return _build_platform_map(project_root)

    @server.tool(name=f"{namespace}.project_info")
    async def project_info() -> dict:
        """Get project metadata including name, root, and framework versions.

        Returns the project name (from pyproject.toml), Python version,
        Kailash SDK version, and which frameworks are installed.
        """
        return {
            "project": _get_project_info(project_root),
            "frameworks": _get_framework_versions(),
            "scan_metadata": {
                "method": "importlib.metadata",
                "limitations": [],
            },
        }

    # -----------------------------------------------------------------------
    # MCP Resources (MCP-507)
    # -----------------------------------------------------------------------

    def _models_data() -> str:
        scan_models = _safe_import_scanner(
            "kailash_mcp.contrib.dataflow", "_scan_models"
        )
        if scan_models is not None:
            try:
                models, meta = scan_models(project_root)
                return json.dumps({"models": models, "scan_metadata": meta}, indent=2)
            except Exception:
                pass
        return json.dumps({"models": [], "installed": False}, indent=2)

    def _handlers_data() -> str:
        scan_handlers = _safe_import_scanner(
            "kailash_mcp.contrib.nexus", "_scan_handlers"
        )
        if scan_handlers is not None:
            try:
                handlers, meta = scan_handlers(project_root)
                return json.dumps(
                    {"handlers": handlers, "scan_metadata": meta}, indent=2
                )
            except Exception:
                pass
        return json.dumps({"handlers": [], "installed": False}, indent=2)

    def _agents_data() -> str:
        scan_agents = _safe_import_scanner("kailash_mcp.contrib.kaizen", "_scan_agents")
        if scan_agents is not None:
            try:
                agents, meta = scan_agents(project_root)
                return json.dumps({"agents": agents, "scan_metadata": meta}, indent=2)
            except Exception:
                pass
        return json.dumps({"agents": [], "installed": False}, indent=2)

    def _node_types_data() -> str:
        scan_nodes = _safe_import_scanner(
            "kailash_mcp.contrib.core", "_get_cached_node_types"
        )
        if scan_nodes is not None:
            try:
                node_types, meta = scan_nodes()
                return json.dumps(
                    {"node_types": node_types, "scan_metadata": meta}, indent=2
                )
            except Exception:
                pass
        return json.dumps({"node_types": [], "installed": False}, indent=2)

    @server.resource("kailash://models")
    async def models_resource() -> str:
        """List of all DataFlow models in this project."""
        return _models_data()

    @server.resource("kailash://handlers")
    async def handlers_resource() -> str:
        """List of all Nexus handlers in this project."""
        return _handlers_data()

    @server.resource("kailash://agents")
    async def agents_resource() -> str:
        """List of all Kaizen agents in this project."""
        return _agents_data()

    @server.resource("kailash://platform-map")
    async def platform_map_resource() -> str:
        """Complete cross-framework map of this project."""
        return json.dumps(_build_platform_map(project_root), indent=2)

    @server.resource("kailash://node-types")
    async def node_types_resource() -> str:
        """Available Core SDK node types."""
        return _node_types_data()

    # -----------------------------------------------------------------------
    # Unified discovery tools (MCP-510)
    # -----------------------------------------------------------------------

    @server.tool(name=f"{namespace}.discover_tools")
    async def discover_tools(framework: str = "") -> dict:
        """Discover all MCP tools registered across Kailash frameworks.

        Returns a unified view of every tool available on this server,
        grouped by framework namespace. Use this to find what operations
        are available before calling specific tools.

        Args:
            framework: Optional framework filter (e.g., "dataflow", "core").
                       Empty string returns tools from all frameworks.
        """
        from kailash_mcp.platform_server import FRAMEWORK_CONTRIBUTORS

        tool_inventory: dict[str, list[dict[str, str]]] = {}

        for module_path, ns in FRAMEWORK_CONTRIBUTORS:
            if framework and ns != framework:
                continue

            tools_for_ns: list[dict[str, str]] = []

            # Discover tools by importing the contributor and introspecting
            # the server's tool registry for matching namespace prefixes.
            try:
                tool_names = set()
                try:
                    tool_names = set(server._tool_manager._tools.keys())
                except AttributeError:
                    try:
                        tool_names = set(server._tools.keys())
                    except AttributeError:
                        pass

                prefix = f"{ns}."
                for tool_name in sorted(tool_names):
                    if tool_name.startswith(prefix):
                        description = ""
                        try:
                            tool_obj = server._tool_manager._tools[tool_name]
                            description = getattr(tool_obj, "description", "") or ""
                        except (AttributeError, KeyError):
                            pass
                        tools_for_ns.append(
                            {
                                "name": tool_name,
                                "framework": ns,
                                "description": description[:200],
                            }
                        )
            except Exception as exc:
                logger.debug("Tool discovery for %s failed: %s", ns, exc)

            if tools_for_ns:
                tool_inventory[ns] = tools_for_ns

        total = sum(len(v) for v in tool_inventory.values())
        return {
            "tools": tool_inventory,
            "total": total,
            "frameworks_found": sorted(tool_inventory.keys()),
            "scan_metadata": {
                "method": "server_registry_introspection",
                "filter": framework or "all",
                "limitations": [
                    "Only tools registered at server startup are listed",
                    "Tier-gated tools may be absent if tier is disabled",
                ],
            },
        }

    @server.tool(name=f"{namespace}.discover_resources")
    async def discover_resources(framework: str = "") -> dict:
        """Discover all MCP resources registered across Kailash frameworks.

        Returns a unified view of every resource URI available on this
        server. Resources are read-only data endpoints (models, schemas,
        platform map, etc.).

        Args:
            framework: Optional filter by URI prefix (e.g., "dataflow").
                       Empty string returns all resources.
        """
        resource_inventory: list[dict[str, str]] = []

        try:
            resource_map: dict[str, Any] = {}
            try:
                resource_map = dict(server._resource_manager._resources)
            except AttributeError:
                try:
                    resource_map = dict(server._resources)
                except AttributeError:
                    pass

            for uri in sorted(resource_map.keys()):
                # Apply framework filter on URI path segments
                if framework:
                    # Match "kailash://dataflow/..." or "kailash://models" etc.
                    uri_lower = uri.lower()
                    if framework.lower() not in uri_lower:
                        continue

                description = ""
                try:
                    res_obj = resource_map[uri]
                    description = getattr(res_obj, "description", "") or ""
                except (AttributeError, KeyError):
                    pass

                resource_inventory.append(
                    {
                        "uri": uri,
                        "description": description[:200],
                    }
                )
        except Exception as exc:
            logger.debug("Resource discovery failed: %s", exc)

        return {
            "resources": resource_inventory,
            "total": len(resource_inventory),
            "scan_metadata": {
                "method": "server_registry_introspection",
                "filter": framework or "all",
                "limitations": [
                    "Only resources registered at server startup are listed",
                    "Template resources (with URI parameters) listed as templates",
                ],
            },
        }

    @server.tool(name=f"{namespace}.get_platform_info")
    async def get_platform_info() -> dict:
        """Return comprehensive platform metadata.

        Includes installed packages, their versions, available capabilities
        (which frameworks are active), and the server's tool/resource counts.
        Use this to understand what this Kailash installation can do.
        """
        frameworks = _get_framework_versions()
        project = _get_project_info(project_root)

        # Count tools and resources from server registry
        tool_count = 0
        resource_count = 0
        try:
            tool_count = len(server._tool_manager._tools)
        except AttributeError:
            try:
                tool_count = len(server._tools)
            except AttributeError:
                pass
        try:
            resource_count = len(server._resource_manager._resources)
        except AttributeError:
            try:
                resource_count = len(server._resources)
            except AttributeError:
                pass

        # Build capabilities list from installed frameworks
        capabilities: list[str] = []
        capability_map = {
            "core": "workflow_orchestration",
            "dataflow": "database_operations",
            "nexus": "multi_channel_deployment",
            "kaizen": "ai_agent_framework",
            "pact": "organizational_governance",
            "trust": "trust_plane_eatp",
            "ml": "ml_lifecycle",
            "align": "llm_alignment",
        }
        for fw, info in frameworks.items():
            if info.get("installed"):
                cap = capability_map.get(fw)
                if cap:
                    capabilities.append(cap)

        return {
            "project": project,
            "frameworks": frameworks,
            "capabilities": sorted(capabilities),
            "server": {
                "tools_registered": tool_count,
                "resources_registered": resource_count,
            },
            "scan_metadata": {
                "method": "importlib.metadata",
                "limitations": [],
            },
        }
