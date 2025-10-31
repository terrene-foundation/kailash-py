"""Async Testing User Flows E2E Tests

These tests validate critical user scenarios using AsyncWorkflowBuilder
with realistic workflows that cover connection patterns and data flow.

Key functionality tested:
- AsyncWorkflowBuilder connection merging
- Multiple connections between same nodes
- Data path resolution for nested outputs
- Real async execution scenarios
"""

import asyncio
from typing import Any, Dict

import pytest
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow import AsyncWorkflowBuilder

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio, pytest.mark.regression]


class TestAsyncTestingUserFlows:
    """Critical user flow tests for AsyncWorkflowBuilder functionality."""

    async def test_user_flow_health_monitoring_with_multiple_connections(self):
        """Test health monitoring workflow with multiple connections between same nodes.

        This test validates the critical connection merging fix where multiple
        connections between the same pair of nodes must preserve all mappings.
        """
        builder = AsyncWorkflowBuilder("health_monitoring")

        # System health evaluation
        health_check_code = """
import time
import random

# Simulate system health checks
cpu_usage = random.randint(20, 90)
memory_usage = random.randint(30, 95)
disk_usage = random.randint(10, 80)

# Health evaluation logic
alerts = []
if cpu_usage > 80:
    alerts.append(f"High CPU usage: {cpu_usage}%")
if memory_usage > 85:
    alerts.append(f"High memory usage: {memory_usage}%")
if disk_usage > 75:
    alerts.append(f"High disk usage: {disk_usage}%")

# Determine if alerts are needed
needs_alerting = len(alerts) > 0

result = {
    "alerts": alerts,
    "needs_alerting": needs_alerting,
    "cpu_usage": cpu_usage,
    "memory_usage": memory_usage,
    "disk_usage": disk_usage,
    "timestamp": time.time()
}
"""

        # Alert notification system
        alert_code = """
# Process alerts and alerting status
alert_list = alerts if alerts else []
should_alert = needs_alerting if needs_alerting is not None else False

if should_alert and alert_list:
    notifications = []
    for alert in alert_list:
        notifications.append({
            "type": "warning",
            "message": alert,
            "priority": "high" if "High" in alert else "medium"
        })

    result = {
        "notifications_sent": len(notifications),
        "notifications": notifications,
        "alert_status": "active"
    }
else:
    result = {
        "notifications_sent": 0,
        "notifications": [],
        "alert_status": "none"
    }
"""

        # Add nodes
        builder.add_async_code("evaluate_health", health_check_code)
        builder.add_async_code("send_alerts", alert_code)

        # CRITICAL TEST: Add multiple connections between same nodes
        # This tests the connection merging functionality that was fixed
        builder.add_connection(
            "evaluate_health", "result.alerts", "send_alerts", "alerts"
        )
        builder.add_connection(
            "evaluate_health", "result.needs_alerting", "send_alerts", "needs_alerting"
        )

        workflow = builder.build()
        runtime = AsyncLocalRuntime()

        result = await runtime.execute_workflow_async(workflow, {})

        # Verify workflow executed successfully
        assert len(result["errors"]) == 0
        assert "evaluate_health" in result["results"]
        assert "send_alerts" in result["results"]

        # Verify health evaluation
        health_result = result["results"]["evaluate_health"]
        assert "alerts" in health_result
        assert "needs_alerting" in health_result
        assert isinstance(health_result["alerts"], list)
        assert isinstance(health_result["needs_alerting"], bool)

        # Verify alert processing (tests connection merging)
        alert_result = result["results"]["send_alerts"]
        assert "notifications_sent" in alert_result
        assert "alert_status" in alert_result

        # CRITICAL: Verify both connections worked (alerts AND needs_alerting passed)
        if health_result["needs_alerting"]:
            assert alert_result["alert_status"] == "active"
            assert alert_result["notifications_sent"] > 0
        else:
            assert alert_result["alert_status"] == "none"
            assert alert_result["notifications_sent"] == 0

    async def test_user_flow_data_processing_pipeline_with_complex_paths(self):
        """Test data processing pipeline with complex data path connections."""
        builder = AsyncWorkflowBuilder("data_pipeline")

        # Data source simulation
        data_source_code = """
import json

# Simulate realistic data source
raw_data = [
    {"id": 1, "value": 100, "category": "A", "timestamp": "2024-01-01"},
    {"id": 2, "value": 200, "category": "B", "timestamp": "2024-01-02"},
    {"id": 3, "value": 150, "category": "A", "timestamp": "2024-01-03"},
    {"id": 4, "value": 300, "category": "C", "timestamp": "2024-01-04"},
    {"id": 5, "value": 250, "category": "B", "timestamp": "2024-01-05"}
]

# Process raw data
processed_data = []
total_value = 0
categories = set()

for item in raw_data:
    processed_item = {
        "id": item["id"],
        "normalized_value": item["value"] / 100,
        "category": item["category"],
        "processed": True
    }
    processed_data.append(processed_item)
    total_value += item["value"]
    categories.add(item["category"])

result = {
    "processed_records": processed_data,
    "summary": {
        "total_records": len(processed_data),
        "total_value": total_value,
        "unique_categories": list(categories),
        "avg_value": total_value / len(processed_data)
    }
}
"""

        # Analytics processor
        analytics_code = """
# Analyze processed data
records = processed_records if processed_records else []
summary_data = summary if summary else {}

# Perform analytics
category_analysis = {}
for record in records:
    cat = record["category"]
    if cat not in category_analysis:
        category_analysis[cat] = {"count": 0, "total_value": 0}
    category_analysis[cat]["count"] += 1
    category_analysis[cat]["total_value"] += record["normalized_value"]

# Calculate category averages
for cat in category_analysis:
    if category_analysis[cat]["count"] > 0:
        category_analysis[cat]["avg_value"] = (
            category_analysis[cat]["total_value"] / category_analysis[cat]["count"]
        )

result = {
    "category_analysis": category_analysis,
    "insights": {
        "most_common_category": max(category_analysis.keys(), key=lambda x: category_analysis[x]["count"]),
        "highest_avg_category": max(category_analysis.keys(), key=lambda x: category_analysis[x]["avg_value"]),
        "total_categories_analyzed": len(category_analysis)
    },
    "data_quality": {
        "records_processed": len(records),
        "summary_available": bool(summary_data)
    }
}
"""

        # Add nodes
        builder.add_async_code("data_source", data_source_code)
        builder.add_async_code("analytics", analytics_code)

        # Connect with complex paths
        builder.add_connection(
            "data_source", "result.processed_records", "analytics", "processed_records"
        )
        builder.add_connection("data_source", "result.summary", "analytics", "summary")

        workflow = builder.build()
        runtime = AsyncLocalRuntime()

        result = await runtime.execute_workflow_async(workflow, {})

        # Verify execution
        assert len(result["errors"]) == 0
        assert "data_source" in result["results"]
        assert "analytics" in result["results"]

        # Verify data processing
        source_result = result["results"]["data_source"]
        assert len(source_result["processed_records"]) == 5
        assert source_result["summary"]["total_records"] == 5
        assert len(source_result["summary"]["unique_categories"]) == 3

        # Verify analytics (tests complex path connections)
        analytics_result = result["results"]["analytics"]
        assert "category_analysis" in analytics_result
        assert len(analytics_result["category_analysis"]) == 3  # A, B, C
        assert analytics_result["data_quality"]["records_processed"] == 5
        assert analytics_result["data_quality"]["summary_available"] is True

    async def test_user_flow_async_task_coordination(self):
        """Test async task coordination with concurrent processing."""
        builder = AsyncWorkflowBuilder("task_coordination")

        # Task generator
        task_generator_code = '''
import asyncio
import time

async def generate_tasks():
    """Generate multiple async tasks."""
    tasks = []
    for i in range(5):
        task = {
            "id": f"task_{i}",
            "payload": f"data_{i}",
            "priority": i % 3,  # 0=high, 1=medium, 2=low
            "created_at": time.time()
        }
        tasks.append(task)
        await asyncio.sleep(0.01)  # Simulate async generation
    return tasks

# Generate tasks
generated_tasks = await generate_tasks()

result = {
    "tasks": generated_tasks,
    "task_count": len(generated_tasks),
    "priority_distribution": {
        "high": len([t for t in generated_tasks if t["priority"] == 0]),
        "medium": len([t for t in generated_tasks if t["priority"] == 1]),
        "low": len([t for t in generated_tasks if t["priority"] == 2])
    }
}
'''

        # Task processor
        task_processor_code = '''
import asyncio
import time

async def process_task(task):
    """Process a single task."""
    start_time = time.time()

    # Simulate processing time based on priority
    processing_time = 0.01 * (task["priority"] + 1)
    await asyncio.sleep(processing_time)

    return {
        "task_id": task["id"],
        "original_payload": task["payload"],
        "processed_payload": f"processed_{task['payload']}",
        "processing_time": time.time() - start_time,
        "status": "completed"
    }

# Process all tasks
task_list = tasks if tasks else []
processed_results = []

for task in task_list:
    processed_task = await process_task(task)
    processed_results.append(processed_task)

# Calculate summary
total_processing_time = sum(r["processing_time"] for r in processed_results)
avg_processing_time = total_processing_time / len(processed_results) if processed_results else 0

result = {
    "processed_tasks": processed_results,
    "processing_summary": {
        "total_tasks": len(processed_results),
        "total_processing_time": total_processing_time,
        "avg_processing_time": avg_processing_time,
        "all_completed": all(r["status"] == "completed" for r in processed_results)
    }
}
'''

        # Add nodes
        builder.add_async_code("task_generator", task_generator_code)
        builder.add_async_code("task_processor", task_processor_code)

        # Connect tasks
        builder.add_connection(
            "task_generator", "result.tasks", "task_processor", "tasks"
        )

        workflow = builder.build()
        runtime = AsyncLocalRuntime()

        result = await runtime.execute_workflow_async(workflow, {})

        # Verify execution
        assert len(result["errors"]) == 0
        assert "task_generator" in result["results"]
        assert "task_processor" in result["results"]

        # Verify task generation
        gen_result = result["results"]["task_generator"]
        assert gen_result["task_count"] == 5
        assert len(gen_result["tasks"]) == 5

        # Verify task processing
        proc_result = result["results"]["task_processor"]
        assert proc_result["processing_summary"]["total_tasks"] == 5
        assert proc_result["processing_summary"]["all_completed"] is True
        assert len(proc_result["processed_tasks"]) == 5

    async def test_user_flow_real_world_data_transformation(self):
        """Test real-world data transformation scenario with multiple stages."""
        builder = AsyncWorkflowBuilder("data_transformation")

        # Data ingestion
        ingestion_code = """
import json
import time

# Simulate real data ingestion
raw_records = [
    {"user_id": "u001", "action": "login", "timestamp": "2024-01-01T10:00:00", "ip": "192.168.1.1"},
    {"user_id": "u002", "action": "purchase", "timestamp": "2024-01-01T10:15:00", "amount": 99.99},
    {"user_id": "u001", "action": "view_product", "timestamp": "2024-01-01T10:30:00", "product_id": "p123"},
    {"user_id": "u003", "action": "login", "timestamp": "2024-01-01T11:00:00", "ip": "192.168.1.2"},
    {"user_id": "u002", "action": "logout", "timestamp": "2024-01-01T11:30:00"}
]

# Initial processing
processed_records = []
for record in raw_records:
    processed_record = {
        "id": f"{record['user_id']}_{record['action']}_{hash(record['timestamp']) % 1000}",
        "user_id": record["user_id"],
        "action": record["action"],
        "timestamp": record["timestamp"],
        "metadata": {k: v for k, v in record.items() if k not in ["user_id", "action", "timestamp"]},
        "processed_at": time.time()
    }
    processed_records.append(processed_record)

result = {
    "records": processed_records,
    "ingestion_stats": {
        "total_records": len(processed_records),
        "unique_users": len(set(r["user_id"] for r in processed_records)),
        "action_types": list(set(r["action"] for r in processed_records))
    }
}
"""

        # Data enrichment
        enrichment_code = """
# Enrich processed data
input_records = records if records else []
stats = ingestion_stats if ingestion_stats else {}

# Create user profiles
user_profiles = {}
for record in input_records:
    user_id = record["user_id"]
    if user_id not in user_profiles:
        user_profiles[user_id] = {
            "user_id": user_id,
            "actions": [],
            "first_seen": record["timestamp"],
            "last_seen": record["timestamp"]
        }

    user_profiles[user_id]["actions"].append(record["action"])
    if record["timestamp"] > user_profiles[user_id]["last_seen"]:
        user_profiles[user_id]["last_seen"] = record["timestamp"]

# Enrich records with user context
enriched_records = []
for record in input_records:
    profile = user_profiles[record["user_id"]]
    enriched_record = record.copy()
    enriched_record["user_context"] = {
        "total_actions": len(profile["actions"]),
        "action_diversity": len(set(profile["actions"])),
        "user_type": "active" if len(profile["actions"]) > 2 else "casual"
    }
    enriched_records.append(enriched_record)

result = {
    "enriched_records": enriched_records,
    "user_profiles": list(user_profiles.values()),
    "enrichment_stats": {
        "records_enriched": len(enriched_records),
        "profiles_created": len(user_profiles),
        "avg_actions_per_user": sum(len(p["actions"]) for p in user_profiles.values()) / len(user_profiles) if user_profiles else 0
    }
}
"""

        # Add nodes
        builder.add_async_code("data_ingestion", ingestion_code)
        builder.add_async_code("data_enrichment", enrichment_code)

        # Connect with multiple paths
        builder.add_connection(
            "data_ingestion", "result.records", "data_enrichment", "records"
        )
        builder.add_connection(
            "data_ingestion",
            "result.ingestion_stats",
            "data_enrichment",
            "ingestion_stats",
        )

        workflow = builder.build()
        runtime = AsyncLocalRuntime()

        result = await runtime.execute_workflow_async(workflow, {})

        # Verify execution
        assert len(result["errors"]) == 0
        assert "data_ingestion" in result["results"]
        assert "data_enrichment" in result["results"]

        # Verify ingestion
        ingestion_result = result["results"]["data_ingestion"]
        assert ingestion_result["ingestion_stats"]["total_records"] == 5
        assert ingestion_result["ingestion_stats"]["unique_users"] == 3
        assert len(ingestion_result["records"]) == 5

        # Verify enrichment (tests multiple connections)
        enrichment_result = result["results"]["data_enrichment"]
        assert enrichment_result["enrichment_stats"]["records_enriched"] == 5
        assert enrichment_result["enrichment_stats"]["profiles_created"] == 3
        assert len(enrichment_result["enriched_records"]) == 5

        # Verify enrichment worked
        enriched_record = enrichment_result["enriched_records"][0]
        assert "user_context" in enriched_record
        assert "total_actions" in enriched_record["user_context"]
        assert "user_type" in enriched_record["user_context"]
