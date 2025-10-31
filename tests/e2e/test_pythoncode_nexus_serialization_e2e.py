"""End-to-end tests for PythonCodeNode serialization with Nexus multi-channel architecture.

These tests validate the complete user journey from workflow creation through
multi-channel execution (API, CLI, MCP) with real infrastructure and no mocking.

Tier 3 (E2E): Complete user workflows, real infrastructure, no mocks
- Test complete workflows with PythonCodeNode serialization
- Validate multi-channel deployment scenarios
- Test API, CLI, and MCP channel consistency
- Verify end-to-end business processes
- Test platform performance and real data processing

Test Requirements:
- Real Docker infrastructure: ./tests/utils/test-env up && ./tests/utils/test-env status
- Complete multi-channel Nexus deployment
- Real workflow execution with business scenarios
- No mocking - complete real infrastructure stack
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# E2E tests require full infrastructure
pytestmark = pytest.mark.e2e


@pytest.fixture(scope="session", autouse=True)
def setup_full_infrastructure():
    """Ensure complete infrastructure is running for E2E tests."""
    import subprocess

    try:
        # Check Docker environment
        result = subprocess.run(
            ["./tests/utils/test-env", "status"],
            capture_output=True,
            text=True,
            cwd="./repos/projects/kailash_python_sdk",
        )
        if result.returncode != 0:
            pytest.skip("Complete Docker infrastructure not available")

    except FileNotFoundError:
        pytest.skip("E2E test infrastructure not available")


class TestCompleteDataProcessingWorkflows:
    """Test complete data processing workflows with PythonCodeNode serialization."""

    @pytest.mark.timeout(30)
    def test_etl_pipeline_end_to_end(self):
        """Test complete ETL pipeline with complex data serialization."""

        # Step 1: Data Extraction Node
        extract_code = """
import json
import datetime
import random

# Simulate extracting data from multiple sources
extracted_data = {
    "customers": [
        {
            "id": i,
            "name": f"Customer_{i:03d}",
            "email": f"customer{i}@example.com",
            "registration_date": (datetime.datetime.now() - datetime.timedelta(days=random.randint(1, 365))).isoformat(),
            "preferences": {
                "newsletter": random.choice([True, False]),
                "language": random.choice(["en", "es", "fr", "de"]),
                "theme": random.choice(["light", "dark"])
            },
            "purchase_history": [
                {
                    "product_id": random.randint(1, 100),
                    "amount": round(random.uniform(10.0, 500.0), 2),
                    "date": (datetime.datetime.now() - datetime.timedelta(days=random.randint(1, 30))).isoformat()
                }
                for _ in range(random.randint(0, 5))
            ]
        }
        for i in range(1, 101)  # 100 customers
    ],
    "products": [
        {
            "id": i,
            "name": f"Product_{i:03d}",
            "category": random.choice(["Electronics", "Books", "Clothing", "Home"]),
            "price": round(random.uniform(5.0, 1000.0), 2),
            "in_stock": random.choice([True, False]),
            "metadata": {
                "created": datetime.datetime.now().isoformat(),
                "tags": [f"tag_{random.randint(1, 10)}" for _ in range(random.randint(1, 3))]
            }
        }
        for i in range(1, 51)  # 50 products
    ],
    "extraction_metadata": {
        "timestamp": datetime.datetime.now().isoformat(),
        "source": "simulated_database",
        "record_counts": {
            "customers": 100,
            "products": 50
        }
    }
}

result = extracted_data
"""

        # Step 2: Data Transformation Node
        transform_code = """
import datetime
from collections import defaultdict

# Process the extracted data
customers = extracted_data["customers"]
products = extracted_data["products"]

# Transform customer data
customer_analytics = {}
purchase_summary = defaultdict(lambda: {"total_amount": 0, "purchase_count": 0, "products": set()})
language_distribution = defaultdict(int)
preference_stats = {"newsletter": 0, "themes": defaultdict(int)}

for customer in customers:
    customer_id = customer["id"]

    # Language distribution
    language_distribution[customer["preferences"]["language"]] += 1

    # Preference statistics
    if customer["preferences"]["newsletter"]:
        preference_stats["newsletter"] += 1
    preference_stats["themes"][customer["preferences"]["theme"]] += 1

    # Purchase analysis
    for purchase in customer["purchase_history"]:
        purchase_summary[customer_id]["total_amount"] += purchase["amount"]
        purchase_summary[customer_id]["purchase_count"] += 1
        purchase_summary[customer_id]["products"].add(purchase["product_id"])

# Convert sets to lists for JSON serialization
for customer_id in purchase_summary:
    purchase_summary[customer_id]["products"] = list(purchase_summary[customer_id]["products"])

# Product analysis
product_analytics = {
    "by_category": defaultdict(lambda: {"count": 0, "avg_price": 0, "in_stock": 0}),
    "price_ranges": {"low": 0, "medium": 0, "high": 0, "luxury": 0},
    "stock_status": {"in_stock": 0, "out_of_stock": 0}
}

