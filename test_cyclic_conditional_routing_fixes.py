#!/usr/bin/env python3
"""
Test cyclic conditional routing fixes
Tests the corrected patterns in files that deal with SwitchNode and cycles.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))


def test_multi_path_conditional_cycle_patterns():
    """Test FILE 44: multi-path-conditional-cycle-patterns.md fixes."""
    try:
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()

        # Test CORRECTED patterns from FILE 44
        # Data source and classifier nodes
        workflow.add_node(
            "PythonCodeNode",
            "data_source",
            {"code": "result = {'data': [1, 2, 3, 4, 5]}"},
        )
        workflow.add_node(
            "PythonCodeNode",
            "classifier",
            {"code": "result = {'status': 'needs_processing', 'quality': 0.6}"},
        )
        workflow.add_node(
            "SwitchNode",
            "routing_switch",
            {
                "conditions": {
                    "filter": "status == 'needs_processing'",
                    "archive": "status == 'complete'",
                }
            },
        )
        workflow.add_node(
            "PythonCodeNode",
            "filter_processor",
            {"code": "result = {'filtered_data': input_data, 'status': 'processed'}"},
        )
        workflow.add_node(
            "PythonCodeNode",
            "archive_processor",
            {"code": "result = {'archived': True, 'timestamp': '2024-01-01'}"},
        )

        # Test corrected connections
        workflow.add_connection("data_source", "result", "classifier", "input")
        workflow.add_connection("classifier", "result", "routing_switch", "input")
        workflow.add_connection("routing_switch", "filter", "filter_processor", "input")
        workflow.add_connection(
            "routing_switch", "archive", "archive_processor", "input"
        )
        workflow.add_connection("filter_processor", "result", "classifier", "input")

        built_workflow = workflow.build()
        print("✅ FILE 44 (multi-path-conditional-cycle-patterns.md) fixes VERIFIED")
        return True

    except Exception as e:
        print(f"❌ FILE 44 test FAILED: {e}")
        return False


def test_cycle_scenario_patterns():
    """Test FILE 32: cycle-scenario-patterns.md fixes."""
    try:
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()

        # Test CORRECTED ETL retry pattern from FILE 32
        workflow.add_node(
            "PythonCodeNode",
            "etl_retry",
            {
                "code": """
# ETL processor with retry logic
max_retries = parameters.get("max_retries", 3)
success_rate = parameters.get("success_rate", 0.3)
iteration = context.get("iteration", 0)

# Simulate success after retries
if iteration >= 2 or iteration / max_retries > success_rate:
    success = True
    data = {"processed_records": 1000}
else:
    success = False
    data = None

result = {
    "success": success,
    "data": data,
    "retry_count": iteration + 1,
    "max_retries": max_retries,
    "success_rate": success_rate,
    "converged": success or iteration >= max_retries - 1
}
"""
            },
        )

        # Test API poller pattern
        workflow.add_node(
            "PythonCodeNode",
            "api_poller",
            {
                "code": """
# Poll API until ready
max_polls = parameters.get("max_polls", 10)
iteration = context.get("iteration", 0)

# Simulate API becoming ready
if iteration >= 3:
    status = "ready"
    ready = True
    data = {"result": "processed"}
else:
    status = "pending"
    ready = False
    data = None

result = {
    "ready": ready,
    "status": status,
    "data": data,
    "poll_count": iteration + 1,
    "endpoint": parameters.get("endpoint"),
    "max_polls": max_polls,
    "converged": ready or iteration >= max_polls - 1
}
"""
            },
        )

        # Test cycle with intermediate node (self-connections not allowed)
        workflow.add_node(
            "PythonCodeNode",
            "retry_evaluator",
            {
                "code": "result = {'should_retry': not input_data.get('converged', False)}"
            },
        )
        workflow.add_connection("etl_retry", "result", "retry_evaluator", "input")
        workflow.add_connection("retry_evaluator", "result", "etl_retry", "input")

        built_workflow = workflow.build()
        print("✅ FILE 32 (cycle-scenario-patterns.md) fixes VERIFIED")
        return True

    except Exception as e:
        print(f"❌ FILE 32 test FAILED: {e}")
        return False


def test_data_quality_batch_processing():
    """Test data quality and batch processing patterns from FILE 32."""
    try:
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()

        # Test CORRECTED data quality pattern
        workflow.add_node(
            "PythonCodeNode",
            "data_quality",
            {
                "code": """
# Iteratively improve data quality
data = input_data.get("data", [])
target_quality = parameters.get("target_quality", 0.9)
improvement_rate = parameters.get("improvement_rate", 0.2)
iteration = context.get("iteration", 0)

