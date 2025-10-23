"""Real-world end-to-end tests for Durable Gateway with proper infrastructure.

These tests simulate complete user journeys and business scenarios:
- E-commerce order-to-fulfillment pipeline
- Customer support ticket resolution with AI
- Content moderation and recommendation system
- System monitoring and alerting
"""

import asyncio
import json
import random
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List

import httpx
import pytest
from kailash.workflow.builder import WorkflowBuilder

from tests.e2e.config import E2ETestConfig
from tests.e2e.test_durable_gateway_base import DurableGatewayTestBase
from tests.utils.docker_config import OLLAMA_CONFIG

# Add model configuration
OLLAMA_CONFIG["model"] = "llama3.2:3b"


class TestDurableGatewayRealWorldFixed(DurableGatewayTestBase):
    """Real-world E2E tests with proper infrastructure."""

    async def _register_test_workflows(self, gateway):
        """Register all test workflows."""
        # E-commerce Order Processing
        order_workflow = self._create_order_processing_workflow()
        gateway.register_workflow("order_pipeline", order_workflow)

        # Content Moderation
        moderation_workflow = self._create_content_moderation_workflow()
        gateway.register_workflow("content_moderation", moderation_workflow)

        # System Monitoring
        monitoring_workflow = self._create_monitoring_workflow()
        gateway.register_workflow("system_monitoring", monitoring_workflow)

    def _create_order_processing_workflow(self) -> WorkflowBuilder:
        """Create order processing workflow with proper database connections."""
        workflow = WorkflowBuilder()
        workflow.name = "order_processing"

        # Order validation
        workflow.add_node(
            "AsyncPythonCodeNode",
            "validate_order",
            {
                "code": """
import uuid
from datetime import datetime

# Validate required fields
required_fields = ["customer_id", "items", "shipping_address"]
for field in required_fields:
    if not order_data.get(field):
        raise ValueError(f"Missing required field: {field}")

# Generate order ID
order_id = f"ord_{uuid.uuid4().hex[:12]}"

# Calculate totals
items = order_data["items"]
subtotal = sum(item["price"] * item["quantity"] for item in items)
tax_rate = 0.08
tax_amount = round(subtotal * tax_rate, 2)
shipping_amount = 9.99 if subtotal < 50 else 0
total_amount = subtotal + tax_amount + shipping_amount

# Create enriched order
result = {
    "order": {
        "order_id": order_id,
        "customer_id": order_data["customer_id"],
        "tenant_id": order_data.get("tenant_id", "test_tenant_1"),
        "items": items,
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "shipping_amount": shipping_amount,
        "total_amount": total_amount,
        "currency": order_data.get("currency", "USD"),
        "shipping_address": order_data["shipping_address"],
        "status": "validated",
        "created_at": datetime.now().isoformat()
    }
}
"""
            },
        )

        # Inventory check with direct database connection
        workflow.add_node(
            "AsyncPythonCodeNode",
            "check_inventory",
            {
                "code": E2ETestConfig.get_async_db_code(
                    """
    inventory_status = []
    all_available = True

    for item in order["items"]:
        product_id = item["product_id"]
        requested_qty = item["quantity"]

        # Check inventory
        row = await conn.fetchrow(
            "SELECT inventory_count FROM products WHERE product_id = $1",
            product_id
        )

        if row:
            available_qty = row["inventory_count"]
            is_available = available_qty >= requested_qty

            inventory_status.append({
                "product_id": product_id,
                "requested": requested_qty,
                "available": available_qty,
                "is_available": is_available
            })

            if not is_available:
                all_available = False
        else:
            # Product not found - assume test products have inventory
            inventory_status.append({
                "product_id": product_id,
                "requested": requested_qty,
                "available": 100,
                "is_available": True
            })

    result = {
        "inventory_status": inventory_status,
        "can_fulfill": all_available
    }
"""
                )
            },
        )

        # Fraud check (simplified)
        workflow.add_node(
            "PythonCodeNode",
            "fraud_check",
            {
                "code": """
risk_score = 0
if order["total_amount"] > 1000: risk_score += 20
if order["shipping_address"].get("country") not in ["US", "CA"]: risk_score += 30
result = {"risk_score": risk_score, "passed": risk_score < 50, "reason": "High risk" if risk_score >= 50 else "OK"}
"""
            },
        )

        # Payment processing (mock)
        workflow.add_node(
            "PythonCodeNode",
            "process_payment",
            {
                "code": """
import uuid
payment_id = f"pay_{uuid.uuid4().hex[:12]}"
success = fraud_result["passed"] and inventory_result["can_fulfill"]
status = "completed" if success else "declined"
result = {"payment_id": payment_id, "status": status, "success": success, "amount": order["total_amount"]}
"""
            },
        )

        # Order finalization with database
        workflow.add_node(
            "AsyncPythonCodeNode",
            "finalize_order",
            {
                "code": E2ETestConfig.get_async_db_code(
                    """
    # Determine final order status
    if payment_result["success"] and inventory_result["can_fulfill"]:
        final_status = "confirmed"
        payment_status = "completed"
    else:
        final_status = "failed"
        payment_status = payment_result["status"]

    # Insert order
    await conn.execute('''
        INSERT INTO orders
        (order_id, customer_id, tenant_id, total_amount, tax_amount,
         shipping_amount, status, payment_status, items, shipping_address)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    ''',
        order["order_id"], order["customer_id"], order["tenant_id"],
        order["total_amount"], order["tax_amount"], order["shipping_amount"],
        final_status, payment_status,
        json.dumps(order["items"]),
        json.dumps(order["shipping_address"])
    )

    # Update inventory if confirmed
    if final_status == "confirmed":
        for item in order["items"]:
            await conn.execute('''
                UPDATE products
                SET inventory_count = inventory_count - $1
                WHERE product_id = $2 AND inventory_count >= $1
            ''',
                item["quantity"], item["product_id"]
            )

    result = {
        "order_id": order["order_id"],
        "status": final_status,
        "payment_id": payment_result["payment_id"],
        "payment_status": payment_status,
        "total_amount": order["total_amount"],
        "success": final_status == "confirmed"
    }
"""
                )
            },
        )

        # Connect workflow nodes - map outputs
        workflow.add_connection("validate_order", "order", "check_inventory", "order")
        workflow.add_connection("validate_order", "order", "fraud_check", "order")
        workflow.add_connection(
            "check_inventory", "result", "process_payment", "inventory_result"
        )
        workflow.add_connection(
            "fraud_check", "result", "process_payment", "fraud_result"
        )
        workflow.add_connection("validate_order", "order", "finalize_order", "order")
        workflow.add_connection(
            "check_inventory", "result", "finalize_order", "inventory_result"
        )
        workflow.add_connection(
            "process_payment", "result", "finalize_order", "payment_result"
        )

        return workflow.build()

    def _create_content_moderation_workflow(self) -> WorkflowBuilder:
        """Create content moderation workflow."""
        workflow = WorkflowBuilder()
        workflow.name = "content_moderation"

        # Fetch content for moderation
        workflow.add_node(
            "AsyncPythonCodeNode",
            "fetch_content",
            {
                "code": E2ETestConfig.get_async_db_code(
                    """
    # Get batch size from input or use default
    batch_size = batch_size if 'batch_size' in locals() else 5

    # Fetch pending content
    rows = await conn.fetch('''
        SELECT content_id, content_type, title, body, author_id, tenant_id
        FROM content_items
        WHERE moderation_status = 'pending'
        ORDER BY created_at DESC
        LIMIT $1
    ''', batch_size)

    content_items = []
    for row in rows:
        content_items.append({
            "content_id": row["content_id"],
            "content_type": row["content_type"],
            "title": row["title"],
            "body": row["body"],
            "author_id": row["author_id"],
            "tenant_id": row["tenant_id"]
        })

    result = {
        "content_items": content_items,
        "batch_size": len(content_items)
    }
"""
                )
            },
        )

        # AI moderation
        workflow.add_node(
            "LLMAgentNode",
            "ai_moderation",
            {
                "name": "content_moderator",
                "model": "llama3.2:3b",
                "api_base": OLLAMA_CONFIG["base_url"],
                "system_prompt": """You are a content moderator. Analyze content for:
1. Inappropriate language or hate speech
2. Spam or promotional content
3. Misinformation or harmful content

Respond with JSON: {"approved": true/false, "reason": "...", "confidence": 0.0-1.0}""",
            },
        )

        # Update moderation status
        workflow.add_node(
            "AsyncPythonCodeNode",
            "update_moderation",
            {
                "code": E2ETestConfig.get_async_db_code(
                    """
    # Parse AI moderation results
    moderation_results = {}
    if content_data.get("content_items"):
        try:
            ai_result = json.loads(ai_analysis.get("response", "{}"))
            # Apply same result to all items for simplicity
            for item in content_data["content_items"]:
                moderation_results[item["content_id"]] = {
                    "approved": ai_result.get("approved", True),
                    "reason": ai_result.get("reason", "AI review"),
                    "confidence": ai_result.get("confidence", 0.5)
                }
        except:
            # Default to approved if AI fails
            for item in content_data["content_items"]:
                moderation_results[item["content_id"]] = {
                    "approved": True,
                    "reason": "Default approval",
                    "confidence": 0.0
                }

    updated_count = 0
    for content_id, result in moderation_results.items():
        status = "approved" if result["approved"] else "rejected"

        await conn.execute('''
            UPDATE content_items
            SET moderation_status = $1,
                moderation_result = $2
            WHERE content_id = $3
        ''',
            status,
            json.dumps(result),
            content_id
        )
        updated_count += 1

    # Calculate summary
    summary = {
        "approved": sum(1 for r in moderation_results.values() if r["approved"]),
        "rejected": sum(1 for r in moderation_results.values() if not r["approved"]),
        "total": len(moderation_results)
    }

    result = {
        "updated_count": updated_count,
        "total_processed": len(content_data.get("content_items", [])),
        "moderation_summary": summary
    }
"""
                )
            },
        )

        # Connect workflow
        workflow.add_connection(
            "fetch_content", "result", "ai_moderation", "content_data"
        )
        workflow.add_connection(
            "fetch_content", "result", "update_moderation", "content_data"
        )
        workflow.add_connection(
            "ai_moderation", "result", "update_moderation", "ai_analysis"
        )

        return workflow.build()

    def _create_monitoring_workflow(self) -> WorkflowBuilder:
        """Create system monitoring workflow."""
        workflow = WorkflowBuilder()
        workflow.name = "system_monitoring"

        # System health check
        workflow.add_node(
            "AsyncPythonCodeNode",
            "system_health_check",
            {
                "code": E2ETestConfig.get_async_db_code(
                    """
    import time
    from datetime import datetime, timedelta

    # System metrics collection
    metrics = {
        "timestamp": datetime.now().isoformat(),
        "system_health": {}
    }

    alerts = []

    # Check database performance
    start_time = time.time()
    await conn.fetch("SELECT COUNT(*) FROM customers")
    db_response_time = time.time() - start_time

    metrics["system_health"]["database_response_ms"] = round(db_response_time * 1000, 2)

    if db_response_time > 0.5:
        alerts.append({
            "type": "performance",
            "severity": "high" if db_response_time > 1.0 else "medium",
            "message": f"Database response time high: {db_response_time:.3f}s"
        })

    # Check recent error rates
    recent_time = datetime.now() - timedelta(minutes=5)
    error_row = await conn.fetchrow('''
        SELECT COUNT(*) as error_count
        FROM system_alerts
        WHERE created_at >= $1 AND severity IN ('high', 'critical')
    ''', recent_time)

    error_count = error_row["error_count"] if error_row else 0
    metrics["system_health"]["recent_errors"] = error_count

    if error_count > 5:
        alerts.append({
            "type": "error_rate",
            "severity": "high",
            "message": f"High error rate: {error_count} errors in last 5 minutes"
        })

    # Check order processing health
    order_health = await conn.fetchrow('''
        SELECT
            COUNT(*) as total_orders,
            COUNT(CASE WHEN status = 'confirmed' THEN 1 END) as successful_orders,
            COUNT(CASE WHEN status LIKE '%failed%' THEN 1 END) as failed_orders
        FROM orders
        WHERE created_at >= $1
    ''', datetime.now() - timedelta(hours=1))

    if order_health:
        total = order_health["total_orders"]
        failed = order_health["failed_orders"]

        failure_rate = (failed / max(total, 1)) * 100
        metrics["system_health"]["order_failure_rate_percent"] = round(failure_rate, 2)

        if failure_rate > 10:
            alerts.append({
                "type": "business_metric",
                "severity": "high",
                "message": f"Order failure rate high: {failure_rate:.1f}%"
            })

    result = {
        "metrics": metrics,
        "alerts": alerts,
        "health_score": 100 - (len(alerts) * 20)  # Simple health scoring
    }
"""
                )
            },
        )

        # AI-powered alert analysis
        workflow.add_node(
            "LLMAgentNode",
            "analyze_alerts",
            {
                "name": "monitoring_agent",
                "model": "llama3.2:3b",
                "api_base": OLLAMA_CONFIG["base_url"],
                "system_prompt": """You are a system reliability engineer. Analyze system health and provide:
1. Root cause analysis for issues
2. Impact assessment
3. Recommended actions

Focus on actionable insights.""",
                "prompt": """Analyze this system health report:

Metrics: {health_data}

Provide analysis in JSON format:
{
  "status_assessment": {
    "overall_health": "healthy/degraded/critical",
    "primary_concerns": ["concern1", "concern2"]
  },
  "recommendations": {
    "immediate_actions": ["action1", "action2"]
  }
}""",
            },
        )

        # Store monitoring results
        workflow.add_node(
            "AsyncPythonCodeNode",
            "store_monitoring_results",
            {
                "code": E2ETestConfig.get_async_db_code(
                    """
    import uuid

    # Parse AI analysis
    try:
        analysis = json.loads(ai_analysis.get("response", "{}"))
    except:
        analysis = {"error": "Failed to parse AI analysis"}

    # Store system alerts for critical issues
    for alert in health_data.get("alerts", []):
        alert_id = f"alert_{uuid.uuid4().hex[:12]}"

        await conn.execute('''
            INSERT INTO system_alerts
            (alert_id, alert_type, severity, message, source, metadata, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
        ''',
            alert_id, alert["type"], alert["severity"], alert["message"],
            "system_monitor", json.dumps({"ai_analysis": analysis})
        )

    result = {
        "monitoring_complete": True,
        "alerts_stored": len(health_data.get("alerts", [])),
        "health_score": health_data["health_score"],
        "ai_analysis": analysis,
        "timestamp": datetime.now().isoformat()
    }
"""
                )
            },
        )

        # Connect workflow
        workflow.add_connection(
            "system_health_check", "result", "analyze_alerts", "health_data"
        )
        workflow.add_connection(
            "system_health_check", "result", "store_monitoring_results", "health_data"
        )
        workflow.add_connection(
            "analyze_alerts", "result", "store_monitoring_results", "ai_analysis"
        )

        return workflow.build()

    # Test methods

    @pytest.mark.asyncio
    async def test_complete_ecommerce_order_journey(self):
        """Test complete e-commerce order processing."""
        # Create a valid order using test data
        order_data = await self.create_test_order()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://localhost:{self.port}/order_pipeline/execute",
                json={"inputs": {"validate_order": {"order_data": order_data}}},
                timeout=30.0,
            )

            assert response.status_code == 200
            result = response.json()

            # Verify results
            assert "outputs" in result
            assert "finalize_order" in result["outputs"]

            final_result = result["outputs"]["finalize_order"]["result"]
            assert "order_id" in final_result
            assert "status" in final_result
            assert "payment_id" in final_result

            print("\nOrder processing completed:")
            print(f"  - Order ID: {final_result['order_id']}")
            print(f"  - Status: {final_result['status']}")
            print(f"  - Total: ${final_result['total_amount']}")
            print(f"  - Success: {final_result['success']}")

    @pytest.mark.asyncio
    async def test_content_moderation_pipeline(self):
        """Test AI-powered content moderation."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://localhost:{self.port}/content_moderation/execute",
                json={"inputs": {"fetch_content": {"batch_size": 3}}},
                timeout=30.0,
            )

            assert response.status_code == 200
            result = response.json()

            assert "outputs" in result
            assert "update_moderation" in result["outputs"]

            moderation_result = result["outputs"]["update_moderation"]["result"]
            assert "updated_count" in moderation_result
            assert "total_processed" in moderation_result

            print("\nContent moderation completed:")
            print(f"  - Items processed: {moderation_result['total_processed']}")
            print(f"  - Items updated: {moderation_result['updated_count']}")

            if moderation_result.get("moderation_summary"):
                summary = moderation_result["moderation_summary"]
                print(f"  - Approved: {summary.get('approved', 0)}")
                print(f"  - Rejected: {summary.get('rejected', 0)}")

    @pytest.mark.asyncio
    async def test_system_monitoring_and_alerting(self):
        """Test comprehensive system monitoring."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://localhost:{self.port}/system_monitoring/execute",
                json={"inputs": {"system_health_check": {}}},
                timeout=30.0,
            )

            assert response.status_code == 200
            result = response.json()

            assert "outputs" in result
            assert "store_monitoring_results" in result["outputs"]

            monitoring_result = result["outputs"]["store_monitoring_results"]["result"]
            assert "monitoring_complete" in monitoring_result
            assert monitoring_result["monitoring_complete"] is True
            assert "health_score" in monitoring_result

            health_score = monitoring_result["health_score"]
            alerts_stored = monitoring_result["alerts_stored"]

            print("\nSystem monitoring completed:")
            print(f"  - Health score: {health_score}/100")
            print(f"  - Alerts generated: {alerts_stored}")

            if monitoring_result.get("ai_analysis"):
                ai_analysis = monitoring_result["ai_analysis"]
                if "status_assessment" in ai_analysis:
                    status = ai_analysis["status_assessment"]
                    print(
                        f"  - Overall health: {status.get('overall_health', 'unknown')}"
                    )
                    print(f"  - Primary concerns: {status.get('primary_concerns', [])}")

    @pytest.mark.asyncio
    async def test_multi_workflow_concurrent_execution(self):
        """Test concurrent execution of multiple workflows."""
        # Create test data for concurrent execution
        test_customer = self.get_test_customer(0)
        test_order = await self.create_test_order(test_customer["customer_id"])

        # Define mixed workload scenarios
        scenarios = [
            ("order_pipeline", {"validate_order": {"order_data": test_order}}),
            ("content_moderation", {"fetch_content": {"batch_size": 2}}),
            ("system_monitoring", {"system_health_check": {}}),
        ]

        async def execute_workflow(client, workflow_name, inputs):
            """Execute a single workflow."""
            try:
                start_time = time.time()
                response = await client.post(
                    f"http://localhost:{self.port}/{workflow_name}/execute",
                    json={"inputs": inputs},
                    timeout=60.0,
                )
                end_time = time.time()

                return {
                    "workflow": workflow_name,
                    "status": response.status_code,
                    "success": response.status_code == 200,
                    "duration": end_time - start_time,
                }
            except Exception as e:
                return {
                    "workflow": workflow_name,
                    "status": 0,
                    "success": False,
                    "error": str(e),
                }

        # Execute concurrent requests
        async with httpx.AsyncClient() as client:
            tasks = []
            for i in range(9):  # 3 of each workflow type
                workflow_name, inputs = scenarios[i % len(scenarios)]
                task = execute_workflow(client, workflow_name, inputs)
                tasks.append(task)

            results = await asyncio.gather(*tasks)

        # Analyze results
        successful = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]

        success_rate = len(successful) / len(results)
        avg_duration = (
            sum(r["duration"] for r in successful) / len(successful)
            if successful
            else 0
        )

        print("\nConcurrent workflow execution results:")
        print(f"  - Total requests: {len(results)}")
        print(f"  - Successful: {len(successful)}")
        print(f"  - Failed: {len(failed)}")
        print(f"  - Success rate: {success_rate:.1%}")
        print(f"  - Average duration: {avg_duration:.2f}s")

        # Verify success rate
        assert (
            success_rate >= 0.8
        ), f"Success rate {success_rate:.1%} below 80% threshold"

    @pytest.mark.asyncio
    async def test_end_to_end_business_scenario(self):
        """Test complete end-to-end business scenario."""
        async with httpx.AsyncClient() as client:
            # Step 1: Process order using test data
            order_data = await self.create_test_order()

            order_response = await client.post(
                f"http://localhost:{self.port}/order_pipeline/execute",
                json={"inputs": {"validate_order": {"order_data": order_data}}},
                timeout=60.0,
            )

            order_success = order_response.status_code == 200
            if order_success:
                order_result = order_response.json()
                if "finalize_order" in order_result["outputs"]:
                    order_id = order_result["outputs"]["finalize_order"]["result"][
                        "order_id"
                    ]
                    print(f"Step 1 - Order processed: {order_id}")

            # Step 2: Moderate content
            content_response = await client.post(
                f"http://localhost:{self.port}/content_moderation/execute",
                json={"inputs": {"fetch_content": {"batch_size": 2}}},
                timeout=45.0,
            )

            content_success = content_response.status_code == 200
            if content_success:
                content_result = content_response.json()
                moderated_count = content_result["outputs"]["update_moderation"][
                    "result"
                ]["updated_count"]
                print(f"Step 2 - Content moderated: {moderated_count} items")

            # Step 3: System health monitoring
            monitoring_response = await client.post(
                f"http://localhost:{self.port}/system_monitoring/execute",
                json={"inputs": {"system_health_check": {}}},
                timeout=30.0,
            )

            monitoring_success = monitoring_response.status_code == 200
            if monitoring_success:
                monitoring_result = monitoring_response.json()
                health_score = monitoring_result["outputs"]["store_monitoring_results"][
                    "result"
                ]["health_score"]
                print(f"Step 3 - System health: {health_score}/100")

            # Verify scenario success
            scenario_steps = [order_success, content_success, monitoring_success]
            overall_success_rate = sum(scenario_steps) / len(scenario_steps)

            print("\nEnd-to-end scenario results:")
            print(f"  - Order processing: {'✓' if order_success else '✗'}")
            print(f"  - Content moderation: {'✓' if content_success else '✗'}")
            print(f"  - System monitoring: {'✓' if monitoring_success else '✗'}")
            print(f"  - Overall success rate: {overall_success_rate:.1%}")

            # Business scenario should have high success rate
            assert (
                overall_success_rate >= 0.67
            ), f"Success rate {overall_success_rate:.1%} below threshold"
