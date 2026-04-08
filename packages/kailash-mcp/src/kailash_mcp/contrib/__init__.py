# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Contributor protocol for the kailash-platform MCP server.

Each framework contributor implements a single function::

    def register_tools(server: FastMCP, project_root: Path, namespace: str) -> None:
        '''Register framework-specific MCP tools.

        All tool names MUST start with '{namespace}.' prefix.
        This function MUST be synchronous and non-blocking.
        Do NOT perform network calls or heavy computation during registration.
        '''
        ...

Contributors that fail to import (because their framework is not installed)
are skipped gracefully by the platform server's contributor loop.
"""

from __future__ import annotations

import enum
import os

__all__ = ["SecurityTier", "is_tier_enabled"]


class SecurityTier(enum.IntEnum):
    """MCP tool security tiers.

    Tier 1 (INTROSPECTION) and Tier 2 (SCAFFOLD) are always enabled.
    Tier 3 (VALIDATION) is enabled by default; disable with
    ``KAILASH_MCP_ENABLE_VALIDATION=false``.
    Tier 4 (EXECUTION) is disabled by default; enable with
    ``KAILASH_MCP_ENABLE_EXECUTION=true``.
    """

    INTROSPECTION = 1
    SCAFFOLD = 2
    VALIDATION = 3
    EXECUTION = 4


def is_tier_enabled(tier: SecurityTier) -> bool:
    """Check if the given security tier is enabled via environment variables."""
    if tier <= SecurityTier.SCAFFOLD:
        return True  # Always enabled
    if tier == SecurityTier.VALIDATION:
        return (
            os.environ.get("KAILASH_MCP_ENABLE_VALIDATION", "true").lower() != "false"
        )
    if tier == SecurityTier.EXECUTION:
        return os.environ.get("KAILASH_MCP_ENABLE_EXECUTION", "").lower() == "true"
    return False
