"""Integration tests for PythonCodeNode serialization fix (TODO-129) - FIXED VERSION.

These tests use real infrastructure and only allowed modules to test serialization behavior.
This follows the 3-tier testing strategy with NO MOCKING for Tier 2.

Test Environment Requirements:
- Docker services must be running: ./tests/utils/test-env up
- Only uses modules from ALLOWED_MODULES list
- Real file operations and data processing
"""

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Test requires real infrastructure
pytestmark = pytest.mark.integration


class TestFileSystemSerializationScenarios:
    """Test serialization in real file system scenarios using only allowed modules."""

    def test_file_processing_serialization(self):
        """Test serialization of file processing results."""
        # Create a test file with Unicode content
        test_content = "Hello World! 🌍\n测试中文\nالعربية\n日本語\n"

        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False, suffix=".txt"
        ) as temp_file:
            temp_file.write(test_content)
            temp_file_path = temp_file.name

        try:
            # File processing code using only allowed modules
            file_processing_code = f"""
import os
import json
from pathlib import Path

file_path = Path("{temp_file_path}")

# Read and process file
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Analyze content
lines = content.strip().split('\\n')
result = {{
    "file_info": {{
        "name": file_path.name,
        "size": len(content),
        "lines": len(lines),
        "exists": file_path.exists()
    }},
    "content_analysis": {{
        "character_count": len(content),
        "word_count": len(content.split()),
        "unique_chars": len(set(content)),
        "has_unicode": any(ord(c) > 127 for c in content)
    }},
    "sample_lines": lines[:3],  # First 3 lines for verification
    "metadata": {{
        "encoding": "utf-8",
        "serialization_test": True
    }}
}}
"""

            node = PythonCodeNode(name="file_processor", code=file_processing_code)
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode", "file_process", {"code": file_processing_code}
            )

            runtime = LocalRuntime()
            results, run_id = runtime.execute(workflow.build())
            result = results.get("file_process")

            # Verify structure and serialization
            assert "result" in result
            data = result["result"]
            assert data["file_info"]["lines"] == 4
            assert data["content_analysis"]["has_unicode"] is True
            assert "🌍" in data["sample_lines"][0]

            # Verify JSON serialization works
            json_str = json.dumps(result, ensure_ascii=False)
            restored = json.loads(json_str)
            assert restored == result

        finally:
            # Cleanup
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def test_binary_file_handling_serialization(self):
        """Test serialization of binary file processing using only allowed modules."""
        # Create binary test file
        binary_data = bytes(range(256))  # All possible byte values

        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as temp_file:
            temp_file.write(binary_data)
            binary_file = temp_file.name

        try:
            # Binary processing code using only allowed modules (hashlib + hex)
            binary_processing_code = f"""
import os
import hashlib
from pathlib import Path

file_path = Path("{binary_file}")

# Read binary file
with open(file_path, 'rb') as f:
    binary_content = f.read()

# Process binary data using only allowed modules
result = {{
    "file_info": {{
        "name": file_path.name,
        "size": len(binary_content),
        "type": "binary"
    }},
    "analysis": {{
        "md5_hash": hashlib.md5(binary_content).hexdigest(),
        "sha256_hash": hashlib.sha256(binary_content).hexdigest(),
        "first_16_bytes_hex": binary_content[:16].hex(),
        "last_16_bytes_hex": binary_content[-16:].hex(),
        "unique_bytes": len(set(binary_content))
    }},
    "metadata": {{
        "encoding": "hex",
        "serialization_safe": True
    }}
}}
"""

            node = PythonCodeNode(name="binary_processor", code=binary_processing_code)
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode", "binary_process", {"code": binary_processing_code}
            )

            runtime = LocalRuntime()
            results, run_id = runtime.execute(workflow.build())
            result = results.get("binary_process")

            # Verify structure
            assert "result" in result
            data = result["result"]
            assert data["file_info"]["size"] == 256
            assert data["analysis"]["unique_bytes"] == 256
            assert data["metadata"]["serialization_safe"] is True

            # Verify JSON serialization works with hex encoded data
            json_str = json.dumps(result)
            restored = json.loads(json_str)
            assert restored == result

        finally:
            # Cleanup
            if os.path.exists(binary_file):
                os.unlink(binary_file)


