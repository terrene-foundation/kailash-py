"""Comprehensive node validation example with real scenarios.

This example demonstrates the NodeValidator with actual workflow scenarios,
real data processing, Docker integration, and Ollama LLM validation.
Tests validation in production-like conditions using real databases and LLMs.
"""

import csv
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import requests

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from examples.utils.data_paths import get_input_data_path, get_output_data_path
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import AsyncSQLDatabaseNode, CSVReaderNode, SQLDatabaseNode
from kailash.nodes.security import CredentialManagerNode
from kailash.nodes.validation import NodeValidator, validate_node_decorator
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow


def setup_test_environment():
    """Set up test data files and check Docker/Ollama availability."""
    print("🔧 Setting up test environment...")

    # Create test data directory
    data_dir = Path("/tmp/validation_test_data")
    data_dir.mkdir(exist_ok=True)

    # Create test CSV file with realistic data
    test_csv = data_dir / "customers.csv"
    with open(test_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "email", "purchase_amount", "date"])
        writer.writerows(
            [
                [1, "John Doe", "john@email.com", 199.99, "2024-01-15"],
                [2, "Jane Smith", "jane@email.com", 299.50, "2024-01-16"],
                [3, "Bob Wilson", "bob@email.com", 450.00, "2024-01-17"],
                [4, "Alice Brown", "alice@email.com", 125.75, "2024-01-18"],
                [5, "Charlie Davis", "charlie@email.com", 89.99, "2024-01-19"],
            ]
        )

    # Create corrupted CSV for testing validation
    bad_csv = data_dir / "bad_customers.csv"
    with open(bad_csv, "w") as f:
        f.write("invalid,csv,format\n")
        f.write("missing,columns\n")
        f.write("123,name with\nlinebreak,email\n")

    # Check Docker availability
    docker_available = False
    try:
        result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
        docker_available = result.returncode == 0
        print(
            f"   Docker: {'✅ Available' if docker_available else '❌ Not available'}"
        )
    except FileNotFoundError:
        print("   Docker: ❌ Not available")

    # Check Ollama availability
    ollama_available = False
    try:
        import requests

        response = requests.get("http://localhost:11434/api/version", timeout=2)
        ollama_available = response.status_code == 200
        print(
            f"   Ollama: {'✅ Available' if ollama_available else '❌ Not available'}"
        )
    except:
        print("   Ollama: ❌ Not available")

    return {
        "data_dir": data_dir,
        "test_csv": test_csv,
        "bad_csv": bad_csv,
        "docker_available": docker_available,
        "ollama_available": ollama_available,
    }


def test_real_pythoncode_validation(env_info):
    """Test PythonCodeNode validation with real code execution."""
    print("\n📝 Testing PythonCodeNode Validation with Real Execution...")

    # Test 1: Missing result wrapper (common mistake)
    print("\n1. Missing result wrapper:")
    bad_code = """
import pandas as pd
df = pd.read_csv(get_input_data_path('customers.csv'))
total_sales = df['purchase_amount'].sum()
print(f"Total sales: ${total_sales}")
# Missing: result = {"total": total_sales}
"""

    suggestions = NodeValidator.validate_node_config(
        "PythonCodeNode", {"code": bad_code}
    )
    if suggestions:
        print("   ⚠️  Validation found issues:")
        for suggestion in suggestions:
            print(f"      - {suggestion.message}")
            if suggestion.code_example:
                print(f"        Fix: {suggestion.code_example}")

    # Test 2: Corrected code that works
    print("\n2. Corrected code:")
    good_code = """
df = pd.read_csv(get_input_data_path('customers.csv'))
total_sales = df['purchase_amount'].sum()
avg_purchase = df['purchase_amount'].mean()
customer_count = len(df)

result = {
    "total_sales": float(total_sales),
    "avg_purchase": float(avg_purchase),
    "customer_count": customer_count,
    "analysis_date": datetime.now().isoformat()
}
"""

    suggestions = NodeValidator.validate_node_config(
        "PythonCodeNode", {"code": good_code}
    )
    if not suggestions:
        print("   ✅ No validation issues found")

        # Actually execute this code to verify it works
        try:
            workflow = Workflow("validation_test", "PythonCode Validation Test")
            workflow.add_node(
                "processor", PythonCodeNode(name="processor", code=good_code)
            )

            runner = LocalRuntime()
            result = runner.execute(workflow)

            if result.get("success"):
                processor_result = result["results"]["processor"]
                print(f"   📊 Execution result: {processor_result}")
            else:
                print(f"   ❌ Execution failed: {result.get('error')}")

        except Exception as e:
            print(f"   ❌ Execution error: {e}")

    # Test 3: Security issue detection
    print("\n3. Security issue detection:")
    unsafe_code = """
user_input = "'; rm -rf / #"
command = f"ls -la {user_input}"
result = {"output": subprocess.check_output(command, shell=True)}
"""

    suggestions = NodeValidator.validate_node_config(
        "PythonCodeNode", {"code": unsafe_code}
    )
    if suggestions:
        print("   🔒 Security issues detected:")
        for suggestion in suggestions:
            print(f"      - {suggestion.message}")


