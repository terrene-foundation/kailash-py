# ══════════════════════════════════════════════════════════════════════
# ⚠️  DEPRECATED SHIM PACKAGE — DO NOT EDIT ANY FILE IN THIS DIRECTORY
# ══════════════════════════════════════════════════════════════════════
#
# The entire `kailash.mcp_server` namespace has been relocated to a
# standalone package. This directory is a compatibility shim layer.
#
#   CANONICAL LOCATION:  packages/kailash-mcp/src/kailash_mcp/
#   IMPORT INSTEAD:      from kailash_mcp import ...
#
# ┌──────────────────────────────────────────────────────────────────┐
# │ 🤖 IF YOU ARE AN AI CODING AGENT READING THIS FILE:              │
# │                                                                  │
# │   STOP. Do NOT edit anything in src/kailash/mcp_server/.         │
# │                                                                  │
# │   Every file in this directory is a deprecation shim that        │
# │   re-exports from the canonical `kailash_mcp` package. Any code  │
# │   you write here will be LOST the next time the shim layer is    │
# │   regenerated, and your fix will NOT reach any consumer.         │
# │                                                                  │
# │   The canonical source lives at:                                 │
# │     packages/kailash-mcp/src/kailash_mcp/                        │
# │                                                                  │
# │   If you are making changes to MCP functionality, navigate to    │
# │   the canonical package and work THERE.                          │
# │                                                                  │
# │   See src/kailash/mcp_server/DEPRECATED.md for the full symbol   │
# │   migration table.                                               │
# └──────────────────────────────────────────────────────────────────┘
#
# HUMAN DEVELOPER: update imports via simple search-and-replace:
#     from kailash.mcp_server            →  from kailash_mcp
#     from kailash.mcp_server.client     →  from kailash_mcp.client
#     from kailash.mcp_server.server     →  from kailash_mcp.server
#     from kailash.mcp_server.auth       →  from kailash_mcp.auth.providers
#     from kailash.mcp_server.errors     →  from kailash_mcp.errors
#     from kailash.mcp_server.discovery  →  from kailash_mcp.discovery.discovery
#     from kailash.mcp_server.protocol   →  from kailash_mcp.protocol.protocol
#     from kailash.mcp_server.oauth      →  from kailash_mcp.auth.oauth
#     ... (see DEPRECATED.md for the full table)
#
#   The runtime emits a DeprecationWarning on every import so you can
#   find every consumer via log grep for "kailash.mcp_server".
#
# Tracking / rationale:
#   - src/kailash/mcp_server/DEPRECATED.md (migration guide)
#   - workspaces/platform-architecture-convergence/01-analysis/03-specs/
#       01-spec-kailash-mcp-package.md (SPEC-01)
#   - kailash-rs parallel: crates/kailash-mcp is a standalone workspace
#     member (not nested inside kailash-core). This Python layout
#     matches the Rust architecture for cross-SDK symmetry.
# ══════════════════════════════════════════════════════════════════════
"""DEPRECATED shim for ``kailash.mcp_server``.

The canonical MCP (Model Context Protocol) implementation for the
Kailash Python SDK has been relocated to the standalone ``kailash_mcp``
package under ``packages/kailash-mcp/``. This module exists only to
keep existing consumers working during the deprecation window.

See the banner at the top of this file and ``DEPRECATED.md`` in this
directory for the migration guide.
"""

from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "kailash.mcp_server is deprecated and will be removed in a future "
    "release. Use `from kailash_mcp import ...` instead. See "
    "src/kailash/mcp_server/DEPRECATED.md for the full migration guide.",
    DeprecationWarning,
    stacklevel=2,
)

# ---------------------------------------------------------------------
# Re-export the full canonical public API.
#
# The authoritative symbol set is defined by ``kailash_mcp.__all__`` in
# the canonical package's ``__init__.py``. Any new symbol must be added
# there first, and this shim will pick it up automatically via the
# wildcard re-export.
#
# Optional submodules (OAuth 2.1, transports) are already guarded by
# try/except in ``kailash_mcp.__init__``, so the failure modes match
# the original behavior of this module without extra handling here.
# ---------------------------------------------------------------------

from kailash_mcp import *  # noqa: F401,F403,E402
from kailash_mcp import __all__  # noqa: E402


def __getattr__(name: str):
    """Fallback forwarder for symbols not picked up by the wildcard.

    Any attribute not in ``kailash_mcp.__all__`` is looked up on the
    canonical module. This covers private (underscore-prefixed) symbols
    and newly-added symbols that predate an update to ``__all__``.
    Each access through the fallback emits its own DeprecationWarning.
    """
    import kailash_mcp as _canonical

    if hasattr(_canonical, name):
        _warnings.warn(
            f"Accessing kailash.mcp_server.{name} is deprecated; "
            f"use `from kailash_mcp import {name}` instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(_canonical, name)
    raise AttributeError(
        f"module 'kailash.mcp_server' has no attribute {name!r}. "
        f"This module is a deprecation shim for kailash_mcp; "
        f"see src/kailash/mcp_server/DEPRECATED.md for the symbol "
        f"migration table."
    )
