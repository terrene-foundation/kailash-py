"""Trust package for Nexus EATP (Extensible Agent Trust Protocol) support.

This package provides components for extracting and managing trust context
from EATP headers in HTTP requests, enabling agent-to-agent trust propagation.

Components:
    - EATPHeaderExtractor: Extracts EATP headers from HTTP requests
    - ExtractedEATPContext: Structured representation of extracted EATP headers
    - TrustMiddleware: ASGI middleware for trust verification
    - TrustMiddlewareConfig: Configuration for TrustMiddleware
    - MCPEATPHandler: Handler for MCP calls with EATP trust integration
    - MCPEATPContext: Context for MCP calls between agents
    - SessionTrustContext: Session-level trust context
    - TrustContextPropagator: Session trust management
    - get_current_session_trust: Get current session trust from context variable
    - set_current_session_trust: Set current session trust in context variable

Usage:
    # Header extraction
    from nexus.trust import EATPHeaderExtractor, ExtractedEATPContext

    extractor = EATPHeaderExtractor()
    context = extractor.extract(request.headers)

    if context.is_valid():
        # Valid EATP context with trace_id and agent_id
        ...

    if context.has_human_origin():
        # Request has verified human origin
        ...

    # Middleware usage
    from nexus.trust import TrustMiddleware, TrustMiddlewareConfig
    from starlette.applications import Starlette

    config = TrustMiddlewareConfig(
        mode="enforcing",
        exempt_paths=["/health", "/metrics"],
        require_human_origin=True,
    )
    app = Starlette(routes=routes)
    app.add_middleware(TrustMiddleware, config=config)

    # MCP + EATP integration
    from nexus.trust import MCPEATPHandler, MCPEATPContext

    handler = MCPEATPHandler()
    context = await handler.prepare_mcp_call(
        calling_agent="agent-a",
        target_agent="agent-b",
        tool_name="search_documents",
        mcp_session_id="session-123",
    )
    is_valid = await handler.verify_mcp_response(context, response)

    # Session trust management
    from nexus.trust import (
        SessionTrustContext,
        TrustContextPropagator,
        get_current_session_trust,
        set_current_session_trust,
    )

    propagator = TrustContextPropagator(default_ttl_hours=8.0)
    session = await propagator.create_session(
        human_origin={"user_id": "user-123"},
    )
    set_current_session_trust(session)
"""

from nexus.trust.headers import EATPHeaderExtractor, ExtractedEATPContext
from nexus.trust.mcp_handler import MCPEATPContext, MCPEATPHandler
from nexus.trust.middleware import TrustMiddleware, TrustMiddlewareConfig
from nexus.trust.session import (
    SessionTrustContext,
    TrustContextPropagator,
    get_current_session_trust,
    set_current_session_trust,
)

__all__ = [
    "EATPHeaderExtractor",
    "ExtractedEATPContext",
    "MCPEATPContext",
    "MCPEATPHandler",
    "SessionTrustContext",
    "TrustContextPropagator",
    "TrustMiddleware",
    "TrustMiddlewareConfig",
    "get_current_session_trust",
    "set_current_session_trust",
]