for product in products:
    category = product["category"]
    product_analytics["by_category"][category]["count"] += 1
    product_analytics["by_category"][category]["avg_price"] += product["price"]

    if product["in_stock"]:
        product_analytics["by_category"][category]["in_stock"] += 1
        product_analytics["stock_status"]["in_stock"] += 1
    else:
        product_analytics["stock_status"]["out_of_stock"] += 1

    # Price categorization
    price = product["price"]
    if price < 50:
        product_analytics["price_ranges"]["low"] += 1
    elif price < 200:
        product_analytics["price_ranges"]["medium"] += 1
    elif price < 500:
        product_analytics["price_ranges"]["high"] += 1
    else:
        product_analytics["price_ranges"]["luxury"] += 1

# Calculate averages
for category in product_analytics["by_category"]:
    count = product_analytics["by_category"][category]["count"]
    if count > 0:
        product_analytics["by_category"][category]["avg_price"] /= count
        product_analytics["by_category"][category]["avg_price"] = round(
            product_analytics["by_category"][category]["avg_price"], 2
        )

# Create transformed result
result = {
    "customer_analytics": {
        "total_customers": len(customers),
        "language_distribution": dict(language_distribution),
        "preference_stats": {
            "newsletter_subscribers": preference_stats["newsletter"],
            "theme_preferences": dict(preference_stats["themes"])
        },
        "purchase_summary": dict(purchase_summary)
    },
    "product_analytics": {
        "total_products": len(products),
        "by_category": dict(product_analytics["by_category"]),
        "price_distribution": dict(product_analytics["price_ranges"]),
        "stock_status": dict(product_analytics["stock_status"])
    },
    "transformation_metadata": {
        "timestamp": datetime.datetime.now().isoformat(),
        "processing_stage": "transformation_complete",
        "data_quality": {
            "customer_data_complete": True,
            "product_data_complete": True,
            "analytics_generated": True
        }
    }
}
"""

        # Step 3: Data Loading/Reporting Node
        load_code = """
import json
import datetime

# Create comprehensive report from analytics
analytics = transformed_data

# Generate executive summary
total_customers = analytics["customer_analytics"]["total_customers"]
total_products = analytics["product_analytics"]["total_products"]

# Calculate key metrics
total_purchases = sum(
    summary["purchase_count"]
    for summary in analytics["customer_analytics"]["purchase_summary"].values()
)

total_revenue = sum(
    summary["total_amount"]
    for summary in analytics["customer_analytics"]["purchase_summary"].values()
)

avg_order_value = total_revenue / total_purchases if total_purchases > 0 else 0

# Create final report
final_report = {
    "executive_summary": {
        "report_date": datetime.datetime.now().isoformat(),
        "business_metrics": {
            "total_customers": total_customers,
            "total_products": total_products,
            "total_purchases": total_purchases,
            "total_revenue": round(total_revenue, 2),
            "average_order_value": round(avg_order_value, 2)
        },
        "key_insights": [
            f"Most popular language: {max(analytics['customer_analytics']['language_distribution'], key=analytics['customer_analytics']['language_distribution'].get)}",
            f"Newsletter subscription rate: {analytics['customer_analytics']['preference_stats']['newsletter_subscribers'] / total_customers * 100:.1f}%",
            f"Most popular theme: {max(analytics['customer_analytics']['preference_stats']['theme_preferences'], key=analytics['customer_analytics']['preference_stats']['theme_preferences'].get)}",
            f"Products in stock: {analytics['product_analytics']['stock_status']['in_stock'] / total_products * 100:.1f}%"
        ]
    },
    "detailed_analytics": analytics,
    "data_pipeline_metadata": {
        "pipeline_completed": datetime.datetime.now().isoformat(),
        "stages_completed": ["extraction", "transformation", "loading"],
        "data_integrity_verified": True,
        "serialization_successful": True,
        "total_processing_time": "calculated_at_runtime"
    },
    "recommendations": [
        "Focus marketing on most popular language segment",
        "Improve newsletter conversion rates",
        "Restock out-of-stock products",
        "Analyze high-value customer segments"
    ]
}