def test_sql_injection_validation(env_info):
    """Test SQL injection detection and prevention suggestions."""
    print("\n🛡️  Testing SQL Injection Validation...")

    # Test 1: Obvious SQL injection vulnerability
    print("\n1. SQL injection vulnerability:")
    user_id = "1; DROP TABLE users; --"
    bad_query = f"SELECT * FROM customers WHERE id = {user_id}"

    suggestions = NodeValidator.validate_node_config(
        "SQLDatabaseNode", {"query": bad_query}
    )
    if suggestions:
        print("   ⚠️  SQL injection risk detected:")
        for suggestion in suggestions:
            print(f"      - {suggestion.message}")
            if suggestion.code_example:
                print(f"        Safe approach: {suggestion.code_example}")

    # Test 2: Parameterized query (safe)
    print("\n2. Safe parameterized query:")
    safe_query = "SELECT * FROM customers WHERE id = ? AND status = ?"
    suggestions = NodeValidator.validate_node_config(
        "SQLDatabaseNode", {"query": safe_query, "parameters": [1, "active"]}
    )

    if not suggestions:
        print("   ✅ No security issues found with parameterized query")

    # Test 3: Dynamic query with validation
    print("\n3. Dynamic query validation:")
    dynamic_queries = [
        "SELECT * FROM customers WHERE name LIKE '%${user_input}%'",
        "INSERT INTO logs (message) VALUES ('${log_message}')",
        "UPDATE users SET last_login = NOW() WHERE id = ${user_id}",
    ]

    for query in dynamic_queries:
        suggestions = NodeValidator.validate_node_config(
            "SQLDatabaseNode", {"query": query}
        )
        status = "⚠️  Issues found" if suggestions else "✅ Clean"
        print(f"      {query[:50]}... -> {status}")


def test_file_path_validation(env_info):
    """Test file path validation with real files."""
    print("\n📁 Testing File Path Validation...")

    test_cases = [
        # Good paths
        (str(env_info["test_csv"]), True, "Valid absolute path to existing file"),
        (str(get_input_data_path("customers.csv")), True, "Valid absolute path"),
        # Problematic paths
        ("data.csv", False, "Relative path - may not work in all environments"),
        ("../../../etc/passwd", False, "Potential security issue - path traversal"),
        ("/nonexistent/file.csv", False, "File does not exist"),
        ("customers.csv", False, "Relative path without directory context"),
    ]

    for file_path, should_be_clean, description in test_cases:
        print(f"\n   Testing: {file_path}")
        print(f"   Expected: {description}")

        suggestions = NodeValidator.validate_node_config(
            "CSVReaderNode", {"file_path": file_path}
        )

        if suggestions:
            print("   ⚠️  Issues found:")
            for suggestion in suggestions:
                print(f"      - {suggestion.message}")
        else:
            print("   ✅ No validation issues")

        # Try to actually read the file if it should work
        if should_be_clean and Path(file_path).exists():
            try:
                workflow = Workflow("file_test", "File Reading Test")
                workflow.add_node(
                    "reader", CSVReaderNode(name="reader", file_path=file_path)
                )

                runner = LocalRuntime()
                result = runner.execute(workflow)

                if result.get("success"):
                    data = result["results"]["reader"]
                    print(f"      📊 Successfully read {len(data)} rows")
                else:
                    print(f"      ❌ Failed to read: {result.get('error')}")

            except Exception as e:
                print(f"      ❌ Exception: {e}")


