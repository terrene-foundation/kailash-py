# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Router mounting for governance API.

Provides two ways to use the governance API:
1. mount_governance_api() -- mount on an existing FastAPI app
2. create_governance_app() -- create a standalone FastAPI app (for testing)

Both configure rate limiting, security headers, and the governance router.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from pact.governance.api.auth import GovernanceAuth
from pact.governance.api.endpoints import create_governance_router
from kailash.trust.pact.engine import GovernanceEngine

logger = logging.getLogger(__name__)

__all__ = ["create_governance_app", "mount_governance_api"]


def mount_governance_api(
    app: FastAPI,
    engine: GovernanceEngine,
    auth: GovernanceAuth,
    *,
    rate_limit: str = "60/minute",
) -> None:
    """Mount governance endpoints on an existing FastAPI app.

    The existing app's limiter (from app.state.limiter) is used for
    rate limiting. If no limiter is configured, endpoints are mounted
    without rate limiting.

    Args:
        app: The FastAPI application to mount governance routes on.
        engine: The GovernanceEngine instance.
        auth: The GovernanceAuth instance.
        rate_limit: Rate limit string (e.g., "60/minute"). Applied to
            all governance endpoints.
    """
    limiter = getattr(app.state, "limiter", None)
    router = create_governance_router(engine, auth, limiter=limiter, rate_limit=rate_limit)
    app.include_router(router)

    logger.info(
        "Governance API mounted at /api/v1/governance with rate_limit=%s",
        rate_limit,
    )


def create_governance_app(
    engine: GovernanceEngine,
    auth: GovernanceAuth,
    *,
    rate_limit: str = "60/minute",
) -> FastAPI:
    """Create a standalone FastAPI app with governance endpoints.

    Primarily used for testing. Includes rate limiting and exception handlers.

    Args:
        engine: The GovernanceEngine instance.
        auth: The GovernanceAuth instance.
        rate_limit: Rate limit string (e.g., "60/minute", "2/minute").

    Returns:
        A configured FastAPI application.
    """
    # Rate limiter
    limiter = Limiter(key_func=get_remote_address)

    app = FastAPI(
        title="PACT Governance API",
        description="Governance REST API for D/T/R organizations under PACT",
        version="0.1.0",
    )

    # Attach limiter to app state (required by slowapi)
    app.state.limiter = limiter

    # Rate limit exceeded handler
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded", "detail": str(exc.detail)},
        )

    # SlowAPI middleware
    app.add_middleware(SlowAPIMiddleware)

    # Create and mount the governance router with rate limiting
    router = create_governance_router(engine, auth, limiter=limiter, rate_limit=rate_limit)
    app.include_router(router)

    logger.info(
        "Governance standalone app created with rate_limit=%s",
        rate_limit,
    )

    return app