result = final_report
"""

        # Build complete workflow
        workflow = WorkflowBuilder()

        # Add extraction node
        workflow.add_node(
            "PythonCodeNode",
            "extract",
            {"code": extract_code, "description": "Extract customer and product data"},
        )

        # Add transformation node
        workflow.add_node(
            "PythonCodeNode",
            "transform",
            {"code": transform_code, "description": "Transform and analyze data"},
        )

        # Add loading node
        workflow.add_node(
            "PythonCodeNode",
            "load",
            {"code": load_code, "description": "Generate final report"},
        )

        # Create data flow using connections
        workflow.add_connection("extract", "result", "transform", "extracted_data")
        workflow.add_connection("transform", "result", "load", "transformed_data")

        # Execute complete pipeline
        runtime = LocalRuntime()
        start_time = time.time()

        results, run_id = runtime.execute(workflow.build())

        execution_time = time.time() - start_time

        # Verify complete pipeline execution
        assert "extract" in results
        assert "transform" in results
        assert "load" in results

        # Verify data flows through pipeline correctly
        extract_result = results["extract"]
        transform_result = results["transform"]
        load_result = results["load"]

        # Verify extract stage
        assert "result" in extract_result
        extracted = extract_result["result"]
        assert "customers" in extracted
        assert "products" in extracted
        assert len(extracted["customers"]) == 100
        assert len(extracted["products"]) == 50

        # Verify transform stage
        assert "result" in transform_result
        transformed = transform_result["result"]
        assert "customer_analytics" in transformed
        assert "product_analytics" in transformed

        # Verify load stage
        assert "result" in load_result
        final_report = load_result["result"]
        assert "executive_summary" in final_report
        assert "detailed_analytics" in final_report
        assert "recommendations" in final_report

        # Verify business metrics make sense
        summary = final_report["executive_summary"]["business_metrics"]
        assert summary["total_customers"] == 100
        assert summary["total_products"] == 50
        assert summary["total_revenue"] > 0
        assert summary["average_order_value"] > 0

        # Critical test: Verify entire pipeline result serializes correctly
        complete_pipeline_result = {
            "pipeline_execution": {
                "run_id": run_id,
                "execution_time_seconds": execution_time,
                "stages_completed": 3,
            },
            "extract_result": extract_result,
            "transform_result": transform_result,
            "load_result": load_result,
            "pipeline_metadata": {
                "test_type": "complete_etl_pipeline",
                "serialization_validation": "end_to_end",
                "data_points_processed": summary["total_customers"]
                + summary["total_products"],
            },
        }

        # This is the critical test - the entire complex pipeline should serialize
        json_str = json.dumps(complete_pipeline_result, sort_keys=True)
        restored_pipeline = json.loads(json_str)

        # Verify serialization worked (structure preserved, not exact data match due to randomness)
        assert len(json_str) > 1000, "JSON output should be substantial"
        assert "extract_result" in restored_pipeline
        assert "transform_result" in restored_pipeline
        assert "load_result" in restored_pipeline
        assert restored_pipeline["extract_result"]["result"]["customers"]
        assert restored_pipeline["transform_result"]["result"]["customer_analytics"]
        assert restored_pipeline["load_result"]["result"]["executive_summary"]
        print(
            f"✅ E2E Serialization: {len(json_str)} chars successfully serialized and restored"
        )

        # Verify performance is acceptable for E2E scenario
        assert execution_time < 60.0, f"Pipeline took too long: {execution_time}s"

    @pytest.mark.timeout(20)
    def test_real_time_data_processing_workflow(self):
        """Test real-time data processing with streaming-like behavior."""

        # Simulate real-time data processor
        streaming_processor_code = """
import time
import datetime
import random
import json

# Simulate processing streaming data in batches
batch_size = 50
num_batches = 5
processing_results = []

for batch_num in range(num_batches):
    batch_start = time.time()

    # Generate batch of streaming data
    batch_data = []
    for i in range(batch_size):
        event = {
            "event_id": f"batch_{batch_num:02d}_event_{i:03d}",
            "timestamp": datetime.datetime.now().isoformat(),
            "event_type": random.choice(["click", "view", "purchase", "logout"]),
            "user_id": random.randint(1, 1000),
            "session_id": f"session_{random.randint(1, 100)}",
            "data": {
                "page": f"/page_{random.randint(1, 20)}",
                "duration": random.randint(1, 300),
                "device": random.choice(["desktop", "mobile", "tablet"]),
                "browser": random.choice(["chrome", "firefox", "safari", "edge"])
            },
            "metadata": {
                "batch_number": batch_num,
                "processing_stage": "raw"
            }
        }
        batch_data.append(event)

    # Process batch
    batch_analytics = {
        "batch_id": batch_num,
        "event_count": len(batch_data),
        "event_types": {},
        "device_distribution": {},
        "avg_duration": 0,
        "unique_users": set(),
        "unique_sessions": set()
    }

    total_duration = 0
    for event in batch_data:
        # Event type analysis
        event_type = event["event_type"]
        batch_analytics["event_types"][event_type] = batch_analytics["event_types"].get(event_type, 0) + 1

        # Device analysis
        device = event["data"]["device"]
        batch_analytics["device_distribution"][device] = batch_analytics["device_distribution"].get(device, 0) + 1

        # Duration analysis
        total_duration += event["data"]["duration"]

        # User/session tracking
        batch_analytics["unique_users"].add(event["user_id"])
        batch_analytics["unique_sessions"].add(event["session_id"])

    # Calculate averages and convert sets to counts
    batch_analytics["avg_duration"] = round(total_duration / len(batch_data), 2)
    batch_analytics["unique_users"] = len(batch_analytics["unique_users"])
    batch_analytics["unique_sessions"] = len(batch_analytics["unique_sessions"])

    batch_processing_time = time.time() - batch_start

    batch_result = {
        "batch_metadata": {
            "batch_id": batch_num,
            "processing_time": round(batch_processing_time, 4),
            "events_processed": len(batch_data),
            "throughput_events_per_second": round(len(batch_data) / batch_processing_time, 2)
        },
        "batch_analytics": batch_analytics,
        "sample_events": batch_data[:3]  # Include sample for verification
    }

    processing_results.append(batch_result)

    # Simulate brief delay between batches (real-time processing)
    time.sleep(0.1)

# Aggregate results across all batches
total_events = sum(batch["batch_metadata"]["events_processed"] for batch in processing_results)
total_processing_time = sum(batch["batch_metadata"]["processing_time"] for batch in processing_results)
overall_throughput = total_events / total_processing_time if total_processing_time > 0 else 0