def test_llm_validation_with_ollama(env_info):
    """Test LLM node validation with real Ollama integration."""
    print("\n🤖 Testing LLM Validation with Ollama...")

    if not env_info["ollama_available"]:
        print("   ⏭️  Skipping - Ollama not available")
        return

    # Test 1: Check if required model is available
    print("\n1. Model availability check:")

    # Check what models are available
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            available_models = [model["name"] for model in models]
            print(f"   Available models: {available_models}")

            # Test validation for different models
            test_models = ["llama3.2", "llama2", "nonexistent-model"]

            for model in test_models:
                suggestions = NodeValidator.validate_node_config(
                    "LLMAgentNode",
                    {"model": model, "base_url": "http://localhost:11434"},
                )

                model_available = any(
                    model in avail_model for avail_model in available_models
                )
                status = "✅ Available" if model_available else "❌ Not available"
                print(f"      {model}: {status}")

                if suggestions:
                    for suggestion in suggestions:
                        print(f"         Warning: {suggestion.message}")

    except Exception as e:
        print(f"   ❌ Error checking models: {e}")

    # Test 2: Prompt template validation
    print("\n2. Prompt template validation:")

    prompt_tests = [
        # Good prompts
        ("Analyze this data: {data}", "✅ Valid template with placeholder"),
        (
            "Process the following information and provide insights.",
            "✅ Clear instruction",
        ),
        # Problematic prompts
        ("", "❌ Empty prompt"),
        ("Do something", "⚠️  Vague instruction"),
        ("Analyze {missing_placeholder}", "⚠️  Template may have missing data"),
    ]

    for prompt, expected in prompt_tests:
        print(f"   Testing: '{prompt[:30]}...'")
        suggestions = NodeValidator.validate_node_config(
            "LLMAgentNode", {"prompt_template": prompt, "model": "llama3.2"}
        )

        if suggestions:
            for suggestion in suggestions:
                print(f"      ⚠️  {suggestion.message}")
        else:
            print("      ✅ No issues found")

    # Test 3: Real LLM execution with validation
    print("\n3. Real LLM execution test:")

    try:
        # Create a workflow with LLM node
        workflow = Workflow("llm_validation", "LLM Validation Test")

        # Add LLM node
        workflow.add_node(
            "analyzer",
            LLMAgentNode(
                name="analyzer",
                model="llama3.2",
                prompt_template="Analyze this customer data and provide 3 key insights: {customer_data}",
                base_url="http://localhost:11434",
            ),
        )

        # Prepare customer data
        customer_data = {
            "total_customers": 5,
            "total_sales": 1165.23,
            "avg_purchase": 233.05,
            "date_range": "2024-01-15 to 2024-01-19",
        }

        runner = LocalRuntime()
        result = runner.execute(
            workflow, customer_data=json.dumps(customer_data, indent=2)
        )

        if result.get("success"):
            llm_response = result["results"]["analyzer"]
            print(f"   📝 LLM Analysis: {llm_response[:200]}...")
        else:
            print(f"   ❌ LLM execution failed: {result.get('error')}")

    except Exception as e:
        print(f"   ❌ LLM test error: {e}")


def test_credential_validation(env_info):
    """Test credential management validation."""
    print("\n🔐 Testing Credential Validation...")

    # Test 1: Hardcoded secrets detection
    print("\n1. Hardcoded secrets detection:")

    secret_tests = [
        ("api_key", "sk-1234567890abcdef", "OpenAI API key pattern"),
        ("password", "password123", "Weak password"),
        ("token", "ghp_1234567890", "GitHub token pattern"),
        ("aws_key", "AKIA1234567890", "AWS access key pattern"),
        (
            "database_url",
            "postgres://user:pass@localhost/db",
            "Database credentials in URL",
        ),
    ]

    for param_name, value, description in secret_tests:
        print(f"   Testing {description}:")
        suggestions = NodeValidator.validate_node_config(
            "CredentialManagerNode", {param_name: value}
        )

        if suggestions:
            for suggestion in suggestions:
                print(f"      ⚠️  {suggestion.message}")
        else:
            print("      ✅ No issues detected")

    # Test 2: Secure credential patterns
    print("\n2. Secure credential patterns:")

    secure_patterns = [
        ("${API_KEY}", "Environment variable reference"),
        ("vault://secret/api-key", "Vault reference"),
        ("aws://secrets/prod/api-key", "AWS Secrets Manager reference"),
    ]

    for pattern, description in secure_patterns:
        print(f"   Testing {description}: {pattern}")
        suggestions = NodeValidator.validate_node_config(
            "CredentialManagerNode", {"credential_value": pattern}
        )

        if not suggestions:
            print("      ✅ Secure pattern recognized")
        else:
            for suggestion in suggestions:
                print(f"      ℹ️  Note: {suggestion.message}")