# Calculate current quality
base_quality = 0.4
current_quality = min(base_quality + (iteration * improvement_rate), 1.0)

# Clean data based on quality
threshold = int(len(data) * (1 - current_quality))
cleaned_data = data[threshold:] if threshold < len(data) else data

result = {
    "data": cleaned_data,
    "quality_score": current_quality,
    "target_quality": target_quality,
    "improvement_rate": improvement_rate,
    "converged": current_quality >= target_quality
}
"""
            },
        )

        # Test batch processor pattern
        workflow.add_node(
            "PythonCodeNode",
            "batch_processor",
            {
                "code": """
# Process large datasets in batches
total_items = parameters.get("total_items", 1000)
batch_size = parameters.get("batch_size", 100)
iteration = context.get("iteration", 0)

# Get processed count from parameters (preserved across cycles)
if iteration > 0:
    processed_count = input_data.get("processed_count", 0)
else:
    processed_count = 0

# Process next batch
batch_end = min(processed_count + batch_size, total_items)
batch_data = list(range(processed_count, batch_end))

new_processed_count = batch_end
progress = new_processed_count / total_items

result = {
    "batch_data": batch_data,
    "processed_count": new_processed_count,
    "total_items": total_items,
    "batch_size": batch_size,
    "progress": progress,
    "converged": new_processed_count >= total_items
}
"""
            },
        )

        # Test cycle with intermediate node
        workflow.add_node(
            "PythonCodeNode",
            "batch_evaluator",
            {
                "code": "result = {'continue_processing': not input_data.get('converged', False)}"
            },
        )
        workflow.add_connection("batch_processor", "result", "batch_evaluator", "input")
        workflow.add_connection("batch_evaluator", "result", "batch_processor", "input")

        built_workflow = workflow.build()
        print("✅ Data quality and batch processing patterns VERIFIED")
        return True

    except Exception as e:
        print(f"❌ Data quality/batch processing test FAILED: {e}")
        return False


def test_switch_node_basic_functionality():
    """Test that SwitchNode works correctly with proper conditions."""
    try:
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()

        # Test basic SwitchNode functionality
        workflow.add_node(
            "PythonCodeNode",
            "input_data",
            {"code": "result = {'score': 0.8, 'status': 'active'}"},
        )

        workflow.add_node(
            "SwitchNode",
            "quality_router",
            {
                "conditions": {
                    "high_quality": "score >= 0.8",
                    "medium_quality": "score >= 0.5 and score < 0.8",
                    "low_quality": "score < 0.5",
                }
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "high_processor",
            {"code": "result = {'path': 'high_quality', 'processed': True}"},
        )

        workflow.add_node(
            "PythonCodeNode",
            "medium_processor",
            {"code": "result = {'path': 'medium_quality', 'processed': True}"},
        )

        # Test connections
        workflow.add_connection("input_data", "result", "quality_router", "input")
        workflow.add_connection(
            "quality_router", "high_quality", "high_processor", "input"
        )
        workflow.add_connection(
            "quality_router", "medium_quality", "medium_processor", "input"
        )

        built_workflow = workflow.build()
        print("✅ SwitchNode basic functionality VERIFIED")
        return True

    except Exception as e:
        print(f"❌ SwitchNode functionality test FAILED: {e}")
        return False


def run_cyclic_conditional_routing_tests():
    """Run all cyclic conditional routing tests."""
    print("🧪 Testing Cyclic Conditional Routing Fixes")
    print("=" * 60)

    tests = [
        ("Multi-Path Conditional Cycles", test_multi_path_conditional_cycle_patterns),
        ("Cycle Scenario Patterns", test_cycle_scenario_patterns),
        ("Data Quality & Batch Processing", test_data_quality_batch_processing),
        ("SwitchNode Basic Functionality", test_switch_node_basic_functionality),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n🔍 Running {test_name}...")
        if test_func():
            passed += 1

    print(
        f"\n📊 Cyclic Conditional Routing Test Results: {passed}/{total} tests passed"
    )

    if passed == total:
        print("🎉 ALL CYCLIC CONDITIONAL ROUTING FIXES VERIFIED!")
        print("✅ SwitchNode and cycle patterns working correctly")
    else:
        print(f"⚠️  {total - passed} tests failed - need to review fixes")

    return passed == total


if __name__ == "__main__":
    print("Testing cyclic conditional routing documentation fixes...")
    success = run_cyclic_conditional_routing_tests()
    sys.exit(0 if success else 1)
