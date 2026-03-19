from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Kaizen Catalog MCP Server -- agent discovery, deployment, and governance.

Provides 11 MCP tools organized in four categories:

Discovery:
    - catalog_search: Search agents by query, capabilities, type, status
    - catalog_describe: Full agent detail
    - catalog_schema: Input/output JSON Schema for an agent
    - catalog_deps: Dependency graph (DAG validation)

Deployment:
    - deploy_agent: Deploy from inline TOML manifest
    - deploy_status: Query deployment status
    - catalog_deregister: Remove agent from catalog

Application:
    - app_register: Register an application
    - app_status: Query application status

Governance:
    - validate_composition: DAG + schema validation for composite pipelines
    - budget_status: Budget tracking query

Usage (standalone)::

    python -m kaizen.mcp.catalog_server

Usage (programmatic)::

    from kaizen.mcp.catalog_server import CatalogMCPServer

    server = CatalogMCPServer()
    response = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
"""

from kaizen.mcp.catalog_server.server import CatalogMCPServer

__all__ = ["CatalogMCPServer"]