def test_workflow_level_validation(env_info):
    """Test validation at the workflow level."""
    print("\n🔗 Testing Workflow-Level Validation...")

    # Create a realistic workflow with potential issues
    workflow = Workflow("validation_demo", "Comprehensive Validation Demo")

    print("\n1. Building workflow with various nodes:")

    # Add nodes with different validation scenarios
    nodes_to_add = [
        (
            "data_reader",
            CSVReaderNode,
            {"name": "data_reader", "file_path": str(env_info["test_csv"])},
        ),
        (
            "processor",
            PythonCodeNode,
            {
                "name": "processor",
                "code": """
import numpy as np

# Process the customer data
df = pd.DataFrame(data)
df['purchase_amount'] = pd.to_numeric(df['purchase_amount'])

# Calculate metrics
total_sales = df['purchase_amount'].sum()
avg_purchase = df['purchase_amount'].mean()
top_customer = df.loc[df['purchase_amount'].idxmax()]

result = {
    "total_sales": float(total_sales),
    "average_purchase": float(avg_purchase),
    "top_customer": {
        "name": top_customer['name'],
        "amount": float(top_customer['purchase_amount'])
    },
    "processed_at": datetime.now().isoformat(),
    "record_count": len(df)
}
""",
            },
        ),
    ]

    # Validate each node before adding
    for node_id, node_class, config in nodes_to_add:
        print(f"\n   Validating {node_id} ({node_class.__name__}):")

        suggestions = NodeValidator.validate_node_config(node_class.__name__, config)

        if suggestions:
            print("      ⚠️  Validation suggestions:")
            for suggestion in suggestions:
                print(f"         - {suggestion.message}")
        else:
            print("      ✅ No validation issues")

        # Add node to workflow
        workflow.add_node(node_id, node_class(**config))

    # Connect nodes
    workflow.connect("data_reader", "processor", {"data": "data"})

    # Test workflow execution
    print("\n2. Testing workflow execution:")
    try:
        runner = LocalRuntime()
        result = runner.execute(workflow)

        if result.get("success"):
            print("   ✅ Workflow executed successfully")
            processor_result = result["results"]["processor"]
            print(f"   📊 Results: {json.dumps(processor_result, indent=2)}")
        else:
            print(f"   ❌ Workflow execution failed: {result.get('error')}")

    except Exception as e:
        print(f"   ❌ Workflow execution error: {e}")


def demonstrate_custom_validation_rules():
    """Show how to create custom validation rules for specific use cases."""
    print("\n⚙️  Demonstrating Custom Validation Rules...")

    # Add organization-specific validation patterns
    from kailash.nodes.validation import ValidationSuggestion

    print("\n1. Adding custom validation patterns:")

    # Custom patterns for this organization
    custom_patterns = {
        r"prod[_-]?(?:key|token|secret)": ValidationSuggestion(
            message="Production secrets should not be hardcoded",
            code_example="Use credential_manager or environment variables",
            doc_link="https://docs.company.com/security/secrets",
        ),
        r"TODO|FIXME|HACK": ValidationSuggestion(
            message="Code contains unfinished implementations",
            code_example="Complete implementation before production deployment",
        ),
        r"localhost|127\.0\.0\.1": ValidationSuggestion(
            message="Localhost references may not work in production",
            code_example="Use configurable hostnames: ${DATABASE_HOST}",
        ),
        r"DROP\s+TABLE|DELETE\s+FROM.*WHERE\s+1=1": ValidationSuggestion(
            message="Potentially dangerous SQL operation detected",
            code_example="Use more specific WHERE clauses or confirm this is intentional",
        ),
    }

    # Add to validator (in real use, this would be done at application startup)
    NodeValidator.PARAMETER_PATTERNS.update(custom_patterns)

    print("   ✅ Added custom validation patterns")

    # Test custom patterns
    print("\n2. Testing custom patterns:")

    test_configs = [
        (
            "PythonCodeNode",
            {"code": "# TODO: implement this function\nresult = {}"},
            "Unfinished code",
        ),
        (
            "SQLDatabaseNode",
            {"query": "SELECT * FROM users WHERE id = 1", "host": "localhost"},
            "Localhost reference",
        ),
        ("CredentialManagerNode", {"prod_api_key": "secret123"}, "Production secret"),
        ("SQLDatabaseNode", {"query": "DELETE FROM logs WHERE 1=1"}, "Dangerous SQL"),
    ]

    for node_type, config, test_name in test_configs:
        print(f"\n   Testing {test_name}:")
        suggestions = NodeValidator.validate_node_config(node_type, config)

        if suggestions:
            for suggestion in suggestions:
                print(f"      ⚠️  {suggestion.message}")
                if suggestion.code_example:
                    print(f"         Better: {suggestion.code_example}")
        else:
            print("      ✅ No custom validation issues")


def main():
    """Run comprehensive validation tests."""
    print("🧪 Comprehensive Node Validation Testing")
    print("=" * 50)

    # Setup test environment
    env_info = setup_test_environment()

    # Run validation tests
    test_real_pythoncode_validation(env_info)
    test_sql_injection_validation(env_info)
    test_file_path_validation(env_info)
    test_llm_validation_with_ollama(env_info)
    test_credential_validation(env_info)
    test_workflow_level_validation(env_info)
    demonstrate_custom_validation_rules()

    print("\n" + "=" * 50)
    print("✅ Comprehensive validation testing completed!")
    print("\nKey benefits demonstrated:")
    print("   • Early error detection before workflow execution")
    print("   • Security issue identification (SQL injection, hardcoded secrets)")
    print("   • Performance optimization suggestions")
    print("   • Best practice recommendations")
    print("   • Custom validation rules for organization-specific requirements")
    print(
        "\n💡 Use NodeValidator to improve code quality and prevent production issues!"
    )


if __name__ == "__main__":
    main()
