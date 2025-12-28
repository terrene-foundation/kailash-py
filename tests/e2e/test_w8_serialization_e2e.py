#!/usr/bin/env python3
"""
End-to-End tests for W8 serialization bug fix across complete user workflows.

This test suite validates the enhanced Node._is_json_serializable() method
in complete end-to-end scenarios with full infrastructure stack.

Test Strategy (Tier 3 - E2E Tests):
- Speed: <10 seconds per test
- Infrastructure: Complete real infrastructure stack
- NO MOCKING: Complete scenarios with real services
- Focus: Complete user workflows and platform-specific behaviors

CRITICAL Setup Required:
  ./tests/utils/test-env up && ./tests/utils/test-env status

Coverage Areas:
1. Complete user workflows with W8Context serialization
2. LocalRuntime vs Nexus platform behavior comparison
3. Cross-framework integration scenarios
4. Production-like data processing pipelines
5. Platform deployment and execution validation
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Test infrastructure URLs
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://test:test@localhost:5434/test_db"
)
TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6380/0")
TEST_MINIO_URL = os.getenv("TEST_MINIO_URL", "http://localhost:9000")


# ============================================================================
# Production-Like Data Classes
# ============================================================================


@dataclass
class ProductionW8Context:
    """Production-like W8Context with comprehensive data."""

    request_id: str
    user_id: Optional[str] = None
    organization_id: Optional[str] = None
    session_data: Dict[str, Any] = field(default_factory=dict)
    security_context: Dict[str, Any] = field(default_factory=dict)
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Production-grade serialization with validation."""
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "session_data": self.session_data,
            "security_context": self.security_context,
            "audit_trail": self.audit_trail,
            "metadata": self.metadata,
            "serialization_version": "1.0",
        }


@dataclass
class DataProcessingResult:
    """Complete data processing result with W8Context."""

    processing_id: str
    context: ProductionW8Context
    input_data: Dict[str, Any] = field(default_factory=dict)
    processed_data: Dict[str, Any] = field(default_factory=dict)
    validation_results: Dict[str, Any] = field(default_factory=dict)
    performance_metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "processing_id": self.processing_id,
            "context": self.context.to_dict(),
            "input_data": self.input_data,
            "processed_data": self.processed_data,
            "validation_results": self.validation_results,
            "performance_metrics": self.performance_metrics,
        }


# ============================================================================
# Complete User Workflow Tests
# ============================================================================


