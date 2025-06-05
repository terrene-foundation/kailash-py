"""
Secure ETL Workflow Template

This template demonstrates how to create a secure ETL (Extract, Transform, Load) workflow
with comprehensive security measures including path validation, input sanitization,
and audit logging.

Features:
- Secure file operations with path validation
- Input sanitization and validation
- Audit logging for security events
- Resource limits and execution timeouts
- Security configuration management

Usage:
    python secure_etl.py
"""

import os
import tempfile
from pathlib import Path

from kailash import Workflow
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.data.writers import CSVWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.security import SecurityConfig, set_security_config


def create_secure_etl_workflow():
    """
    Create a secure ETL workflow with comprehensive security measures.

    Returns:
        Configured Workflow instance with security settings
    """
    # Step 1: Configure security policy
    security_config = SecurityConfig(
        # Restrict file operations to specific directories
        allowed_directories=[
            tempfile.gettempdir(),  # Allow temp directory for testing
            "/app/data",  # Production data directory
            os.getcwd(),  # Current working directory for development
        ],
        # Set resource limits
        max_file_size=10 * 1024 * 1024,  # 10MB file size limit
        execution_timeout=120.0,  # 2 minute execution timeout
        memory_limit=512 * 1024 * 1024,  # 512MB memory limit
        # File type restrictions
        allowed_file_extensions=[".csv", ".json", ".txt", ".yaml", ".yml"],
        # Enable comprehensive security logging
        enable_audit_logging=True,
        enable_path_validation=True,
        enable_command_validation=True,
    )

    # Apply security configuration globally
    set_security_config(security_config)

    # Step 2: Create workflow with security context
    workflow = Workflow("secure_etl_pipeline")

    # Step 3: Add secure data extraction node
    # File path will be validated against allowed directories
    workflow.add_node(
        "extractor",
        CSVReaderNode(),
        file_path="data/input.csv",  # Will be validated at runtime
    )

    # Step 4: Add secure transformation node with resource limits
    transformation_code = """
# Secure data transformation with input validation
import re

def is_safe_value(value):
    '''Check if value is safe for processing'''
    if not isinstance(value, (str, int, float)):
        return False

    # Check for potentially dangerous patterns
    dangerous_patterns = ['<script>', 'javascript:', 'eval(', 'exec(']
    value_str = str(value)
    return not any(pattern in value_str.lower() for pattern in dangerous_patterns)

# Process data with security checks
safe_data = []
for row in data:
    # Validate each field in the row
    safe_row = {}
    for key, value in row.items():
        if is_safe_value(value):
            # Clean and process the value
            if isinstance(value, str):
                # Remove potentially dangerous characters
                cleaned_value = re.sub(r'[<>;&|`$]', '', value)
                safe_row[key] = cleaned_value.strip()
            else:
                safe_row[key] = value
        else:
            # Log security issue and skip dangerous values
            print(f"Skipped dangerous value: {key}={value}")
            safe_row[key] = None

    safe_data.append(safe_row)

# Filter out rows with too many null values (security measure)
result = [row for row in safe_data if sum(1 for v in row.values() if v is not None) >= len(row) * 0.5]

print(f"Processed {len(data)} input rows, {len(result)} safe output rows")
"""

    workflow.add_node(
        "transformer",
        PythonCodeNode(code=transformation_code),
        # Security config will automatically apply resource limits
    )

    # Step 5: Add secure data loading node
    workflow.add_node(
        "loader",
        CSVWriterNode(),
        file_path="data/output.csv",  # Will be validated at runtime
    )

    # Step 6: Connect nodes in secure pipeline
    workflow.connect("extractor", "transformer", mapping={"data": "data"})
    workflow.connect("transformer", "loader", mapping={"result": "data"})

    return workflow


def setup_test_data():
    """
    Create test data for the secure ETL demonstration.

    Returns:
        Path to the created test input file
    """
    # Create test data directory
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    # Create test CSV with some potentially dangerous content
    test_data = """name,email,description,score
John Doe,john@example.com,Normal user data,85
Jane Smith,jane@example.com,Another normal user,92
Evil User,evil@test.com,"<script>alert('xss')</script>",0
Safe User,safe@example.com,Completely safe content,88
Suspicious,suspect@test.com,"eval('malicious code')",15
"""

    input_file = data_dir / "input.csv"
    input_file.write_text(test_data)

    print(f"Created test data file: {input_file}")
    return input_file


def run_secure_etl():
    """
    Execute the secure ETL workflow with comprehensive security measures.
    """
    print("=== Secure ETL Workflow Demo ===")

    # Step 1: Setup test environment
    input_file = setup_test_data()

    # Step 2: Create secure workflow
    workflow = create_secure_etl_workflow()

    # Step 3: Validate workflow structure
    try:
        workflow.validate()
        print("✅ Workflow validation passed")
    except Exception as e:
        print(f"❌ Workflow validation failed: {e}")
        return

    # Step 4: Execute with security monitoring
    runtime = LocalRuntime()

    try:
        print("🔒 Executing workflow with security controls...")

        # Execute with parameter validation
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "extractor": {"file_path": str(input_file)},
                "loader": {"file_path": "data/secure_output.csv"},
            },
        )

        print(f"✅ Workflow executed successfully (Run ID: {run_id})")

        # Display results with security summary
        if results:
            print("\n📊 Execution Results:")
            for node_id, node_result in results.items():
                if isinstance(node_result, dict):
                    print(
                        f"  {node_id}: {len(node_result.get('data', []))} items processed"
                    )

        # Check output file
        output_file = Path("data/secure_output.csv")
        if output_file.exists():
            print(f"📁 Output file created: {output_file}")
            print(f"📏 Output file size: {output_file.stat().st_size} bytes")

            # Display first few lines of output
            print("\n📋 Output preview:")
            with open(output_file, "r") as f:
                for i, line in enumerate(f):
                    if i < 5:  # Show first 5 lines
                        print(f"  {line.strip()}")
                    else:
                        break

    except Exception as e:
        print(f"❌ Workflow execution failed: {e}")
        print("🔍 Check security logs for details")

    print("\n🛡️  Security measures applied:")
    print("  - Path validation for all file operations")
    print("  - Input sanitization and content filtering")
    print("  - Resource limits (memory, time, file size)")
    print("  - Comprehensive audit logging")
    print("  - Code execution sandboxing")


def cleanup_test_data():
    """Clean up test files."""
    files_to_remove = ["data/input.csv", "data/output.csv", "data/secure_output.csv"]

    for file_path in files_to_remove:
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass

    # Remove data directory if empty
    try:
        Path("data").rmdir()
    except Exception:
        pass


if __name__ == "__main__":
    try:
        run_secure_etl()
    finally:
        # Clean up test data
        print("\n🧹 Cleaning up test files...")
        cleanup_test_data()
        print("✅ Cleanup complete")