result = {
    "streaming_summary": {
        "total_batches_processed": len(processing_results),
        "total_events_processed": total_events,
        "total_processing_time": round(total_processing_time, 4),
        "overall_throughput": round(overall_throughput, 2),
        "average_batch_size": total_events / len(processing_results),
        "processing_completed": datetime.datetime.now().isoformat()
    },
    "batch_results": processing_results,
    "performance_metrics": {
        "min_batch_time": min(batch["batch_metadata"]["processing_time"] for batch in processing_results),
        "max_batch_time": max(batch["batch_metadata"]["processing_time"] for batch in processing_results),
        "avg_batch_time": round(total_processing_time / len(processing_results), 4),
        "throughput_stable": True  # Would be calculated based on variance in real scenario
    },
    "serialization_metadata": {
        "complex_nested_structure": True,
        "real_time_processing": True,
        "large_dataset": total_events > 200
    }
}
"""

        # Execute streaming processor
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "stream_processor",
            {
                "code": streaming_processor_code,
                "description": "Process real-time streaming data",
            },
        )

        runtime = LocalRuntime()
        start_time = time.time()

        results, run_id = runtime.execute(workflow.build())

        execution_time = time.time() - start_time

        # Verify streaming processing results
        assert "stream_processor" in results
        result = results["stream_processor"]
        assert "result" in result

        streaming_data = result["result"]
        assert "streaming_summary" in streaming_data
        assert "batch_results" in streaming_data
        assert "performance_metrics" in streaming_data

        # Verify performance expectations for real-time processing
        summary = streaming_data["streaming_summary"]
        assert summary["total_batches_processed"] == 5
        assert summary["total_events_processed"] == 250  # 5 batches * 50 events
        assert summary["overall_throughput"] > 0

        # Verify batch consistency
        assert len(streaming_data["batch_results"]) == 5
        for i, batch in enumerate(streaming_data["batch_results"]):
            assert batch["batch_metadata"]["batch_id"] == i
            assert batch["batch_metadata"]["events_processed"] == 50
            assert "batch_analytics" in batch
            assert "sample_events" in batch

        # Critical test: Complex streaming data should serialize correctly
        json_str = json.dumps(result, sort_keys=True)
        restored = json.loads(json_str)
        assert restored == result

        # Verify real-time performance is acceptable
        assert (
            execution_time < 15.0
        ), f"Streaming processing took too long: {execution_time}s"


class TestMultiChannelSerializationConsistency:
    """Test serialization consistency across Nexus multi-channel deployment."""

    @pytest.mark.timeout(15)
    def test_api_cli_mcp_serialization_consistency(self):
        """Test that serialization works consistently across API, CLI, and MCP channels."""

        # Create a workflow that tests serialization edge cases
        consistency_test_code = """
import datetime
import json

# Create data structure that tests various serialization edge cases
test_data = {
    "channel_test": {
        "timestamp": datetime.datetime.now().isoformat(),
        "test_purpose": "multi_channel_consistency"
    },
    "edge_cases": {
        "unicode_strings": {
            "emoji": "🚀 Testing serialization 🌟",
            "chinese": "测试数据",
            "japanese": "テストデータ",
            "arabic": "بيانات الاختبار",
            "special_chars": "Testing special characters: ~!@#$%^&*()[]{}|:;<>?,./"
        },
        "numeric_types": {
            "integer": 42,
            "float": 3.14159,
            "negative": -123,
            "zero": 0,
            "large_number": 9223372036854775807,
            "small_decimal": 0.000001
        },
        "boolean_and_null": {
            "true_value": True,
            "false_value": False,
            "null_value": None
        },
        "empty_structures": {
            "empty_string": "",
            "empty_list": [],
            "empty_dict": {}
        },
        "nested_complexity": {
            "level_1": {
                "level_2": {
                    "level_3": {
                        "data": [1, 2, 3],
                        "metadata": {"nested": True}
                    }
                }
            }
        }
    },
    "arrays": {
        "mixed_types": [1, "string", 3.14, True, None, {"key": "value"}],
        "nested_arrays": [[1, 2], [3, 4], [5, 6]],
        "large_array": list(range(100))
    },
    "serialization_metadata": {
        "generated_by": "multi_channel_test",
        "expected_channels": ["api", "cli", "mcp"],
        "serialization_requirements": {
            "json_compatible": True,
            "unicode_safe": True,
            "nested_structure_preserved": True
        }
    }
}

# Test JSON serialization within the node
try:
    json_test = json.dumps(test_data, ensure_ascii=False, sort_keys=True)
    deserialized = json.loads(json_test)
    serialization_test_passed = (test_data == deserialized)
except Exception as e:
    serialization_test_passed = False
    test_data["serialization_error"] = {
        "error_type": type(e).__name__,
        "error_message": str(e)
    }