class TestDataProcessingSerializationScenarios:
    """Test serialization in data processing scenarios using allowed modules."""

    def test_json_data_processing_serialization(self):
        """Test serialization of JSON data processing."""
        # Create test JSON file
        test_data = {
            "users": [
                {"id": 1, "name": "Alice", "score": 95.5, "active": True},
                {"id": 2, "name": "Bob", "score": 87.2, "active": False},
                {"id": 3, "name": "Charlie", "score": 92.8, "active": True},
            ],
            "metadata": {
                "version": "1.0",
                "created": "2024-07-31T12:00:00Z",
                "unicode_test": "测试数据 🎯",
            },
        }

        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False, suffix=".json"
        ) as temp_file:
            json.dump(test_data, temp_file, ensure_ascii=False)
            json_file = temp_file.name

        try:
            # JSON processing code using only allowed modules
            json_processing_code = f"""
import json
import os
from pathlib import Path
from datetime import datetime

file_path = Path("{json_file}")

# Read and process JSON data
with open(file_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Process the data
active_users = [user for user in data["users"] if user["active"]]
average_score = sum(user["score"] for user in data["users"]) / len(data["users"])

result = {{
    "processing_info": {{
        "input_file": file_path.name,
        "total_users": len(data["users"]),
        "active_users": len(active_users),
        "processed_at": datetime.now().isoformat()
    }},
    "statistics": {{
        "average_score": round(average_score, 2),
        "max_score": max(user["score"] for user in data["users"]),
        "min_score": min(user["score"] for user in data["users"])
    }},
    "active_user_names": [user["name"] for user in active_users],
    "original_metadata": data["metadata"],
    "serialization_test": {{
        "unicode_preserved": "🎯" in str(data),
        "complex_structure": True,
        "nested_data": True
    }}
}}
"""

            node = PythonCodeNode(name="json_processor", code=json_processing_code)
            workflow = WorkflowBuilder()
            workflow.add_node(
                "PythonCodeNode", "json_process", {"code": json_processing_code}
            )

            runtime = LocalRuntime()
            results, run_id = runtime.execute(workflow.build())
            result = results.get("json_process")

            # Verify structure and processing
            assert "result" in result
            data = result["result"]
            assert data["processing_info"]["total_users"] == 3
            assert data["processing_info"]["active_users"] == 2
            assert data["statistics"]["average_score"] == 91.83
            assert "Alice" in data["active_user_names"]
            assert "Charlie" in data["active_user_names"]
            assert data["serialization_test"]["unicode_preserved"] is True

            # Verify JSON serialization works
            json_str = json.dumps(result, ensure_ascii=False)
            restored = json.loads(json_str)
            assert restored == result

        finally:
            # Cleanup
            if os.path.exists(json_file):
                os.unlink(json_file)


class TestMathematicalSerializationScenarios:
    """Test serialization in mathematical processing scenarios."""

    def test_statistical_analysis_serialization(self):
        """Test serialization of statistical analysis using math and statistics modules."""
        stats_code = """
import math
import statistics
import json
from datetime import datetime

# Sample dataset for analysis
data = [1.2, 2.5, 3.1, 4.7, 5.3, 6.8, 7.2, 8.9, 9.1, 10.5]

# Perform statistical analysis
result = {
    "dataset_info": {
        "size": len(data),
        "min_value": min(data),
        "max_value": max(data),
        "range": max(data) - min(data)
    },
    "central_tendency": {
        "mean": statistics.mean(data),
        "median": statistics.median(data),
        "mode_available": len(set(data)) < len(data)
    },
    "variability": {
        "variance": statistics.variance(data),
        "stdev": statistics.stdev(data),
        "coefficient_of_variation": statistics.stdev(data) / statistics.mean(data)
    },
    "mathematical_operations": {
        "sum": sum(data),
        "product": math.prod(data),
        "geometric_mean": statistics.geometric_mean(data),
        "harmonic_mean": statistics.harmonic_mean(data)
    },
    "analysis_metadata": {
        "computed_at": datetime.now().isoformat(),
        "precision": "float64",
        "all_values_positive": all(x > 0 for x in data)
    }
}
"""

        node = PythonCodeNode(name="stats_processor", code=stats_code)
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "stats_process", {"code": stats_code})

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())
        result = results.get("stats_process")

        # Verify structure and calculations
        assert "result" in result
        data = result["result"]
        assert data["dataset_info"]["size"] == 10
        assert abs(data["central_tendency"]["mean"] - 5.93) < 0.01
        assert data["central_tendency"]["median"] == 6.05
        assert data["analysis_metadata"]["all_values_positive"] is True

        # Verify JSON serialization works with floating point numbers
        json_str = json.dumps(result)
        restored = json.loads(json_str)
        assert restored == result


