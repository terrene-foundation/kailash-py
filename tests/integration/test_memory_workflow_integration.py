"""
Integration tests for memory and workflow systems.

Tests real integration between semantic memory, workflow templates,
and enterprise features with real infrastructure (no mocking).
"""

import asyncio
import time
from datetime import UTC, datetime

import pytest

from kailash.nodes.ai.semantic_memory import (
    SemanticMemorySearchNode,
    SemanticMemoryStoreNode,
)
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow
from kailash.workflow.templates import CycleTemplates


class TestMemoryWorkflowIntegration:
    """Test integration between memory systems and workflows."""

    @pytest.mark.asyncio
    async def test_semantic_memory_in_workflow(self):
        """Test semantic memory nodes integrated in a workflow."""
        # Create workflow with semantic memory nodes
        workflow = Workflow("memory_integration", "Memory Integration Test")

        # Add semantic memory nodes
        workflow.add_node(
            "store_docs",
            SemanticMemoryStoreNode(name="store_docs"),
            content=[
                "Technical documentation about Python",
                "User guide for API integration",
            ],
            collection="integration_docs",
        )

        workflow.add_node(
            "search_docs",
            SemanticMemorySearchNode(name="search_docs"),
            query="API integration guide",
            collection="integration_docs",
            threshold=0.1,
        )

        # Connect nodes
        workflow.connect("store_docs", "search_docs")

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify results
        assert run_id is not None
        assert "store_docs" in results
        assert "search_docs" in results

        store_result = results["store_docs"]
        search_result = results["search_docs"]

        assert store_result["success"] is True
        assert store_result["count"] == 2
        assert search_result["success"] is True

    @pytest.mark.asyncio
    async def test_memory_in_cyclic_workflow(self):
        """Test semantic memory in a cyclic workflow pattern."""
        workflow = Workflow("memory_cycle", "Memory Cycle Test")

        # Add memory storage node
        workflow.add_node(
            "store_knowledge",
            SemanticMemoryStoreNode(name="store_knowledge"),
            content="Initial knowledge base entry",
            collection="knowledge_cycle",
        )

        # Add processing node that generates new content
        processing_code = """
# Simulate processing that generates new content
import random

# Get stored knowledge (in real scenario, this would come from previous node)
new_content = f"Generated insight {random.randint(1, 1000)}: Advanced analytics pattern"

result = {
    "new_content": new_content,
    "processing_complete": True,
    "iteration": iteration if 'iteration' in locals() else 1
}
"""

        workflow.add_node(
            "process_knowledge",
            PythonCodeNode(name="process_knowledge", code=processing_code),
        )

        # Add evaluation node
        evaluation_code = """
# Evaluate if we have enough knowledge
iteration = iteration if 'iteration' in locals() else 1
iteration += 1

quality_score = min(0.9, iteration * 0.2)  # Improve with each iteration

result = {
    "quality": quality_score,
    "iteration": iteration,
    "sufficient_knowledge": quality_score >= 0.8
}
"""

        workflow.add_node(
            "evaluate_knowledge",
            PythonCodeNode(name="evaluate_knowledge", code=evaluation_code),
        )

        # Connect nodes
        workflow.connect("store_knowledge", "process_knowledge")
        workflow.connect("process_knowledge", "evaluate_knowledge")

        # Create optimization cycle
        cycle_id = CycleTemplates.optimization_cycle(
            workflow=workflow,
            processor_node="process_knowledge",
            evaluator_node="evaluate_knowledge",
            convergence="quality >= 0.8",
            max_iterations=5,
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify cyclic execution
        assert run_id is not None
        assert "store_knowledge" in results
        assert "evaluate_knowledge" in results

        eval_result = results["evaluate_knowledge"]
        assert eval_result["sufficient_knowledge"] is True

    @pytest.mark.asyncio
    async def test_memory_search_optimization_cycle(self):
        """Test semantic search in an optimization cycle."""
        workflow = Workflow("search_optimization", "Search Optimization Test")

        # Populate memory with test data
        workflow.add_node(
            "populate_memory",
            SemanticMemoryStoreNode(name="populate_memory"),
            content=[
                "Machine learning algorithms for data analysis",
                "Deep learning neural networks",
                "Statistical analysis and regression models",
                "Natural language processing techniques",
                "Computer vision and image recognition",
            ],
            collection="ml_knowledge",
        )

        # Search and refine cycle
        search_code = """
# Progressive search refinement
queries = [
    "machine learning algorithms",
    "deep learning neural networks",
    "statistical models analysis",
    "natural language processing",
    "computer vision techniques"
]

iteration = iteration if 'iteration' in locals() else 0
current_query = queries[iteration % len(queries)]

result = {
    "current_query": current_query,
    "iteration": iteration,
    "search_ready": True
}
"""

        workflow.add_node(
            "refine_search",
            PythonCodeNode(name="refine_search", code=search_code),
        )

        workflow.add_node(
            "search_memory",
            SemanticMemorySearchNode(name="search_memory"),
            collection="ml_knowledge",
            threshold=0.1,
        )

        evaluation_code = """
# Evaluate search results quality
iteration = iteration if 'iteration' in locals() else 0
iteration += 1

# Simulate improving search quality
search_quality = min(0.95, 0.6 + iteration * 0.1)

result = {
    "search_quality": search_quality,
    "iteration": iteration,
    "optimization_complete": search_quality >= 0.9
}
"""

        workflow.add_node(
            "evaluate_search",
            PythonCodeNode(name="evaluate_search", code=evaluation_code),
        )

        # Connect nodes
        workflow.connect("populate_memory", "refine_search")
        workflow.connect("refine_search", "search_memory")
        workflow.connect("search_memory", "evaluate_search")

        # Create optimization cycle
        cycle_id = CycleTemplates.optimization_cycle(
            workflow=workflow,
            processor_node="search_memory",
            evaluator_node="evaluate_search",
            convergence="search_quality >= 0.9",
            max_iterations=4,
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify optimization worked
        assert run_id is not None
        assert "populate_memory" in results
        assert "evaluate_search" in results

        eval_result = results["evaluate_search"]
        assert eval_result["optimization_complete"] is True


class TestEnterpriseMemoryIntegration:
    """Test enterprise memory features with workflow integration."""

    @pytest.mark.asyncio
    async def test_memory_with_retry_cycle(self):
        """Test memory operations with retry pattern for resilience."""
        workflow = Workflow("memory_retry", "Memory Retry Test")

        # Simulate unreliable memory operation
        memory_code = """
# Simulate unreliable memory storage
import random

attempt = attempt if 'attempt' in locals() else 0
attempt += 1

# Fail first 2 attempts, succeed on 3rd
if attempt <= 2:
    success = False
    error_msg = f"Memory storage failed on attempt {attempt}"
else:
    success = True
    error_msg = None

result = {
    "success": success,
    "attempt": attempt,
    "error": error_msg,
    "stored_items": ["doc1", "doc2", "doc3"] if success else []
}
"""

        workflow.add_node(
            "unreliable_memory",
            PythonCodeNode(name="unreliable_memory", code=memory_code),
        )

        # Create retry cycle
        cycle_id = CycleTemplates.retry_cycle(
            workflow=workflow,
            target_node="unreliable_memory",
            max_retries=5,
            backoff_strategy="exponential",
            success_condition="success == True",
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify retry succeeded
        assert run_id is not None
        assert "unreliable_memory" in results

        memory_result = results["unreliable_memory"]
        assert memory_result["success"] is True
        assert memory_result["attempt"] >= 3

    @pytest.mark.asyncio
    async def test_memory_tier_workflow(self):
        """Test memory tier management in workflow context."""
        workflow = Workflow("memory_tiers", "Memory Tier Management")

        # Simulate hot tier storage
        hot_storage_code = """
# Hot tier - recent, frequently accessed data
from datetime import datetime, UTC

hot_data = [
    {"id": "hot_1", "content": "Recent analysis report", "tier": "hot", "priority": "high"},
    {"id": "hot_2", "content": "Current project status", "tier": "hot", "priority": "high"},
]

result = {
    "tier": "hot",
    "stored_count": len(hot_data),
    "data": hot_data,
    "timestamp": datetime.now(UTC).isoformat()
}
"""

        # Simulate warm tier storage
        warm_storage_code = """
# Warm tier - moderately accessed data
from datetime import datetime, UTC, timedelta

warm_data = [
    {"id": "warm_1", "content": "Monthly performance metrics", "tier": "warm", "priority": "medium"},
    {"id": "warm_2", "content": "Quarterly business review", "tier": "warm", "priority": "medium"},
]

result = {
    "tier": "warm",
    "stored_count": len(warm_data),
    "data": warm_data,
    "timestamp": datetime.now(UTC).isoformat()
}
"""

        # Simulate cold tier storage
        cold_storage_code = """
# Cold tier - archived, rarely accessed data
from datetime import datetime, UTC, timedelta

cold_data = [
    {"id": "cold_1", "content": "Historical audit logs", "tier": "cold", "priority": "low"},
    {"id": "cold_2", "content": "Legacy system documentation", "tier": "cold", "priority": "low"},
]

result = {
    "tier": "cold",
    "stored_count": len(cold_data),
    "data": cold_data,
    "timestamp": datetime.now(UTC).isoformat()
}
"""

        # Add tier nodes
        workflow.add_node(
            "hot_storage", PythonCodeNode(name="hot_storage", code=hot_storage_code)
        )
        workflow.add_node(
            "warm_storage", PythonCodeNode(name="warm_storage", code=warm_storage_code)
        )
        workflow.add_node(
            "cold_storage", PythonCodeNode(name="cold_storage", code=cold_storage_code)
        )

        # Add tier coordinator
        coordinator_code = """
# Coordinate tier storage results
tier_results = {}

# Collect results from all tiers
if 'hot_storage' in globals():
    tier_results['hot'] = {"count": 2, "status": "active"}
if 'warm_storage' in globals():
    tier_results['warm'] = {"count": 2, "status": "active"}
if 'cold_storage' in globals():
    tier_results['cold'] = {"count": 2, "status": "archived"}

total_items = sum(tier["count"] for tier in tier_results.values())

result = {
    "tier_summary": tier_results,
    "total_items": total_items,
    "coordination_complete": True
}
"""

        workflow.add_node(
            "tier_coordinator",
            PythonCodeNode(name="tier_coordinator", code=coordinator_code),
        )

        # Connect tiers to coordinator (parallel processing)
        workflow.connect("hot_storage", "tier_coordinator")
        workflow.connect("warm_storage", "tier_coordinator")
        workflow.connect("cold_storage", "tier_coordinator")

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify tier coordination
        assert run_id is not None
        assert "tier_coordinator" in results

        coordinator_result = results["tier_coordinator"]
        assert coordinator_result["coordination_complete"] is True
        assert coordinator_result["total_items"] == 6

        # Verify individual tiers
        for tier in ["hot_storage", "warm_storage", "cold_storage"]:
            assert tier in results
            tier_result = results[tier]
            assert tier_result["stored_count"] == 2

    @pytest.mark.asyncio
    async def test_memory_analytics_workflow(self):
        """Test memory analytics and access pattern tracking."""
        workflow = Workflow("memory_analytics", "Memory Analytics Workflow")

        # Simulate memory access logging
        access_logger_code = """
# Log memory access patterns
import random
from datetime import datetime, UTC

access_patterns = []
for i in range(10):
    access = {
        "item_id": f"item_{i+1}",
        "access_time": datetime.now(UTC).isoformat(),
        "access_type": random.choice(["read", "write", "search"]),
        "user_id": f"user_{random.randint(1, 5)}",
        "duration_ms": random.randint(10, 500)
    }
    access_patterns.append(access)

result = {
    "access_patterns": access_patterns,
    "total_accesses": len(access_patterns),
    "logging_complete": True
}
"""

        # Simulate access pattern analysis
        analytics_code = """
# Analyze access patterns
access_data = access_patterns if 'access_patterns' in locals() else []

# Basic analytics
read_count = len([a for a in access_data if a["access_type"] == "read"])
write_count = len([a for a in access_data if a["access_type"] == "write"])
search_count = len([a for a in access_data if a["access_type"] == "search"])

avg_duration = sum(a["duration_ms"] for a in access_data) / len(access_data) if access_data else 0

unique_users = len(set(a["user_id"] for a in access_data))
unique_items = len(set(a["item_id"] for a in access_data))

result = {
    "analytics": {
        "read_operations": read_count,
        "write_operations": write_count,
        "search_operations": search_count,
        "avg_duration_ms": avg_duration,
        "unique_users": unique_users,
        "unique_items": unique_items
    },
    "analysis_complete": True
}
"""

        workflow.add_node(
            "access_logger",
            PythonCodeNode(name="access_logger", code=access_logger_code),
        )
        workflow.add_node(
            "pattern_analytics",
            PythonCodeNode(name="pattern_analytics", code=analytics_code),
        )

        # Connect nodes
        workflow.connect("access_logger", "pattern_analytics")

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify analytics
        assert run_id is not None
        assert "pattern_analytics" in results

        analytics_result = results["pattern_analytics"]
        assert analytics_result["analysis_complete"] is True

        analytics = analytics_result["analytics"]
        assert analytics["read_operations"] >= 0
        assert analytics["write_operations"] >= 0
        assert analytics["search_operations"] >= 0
        assert analytics["unique_users"] > 0
        assert analytics["unique_items"] > 0


class TestWorkflowTemplateRealExecution:
    """Test workflow templates with real execution scenarios."""

    @pytest.mark.asyncio
    async def test_data_quality_cycle_real_execution(self):
        """Test data quality cycle with real execution."""
        workflow = Workflow("data_quality_real", "Real Data Quality Test")

        # Data cleaner
        cleaner_code = """
# Simulate data cleaning
import random

# Simulate incoming data with quality issues
raw_data = [
    {"id": 1, "name": "  John Doe  ", "email": "john@example.com", "score": 85},
    {"id": 2, "name": "jane smith", "email": "JANE@EXAMPLE.COM", "score": None},
    {"id": 3, "name": "Bob Johnson", "email": "invalid-email", "score": 92},
    {"id": 4, "name": "", "email": "empty@example.com", "score": 78}
]

cleaned_data = []
for record in raw_data:
    cleaned = record.copy()

    # Clean name
    if cleaned["name"]:
        cleaned["name"] = cleaned["name"].strip().title()

    # Clean email
    if cleaned["email"]:
        cleaned["email"] = cleaned["email"].lower()

    # Handle missing scores
    if cleaned["score"] is None:
        cleaned["score"] = 0

    # Only include records with valid data
    if cleaned["name"] and "@" in cleaned["email"]:
        cleaned_data.append(cleaned)

result = {
    "cleaned_data": cleaned_data,
    "records_processed": len(raw_data),
    "records_cleaned": len(cleaned_data),
    "cleaning_complete": True
}
"""

        # Data validator
        validator_code = """
# Validate cleaned data quality
cleaned_records = cleaned_data if 'cleaned_data' in locals() else []

validation_results = []
quality_issues = 0

for record in cleaned_records:
    issues = []

    # Validate name
    if not record.get("name") or len(record["name"]) < 2:
        issues.append("invalid_name")

    # Validate email
    email = record.get("email", "")
    if "@" not in email or "." not in email:
        issues.append("invalid_email")

    # Validate score
    score = record.get("score", 0)
    if not isinstance(score, (int, float)) or score < 0 or score > 100:
        issues.append("invalid_score")

    if issues:
        quality_issues += 1

    validation_results.append({
        "record_id": record.get("id"),
        "issues": issues,
        "valid": len(issues) == 0
    })

total_records = len(cleaned_records)
valid_records = sum(1 for r in validation_results if r["valid"])
quality_score = valid_records / total_records if total_records > 0 else 0

result = {
    "validation_results": validation_results,
    "quality_score": quality_score,
    "valid_records": valid_records,
    "total_records": total_records,
    "quality_issues": quality_issues,
    "validation_complete": True
}
"""

        workflow.add_node(
            "data_cleaner", PythonCodeNode(name="data_cleaner", code=cleaner_code)
        )
        workflow.add_node(
            "data_validator", PythonCodeNode(name="data_validator", code=validator_code)
        )

        # Create data quality cycle
        cycle_id = CycleTemplates.data_quality_cycle(
            workflow=workflow,
            cleaner_node="data_cleaner",
            validator_node="data_validator",
            quality_threshold=0.8,
            max_iterations=3,
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify data quality improvement
        assert run_id is not None
        assert "data_validator" in results

        validator_result = results["data_validator"]
        assert validator_result["validation_complete"] is True
        assert validator_result["quality_score"] > 0

    @pytest.mark.asyncio
    async def test_optimization_cycle_convergence(self):
        """Test optimization cycle reaches convergence."""
        workflow = Workflow("optimization_convergence", "Optimization Convergence Test")

        # Optimizer that improves solution iteratively
        optimizer_code = """
# Iterative optimization
import random
import math

# Initialize or get current solution
current_value = current_value if 'current_value' in locals() else 0.1
iteration = iteration if 'iteration' in locals() else 0
iteration += 1

# Simulate optimization algorithm (gradient descent-like)
learning_rate = 0.1
target = 0.95

# Simple optimization: move towards target
improvement = (target - current_value) * learning_rate
current_value += improvement + random.uniform(-0.02, 0.02)  # Add noise

# Ensure bounds
current_value = max(0.0, min(1.0, current_value))

result = {
    "current_value": current_value,
    "iteration": iteration,
    "improvement": improvement,
    "optimization_step_complete": True
}
"""

        # Evaluator that checks convergence
        evaluator_code = """
# Evaluate optimization progress
value = current_value if 'current_value' in locals() else 0.0
iteration = iteration if 'iteration' in locals() else 0

target_threshold = 0.90
convergence_achieved = value >= target_threshold

# Calculate quality metrics
quality = value
stability = 1.0 - abs(improvement if 'improvement' in locals() else 0.1)
convergence_score = (quality + stability) / 2

result = {
    "quality": quality,
    "stability": stability,
    "convergence_score": convergence_score,
    "convergence_achieved": convergence_achieved,
    "iteration": iteration,
    "target_threshold": target_threshold
}
"""

        workflow.add_node(
            "optimizer", PythonCodeNode(name="optimizer", code=optimizer_code)
        )
        workflow.add_node(
            "evaluator", PythonCodeNode(name="evaluator", code=evaluator_code)
        )

        # Create optimization cycle
        cycle_id = CycleTemplates.optimization_cycle(
            workflow=workflow,
            processor_node="optimizer",
            evaluator_node="evaluator",
            convergence="quality >= 0.90",
            max_iterations=10,
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify convergence achieved
        assert run_id is not None
        assert "evaluator" in results

        evaluator_result = results["evaluator"]
        assert evaluator_result["convergence_achieved"] is True
        assert evaluator_result["quality"] >= 0.90
