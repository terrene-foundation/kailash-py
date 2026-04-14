# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
A2A HTTP Service.

Nexus-based HTTP service implementing the A2A protocol with EATP
trust extensions for secure agent-to-agent communication.

Endpoints:
- GET /.well-known/agent.json - Agent Card (public)
- POST /a2a/jsonrpc - JSON-RPC 2.0 handler
- GET /health - Health check

Example:
    >>> from kailash.trust.a2a import A2AService
    >>> service = A2AService(
    ...     trust_operations=trust_ops,
    ...     agent_id="agent-001",
    ...     agent_name="Data Analyzer",
    ...     agent_version="1.0.0",
    ...     private_key=private_key,
    ... )
    >>> app = service.create_app()
    >>> # Run with uvicorn: uvicorn app:app --host 0.0.0.0 --port 8000
"""

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from nexus import JSONResponse, Nexus, Request, Response

from kailash.trust.a2a.agent_card import AgentCardCache, AgentCardGenerator
from kailash.trust.a2a.auth import A2AAuthenticator, extract_token_from_header
from kailash.trust.a2a.exceptions import (
    A2AError,
    AuthenticationError,
    JsonRpcParseError,
)
from kailash.trust.a2a.jsonrpc import A2AMethodHandlers, JsonRpcHandler
from kailash.trust.a2a.models import AgentCard, JsonRpcRequest, JsonRpcResponse
from kailash.trust.operations import TrustOperations

logger = logging.getLogger(__name__)


class A2AService:
    """
    A2A HTTP Service implementation.

    Provides a Nexus application with A2A protocol endpoints
    including Agent Card serving and JSON-RPC handling.

    Example:
        >>> service = A2AService(
        ...     trust_operations=trust_ops,
        ...     agent_id="agent-001",
        ...     agent_name="My Agent",
        ...     agent_version="1.0.0",
        ...     private_key=private_key,
        ...     capabilities=["analyze", "report"],
        ... )
        >>> app = service.create_app()
    """

    def __init__(
        self,
        trust_operations: TrustOperations,
        agent_id: str,
        agent_name: str,
        agent_version: str,
        private_key: str,
        capabilities: Optional[List[str]] = None,
        description: Optional[str] = None,
        base_url: Optional[str] = None,
        cors_origins: Optional[List[str]] = None,
        card_cache_ttl: int = 300,
    ):
        """
        Initialize the A2A service.

        Args:
            trust_operations: TrustOperations for trust methods.
            agent_id: This agent's unique identifier.
            agent_name: Human-readable agent name.
            agent_version: Agent version string.
            private_key: Base64-encoded Ed25519 private key.
            capabilities: List of agent capabilities.
            description: Optional agent description.
            base_url: Base URL for the service (for endpoint URLs in Agent Card).
            cors_origins: Allowed CORS origins (default: ["*"]).
            card_cache_ttl: Agent Card cache TTL in seconds (default: 5 minutes).
        """
        self._trust_ops = trust_operations
        self._agent_id = agent_id
        self._agent_name = agent_name
        self._agent_version = agent_version
        self._private_key = private_key
        self._capabilities = capabilities or []
        self._description = description
        self._base_url = base_url
        self._cors_origins = cors_origins or []

        # Initialize components
        self._card_generator = AgentCardGenerator(
            trust_operations=trust_operations,
            base_url=base_url,
        )
        self._card_cache = AgentCardCache(ttl_seconds=card_cache_ttl)
        self._authenticator = A2AAuthenticator(
            trust_operations=trust_operations,
            agent_id=agent_id,
            private_key=private_key,
        )
        self._jsonrpc_handler = JsonRpcHandler()

        # Register default method handlers
        self._method_handlers = A2AMethodHandlers(
            trust_operations=trust_operations,
            agent_id=agent_id,
            capabilities=self._capabilities,
        )
        self._method_handlers.register_all(self._jsonrpc_handler)

        # Track startup time for health checks
        self._started_at: Optional[datetime] = None

    def create_app(self) -> Any:
        """
        Create the Nexus application.

        Returns:
            The underlying ASGI application (FastAPI), compatible with
            uvicorn and TestClient.
        """
        nexus_app = Nexus(
            cors_origins=self._cors_origins,
            cors_allow_methods=["*"],
            cors_allow_headers=["*"],
            cors_allow_credentials=True,
        )

        # Register routes
        self._register_routes(nexus_app)

        # Add startup/shutdown handlers via the underlying ASGI app
        fastapi_app = nexus_app.fastapi_app

        @fastapi_app.on_event("startup")
        async def startup():
            self._started_at = datetime.now(timezone.utc)
            logger.info("a2a_service.started", extra={"agent_id": self._agent_id})

        @fastapi_app.on_event("shutdown")
        async def shutdown():
            logger.info("a2a_service.shutdown", extra={"agent_id": self._agent_id})

        return fastapi_app

    def _register_routes(self, app: Nexus) -> None:
        """Register all routes on the Nexus app."""

        @app.endpoint("/a2a/health", methods=["GET"])
        async def health_check():
            """Health check endpoint."""
            return {
                "status": "healthy",
                "agent_id": self._agent_id,
                "version": self._agent_version,
                "started_at": (
                    self._started_at.isoformat() if self._started_at else None
                ),
            }

        @app.endpoint("/.well-known/agent.json", methods=["GET"])
        async def get_agent_card(request: Request):
            """
            Serve the Agent Card.

            Returns the agent's public identity including capabilities
            and EATP trust extensions. Supports ETag caching.
            """
            # Try cache first
            card = self._card_cache.get(self._agent_id)

            if not card:
                # Generate new card
                card = await self._card_generator.generate(
                    agent_id=self._agent_id,
                    name=self._agent_name,
                    version=self._agent_version,
                    description=self._description,
                )
                self._card_cache.set(self._agent_id, card)

            # Compute ETag
            etag = f'"{card.compute_etag()}"'

            # Check If-None-Match for conditional GET
            if_none_match = request.headers.get("if-none-match")
            if if_none_match and if_none_match == etag:
                return Response(status_code=304)

            # Return card with caching headers
            return JSONResponse(
                content=card.to_dict(),
                headers={
                    "ETag": etag,
                    "Cache-Control": "public, max-age=300",
                },
            )

        @app.endpoint("/a2a/jsonrpc", methods=["POST"])
        async def jsonrpc_handler(request: Request):
            """
            Handle JSON-RPC 2.0 requests.

            All A2A method calls go through this endpoint.
            Protected methods require Bearer token authentication.
            """
            try:
                # Get raw body
                body = await request.body()

                # Extract auth token from Authorization header
                authorization = request.headers.get("authorization")
                auth_token = extract_token_from_header(authorization)

                # Handle request
                response = await self._jsonrpc_handler.handle(body, auth_token)

                return JSONResponse(content=response.to_dict())

            except JsonRpcParseError as e:
                return JSONResponse(
                    content=JsonRpcResponse.create_error(
                        None, e.code, e.message, e.data
                    ).to_dict(),
                    status_code=400,
                )

        @app.endpoint("/a2a/jsonrpc/batch", methods=["POST"])
        async def jsonrpc_batch_handler(request: Request):
            """
            Handle batch JSON-RPC 2.0 requests.

            Accepts an array of JSON-RPC requests and returns
            an array of responses.
            """
            try:
                body = await request.body()
                authorization = request.headers.get("authorization")
                auth_token = extract_token_from_header(authorization)

                responses = await self._jsonrpc_handler.handle_batch(body, auth_token)

                return JSONResponse(content=[r.to_dict() for r in responses])

            except JsonRpcParseError as e:
                return JSONResponse(
                    content=JsonRpcResponse.create_error(
                        None, e.code, e.message, e.data
                    ).to_dict(),
                    status_code=400,
                )

    def register_method(
        self,
        name: str,
        handler,
    ) -> None:
        """
        Register a custom JSON-RPC method.

        Args:
            name: Method name (e.g., "custom.method").
            handler: Async function to handle the method.
        """
        self._jsonrpc_handler.register_method(name, handler)

    def invalidate_card_cache(self) -> None:
        """Invalidate the Agent Card cache."""
        self._card_cache.invalidate(self._agent_id)

    @property
    def authenticator(self) -> A2AAuthenticator:
        """Get the authenticator for creating tokens."""
        return self._authenticator


def create_a2a_app(
    trust_operations: TrustOperations,
    agent_id: str,
    agent_name: str,
    agent_version: str,
    private_key: str,
    capabilities: Optional[List[str]] = None,
    **kwargs,
) -> Any:
    """
    Convenience function to create an A2A app.

    Args:
        trust_operations: TrustOperations instance.
        agent_id: Agent identifier.
        agent_name: Agent name.
        agent_version: Agent version.
        private_key: Ed25519 private key.
        capabilities: Agent capabilities.
        **kwargs: Additional arguments for A2AService.

    Returns:
        ASGI application compatible with uvicorn and TestClient.
    """
    service = A2AService(
        trust_operations=trust_operations,
        agent_id=agent_id,
        agent_name=agent_name,
        agent_version=agent_version,
        private_key=private_key,
        capabilities=capabilities,
        **kwargs,
    )
    return service.create_app()