class TestComplexDataStructureSerializationScenarios:
    """Test serialization of complex nested data structures."""

    def test_nested_data_structure_serialization(self):
        """Test serialization of deeply nested data structures."""
        complex_code = """
import json
import uuid
from datetime import datetime
from collections import defaultdict

# Create complex nested data structure
companies = [
    {
        "id": str(uuid.uuid4()),
        "name": "TechCorp Inc.",
        "founded": 2010,
        "employees": [
            {"name": "Alice Johnson", "department": "Engineering", "salary": 95000},
            {"name": "Bob Smith", "department": "Marketing", "salary": 75000},
            {"name": "Carol Davis", "department": "Engineering", "salary": 105000}
        ],
        "locations": {
            "headquarters": {"city": "San Francisco", "country": "USA"},
            "branches": [
                {"city": "New York", "country": "USA", "employees": 50},
                {"city": "London", "country": "UK", "employees": 30}
            ]
        }
    }
]

# Process the complex data
dept_stats = defaultdict(list)
for company in companies:
    for emp in company["employees"]:
        dept_stats[emp["department"]].append(emp["salary"])

result = {
    "company_analysis": {
        "total_companies": len(companies),
        "total_employees": sum(len(c["employees"]) for c in companies),
        "total_locations": sum(1 + len(c["locations"]["branches"]) for c in companies)
    },
    "department_stats": {
        dept: {
            "employee_count": len(salaries),
            "avg_salary": sum(salaries) / len(salaries),
            "total_payroll": sum(salaries)
        }
        for dept, salaries in dept_stats.items()
    },
    "location_distribution": [
        {
            "city": company["locations"]["headquarters"]["city"],
            "type": "headquarters",
            "company": company["name"]
        }
        for company in companies
    ] + [
        {
            "city": branch["city"],
            "type": "branch",
            "employees": branch["employees"]
        }
        for company in companies
        for branch in company["locations"]["branches"]
    ],
    "metadata": {
        "analysis_timestamp": datetime.now().isoformat(),
        "data_complexity": "high",
        "nested_levels": 4,
        "serialization_challenge": "complex objects with UUIDs and nested collections"
    }
}
"""

        node = PythonCodeNode(name="complex_processor", code=complex_code)
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "complex_process", {"code": complex_code})

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())
        result = results.get("complex_process")

        # Verify structure and processing
        assert "result" in result
        data = result["result"]
        assert data["company_analysis"]["total_employees"] == 3
        assert data["company_analysis"]["total_locations"] == 3
        assert "Engineering" in data["department_stats"]
        assert "Marketing" in data["department_stats"]
        assert len(data["location_distribution"]) == 3

        # Verify JSON serialization works with complex nested structures
        json_str = json.dumps(result, ensure_ascii=False)
        restored = json.loads(json_str)
        assert restored == result


class TestErrorHandlingSerializationScenarios:
    """Test error handling scenarios in serialization contexts."""

    def test_controlled_error_serialization(self):
        """Test that errors are properly serialized and handled."""
        error_handling_code = """
import json
import os
from pathlib import Path

try:
    # Attempt to read a non-existent file
    nonexistent_path = Path("/tmp/definitely_does_not_exist_12345.txt")
    with open(nonexistent_path, 'r') as f:
        content = f.read()

    result = {"success": True, "content": content}

except FileNotFoundError as e:
    # Handle the expected error gracefully
    result = {
        "success": False,
        "error_info": {
            "type": "FileNotFoundError",
            "message": str(e),
            "attempted_path": str(nonexistent_path)
        },
        "fallback_data": {
            "message": "File operation failed, but error was handled gracefully",
            "timestamp": "2024-07-31T12:00:00Z",
            "recovery_successful": True
        },
        "serialization_test": {
            "error_object_serializable": True,
            "graceful_degradation": True
        }
    }
except Exception as e:
    result = {
        "success": False,
        "error_info": {
            "type": type(e).__name__,
            "message": str(e)
        }
    }
"""

        node = PythonCodeNode(name="error_handler", code=error_handling_code)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode", "error_process", {"code": error_handling_code}
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())
        result = results.get("error_process")

        # Verify error handling and structure
        assert "result" in result
        data = result["result"]
        assert data["success"] is False
        assert data["error_info"]["type"] == "FileNotFoundError"
        assert data["fallback_data"]["recovery_successful"] is True
        assert data["serialization_test"]["error_object_serializable"] is True

        # Verify JSON serialization works with error information
        json_str = json.dumps(result)
        restored = json.loads(json_str)
        assert restored == result