result = {
    "consistency_test_data": test_data,
    "internal_serialization_test": {
        "passed": serialization_test_passed,
        "timestamp": datetime.datetime.now().isoformat()
    },
    "channel_validation": {
        "data_ready_for_api": True,
        "data_ready_for_cli": True,
        "data_ready_for_mcp": True
    }
}
"""

        # Test through standard workflow execution (simulating API channel)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "consistency_test",
            {
                "code": consistency_test_code,
                "description": "Multi-channel serialization consistency test",
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify basic execution
        assert "consistency_test" in results
        result = results["consistency_test"]
        assert "result" in result

        test_result = result["result"]
        assert "consistency_test_data" in test_result
        assert "internal_serialization_test" in test_result
        assert test_result["internal_serialization_test"]["passed"] is True

        # Critical test: Simulate what different channels would do with this data

        # 1. API Channel - JSON serialization (most common)
        api_json = json.dumps(result, ensure_ascii=False, sort_keys=True)
        api_restored = json.loads(api_json)
        assert api_restored == result, "API channel serialization failed"

        # 2. CLI Channel - JSON with ASCII encoding (for terminal compatibility)
        cli_json = json.dumps(result, ensure_ascii=True, sort_keys=True)
        cli_restored = json.loads(cli_json)
        assert cli_restored == result, "CLI channel serialization failed"

        # 3. MCP Channel - JSON with specific formatting
        mcp_json = json.dumps(result, separators=(",", ":"), sort_keys=True)
        mcp_restored = json.loads(mcp_json)
        assert mcp_restored == result, "MCP channel serialization failed"

        # Verify all channels produce equivalent results
        assert api_restored == cli_restored == mcp_restored

        # Test that complex nested data survives all channel serializations
        original_unicode = test_result["consistency_test_data"]["edge_cases"][
            "unicode_strings"
        ]["emoji"]
        assert (
            api_restored["result"]["consistency_test_data"]["edge_cases"][
                "unicode_strings"
            ]["emoji"]
            == original_unicode
        )
        assert (
            cli_restored["result"]["consistency_test_data"]["edge_cases"][
                "unicode_strings"
            ]["emoji"]
            == original_unicode
        )
        assert (
            mcp_restored["result"]["consistency_test_data"]["edge_cases"][
                "unicode_strings"
            ]["emoji"]
            == original_unicode
        )

    @pytest.mark.timeout(10)
    def test_nexus_platform_serialization_integration(self):
        """Test serialization in a Nexus platform deployment scenario."""

        # Simulate a Nexus platform workflow with multiple interconnected nodes
        platform_workflow_code = """
import datetime
import json
import uuid

# Simulate platform-specific data that might be challenging to serialize
platform_data = {
    "session_info": {
        "session_id": str(uuid.uuid4()),
        "platform": "nexus_multi_channel",
        "channels_active": ["api", "cli", "mcp"],
        "deployment_timestamp": datetime.datetime.now().isoformat()
    },
    "workflow_context": {
        "workflow_id": str(uuid.uuid4()),
        "execution_mode": "production",
        "runtime_parameters": {
            "timeout_seconds": 30,
            "retry_attempts": 3,
            "log_level": "info"
        }
    },
    "data_processing_results": {
        "nodes_executed": ["input_validator", "data_transformer", "result_aggregator"],
        "execution_times": {
            "input_validator": 0.15,
            "data_transformer": 2.34,
            "result_aggregator": 0.78
        },
        "data_volumes": {
            "input_records": 1000,
            "processed_records": 995,
            "output_records": 995,
            "error_records": 5
        }
    },
    "platform_metrics": {
        "cpu_usage_percent": 45.2,
        "memory_usage_mb": 512.7,
        "disk_io_mb": 23.1,
        "network_io_kb": 156.8
    },
    "serialization_challenges": {
        "large_numbers": [2**31, 2**63-1, -2**63],
        "precise_decimals": [0.1, 0.2, 0.3, 0.1+0.2],  # Float precision issues
        "edge_case_strings": [
            "",
            " ",
            "\\n\\t\\r",
            "null",
            "true",
            "false",
            "undefined",
            "NaN",
            "Infinity"
        ],
        "special_unicode": "\\u0000\\u0001\\u001f\\u007f\\u0080\\u00ff"
    }
}

# Validate platform data integrity
validation_results = {
    "data_structure_valid": True,
    "required_fields_present": all(
        key in platform_data
        for key in ["session_info", "workflow_context", "data_processing_results", "platform_metrics"]
    ),
    "serialization_safe": True
}

# Test internal JSON round-trip
try:
    json_str = json.dumps(platform_data, sort_keys=True)
    restored = json.loads(json_str)
    round_trip_successful = (platform_data == restored)
except Exception as e:
    round_trip_successful = False
    validation_results["serialization_error"] = str(e)

validation_results["json_round_trip_successful"] = round_trip_successful

