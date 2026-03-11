"""Validation test for Migration Guide Pattern 2: Multi-Step Workflow with Validation.

Validates that the handler pattern from the migration guide runs correctly
with real infrastructure (NO MOCKING).

Pattern 2 demonstrates: ~70 lines legacy -> ~35 lines handler (50% reduction).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../src"))

from datetime import datetime

from kailash.nodes.handler import make_handler_workflow
from kailash.runtime import AsyncLocalRuntime

# --- Handler function from migration guide Pattern 2 ---


async def create_order(customer_id: str, items: list) -> dict:
    """Create a new order with automatic tax calculation."""
    if not customer_id:
        raise ValueError("customer_id is required")
    if not items or len(items) == 0:
        raise ValueError("Order must have at least one item")

    # Validate items
    validated_items = []
    for item in items:
        if "product_id" not in item:
            raise ValueError("Each item must have product_id")
        if "quantity" not in item or item["quantity"] < 1:
            raise ValueError("Each item must have quantity >= 1")
        validated_items.append(
            {
                "product_id": item["product_id"],
                "quantity": int(item["quantity"]),
                "price": float(item.get("price", 0)),
            }
        )

    # Calculate totals
    subtotal = sum(item["quantity"] * item["price"] for item in validated_items)
    tax = subtotal * 0.08
    total = subtotal + tax

    # Create order
    order = {
        "order_id": f'ORD-{datetime.now().strftime("%Y%m%d%H%M%S")}',
        "customer_id": customer_id,
        "items": validated_items,
        "subtotal": round(subtotal, 2),
        "tax": round(tax, 2),
        "total": round(total, 2),
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    }

    return {"order": order}


# --- Tests ---


class TestPattern2MultiStep:
    """Validate Pattern 2: Multi-Step Workflow with Validation."""

    @pytest.mark.asyncio
    async def test_handler_creates_order(self):
        """Handler creates order with correct tax calculation."""
        workflow = make_handler_workflow(create_order, "handler")
        runtime = AsyncLocalRuntime()

        items = [
            {"product_id": "PROD-1", "quantity": 2, "price": 10.00},
            {"product_id": "PROD-2", "quantity": 1, "price": 25.00},
        ]

        results, run_id = await runtime.execute_workflow_async(
            workflow, inputs={"customer_id": "CUST-001", "items": items}
        )

        assert run_id is not None
        handler_result = next(iter(results.values()), {})
        order = handler_result["order"]

        assert order["customer_id"] == "CUST-001"
        assert order["subtotal"] == 45.00
        assert order["tax"] == 3.60
        assert order["total"] == 48.60
        assert order["status"] == "pending"
        assert len(order["items"]) == 2
        assert order["order_id"].startswith("ORD-")

    @pytest.mark.asyncio
    async def test_handler_validates_customer_id(self):
        """Handler rejects missing customer_id."""
        workflow = make_handler_workflow(create_order, "handler")
        runtime = AsyncLocalRuntime()

        with pytest.raises(Exception, match="customer_id is required"):
            await runtime.execute_workflow_async(
                workflow,
                inputs={
                    "customer_id": "",
                    "items": [{"product_id": "P1", "quantity": 1}],
                },
            )

    @pytest.mark.asyncio
    async def test_handler_validates_empty_items(self):
        """Handler rejects empty items list."""
        workflow = make_handler_workflow(create_order, "handler")
        runtime = AsyncLocalRuntime()

        with pytest.raises(Exception, match="at least one item"):
            await runtime.execute_workflow_async(
                workflow, inputs={"customer_id": "CUST-001", "items": []}
            )

    @pytest.mark.asyncio
    async def test_handler_validates_item_product_id(self):
        """Handler rejects items without product_id."""
        workflow = make_handler_workflow(create_order, "handler")
        runtime = AsyncLocalRuntime()

        with pytest.raises(Exception, match="product_id"):
            await runtime.execute_workflow_async(
                workflow,
                inputs={
                    "customer_id": "CUST-001",
                    "items": [{"quantity": 1}],
                },
            )

    @pytest.mark.asyncio
    async def test_handler_validates_item_quantity(self):
        """Handler rejects items with invalid quantity."""
        workflow = make_handler_workflow(create_order, "handler")
        runtime = AsyncLocalRuntime()

        with pytest.raises(Exception, match="quantity >= 1"):
            await runtime.execute_workflow_async(
                workflow,
                inputs={
                    "customer_id": "CUST-001",
                    "items": [{"product_id": "P1", "quantity": 0}],
                },
            )

    @pytest.mark.asyncio
    async def test_handler_zero_price_order(self):
        """Handler handles items with no price (defaults to 0)."""
        workflow = make_handler_workflow(create_order, "handler")
        runtime = AsyncLocalRuntime()

        results, _ = await runtime.execute_workflow_async(
            workflow,
            inputs={
                "customer_id": "CUST-002",
                "items": [{"product_id": "FREE-1", "quantity": 1}],
            },
        )

        handler_result = next(iter(results.values()), {})
        order = handler_result["order"]
        assert order["subtotal"] == 0.0
        assert order["tax"] == 0.0
        assert order["total"] == 0.0