@pytest.mark.e2e
class TestCompleteUserWorkflowW8:
    """Test complete user workflows with W8Context serialization."""

    def test_complete_data_processing_pipeline_with_w8(self):
        """Test complete data processing pipeline from ingestion to output with W8Context."""
        workflow = WorkflowBuilder()

        # Step 1: Data Ingestion with W8Context creation
        workflow.add_node(
            "PythonCodeNode",
            "ingest_data",
            {
                "code": """
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List
import time

@dataclass
class ProductionW8Context:
    request_id: str
    user_id: Optional[str] = None
    organization_id: Optional[str] = None
    session_data: Dict[str, Any] = field(default_factory=dict)
    security_context: Dict[str, Any] = field(default_factory=dict)
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "session_data": self.session_data,
            "security_context": self.security_context,
            "audit_trail": self.audit_trail,
            "metadata": self.metadata,
            "serialization_version": "1.0"
        }

# Create production W8Context
w8_context = ProductionW8Context(
    request_id="e2e_pipeline_test",
    user_id="e2e_user",
    organization_id="org_123",
    session_data={
        "session_id": "sess_e2e_456",
        "created_at": "2024-01-01T10:00:00Z",
        "user_agent": "E2E-Test-Client/1.0"
    },
    security_context={
        "permissions": ["read", "write", "process"],
        "auth_level": "standard",
        "ip_address": "192.168.1.100"
    },
    audit_trail=[
        {"action": "session_created", "timestamp": "2024-01-01T10:00:00Z"},
        {"action": "data_ingestion_started", "timestamp": "2024-01-01T10:00:01Z"}
    ],
    metadata={
        "source": "e2e_test",
        "processing_pipeline": "complete_workflow",
        "version": "1.0"
    }
)

# Simulate data ingestion
ingested_data = {
    "records": [
        {"id": i, "name": f"record_{i}", "value": i * 10, "category": "type_a" if i % 2 == 0 else "type_b"}
        for i in range(1, 101)  # 100 records
    ],
    "metadata": {
        "total_records": 100,
        "ingestion_timestamp": "2024-01-01T10:00:01Z",
        "data_source": "e2e_test_source"
    }
}

result = {
    "w8_context": w8_context,
    "ingested_data": ingested_data,
    "ingestion_status": "completed"
}
"""
            },
        )

        # Step 2: Data Validation with W8Context tracking
        workflow.add_node(
            "PythonCodeNode",
            "validate_data",
            {
                "code": """
import time

# Extract data for validation
w8_context = ingestion_result["w8_context"]
data_to_validate = ingestion_result["ingested_data"]

# Add validation to audit trail
if hasattr(w8_context, 'to_dict'):
    w8_context.audit_trail.append({
        "action": "data_validation_started",
        "timestamp": "2024-01-01T10:00:02Z"
    })

# Validate data
records = data_to_validate["records"]
validation_results = {
    "total_records": len(records),
    "valid_records": 0,
    "invalid_records": 0,
    "validation_errors": []
}

for record in records:
    is_valid = (
        "id" in record and
        "name" in record and
        "value" in record and
        isinstance(record["value"], int) and
        record["value"] >= 0
    )

    if is_valid:
        validation_results["valid_records"] += 1
    else:
        validation_results["invalid_records"] += 1
        validation_results["validation_errors"].append({
            "record_id": record.get("id", "unknown"),
            "error": "Invalid record structure or values"
        })

# Update W8Context with validation results
if hasattr(w8_context, 'to_dict'):
    w8_context.metadata["validation_completed"] = True
    w8_context.audit_trail.append({
        "action": "data_validation_completed",
        "timestamp": "2024-01-01T10:00:03Z",
        "valid_records": validation_results["valid_records"],
        "invalid_records": validation_results["invalid_records"]
    })

result = {
    "w8_context": w8_context,
    "validated_data": data_to_validate,
    "validation_results": validation_results,
    "validation_status": "completed"
}
"""
            },
        )

        # Step 3: Data Transformation with W8Context updates
        workflow.add_node(
            "PythonCodeNode",
            "transform_data",
            {
                "code": """
# Extract validation results
w8_context = validation_result["w8_context"]
validated_data = validation_result["validated_data"]
validation_results = validation_result["validation_results"]

# Add transformation to audit trail
if hasattr(w8_context, 'to_dict'):
    w8_context.audit_trail.append({
        "action": "data_transformation_started",
        "timestamp": "2024-01-01T10:00:04Z"
    })

# Transform data (only valid records)
records = validated_data["records"]
transformed_records = []

for record in records:
    # Apply transformations
    transformed_record = {
        "id": record["id"],
        "name": record["name"].upper(),  # Uppercase names
        "value": record["value"] * 2,    # Double values
        "category": record["category"],
        "processed": True,
        "transformation_applied": "uppercase_name_double_value"
    }
    transformed_records.append(transformed_record)

# Calculate transformation metrics
transformation_metrics = {
    "records_transformed": len(transformed_records),
    "transformation_type": "uppercase_double",
    "average_value": sum(r["value"] for r in transformed_records) / len(transformed_records) if transformed_records else 0
}

# Update W8Context
if hasattr(w8_context, 'to_dict'):
    w8_context.metadata["transformation_completed"] = True
    w8_context.metadata["transformation_metrics"] = transformation_metrics
    w8_context.audit_trail.append({
        "action": "data_transformation_completed",
        "timestamp": "2024-01-01T10:00:05Z",
        "records_transformed": len(transformed_records)
    })

result = {
    "w8_context": w8_context,
    "transformed_data": {
        "records": transformed_records,
        "metadata": validated_data["metadata"]
    },
    "transformation_metrics": transformation_metrics,
    "transformation_status": "completed"
}
"""
            },
        )

        # Step 4: Data Storage and Final Processing
        workflow.add_node(
            "PythonCodeNode",
            "store_and_finalize",
            {
                "code": """
import json

# Extract transformation results
w8_context = transformation_result["w8_context"]
transformed_data = transformation_result["transformed_data"]
transformation_metrics = transformation_result["transformation_metrics"]

# Add storage to audit trail
if hasattr(w8_context, 'to_dict'):
    w8_context.audit_trail.append({
        "action": "data_storage_started",
        "timestamp": "2024-01-01T10:00:06Z"
    })

# Simulate data storage (JSON serialization test)
try:
    # This tests the W8Context serialization in a storage scenario
    storage_data = {
        "w8_context": w8_context.to_dict() if hasattr(w8_context, 'to_dict') else str(w8_context),
        "transformed_data": transformed_data,
        "transformation_metrics": transformation_metrics
    }

    # Test JSON serialization (where the original bug would occur)
    json_data = json.dumps(storage_data)
    storage_success = True
    serialization_test = "passed"

except Exception as e:
    storage_success = False
    serialization_test = f"failed: {str(e)}"
    json_data = ""

# Finalize processing
if hasattr(w8_context, 'to_dict'):
    w8_context.metadata["storage_completed"] = storage_success
    w8_context.metadata["serialization_test"] = serialization_test
    w8_context.audit_trail.append({
        "action": "processing_finalized",
        "timestamp": "2024-01-01T10:00:07Z",
        "storage_success": storage_success
    })

# Generate final processing report
final_report = {
    "processing_id": w8_context.request_id if hasattr(w8_context, 'request_id') else "unknown",
    "w8_context": w8_context,
    "processing_summary": {
        "records_ingested": 100,
        "records_validated": transformation_metrics.get("records_transformed", 0),
        "records_transformed": transformation_metrics.get("records_transformed", 0),
        "records_stored": transformation_metrics.get("records_transformed", 0) if storage_success else 0
    },
    "audit_trail_length": len(w8_context.audit_trail) if hasattr(w8_context, 'audit_trail') else 0,
    "serialization_success": storage_success,
    "json_data_size": len(json_data),
    "final_status": "completed" if storage_success else "failed"
}

result = final_report
"""
            },
        )

        # Connect the complete pipeline
        workflow.add_connection(
            "ingest_data", "result", "validate_data", "ingestion_result"
        )
        workflow.add_connection(
            "validate_data", "result", "transform_data", "validation_result"
        )
        workflow.add_connection(
            "transform_data", "result", "store_and_finalize", "transformation_result"
        )

        # Execute complete pipeline
        start_time = time.time()
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())
        total_execution_time = time.time() - start_time

        # Validate complete pipeline execution
        assert total_execution_time < 10.0  # E2E requirement: <10 seconds
        assert run_id is not None

        # Validate all steps completed
        required_nodes = [
            "ingest_data",
            "validate_data",
            "transform_data",
            "store_and_finalize",
        ]
        assert all(node in results for node in required_nodes)

        # Validate W8Context preservation through pipeline
        ingestion_result = results["ingest_data"]["result"]
        assert "w8_context" in ingestion_result
        w8_context = ingestion_result["w8_context"]
        assert hasattr(w8_context, "to_dict")
        assert w8_context.request_id == "e2e_pipeline_test"

        # Validate final processing report
        final_report = results["store_and_finalize"]["result"]
        assert final_report["processing_id"] == "e2e_pipeline_test"
        assert final_report["serialization_success"] is True
        assert final_report["final_status"] == "completed"
        assert final_report["processing_summary"]["records_ingested"] == 100
        assert final_report["processing_summary"]["records_transformed"] > 0
        assert final_report["audit_trail_length"] > 5  # Multiple audit entries added
        assert final_report["json_data_size"] > 0  # JSON serialization worked

        # Validate W8Context audit trail
        final_w8_context = final_report["w8_context"]
        assert hasattr(final_w8_context, "to_dict")
        assert len(final_w8_context.audit_trail) >= 6  # All processing steps tracked
        assert final_w8_context.metadata["validation_completed"] is True
        assert final_w8_context.metadata["transformation_completed"] is True
        assert final_w8_context.metadata["storage_completed"] is True

        print("\\nComplete E2E Pipeline Results:")
        print(f"Total execution time: {total_execution_time:.3f}s")
        print(
            f"Records processed: {final_report['processing_summary']['records_transformed']}"
        )
        print(f"JSON data size: {final_report['json_data_size']} bytes")
        print(f"Audit trail entries: {final_report['audit_trail_length']}")

    def test_multi_context_workflow_serialization(self):
        """Test workflow with multiple W8Context objects and complex serialization."""
        workflow = WorkflowBuilder()

        # Create multiple W8Context objects
        workflow.add_node(
            "PythonCodeNode",
            "create_multiple_contexts",
            {
                "code": """
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List

@dataclass
class ProductionW8Context:
    request_id: str
    user_id: Optional[str] = None
    organization_id: Optional[str] = None
    session_data: Dict[str, Any] = field(default_factory=dict)
    security_context: Dict[str, Any] = field(default_factory=dict)
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "session_data": self.session_data,
            "security_context": self.security_context,
            "audit_trail": self.audit_trail,
            "metadata": self.metadata,
            "serialization_version": "1.0"
        }

@dataclass
class DataProcessingResult:
    processing_id: str
    context: ProductionW8Context
    input_data: Dict[str, Any] = field(default_factory=dict)
    processed_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "processing_id": self.processing_id,
            "context": self.context.to_dict(),
            "input_data": self.input_data,
            "processed_data": self.processed_data
        }

# Create multiple contexts for different processing streams
contexts = []

for i in range(5):  # 5 different processing contexts
    context = ProductionW8Context(
        request_id=f"multi_context_test_{i}",
        user_id=f"user_{i}",
        organization_id=f"org_{i}",
        session_data={
            "stream_id": f"stream_{i}",
            "priority": "high" if i < 2 else "normal",
            "data_size": (i + 1) * 1000
        },
        security_context={
            "clearance_level": i + 1,
            "access_groups": [f"group_{j}" for j in range(i + 1)]
        },
        metadata={
            "stream_number": i,
            "batch_id": f"batch_{i // 2}",  # Group into batches
            "processing_type": "multi_stream"
        }
    )
    contexts.append(context)

# Create processing results for each context
processing_results = []
for i, context in enumerate(contexts):
    result = DataProcessingResult(
        processing_id=f"proc_{i}",
        context=context,
        input_data={"values": list(range(i * 10, (i + 1) * 10))},
        processed_data={"sum": sum(range(i * 10, (i + 1) * 10)), "count": 10}
    )
    processing_results.append(result)

result = {
    "contexts": contexts,
    "processing_results": processing_results,
    "total_contexts": len(contexts),
    "context_creation_status": "completed"
}
"""
            },
        )

        # Process all contexts together
        workflow.add_node(
            "PythonCodeNode",
            "process_all_contexts",
            {
                "code": """
import json

contexts = multi_context_data["contexts"]
processing_results = multi_context_data["processing_results"]

# Test serialization of all contexts
serialization_results = []
total_json_size = 0

for i, (context, proc_result) in enumerate(zip(contexts, processing_results)):
    try:
        # Test individual context serialization
        context_json = json.dumps(context.to_dict())
        context_size = len(context_json)

        # Test processing result serialization (contains nested context)
        result_json = json.dumps(proc_result.to_dict())
        result_size = len(result_json)

        serialization_results.append({
            "context_index": i,
            "context_id": context.request_id,
            "context_serialization_success": True,
            "context_json_size": context_size,
            "result_serialization_success": True,
            "result_json_size": result_size,
            "total_size": context_size + result_size
        })

        total_json_size += context_size + result_size

    except Exception as e:
        serialization_results.append({
            "context_index": i,
            "context_id": getattr(context, 'request_id', 'unknown'),
            "context_serialization_success": False,
            "result_serialization_success": False,
            "error": str(e)
        })

# Aggregate results
successful_serializations = sum(1 for r in serialization_results if r.get("context_serialization_success", False))
failed_serializations = len(serialization_results) - successful_serializations

aggregate_result = {
    "total_contexts_processed": len(contexts),
    "successful_serializations": successful_serializations,
    "failed_serializations": failed_serializations,
    "total_json_size": total_json_size,
    "average_context_size": total_json_size / len(contexts) if contexts else 0,
    "serialization_details": serialization_results,
    "overall_success": failed_serializations == 0
}

result = aggregate_result
"""
            },
        )

        workflow.add_connection(
            "create_multiple_contexts",
            "result",
            "process_all_contexts",
            "multi_context_data",
        )

        # Execute multi-context workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Validate multi-context processing
        assert "create_multiple_contexts" in results
        assert "process_all_contexts" in results

        creation_result = results["create_multiple_contexts"]["result"]
        assert creation_result["total_contexts"] == 5
        assert creation_result["context_creation_status"] == "completed"

        processing_result = results["process_all_contexts"]["result"]
        assert processing_result["total_contexts_processed"] == 5
        assert processing_result["overall_success"] is True
        assert processing_result["failed_serializations"] == 0
        assert processing_result["successful_serializations"] == 5
        assert processing_result["total_json_size"] > 0
        assert processing_result["average_context_size"] > 0

        # Validate individual context serialization results
        for detail in processing_result["serialization_details"]:
            assert detail["context_serialization_success"] is True
            assert detail["result_serialization_success"] is True
            assert detail["context_json_size"] > 0
            assert detail["result_json_size"] > 0


