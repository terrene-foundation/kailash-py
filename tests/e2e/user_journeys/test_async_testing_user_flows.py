"""User flow tests for async testing framework - demonstrating developer experience."""

import asyncio
import json
from typing import Any, Dict

import pytest
from kailash.testing import (
    AsyncAssertions,
    AsyncTestUtils,
    AsyncWorkflowFixtures,
    AsyncWorkflowTestCase,
)
from kailash.workflow import AsyncWorkflowBuilder


@pytest.mark.e2e
class TestAsyncTestingUserFlows:
    """End-to-end tests demonstrating developer workflows with the testing framework."""

    @pytest.mark.asyncio
    async def test_new_developer_first_workflow_test(self):
        """Test: New developer writing their first workflow test."""
        # User story: As a new developer, I want to write a simple test for my first workflow
        # Expected: Easy setup, clear API, helpful error messages

        class FirstWorkflowTest(AsyncWorkflowTestCase):
            """A new developer's first test case."""

            async def test_my_first_workflow(self):
                """My first workflow test - should be easy!"""
                # Create a simple workflow
                workflow = (
                    AsyncWorkflowBuilder("hello_world")
                    .add_async_code(
                        "greet",
                        """
try:
    name = name if 'name' in locals() else "World"
except NameError:
    name = "World"
result = {"greeting": f"Hello, {name}!"}
""",
                    )
                    .build()
                )

                # Execute and test
                result = await self.execute_workflow(workflow, {"name": "Developer"})

                # Simple assertions
                self.assert_workflow_success(result)
                self.assert_node_output(
                    result, "greet", "Hello, Developer!", "greeting"
                )

        # This should "just work" for a new developer
        async with FirstWorkflowTest() as test:
            await test.test_my_first_workflow()

    @pytest.mark.asyncio
    async def test_data_engineer_pipeline_testing(self):
        """Test: Data engineer testing a complex ETL pipeline."""
        # User story: As a data engineer, I need to test data pipelines with mocked databases

        class DataPipelineTest(AsyncWorkflowTestCase):
            """Test case for data pipeline engineer."""

            async def setUp(self):
                """Set up test environment with realistic data."""
                await super().setUp()

                # Mock source database with sample data
                self.source_db = await self.create_test_resource(
                    "source_db", None, mock=True
                )

                # Configure realistic sample data
                sample_data = [
                    {
                        "id": 1,
                        "customer_id": "C001",
                        "amount": 150.00,
                        "date": "2023-01-01",
                        "status": "completed",
                    },
                    {
                        "id": 2,
                        "customer_id": "C002",
                        "amount": 75.50,
                        "date": "2023-01-01",
                        "status": "pending",
                    },
                    {
                        "id": 3,
                        "customer_id": "C001",
                        "amount": 200.00,
                        "date": "2023-01-02",
                        "status": "completed",
                    },
                    {
                        "id": 4,
                        "customer_id": "C003",
                        "amount": 95.25,
                        "date": "2023-01-02",
                        "status": "failed",
                    },
                    {
                        "id": 5,
                        "customer_id": "C002",
                        "amount": 300.00,
                        "date": "2023-01-03",
                        "status": "completed",
                    },
                ]
                self.source_db.fetch.return_value = sample_data

                # Mock target warehouse
                self.warehouse_db = await self.create_test_resource(
                    "warehouse_db", None, mock=True
                )
                self.warehouse_db.execute.return_value = None

                # Mock notification service
                self.notification_service = (
                    AsyncWorkflowFixtures.create_mock_http_client()
                )
                self.notification_service.add_response(
                    "POST",
                    "/notifications/slack",
                    {"status": "sent", "message_id": "msg_123"},
                )
                await self.create_test_resource(
                    "notifications", lambda: self.notification_service, mock=True
                )

            async def test_daily_sales_etl_pipeline(self):
                """Test the daily sales ETL pipeline."""
                workflow = (
                    AsyncWorkflowBuilder("daily_sales_etl")
                    .add_async_code(
                        "extract_daily_sales",
                        """
# Extract sales data for a specific date
source_db = await get_resource("source_db")
try:
    target_date = date if 'date' in locals() else None
except NameError:
    target_date = None

sales = await source_db.fetch('''
    SELECT * FROM sales
    WHERE DATE(date) = %s
    ORDER BY id
''', target_date)

result = {
    "raw_sales": [dict(sale) for sale in sales],
    "record_count": len(sales)
}
""",
                    )
                    .add_async_code(
                        "transform_sales_data",
                        """
# Transform and aggregate sales data
transformed_sales = []
customer_totals = {}

for sale in raw_sales:
    # Only process completed sales
    if sale["status"] == "completed":
        customer_id = sale["customer_id"]
        amount = sale["amount"]

        # Track customer totals
        if customer_id not in customer_totals:
            customer_totals[customer_id] = 0
        customer_totals[customer_id] += amount

        # Transform individual record
        transformed_sale = {
            "sale_id": sale["id"],
            "customer_id": customer_id,
            "amount": amount,
            "sale_date": sale["date"],
            "processed_at": "2023-01-04T10:00:00"  # Mock processing time
        }
        transformed_sales.append(transformed_sale)

# Create daily summary
daily_summary = {
    "date": date if 'date' in locals() else None,
    "total_sales": sum(s["amount"] for s in transformed_sales),
    "total_transactions": len(transformed_sales),
    "unique_customers": len(customer_totals),
    "top_customer": max(customer_totals, key=customer_totals.get) if customer_totals else None
}

result = {
    "transformed_sales": transformed_sales,
    "daily_summary": daily_summary,
    "customer_totals": customer_totals
}
""",
                    )
                    .add_async_code(
                        "load_to_warehouse",
                        """
# Load transformed data to warehouse
warehouse_db = await get_resource("warehouse_db")

# Bulk insert sales records
for sale in transformed_sales:
    await warehouse_db.execute('''
        INSERT INTO daily_sales (sale_id, customer_id, amount, sale_date, processed_at)
        VALUES (%s, %s, %s, %s, %s)
    ''',
        sale["sale_id"], sale["customer_id"], sale["amount"],
        sale["sale_date"], sale["processed_at"]
    )

# Insert daily summary
await warehouse_db.execute('''
    INSERT INTO daily_summaries (date, total_sales, total_transactions, unique_customers, top_customer)
    VALUES (%s, %s, %s, %s, %s)
''',
    daily_summary["date"], daily_summary["total_sales"],
    daily_summary["total_transactions"], daily_summary["unique_customers"],
    daily_summary["top_customer"]
)

result = {
    "sales_loaded": len(transformed_sales),
    "summary_loaded": True
}
""",
                    )
                    .add_async_code(
                        "send_completion_notification",
                        """
# Send notification about ETL completion
notifications = await get_resource("notifications")

message = {
    "channel": "#data-team",
    "text": f"Daily ETL completed for {daily_summary['date']}",
    "attachments": [{
        "color": "good",
        "fields": [
            {"title": "Total Sales", "value": f"${daily_summary['total_sales']:.2f}", "short": True},
            {"title": "Transactions", "value": str(daily_summary['total_transactions']), "short": True},
            {"title": "Customers", "value": str(daily_summary['unique_customers']), "short": True}
        ]
    }]
}

resp = await notifications.post("/notifications/slack", json=message)
notification_result = await resp.json()

result = {
    "notification_sent": True,
    "message_id": notification_result.get("message_id")
}
""",
                    )
                    # Connect the pipeline
                    .add_connection(
                        "extract_daily_sales",
                        "raw_sales",
                        "transform_sales_data",
                        "raw_sales",
                    )
                    .add_connection(
                        "transform_sales_data",
                        "transformed_sales",
                        "load_to_warehouse",
                        "transformed_sales",
                    )
                    .add_connection(
                        "transform_sales_data",
                        "daily_summary",
                        "load_to_warehouse",
                        "daily_summary",
                    )
                    .add_connection(
                        "transform_sales_data",
                        "daily_summary",
                        "send_completion_notification",
                        "daily_summary",
                    )
                    .build()
                )

                # Test the pipeline
                result = await self.execute_workflow(workflow, {"date": "2023-01-01"})

                # Comprehensive validation
                self.assert_workflow_success(result)

                # Validate extraction
                extract_result = result.get_output("extract_daily_sales")
                assert extract_result["record_count"] == 2  # Only 2 sales on 2023-01-01

                # Validate transformation
                transform_result = result.get_output("transform_sales_data")
                assert (
                    len(transform_result["transformed_sales"]) == 1
                )  # Only 1 completed sale
                assert transform_result["daily_summary"]["total_sales"] == 150.00
                assert transform_result["daily_summary"]["unique_customers"] == 1

                # Validate loading
                load_result = result.get_output("load_to_warehouse")
                assert load_result["sales_loaded"] == 1
                assert load_result["summary_loaded"] is True

                # Validate notification
                notification_result = result.get_output("send_completion_notification")
                assert notification_result["notification_sent"] is True
                assert notification_result["message_id"] == "msg_123"

                # Verify database operations
                self.assert_resource_called("source_db", "fetch", times=1)
                self.assert_resource_called(
                    "warehouse_db", "execute", times=2
                )  # 1 sale + 1 summary

                # Verify notification was sent
                self.assert_resource_called("notifications", "post", times=1)

        async with DataPipelineTest() as test:
            await test.test_daily_sales_etl_pipeline()

    @pytest.mark.asyncio
    async def test_api_developer_integration_testing(self):
        """Test: API developer testing service integrations."""
        # User story: As an API developer, I need to test integrations with external services

        class APIIntegrationTest(AsyncWorkflowTestCase):
            """Test case for API integration developer."""

            async def setUp(self):
                """Set up mock external services."""
                await super().setUp()

                # Mock payment service
                self.payment_service = AsyncWorkflowFixtures.create_mock_http_client()
                self.payment_service.add_response(
                    "POST",
                    "/charges",
                    {"id": "ch_123", "status": "succeeded", "amount": 2000},
                )

                # Mock email service
                self.email_service = AsyncWorkflowFixtures.create_mock_http_client()
                self.email_service.add_response(
                    "POST", "/send", {"id": "email_456", "status": "queued"}
                )

                # Mock user database
                self.user_db = await self.create_test_resource(
                    "user_db", None, mock=True
                )
                self.user_db.fetchone.return_value = {
                    "id": 1,
                    "email": "user@example.com",
                    "name": "Test User",
                    "plan": "premium",
                }
                self.user_db.execute.return_value = None

                await self.create_test_resource(
                    "payments", lambda: self.payment_service, mock=True
                )
                await self.create_test_resource(
                    "email", lambda: self.email_service, mock=True
                )

            async def test_subscription_upgrade_flow(self):
                """Test the complete subscription upgrade flow."""
                workflow = (
                    AsyncWorkflowBuilder("subscription_upgrade")
                    .add_async_code(
                        "validate_user",
                        """
# Validate user exists and get current plan
user_db = await get_resource("user_db")
try:
    user_id = user_id if 'user_id' in locals() else None
except NameError:
    user_id = None

user = await user_db.fetchone("SELECT * FROM users WHERE id = %s", user_id)
if not user:
    raise ValueError(f"User {user_id} not found")

result = {
    "user": dict(user),
    "current_plan": user["plan"],
    "can_upgrade": user["plan"] != "enterprise"
}
""",
                    )
                    .add_async_code(
                        "process_payment",
                        """
# Process payment for upgrade
if not can_upgrade:
    raise ValueError("User already on highest plan")

payments = await get_resource("payments")
try:
    new_plan = new_plan if 'new_plan' in locals() else None
except NameError:
    new_plan = None

# Calculate price difference
plan_prices = {"basic": 10, "premium": 25, "enterprise": 50}
current_price = plan_prices[current_plan]
new_price = plan_prices[new_plan]
charge_amount = (new_price - current_price) * 100  # Convert to cents

# Process payment
payment_data = {
    "amount": charge_amount,
    "currency": "usd",
    "customer": user["email"],
    "description": f"Upgrade from {current_plan} to {new_plan}"
}

resp = await payments.post("/charges", json=payment_data)
payment_result = await resp.json()

if payment_result["status"] != "succeeded":
    raise ValueError(f"Payment failed: {payment_result}")

result = {
    "payment_id": payment_result["id"],
    "amount_charged": charge_amount,
    "new_plan": new_plan
}
""",
                    )
                    .add_async_code(
                        "update_user_plan",
                        """
# Update user's plan in database
user_db = await get_resource("user_db")

await user_db.execute('''
    UPDATE users
    SET plan = %s, upgraded_at = NOW()
    WHERE id = %s
''', new_plan, user["id"])

result = {
    "user_updated": True,
    "previous_plan": current_plan,
    "new_plan": new_plan
}
""",
                    )
                    .add_async_code(
                        "send_confirmation_email",
                        """
# Send upgrade confirmation email
email = await get_resource("email")

email_data = {
    "to": user["email"],
    "subject": f"Welcome to {new_plan.title()} Plan!",
    "template": "upgrade_confirmation",
    "variables": {
        "user_name": user["name"],
        "old_plan": current_plan,
        "new_plan": new_plan,
        "amount": f"${amount_charged / 100:.2f}"
    }
}

resp = await email.post("/send", json=email_data)
email_result = await resp.json()

result = {
    "email_sent": True,
    "email_id": email_result["id"]
}
""",
                    )
                    # Connect the flow
                    .add_connection("validate_user", "user", "process_payment", "user")
                    .add_connection(
                        "validate_user",
                        "current_plan",
                        "process_payment",
                        "current_plan",
                    )
                    .add_connection(
                        "validate_user", "can_upgrade", "process_payment", "can_upgrade"
                    )
                    .add_connection(
                        "process_payment", "new_plan", "update_user_plan", "new_plan"
                    )
                    .add_connection("validate_user", "user", "update_user_plan", "user")
                    .add_connection(
                        "validate_user",
                        "current_plan",
                        "update_user_plan",
                        "current_plan",
                    )
                    .add_connection(
                        "validate_user", "user", "send_confirmation_email", "user"
                    )
                    .add_connection(
                        "process_payment",
                        "new_plan",
                        "send_confirmation_email",
                        "new_plan",
                    )
                    .add_connection(
                        "validate_user",
                        "current_plan",
                        "send_confirmation_email",
                        "current_plan",
                    )
                    .add_connection(
                        "process_payment",
                        "amount_charged",
                        "send_confirmation_email",
                        "amount_charged",
                    )
                    .build()
                )

                # Test successful upgrade
                result = await self.execute_workflow(
                    workflow, {"user_id": 1, "new_plan": "enterprise"}
                )

                # Validate complete flow
                self.assert_workflow_success(result)

                # Check user validation
                user_result = result.get_output("validate_user")
                assert user_result["current_plan"] == "premium"
                assert user_result["can_upgrade"] is True

                # Check payment processing
                payment_result = result.get_output("process_payment")
                assert payment_result["payment_id"] == "ch_123"
                assert (
                    payment_result["amount_charged"] == 2500
                )  # $25 difference in cents

                # Check database update
                update_result = result.get_output("update_user_plan")
                assert update_result["user_updated"] is True
                assert update_result["new_plan"] == "enterprise"

                # Check email confirmation
                email_result = result.get_output("send_confirmation_email")
                assert email_result["email_sent"] is True
                assert email_result["email_id"] == "email_456"

                # Verify service interactions
                self.assert_resource_called("user_db", "fetchone", times=1)
                self.assert_resource_called("user_db", "execute", times=1)
                self.assert_resource_called("payments", "post", times=1)
                self.assert_resource_called("email", "post", times=1)

            async def test_error_scenarios(self):
                """Test error handling in the subscription flow."""
                # Test invalid user
                with pytest.raises(AssertionError):
                    self.user_db.fetchone.return_value = None  # No user found

                    workflow = (
                        AsyncWorkflowBuilder("upgrade_no_user")
                        .add_async_code(
                            "validate_user",
                            """
user_db = await get_resource("user_db")
user = await user_db.fetchone("SELECT * FROM users WHERE id = %s", user_id if 'user_id' in locals() else None)
if not user:
    raise ValueError("User not found")
result = {"user": dict(user)}
""",
                        )
                        .build()
                    )

                    result = await self.execute_workflow(workflow, {"user_id": 999})
                    self.assert_workflow_success(result)  # This should fail

        async with APIIntegrationTest() as test:
            await test.test_subscription_upgrade_flow()
            await test.test_error_scenarios()

    @pytest.mark.asyncio
    async def test_devops_engineer_monitoring_testing(self):
        """Test: DevOps engineer testing monitoring and alerting workflows."""
        # User story: As a DevOps engineer, I need to test monitoring workflows and alerts

        class MonitoringTest(AsyncWorkflowTestCase):
            """Test case for DevOps monitoring workflows."""

            async def setUp(self):
                """Set up monitoring test environment."""
                await super().setUp()

                # Mock metrics database
                self.metrics_db = await self.create_test_resource(
                    "metrics_db", None, mock=True
                )

                # Mock alert manager
                self.alert_manager = AsyncWorkflowFixtures.create_mock_http_client()
                self.alert_manager.add_response(
                    "POST", "/alerts", {"alert_id": "alert_789", "status": "firing"}
                )

                # Mock Slack notifications
                self.slack = AsyncWorkflowFixtures.create_mock_http_client()
                self.slack.add_response(
                    "POST", "/chat.postMessage", {"ok": True, "ts": "1234567890.123456"}
                )

                await self.create_test_resource(
                    "alerts", lambda: self.alert_manager, mock=True
                )
                await self.create_test_resource("slack", lambda: self.slack, mock=True)

            async def test_system_health_monitoring(self):
                """Test system health monitoring and alerting."""
                # Configure mock metrics showing unhealthy system
                self.metrics_db.fetch.return_value = [
                    {
                        "metric": "cpu_usage",
                        "value": 95.5,
                        "timestamp": "2023-01-01T10:00:00",
                    },
                    {
                        "metric": "memory_usage",
                        "value": 88.2,
                        "timestamp": "2023-01-01T10:00:00",
                    },
                    {
                        "metric": "disk_usage",
                        "value": 78.9,
                        "timestamp": "2023-01-01T10:00:00",
                    },
                    {
                        "metric": "error_rate",
                        "value": 12.3,
                        "timestamp": "2023-01-01T10:00:00",
                    },
                ]

                workflow = (
                    AsyncWorkflowBuilder("system_health_check")
                    .add_async_code(
                        "collect_metrics",
                        """
# Collect latest system metrics
metrics_db = await get_resource("metrics_db")

latest_metrics = await metrics_db.fetch('''
    SELECT metric, value, timestamp
    FROM system_metrics
    WHERE timestamp > NOW() - INTERVAL '5 minutes'
    ORDER BY timestamp DESC
''')

metrics_dict = {m["metric"]: m["value"] for m in latest_metrics}

result = {
    "metrics": metrics_dict,
    "collected_at": "2023-01-01T10:00:00"
}
""",
                    )
                    .add_async_code(
                        "evaluate_health",
                        """
# Evaluate system health against thresholds
thresholds = {
    "cpu_usage": 90.0,
    "memory_usage": 85.0,
    "disk_usage": 80.0,
    "error_rate": 5.0
}

alerts = []
health_score = 100

for metric, threshold in thresholds.items():
    if metric in metrics:
        value = metrics[metric]
        if value > threshold:
            severity = "critical" if value > threshold * 1.1 else "warning"
            alerts.append({
                "metric": metric,
                "value": value,
                "threshold": threshold,
                "severity": severity
            })
            health_score -= 20 if severity == "critical" else 10

overall_status = "healthy" if health_score > 80 else "degraded" if health_score > 50 else "critical"

result = {
    "health_score": health_score,
    "overall_status": overall_status,
    "alerts": alerts,
    "needs_alerting": len(alerts) > 0
}
""",
                    )
                    .add_async_code(
                        "send_alerts",
                        """
# Send alerts if needed
if not needs_alerting:
    result = {"alerts_sent": 0}
else:
    alerts_api = await get_resource("alerts")
    slack = await get_resource("slack")

    sent_alerts = []

    for alert in alerts:
        # Send to alert manager
        alert_data = {
            "labels": {
                "alertname": f"High{alert['metric'].replace('_', '').title()}",
                "severity": alert["severity"],
                "instance": "prod-server-01"
            },
            "annotations": {
                "summary": f"{alert['metric']} is {alert['value']:.1f}% (threshold: {alert['threshold']:.1f}%)",
                "description": f"System {alert['metric']} has exceeded threshold"
            }
        }

        resp = await alerts_api.post("/alerts", json=[alert_data])
        alert_result = await resp.json()

        sent_alerts.append({
            "metric": alert["metric"],
            "alert_id": alert_result["alert_id"],
            "severity": alert["severity"]
        })

    # Send Slack notification for critical alerts
    critical_alerts = [a for a in alerts if a["severity"] == "critical"]
    if critical_alerts:
        slack_message = {
            "channel": "#alerts",
            "text": f":rotating_light: CRITICAL: System health degraded",
            "attachments": [{
                "color": "danger",
                "fields": [
                    {
                        "title": alert["metric"].replace("_", " ").title(),
                        "value": f"{alert['value']:.1f}% (threshold: {alert['threshold']:.1f}%)",
                        "short": True
                    } for alert in critical_alerts
                ]
            }]
        }

        await slack.post("/chat.postMessage", json=slack_message)

    result = {
        "alerts_sent": len(sent_alerts),
        "critical_alerts": len(critical_alerts),
        "slack_notified": len(critical_alerts) > 0,
        "sent_alerts": sent_alerts
    }
""",
                    )
                    # Connect monitoring flow
                    .add_connection(
                        "collect_metrics", "metrics", "evaluate_health", "metrics"
                    )
                    .add_connection(
                        "evaluate_health", "alerts", "send_alerts", "alerts"
                    )
                    .add_connection(
                        "evaluate_health",
                        "needs_alerting",
                        "send_alerts",
                        "needs_alerting",
                    )
                    .build()
                )

                # Test monitoring workflow
                result = await self.execute_workflow(workflow, {})

                # Validate monitoring results
                self.assert_workflow_success(result)

                # Check metrics collection
                metrics_result = result.get_output("collect_metrics")
                assert "cpu_usage" in metrics_result["metrics"]
                assert metrics_result["metrics"]["cpu_usage"] == 95.5

                # Check health evaluation
                health_result = result.get_output("evaluate_health")
                assert (
                    health_result["overall_status"] == "critical"
                )  # Multiple high metrics
                assert (
                    len(health_result["alerts"]) >= 2
                )  # CPU and error_rate over threshold

                # Check alerting
                alert_result = result.get_output("send_alerts")
                assert alert_result["alerts_sent"] >= 2
                assert alert_result["critical_alerts"] >= 1  # CPU usage is critical
                assert alert_result["slack_notified"] is True

                # Verify integrations
                self.assert_resource_called("metrics_db", "fetch", times=1)
                self.assert_resource_called(
                    "alerts", "post", times=alert_result["alerts_sent"]
                )
                self.assert_resource_called(
                    "slack", "post", times=1
                )  # One slack notification

        async with MonitoringTest() as test:
            await test.test_system_health_monitoring()
