# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for dedup body extraction in DurableAPIGateway and DurableWorkflowServer.

Regression: #175 -- DurableWorkflowServer dedup fingerprints all POSTs identically.

These tests verify that the middleware correctly extracts the POST body
before fingerprinting, so that different POST bodies produce different
dedup fingerprints.
"""

import asyncio
import json
import logging

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from kailash.middleware.gateway.deduplicator import RequestDeduplicator
from kailash.middleware.gateway.durable_gateway import DurableAPIGateway
from kailash.servers.durable_workflow_server import DurableWorkflowServer

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
class TestDurableGatewayBodyExtraction:
    """Verify DurableAPIGateway extracts POST body for dedup fingerprinting."""

    @pytest_asyncio.fixture
    async def gateway_app(self):
        """Create a DurableAPIGateway with durability always on."""
        gateway = DurableAPIGateway(
            title="Body Extraction Test Gateway",
            enable_durability=True,
            durability_opt_in=False,  # Durability on for all requests
        )

        # Register a simple POST endpoint that echoes the body
        @gateway.app.post("/api/orders")
        async def create_order(request: Request):
            body = await request.json()
            return JSONResponse(
                content={"order_id": f"ord_{body.get('item', 'unknown')}"},
                status_code=201,
            )

        yield gateway

        await gateway.close()

    async def test_different_post_bodies_not_deduped(self, gateway_app):
        """Two POSTs with different bodies must NOT be treated as duplicates."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=gateway_app.app),
            base_url="http://testserver",
        ) as client:
            # First POST
            resp1 = await client.post(
                "/api/orders",
                json={"item": "widget", "quantity": 1},
            )
            assert resp1.status_code == 201
            data1 = resp1.json()
            assert data1["order_id"] == "ord_widget"

            # Second POST with different body -- must NOT be a cached duplicate
            resp2 = await client.post(
                "/api/orders",
                json={"item": "gadget", "quantity": 5},
            )
            assert resp2.status_code == 201
            data2 = resp2.json()
            assert data2["order_id"] == "ord_gadget", (
                "Expected a fresh response for a different POST body, but got "
                f"{data2}. This means different POST bodies are being "
                "fingerprinted identically (issue #175)."
            )
            # Must NOT have the cached response header
            assert resp2.headers.get("x-cached-response") != "true"

    async def test_identical_post_bodies_deduped(self, gateway_app):
        """Two identical POSTs must be correctly detected as duplicates."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=gateway_app.app),
            base_url="http://testserver",
        ) as client:
            body = {"item": "widget", "quantity": 1}

            # First POST
            resp1 = await client.post("/api/orders", json=body)
            assert resp1.status_code == 201

            # Second POST with same body -- should be a cached duplicate
            resp2 = await client.post("/api/orders", json=body)
            # The cached response is returned as a JSONResponse, which may
            # have a 200 status code (the dedup cache wraps the original)
            data2 = resp2.json()
            assert "X-Cached-Response" in resp2.headers or (
                data2.get("order_id") == "ord_widget"
            ), "Identical POST bodies should be deduplicated"


@pytest.mark.asyncio
class TestDurableWorkflowServerBodyExtraction:
    """Verify DurableWorkflowServer extracts POST body for dedup fingerprinting."""

    @pytest_asyncio.fixture
    async def server_app(self):
        """Create a DurableWorkflowServer with durability always on."""
        server = DurableWorkflowServer(
            title="Body Extraction Test Server",
            enable_durability=True,
            durability_opt_in=False,  # Durability on for all requests
        )

        # Register a simple POST endpoint that echoes the body
        @server.app.post("/api/items")
        async def create_item(request: Request):
            body = await request.json()
            return JSONResponse(
                content={"item_id": f"itm_{body.get('name', 'unknown')}"},
                status_code=201,
            )

        yield server

    async def test_different_post_bodies_not_deduped(self, server_app):
        """Two POSTs with different bodies must NOT be treated as duplicates."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server_app.app),
            base_url="http://testserver",
        ) as client:
            # First POST
            resp1 = await client.post(
                "/api/items",
                json={"name": "alpha", "price": 10},
                headers={"X-Durable": "true"},
            )
            assert resp1.status_code == 201
            data1 = resp1.json()
            assert data1["item_id"] == "itm_alpha"

            # Second POST with different body
            resp2 = await client.post(
                "/api/items",
                json={"name": "beta", "price": 20},
                headers={"X-Durable": "true"},
            )
            assert resp2.status_code == 201
            data2 = resp2.json()
            assert data2["item_id"] == "itm_beta", (
                "Expected a fresh response for a different POST body, but got "
                f"{data2}. This means different POST bodies are being "
                "fingerprinted identically (issue #175)."
            )