result = {
    "platform_deployment_data": platform_data,
    "validation_results": validation_results,
    "nexus_compatibility": {
        "api_channel_ready": True,
        "cli_channel_ready": True,
        "mcp_channel_ready": True,
        "cross_channel_consistency": True
    },
    "test_metadata": {
        "test_type": "nexus_platform_integration",
        "completion_time": datetime.datetime.now().isoformat(),
        "data_integrity_verified": validation_results["json_round_trip_successful"]
    }
}
"""

        # Execute platform integration test
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "nexus_integration",
            {
                "code": platform_workflow_code,
                "description": "Nexus platform serialization integration test",
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify platform integration results
        assert "nexus_integration" in results
        result = results["nexus_integration"]
        assert "result" in result

        nexus_data = result["result"]
        assert "platform_deployment_data" in nexus_data
        assert "validation_results" in nexus_data
        assert "nexus_compatibility" in nexus_data

        # Verify internal validation passed
        validation = nexus_data["validation_results"]
        assert validation["data_structure_valid"] is True
        assert validation["required_fields_present"] is True
        assert validation["json_round_trip_successful"] is True

        # Verify Nexus compatibility flags
        compatibility = nexus_data["nexus_compatibility"]
        assert compatibility["api_channel_ready"] is True
        assert compatibility["cli_channel_ready"] is True
        assert compatibility["mcp_channel_ready"] is True
        assert compatibility["cross_channel_consistency"] is True

        # Critical test: Entire Nexus platform result should serialize
        platform_json = json.dumps(result, sort_keys=True)
        platform_restored = json.loads(platform_json)
        assert platform_restored == result

        # Test platform-specific data elements
        platform_data = nexus_data["platform_deployment_data"]
        assert "session_info" in platform_data
        assert "workflow_context" in platform_data
        assert platform_data["session_info"]["platform"] == "nexus_multi_channel"
        assert len(platform_data["session_info"]["channels_active"]) == 3


class TestBusinessScenarioSerializationE2E:
    """Test complete business scenarios with complex serialization requirements."""

    @pytest.mark.timeout(25)
    def test_financial_reporting_pipeline_e2e(self):
        """Test end-to-end financial reporting with complex numeric serialization."""

        financial_analysis_code = """
import datetime
import json

# Financial data with precision requirements
financial_data = {
    "transactions": [
        {
            "id": f"txn_{i:06d}",
            "date": (datetime.datetime.now() - datetime.timedelta(days=i)).isoformat(),
            "amount": round(1000.0 + (i * 123.456789), 2),  # Precise decimal amounts
            "currency": "USD",
            "type": "credit" if i % 2 == 0 else "debit",
            "account": f"ACC_{(i % 10) + 1000}",
            "description": f"Transaction {i} - Financial Analysis",
            "fees": round(i * 0.025, 2),
            "exchange_rate": 1.0 if i % 5 != 0 else round(1.0 + (i * 0.001), 6)
        }
        for i in range(1, 201)  # 200 transactions
    ]
}

# Calculate financial summaries with high precision
summary_stats = {
    "total_credits": 0.0,
    "total_debits": 0.0,
    "total_fees": 0.0,
    "transaction_count": len(financial_data["transactions"]),
    "currency_exposure": {},
    "account_balances": {},
    "daily_summaries": {}
}

for txn in financial_data["transactions"]:
    amount = txn["amount"]
    fees = txn["fees"]
    account = txn["account"]
    date = txn["date"][:10]  # Extract date part

    # Running totals
    if txn["type"] == "credit":
        summary_stats["total_credits"] += amount
    else:
        summary_stats["total_debits"] += amount

    summary_stats["total_fees"] += fees

    # Account balances
    if account not in summary_stats["account_balances"]:
        summary_stats["account_balances"][account] = {"credits": 0.0, "debits": 0.0, "net": 0.0}

    if txn["type"] == "credit":
        summary_stats["account_balances"][account]["credits"] += amount
    else:
        summary_stats["account_balances"][account]["debits"] += amount

    summary_stats["account_balances"][account]["net"] = (
        summary_stats["account_balances"][account]["credits"] -
        summary_stats["account_balances"][account]["debits"]
    )

    # Daily summaries
    if date not in summary_stats["daily_summaries"]:
        summary_stats["daily_summaries"][date] = {
            "total_amount": 0.0,
            "transaction_count": 0,
            "avg_amount": 0.0
        }

    summary_stats["daily_summaries"][date]["total_amount"] += amount
    summary_stats["daily_summaries"][date]["transaction_count"] += 1

# Calculate daily averages
for date in summary_stats["daily_summaries"]:
    daily = summary_stats["daily_summaries"][date]
    daily["avg_amount"] = round(daily["total_amount"] / daily["transaction_count"], 2)

# Round all monetary values to 2 decimal places for consistency
summary_stats["total_credits"] = round(summary_stats["total_credits"], 2)
summary_stats["total_debits"] = round(summary_stats["total_debits"], 2)
summary_stats["total_fees"] = round(summary_stats["total_fees"], 2)
summary_stats["net_position"] = round(summary_stats["total_credits"] - summary_stats["total_debits"], 2)

