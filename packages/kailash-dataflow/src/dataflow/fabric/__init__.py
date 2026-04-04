# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Data Fabric Engine — real-time data products from any source.

The fabric module extends DataFlow from "zero-config database operations"
to "zero-config data operations" by adding:

- Source adapters: connect to external APIs, files, cloud storage, databases, streams
- Products: declarative data transformations that auto-refresh on source changes
- FabricRuntime: orchestrates polling, caching, serving, and observability

Usage::

    db = DataFlow("sqlite:///app.db")

    db.source("crm", RestSourceConfig(url="https://api.example.com", ...))

    @db.product("dashboard", depends_on=["User", "crm"])
    async def dashboard(ctx):
        users = await ctx.express.list("User")
        deals = await ctx.source("crm").fetch("deals")
        return {"users": len(users), "deals": len(deals)}

    await db.start()
"""

from __future__ import annotations

from dataflow.adapters.source_adapter import (
    BaseSourceAdapter,
    CircuitBreakerConfig,
    SourceState,
)
from dataflow.fabric.consumers import ConsumerFn, ConsumerRegistry
from dataflow.fabric.config import (
    ApiKeyAuth,
    BasicAuth,
    BearerAuth,
    CloudSourceConfig,
    DatabaseSourceConfig,
    FileSourceConfig,
    OAuth2Auth,
    ProductMode,
    RateLimit,
    RestSourceConfig,
    StalenessPolicy,
    StreamSourceConfig,
    WebhookConfig,
)

__all__ = [
    # Consumer adapters
    "ConsumerFn",
    "ConsumerRegistry",
    # Adapter base
    "BaseSourceAdapter",
    "SourceState",
    "CircuitBreakerConfig",
    # Config types
    "RestSourceConfig",
    "FileSourceConfig",
    "CloudSourceConfig",
    "DatabaseSourceConfig",
    "StreamSourceConfig",
    "StalenessPolicy",
    "RateLimit",
    "WebhookConfig",
    "ProductMode",
    # Auth types
    "BearerAuth",
    "ApiKeyAuth",
    "OAuth2Auth",
    "BasicAuth",
]