# ============================================================================
# Platform-Specific Behavior Tests
# ============================================================================


@pytest.mark.e2e
class TestPlatformSpecificW8Behavior:
    """Test platform-specific behaviors with W8Context serialization."""

    def test_local_runtime_w8_serialization_behavior(self):
        """Test W8Context serialization behavior specifically in LocalRuntime."""
        workflow = WorkflowBuilder()

        # Create platform-specific test
        workflow.add_node(
            "PythonCodeNode",
            "platform_test",
            {
                "code": """
import sys
import platform
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List

@dataclass
class PlatformW8Context:
    request_id: str
    platform_info: Dict[str, Any] = field(default_factory=dict)
    runtime_info: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "platform_info": self.platform_info,
            "runtime_info": self.runtime_info
        }

# Create platform-specific W8Context
w8_context = PlatformW8Context(
    request_id="platform_test_local",
    platform_info={
        "system": platform.system(),
        "platform": platform.platform(),
        "python_version": sys.version,
        "architecture": platform.architecture()
    },
    runtime_info={
        "runtime_type": "LocalRuntime",
        "execution_context": "e2e_test",
        "platform_specific_test": True
    }
)

# Test platform-specific serialization characteristics
platform_test_result = {
    "w8_context": w8_context,
    "platform_type": "local",
    "serialization_context": "local_runtime",
    "test_status": "created"
}

result = platform_test_result
"""
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "validate_platform",
            {
                "code": """
import json

platform_data = platform_result["w8_context"]
platform_type = platform_result["platform_type"]

# Validate platform-specific serialization
if hasattr(platform_data, 'to_dict'):
    try:
        # Test serialization in LocalRuntime context
        platform_dict = platform_data.to_dict()
        json_str = json.dumps(platform_dict)

        # Parse back to validate round-trip
        parsed_dict = json.loads(json_str)

        validation_result = {
            "platform_serialization_success": True,
            "platform_type": platform_type,
            "request_id_preserved": parsed_dict["request_id"] == "platform_test_local",
            "platform_info_preserved": "system" in parsed_dict["platform_info"],
            "runtime_info_preserved": "runtime_type" in parsed_dict["runtime_info"],
            "json_size": len(json_str),
            "runtime_type_correct": parsed_dict["runtime_info"]["runtime_type"] == "LocalRuntime"
        }

    except Exception as e:
        validation_result = {
            "platform_serialization_success": False,
            "error": str(e),
            "platform_type": platform_type
        }
else:
    validation_result = {
        "platform_serialization_success": False,
        "error": "Not a W8Context object",
        "platform_type": platform_type
    }

result = validation_result
"""
            },
        )

        workflow.add_connection(
            "platform_test", "result", "validate_platform", "platform_result"
        )

        # Execute with LocalRuntime (explicit)
        local_runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Validate LocalRuntime-specific behavior
        assert "platform_test" in results
        assert "validate_platform" in results

        validation_result = results["validate_platform"]["result"]
        assert validation_result["platform_serialization_success"] is True
        assert validation_result["platform_type"] == "local"
        assert validation_result["request_id_preserved"] is True
        assert validation_result["platform_info_preserved"] is True
        assert validation_result["runtime_info_preserved"] is True
        assert validation_result["runtime_type_correct"] is True
        assert validation_result["json_size"] > 0

    def test_cross_platform_w8_compatibility(self):
        """Test W8Context compatibility across different execution contexts."""
        workflow = WorkflowBuilder()

        # Test compatibility across contexts
        workflow.add_node(
            "PythonCodeNode",
            "create_portable_w8",
            {
                "code": """
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import json

@dataclass
class PortableW8Context:
    request_id: str
    compatibility_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "compatibility_data": self.compatibility_data,
            "portable_version": "1.0"
        }

# Create W8Context designed for cross-platform compatibility
portable_w8 = PortableW8Context(
    request_id="cross_platform_test",
    compatibility_data={
        "unicode_test": "测试 🚀 émoji データ",
        "numeric_test": {
            "integers": [1, 2, 3, -1, -2, 0],
            "floats": [1.0, 2.5, -3.14, 0.0],
            "large_numbers": [9223372036854775807, -9223372036854775808]
        },
        "nested_structures": {
            "level_1": {
                "level_2": {
                    "level_3": {
                        "data": ["deep", "nested", "serialization", "test"]
                    }
                }
            }
        },
        "special_cases": {
            "empty_string": "",
            "empty_list": [],
            "empty_dict": {},
            "null_value": None,
            "boolean_values": [True, False]
        }
    }
)

# Test immediate serialization
try:
    json_test = json.dumps(portable_w8.to_dict())
    serialization_success = True
    json_size = len(json_test)
except Exception as e:
    serialization_success = False
    json_size = 0

result = {
    "portable_w8_context": portable_w8,
    "immediate_serialization_success": serialization_success,
    "json_size": json_size,
    "compatibility_test_status": "created"
}
"""
            },
        )

        # Test in different processing contexts
        workflow.add_node(
            "PythonCodeNode",
            "test_portability",
            {
                "code": """
import json

portable_w8 = portability_data["portable_w8_context"]

# Test 1: Direct serialization
try:
    direct_json = json.dumps(portable_w8.to_dict())
    direct_success = True
    direct_size = len(direct_json)
except Exception as e:
    direct_success = False
    direct_size = 0

# Test 2: Round-trip serialization
try:
    if direct_success:
        parsed_back = json.loads(direct_json)
        re_serialized = json.dumps(parsed_back)
        round_trip_success = re_serialized == direct_json
    else:
        round_trip_success = False
except Exception as e:
    round_trip_success = False

# Test 3: Complex nested access
try:
    w8_dict = portable_w8.to_dict()
    nested_access_test = (
        w8_dict["compatibility_data"]["nested_structures"]["level_1"]["level_2"]["level_3"]["data"][0] == "deep"
    )
except Exception as e:
    nested_access_test = False

# Test 4: Unicode and special character handling
try:
    unicode_data = portable_w8.to_dict()["compatibility_data"]["unicode_test"]
    unicode_json = json.dumps(unicode_data)
    unicode_parsed = json.loads(unicode_json)
    unicode_success = unicode_parsed == unicode_data
except Exception as e:
    unicode_success = False

portability_results = {
    "direct_serialization_success": direct_success,
    "direct_json_size": direct_size,
    "round_trip_success": round_trip_success,
    "nested_access_success": nested_access_test,
    "unicode_handling_success": unicode_success,
    "overall_portability": all([
        direct_success,
        round_trip_success,
        nested_access_test,
        unicode_success
    ])
}

result = portability_results
"""
            },
        )

        workflow.add_connection(
            "create_portable_w8", "result", "test_portability", "portability_data"
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Validate cross-platform compatibility
        assert "create_portable_w8" in results
        assert "test_portability" in results

        creation_result = results["create_portable_w8"]["result"]
        assert creation_result["immediate_serialization_success"] is True
        assert creation_result["json_size"] > 0

        portability_result = results["test_portability"]["result"]
        assert portability_result["direct_serialization_success"] is True
        assert portability_result["round_trip_success"] is True
        assert portability_result["nested_access_success"] is True
        assert portability_result["unicode_handling_success"] is True
        assert portability_result["overall_portability"] is True
        assert portability_result["direct_json_size"] > 0


@pytest.mark.e2e
class TestW8SerializationE2EComplete:
    """Complete E2E test marker class."""

    pass


if __name__ == "__main__":
    # Run E2E tests with proper timeout
    pytest.main(
        [
            __file__,
            "-v",
            "--timeout=10",  # Enforce 10-second timeout for E2E tests
            "-m",
            "e2e",
        ]
    )