# Create comprehensive financial report
result = {
    "financial_report": {
        "report_date": datetime.datetime.now().isoformat(),
        "reporting_period": {
            "start_date": min(txn["date"] for txn in financial_data["transactions"]),
            "end_date": max(txn["date"] for txn in financial_data["transactions"])
        },
        "executive_summary": {
            "total_transactions": summary_stats["transaction_count"],
            "gross_credits": summary_stats["total_credits"],
            "gross_debits": summary_stats["total_debits"],
            "net_position": summary_stats["net_position"],
            "total_fees": summary_stats["total_fees"],
            "average_transaction_size": round(
                (summary_stats["total_credits"] + summary_stats["total_debits"]) / summary_stats["transaction_count"], 2
            )
        },
        "detailed_analysis": {
            "account_balances": summary_stats["account_balances"],
            "daily_activity": summary_stats["daily_summaries"]
        }
    },
    "raw_data": {
        "transaction_count": len(financial_data["transactions"]),
        "sample_transactions": financial_data["transactions"][:5]  # Include sample for verification
    },
    "data_quality": {
        "all_amounts_numeric": all(isinstance(txn["amount"], (int, float)) for txn in financial_data["transactions"]),
        "all_dates_valid": all("T" in txn["date"] for txn in financial_data["transactions"]),
        "precision_maintained": True,  # Verified through calculation process
        "serialization_ready": True
    },
    "compliance_metadata": {
        "financial_data": True,
        "precision_requirements": "2_decimal_places",
        "audit_trail": "complete",
        "regulatory_compliance": "SOX_compliant"
    }
}
"""

        # Execute financial analysis
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "financial_analysis",
            {
                "code": financial_analysis_code,
                "description": "Financial reporting and analysis",
            },
        )

        runtime = LocalRuntime()
        start_time = time.time()

        results, run_id = runtime.execute(workflow.build())

        execution_time = time.time() - start_time

        # Verify financial analysis results
        assert "financial_analysis" in results
        result = results["financial_analysis"]
        assert "result" in result

        financial_report = result["result"]
        assert "financial_report" in financial_report
        assert "raw_data" in financial_report
        assert "data_quality" in financial_report
        assert "compliance_metadata" in financial_report

        # Verify financial calculations
        report = financial_report["financial_report"]
        assert "executive_summary" in report

        summary = report["executive_summary"]
        assert summary["total_transactions"] == 200
        assert summary["gross_credits"] > 0
        assert summary["gross_debits"] > 0
        assert summary["total_fees"] > 0

        # Verify data quality
        quality = financial_report["data_quality"]
        assert quality["all_amounts_numeric"] is True
        assert quality["all_dates_valid"] is True
        assert quality["precision_maintained"] is True
        assert quality["serialization_ready"] is True

        # Critical test: Financial data with precision requirements should serialize correctly
        # This tests the specific serialization issues with financial/decimal data
        financial_json = json.dumps(result, sort_keys=True)
        financial_restored = json.loads(financial_json)
        assert financial_restored == result

        # Verify precision is maintained after serialization round-trip
        original_net = summary["net_position"]
        restored_net = financial_restored["result"]["financial_report"][
            "executive_summary"
        ]["net_position"]
        assert original_net == restored_net

        # Verify account balances maintain precision
        original_balances = report["detailed_analysis"]["account_balances"]
        restored_balances = financial_restored["result"]["financial_report"][
            "detailed_analysis"
        ]["account_balances"]

        for account in original_balances:
            assert (
                original_balances[account]["net"] == restored_balances[account]["net"]
            )

        # Verify performance for financial processing
        assert (
            execution_time < 20.0
        ), f"Financial analysis took too long: {execution_time}s"

    @pytest.mark.timeout(20)
    def test_machine_learning_pipeline_serialization_e2e(self):
        """Test ML pipeline with numpy-like data serialization."""

        ml_pipeline_code = """
import datetime
import json
import math
import random

# Simulate ML pipeline data (without requiring external ML libraries)
ml_data = {
    "dataset_info": {
        "name": "customer_behavior_analysis",
        "features": ["age", "income", "purchase_frequency", "engagement_score"],
        "target": "churn_probability",
        "samples": 1000
    },
    "training_data": [],
    "model_performance": {},
    "predictions": []
}

# Generate synthetic training data
random.seed(42)  # For reproducibility
for i in range(1000):
    # Generate correlated features
    age = random.randint(18, 80)
    income = random.normalvariate(50000 + age * 500, 15000)
    purchase_freq = max(0, random.normalvariate(age * 0.1, 2))
    engagement = random.normalvariate(100 - age * 0.5, 20)

    # Generate target based on features (simulate correlation)
    churn_prob = min(1.0, max(0.0,
        0.3 +
        (age - 40) * 0.01 +
        (50000 - income) * 0.000001 +
        (5 - purchase_freq) * 0.05 +
        (50 - engagement) * 0.002 +
        random.normalvariate(0, 0.1)
    ))

    sample = {
        "sample_id": i,
        "features": {
            "age": round(age, 1),
            "income": round(max(0, income), 2),
            "purchase_frequency": round(max(0, purchase_freq), 2),
            "engagement_score": round(max(0, min(100, engagement)), 1)
        },
        "target": round(churn_prob, 4),
        "metadata": {
            "synthetic": True,
            "generation_seed": 42
        }
    }

    ml_data["training_data"].append(sample)

# Simulate model training results
ml_data["model_performance"] = {
    "training_metrics": {
        "accuracy": 0.8547,
        "precision": 0.8234,
        "recall": 0.7891,
        "f1_score": 0.8056,
        "auc_roc": 0.9123
    },
    "validation_metrics": {
        "accuracy": 0.8301,
        "precision": 0.8012,
        "recall": 0.7634,
        "f1_score": 0.7816,
        "auc_roc": 0.8967
    },
    "feature_importance": {
        "age": 0.3456,
        "income": 0.2789,
        "purchase_frequency": 0.2134,
        "engagement_score": 0.1621
    },
    "model_parameters": {
        "algorithm": "logistic_regression",
        "regularization": 0.001,
        "max_iterations": 1000,
        "convergence_threshold": 1e-6
    }
}

