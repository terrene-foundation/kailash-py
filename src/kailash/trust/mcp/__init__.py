# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP MCP Server package.

Exposes EATP trust operations as MCP tools and trust data as MCP resources
over the JSON-RPC protocol. Uses stdio transport by default.

This implementation is self-contained and does not depend on the external
``mcp`` Python SDK. It implements the MCP initialize/tools/list/tools/call
and resources/list/resources/read protocol directly over JSON-RPC.

Quick Start::

    import asyncio
    from kailash.trust.mcp.server import EATPMCPServer, run_server
    from kailash.trust.chain_store.memory import InMemoryTrustStore

    # Simple: use defaults
    asyncio.run(run_server())

    # Advanced: provide your own store and operations
    store = InMemoryTrustStore()
    server = EATPMCPServer(trust_store=store)
    asyncio.run(server.serve_stdio())

Tools:
    - **eatp_verify**: Check action authorization (verdict + details)
    - **eatp_status**: Get trust state (score, posture, delegations, constraints)
    - **eatp_audit_query**: Query audit trail with filters
    - **eatp_delegate**: Delegate capabilities (requires TrustOperations)
    - **eatp_revoke**: Revoke delegation (requires TrustOperations)

Resources:
    - **eatp://authorities**: List all organizational authorities
    - **eatp://agents/{id}**: Agent details with trust posture
    - **eatp://chains/{authority_id}**: Delegation chain visualization
    - **eatp://constraints/{agent_id}**: Active constraint envelope
"""

from kailash.trust.mcp.server import EATPMCPServer, run_server

__all__ = [
    "EATPMCPServer",
    "run_server",
]
