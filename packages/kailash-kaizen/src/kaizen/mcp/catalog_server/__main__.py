from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Entry point for ``python -m kaizen.mcp.catalog_server``."""

import logging
import sys

from kaizen.mcp.catalog_server.server import CatalogMCPServer


def main() -> None:
    """Run the Catalog MCP server on stdio."""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    server = CatalogMCPServer()
    server.serve_stdio()


if __name__ == "__main__":
    main()
