# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Guarded import boundary for the optional third-party ``mcp`` package.

``mcp`` is an OPTIONAL extra (``pyproject.toml``: ``mcp = ["mcp[cli]>=1.23.0,<2.0"]``),
so a bare ``pip install kailash`` does NOT provide it. Any module that does
``from mcp.server import FastMCP`` at module scope is therefore un-importable on a
bare install, and the user gets a bare ``ImportError`` naming an internal module
path with no instruction. Every site that needs a symbol from the third-party
``mcp`` package MUST route through an accessor in this module instead, so the
failure is a typed, actionable error raised at USE time rather than IMPORT time.

Why ``mcp.server`` and not ``mcp.server.fastmcp``
------------------------------------------------
Both paths resolve to the same class on ``mcp`` 1.x (verified on 1.26.0:
``mcp.server.FastMCP is mcp.server.fastmcp.FastMCP``), but they do NOT age the
same way. In ``mcp`` 2.0.0:

* ``mcp/server/fastmcp/`` is DELETED outright — the submodule does not exist, so
  ``from mcp.server.fastmcp import FastMCP`` raises ``ModuleNotFoundError``.
* ``mcp/server/__init__.py`` survives with an explicit ``__all__``; the class was
  renamed (``FastMCP`` -> ``MCPServer``) but the package remains the documented
  public export surface in BOTH majors.

So ``mcp.server`` is the shallower, publicly-declared, longer-lived surface, and
routing both call sites through this one helper means an ``mcp`` 2.x migration
changes ONE symbol in ONE file rather than two import paths in two distributions.
"""

import logging

logger = logging.getLogger(__name__)

__all__ = ["FASTMCP_IMPORT_ERROR_MESSAGE", "get_fastmcp_class"]


#: The single, actionable message every FastMCP import failure raises. Shared so
#: the core trust-plane server and the ``kailash-mcp`` platform server cannot
#: drift into two different instructions for the same missing dependency.
FASTMCP_IMPORT_ERROR_MESSAGE = (
    "Cannot import FastMCP from the third-party 'mcp' package. "
    "Install it with: pip install 'mcp[cli]>=1.23.0'"
)


def get_fastmcp_class() -> type:
    """Return the third-party ``FastMCP`` server class.

    Returns:
        The ``FastMCP`` class from ``mcp.server``.

    Raises:
        ImportError: If the optional ``mcp`` package is not installed, or is
            installed at a version that no longer exports ``FastMCP`` from
            ``mcp.server``. The message names the package and the exact install
            command; the originating error is chained as ``__cause__``.
    """
    try:
        from mcp.server import FastMCP
    except ImportError as exc:
        raise ImportError(FASTMCP_IMPORT_ERROR_MESSAGE) from exc

    return FastMCP