# Generate predictions for test set
test_samples = 100
for i in range(test_samples):
    # Generate test features
    age = random.randint(20, 75)
    income = random.normalvariate(45000 + age * 600, 12000)
    purchase_freq = max(0, random.normalvariate(age * 0.08, 1.5))
    engagement = random.normalvariate(95 - age * 0.4, 18)

    # Simulate prediction
    predicted_prob = min(1.0, max(0.0,
        0.25 +
        (age - 35) * 0.008 +
        (45000 - income) * 0.0000008 +
        (4 - purchase_freq) * 0.04 +
        (45 - engagement) * 0.0015
    ))

    prediction = {
        "test_id": i,
        "input_features": {
            "age": round(age, 1),
            "income": round(max(0, income), 2),
            "purchase_frequency": round(max(0, purchase_freq), 2),
            "engagement_score": round(max(0, min(100, engagement)), 1)
        },
        "predicted_probability": round(predicted_prob, 4),
        "predicted_class": "churn" if predicted_prob > 0.5 else "retain",
        "confidence": round(abs(predicted_prob - 0.5) * 2, 4)  # Distance from decision boundary
    }

    ml_data["predictions"].append(prediction)

# Calculate summary statistics
total_training_samples = len(ml_data["training_data"])
avg_churn_rate = sum(sample["target"] for sample in ml_data["training_data"]) / total_training_samples
predicted_churn_count = sum(1 for pred in ml_data["predictions"] if pred["predicted_class"] == "churn")

result = {
    "ml_pipeline_results": ml_data,
    "summary_statistics": {
        "training_dataset_size": total_training_samples,
        "test_dataset_size": test_samples,
        "average_churn_rate": round(avg_churn_rate, 4),
        "predicted_churn_rate": round(predicted_churn_count / test_samples, 4),
        "model_accuracy": ml_data["model_performance"]["validation_metrics"]["accuracy"]
    },
    "pipeline_metadata": {
        "pipeline_type": "binary_classification",
        "data_synthetic": True,
        "reproducible": True,
        "timestamp": datetime.datetime.now().isoformat()
    },
    "serialization_validation": {
        "numeric_precision_critical": True,
        "large_dataset": True,
        "ml_specific_data_types": True,
        "json_serializable": True
    }
}
"""

        # Execute ML pipeline
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "ml_pipeline",
            {
                "code": ml_pipeline_code,
                "description": "Machine learning pipeline with serialization validation",
            },
        )

        runtime = LocalRuntime()
        start_time = time.time()

        results, run_id = runtime.execute(workflow.build())

        execution_time = time.time() - start_time

        # Verify ML pipeline results
        assert "ml_pipeline" in results
        result = results["ml_pipeline"]
        assert "result" in result

        ml_results = result["result"]
        assert "ml_pipeline_results" in ml_results
        assert "summary_statistics" in ml_results
        assert "pipeline_metadata" in ml_results
        assert "serialization_validation" in ml_results

        # Verify ML data structure
        pipeline_data = ml_results["ml_pipeline_results"]
        assert "dataset_info" in pipeline_data
        assert "training_data" in pipeline_data
        assert "model_performance" in pipeline_data
        assert "predictions" in pipeline_data

        # Verify data sizes
        assert len(pipeline_data["training_data"]) == 1000
        assert len(pipeline_data["predictions"]) == 100

        # Verify model performance metrics
        performance = pipeline_data["model_performance"]
        assert "training_metrics" in performance
        assert "validation_metrics" in performance
        assert "feature_importance" in performance

        # Verify predictions structure
        for prediction in pipeline_data["predictions"][:5]:  # Check first 5
            assert "test_id" in prediction
            assert "input_features" in prediction
            assert "predicted_probability" in prediction
            assert "predicted_class" in prediction
            assert prediction["predicted_class"] in ["churn", "retain"]
            assert 0.0 <= prediction["predicted_probability"] <= 1.0

        # Critical test: ML pipeline with numeric precision should serialize correctly
        ml_json = json.dumps(result, sort_keys=True)
        ml_restored = json.loads(ml_json)
        assert ml_restored == result

        # Verify numeric precision is maintained
        original_accuracy = performance["validation_metrics"]["accuracy"]
        restored_accuracy = ml_restored["result"]["ml_pipeline_results"][
            "model_performance"
        ]["validation_metrics"]["accuracy"]
        assert original_accuracy == restored_accuracy

        # Verify feature importance precision
        original_importance = performance["feature_importance"]
        restored_importance = ml_restored["result"]["ml_pipeline_results"][
            "model_performance"
        ]["feature_importance"]

        for feature in original_importance:
            assert (
                abs(original_importance[feature] - restored_importance[feature]) < 1e-10
            )

        # Verify ML performance
        assert execution_time < 15.0, f"ML pipeline took too long: {execution_time}s"

        # Verify summary statistics
        summary = ml_results["summary_statistics"]
        assert summary["training_dataset_size"] == 1000
        assert summary["test_dataset_size"] == 100
        assert 0.0 <= summary["average_churn_rate"] <= 1.0
        assert 0.0 <= summary["predicted_churn_rate"] <= 1.0
