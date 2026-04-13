"""MCP (Model Context Protocol) integration for Nexus.

.. deprecated::
    The Nexus-specific MCP server (``MCPServer``, ``SimpleMCPClient``,
    ``WebSocketServerTransport``, ``WebSocketClientTransport``) has been
    replaced by the unified ``kailash-platform`` MCP server at
    ``kailash_mcp.platform_server``.  These classes have been removed.

    To start the new platform server::

        kailash-mcp --project-root .

    Or in Python::

        from kailash_mcp.platform_server import create_platform_server
        server = create_platform_server()
"""

__all__: list[str] = []
