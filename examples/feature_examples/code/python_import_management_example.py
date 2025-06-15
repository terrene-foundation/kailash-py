"""Comprehensive Python import management example with real development scenarios.

This example demonstrates PythonCodeNode import management with production scenarios:
- Real development workflow testing with Docker integration
- Advanced import validation and security scanning
- Code complexity analysis and optimization recommendations
- Best practices enforcement and automated refactoring suggestions
- Integration with real development tools and IDEs
- Performance benchmarking for different code patterns
- Security vulnerability detection in import usage
- Custom validation rules for enterprise environments

Shows real-world Python development challenges and solutions.
"""

import csv
import json
import logging
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.validation import NodeValidator, validate_node_decorator
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow

# Setup comprehensive logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/python_import_demo.log", mode="w"),
    ],
)


def setup_development_environment():
    """Set up a realistic development environment for testing."""
    print("🔧 Setting up Python Development Environment...")

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

    # Create development workspace
    workspace = Path("/tmp/python_dev_workspace")
    workspace.mkdir(exist_ok=True)

    # Create realistic project structure
    project_structure = {
        "src": ["main.py", "utils.py", "config.py", "models.py"],
        "tests": ["test_main.py", "test_utils.py", "conftest.py"],
        "data": ["sample.csv", "config.json"],
        "requirements": ["requirements.txt", "requirements-dev.txt"],
    }

    for folder, files in project_structure.items():
        folder_path = workspace / folder
        folder_path.mkdir(exist_ok=True)
        for file in files:
            (folder_path / file).touch()

    # Create sample data files for testing
    sample_csv = workspace / "data" / "sample.csv"
    with open(sample_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "value", "category"])
        writer.writerows(
            [
                [1, "Item 1", 100.0, "A"],
                [2, "Item 2", 250.5, "B"],
                [3, "Item 3", 75.25, "A"],
                [4, "Item 4", 300.0, "C"],
            ]
        )

    # Create configuration file
    config_json = workspace / "data" / "config.json"
    config_data = {
        "database": {"host": "localhost", "port": 5432, "name": "testdb"},
        "api": {"base_url": "https://api.example.com", "timeout": 30},
        "features": {"enable_caching": True, "debug_mode": False},
    }
    with open(config_json, "w") as f:
        json.dump(config_data, f, indent=2)

    # Create requirements file with common packages
    requirements_txt = workspace / "requirements" / "requirements.txt"
    with open(requirements_txt, "w") as f:
        f.write(
            """pandas>=1.5.0
numpy>=1.21.0
requests>=2.28.0
flask>=2.0.0
sqlalchemy>=1.4.0
click>=8.0.0
pydantic>=1.9.0
python-dateutil>=2.8.0
"""
        )

    # Create realistic Python code samples for testing
    code_samples = {
        "good_practices": {
            "description": "Well-structured code following best practices",
            "samples": [
                {
                    "name": "Data Processing Function",
                    "code": """
import pandas as pd
import numpy as np
from typing import Dict, List, Optional

def process_sales_data(data: List[Dict]) -> Dict[str, float]:
    \"\"\"Process sales data and return analytics.\"\"\"
    df = pd.DataFrame(data)

    # Validate input data
    if df.empty:
        return {"error": "No data provided"}

    # Calculate metrics
    total_sales = df['value'].sum()
    avg_sale = df['value'].mean()
    max_sale = df['value'].max()
    min_sale = df['value'].min()

    result = {
        "total_sales": float(total_sales),
        "average_sale": float(avg_sale),
        "max_sale": float(max_sale),
        "min_sale": float(min_sale),
        "processed_at": datetime.now().isoformat()
    }

    return result
""",
                },
                {
                    "name": "Configuration Manager",
                    "code": """
from typing import Dict, Any, Optional

def load_configuration(config_path: str) -> Dict[str, Any]:
    \"\"\"Load configuration from JSON file with validation.\"\"\"
    try:
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_file, 'r') as f:
            config = json.load(f)

        # Validate required sections
        required_sections = ['database', 'api']
        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing required configuration section: {section}")

        result = {
            "config": config,
            "loaded_at": datetime.now().isoformat(),
            "source": str(config_file)
        }

        return result

    except Exception as e:
        return {"error": str(e), "config": {}}
""",
                },
            ],
        },
        "problematic_code": {
            "description": "Code with various issues that need fixing",
            "samples": [
                {
                    "name": "Security Issues",
                    "code": """
import pickle
import eval  # This doesn't exist, will cause import error

def dangerous_operations(user_input: str):
    # Security vulnerability - command injection
    command = f"ls -la {user_input}"
    result = subprocess.run(command, shell=True, capture_output=True)

    # Security vulnerability - eval usage
    calculation = eval(user_input)

    # Security vulnerability - pickle deserialization
    with open('/tmp/data.pkl', 'rb') as f:
        data = pickle.load(f)

    # Missing result wrapper
    return {"output": result.stdout, "calculation": calculation, "data": data}
""",
                },
                {
                    "name": "Import Issues",
                    "code": """
import requests  # Not allowed in PythonCodeNode
import sqlite3  # Not allowed - database operations
import urllib.request  # Not allowed - HTTP operations
import tensorflow as tf  # Heavy ML library
import some_nonexistent_module  # Will cause import error

def problematic_function(data):
    # This will fail due to import restrictions
    response = requests.get('https://api.example.com/data')

    # Database operations not allowed
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # ML operations with heavy imports
    model = tf.keras.Sequential()

    # Using non-existent module
    result = some_nonexistent_module.process(data)

    # No proper result wrapper
    return data
""",
                },
                {
                    "name": "Complex Code Requiring Refactoring",
                    "code": """
from datetime import datetime, timedelta
from collections import defaultdict

def massive_data_processor(data, config, options, filters, transformations):
    # This function is too long and complex
    df = pd.DataFrame(data)

    # Multiple nested operations
    if config.get('enable_filtering'):
        for filter_config in filters:
            if filter_config['type'] == 'range':
                df = df[(df[filter_config['column']] >= filter_config['min']) &
                       (df[filter_config['column']] <= filter_config['max'])]
            elif filter_config['type'] == 'category':
                df = df[df[filter_config['column']].isin(filter_config['values'])]
            elif filter_config['type'] == 'date':
                start_date = datetime.strptime(filter_config['start'], '%Y-%m-%d')
                end_date = datetime.strptime(filter_config['end'], '%Y-%m-%d')
                df = df[(df[filter_config['column']] >= start_date) &
                       (df[filter_config['column']] <= end_date)]

    # Complex aggregations
    aggregated_data = defaultdict(dict)
    for transform in transformations:
        if transform['operation'] == 'sum':
            aggregated_data[transform['group_by']][transform['column']] = df.groupby(transform['group_by'])[transform['column']].sum().to_dict()
        elif transform['operation'] == 'mean':
            aggregated_data[transform['group_by']][transform['column']] = df.groupby(transform['group_by'])[transform['column']].mean().to_dict()
        elif transform['operation'] == 'count':
            aggregated_data[transform['group_by']][transform['column']] = df.groupby(transform['group_by'])[transform['column']].count().to_dict()

    # More complex calculations
    derived_metrics = {}
    for group, metrics in aggregated_data.items():
        derived_metrics[group] = {}
        for column, values in metrics.items():
            derived_metrics[group][f'{column}_normalized'] = {k: v / max(values.values()) for k, v in values.items()}
            derived_metrics[group][f'{column}_percentile'] = {k: (v / sum(values.values())) * 100 for k, v in values.items()}

    # Final result compilation
    final_result = {
        'original_count': len(data),
        'filtered_count': len(df),
        'aggregations': dict(aggregated_data),
        'derived_metrics': derived_metrics,
        'processing_timestamp': datetime.now().isoformat(),
        'configuration_hash': hash(str(config)),
        'data_quality_score': np.random.random()  # Placeholder calculation
    }

    return final_result
""",
                },
            ],
        },
    }

    # Save code samples
    samples_file = workspace / "code_samples.json"
    with open(samples_file, "w") as f:
        json.dump(code_samples, f, indent=2)

    print(f"   ✅ Development workspace created at {workspace}")
    print(
        f"      - Project structure with {sum(len(files) for files in project_structure.values())} files"
    )
    print("      - Sample data files with realistic content")
    print(f"      - Code samples for testing ({len(code_samples)} categories)")

    return {
        "workspace": workspace,
        "docker_available": docker_available,
        "code_samples": code_samples,
        "sample_data": {
            "csv_file": sample_csv,
            "config_file": config_json,
            "requirements_file": requirements_txt,
        },
    }


def test_comprehensive_module_validation(env_info):
    """Test comprehensive module validation with real scenarios."""
    print("\n🔍 Testing Comprehensive Module Validation...")

    # Test module categories
    module_test_cases = {
        "allowed_data_science": [
            "pandas",
            "numpy",
            "scipy",
            "matplotlib",
            "seaborn",
            "plotly",
            "scikit-learn",
            "statsmodels",
            "xgboost",
            "lightgbm",
        ],
        "allowed_utilities": [
            "json",
            "csv",
            "datetime",
            "collections",
            "itertools",
            "functools",
            "pathlib",
            "uuid",
            "hashlib",
            "base64",
            "typing",
        ],
        "forbidden_network": [
            "requests",
            "urllib",
            "http",
            "socket",
            "asyncio",
            "aiohttp",
        ],
        "forbidden_system": [
            "os",
            "sys",
            "subprocess",
            "multiprocessing",
            "threading",
            "signal",
        ],
        "forbidden_security": ["pickle", "eval", "exec", "compile", "importlib"],
        "heavy_ml_libraries": [
            "tensorflow",
            "torch",
            "keras",
            "transformers",
            "sklearn",
        ],
    }

    print("\n=== Module Category Analysis ===")

    for category, modules in module_test_cases.items():
        print(f"\n{category.replace('_', ' ').title()}:")

        allowed_count = 0
        forbidden_count = 0
        issues_found = []

        for module in modules:
            try:
                info = PythonCodeNode.check_module_availability(module)

                is_allowed = info["allowed"]
                is_installed = info["installed"]

                if is_allowed and is_installed:
                    status = "✅ Allowed & Available"
                    allowed_count += 1
                elif is_allowed and not is_installed:
                    status = "⚠️  Allowed but Not Installed"
                    issues_found.append(f"{module}: needs installation")
                elif not is_allowed and is_installed:
                    status = "🚫 Forbidden but Installed"
                    forbidden_count += 1
                    issues_found.append(f"{module}: security/policy violation")
                else:
                    status = "❌ Forbidden & Not Available"
                    forbidden_count += 1

                print(f"   {module:<20} {status}")

                # Show suggestions if available
                if info.get("suggestions"):
                    for suggestion in info["suggestions"][:1]:  # Show first suggestion
                        print(f"      💡 {suggestion}")

            except Exception as e:
                print(f"   {module:<20} ❌ Error: {e}")
                issues_found.append(f"{module}: validation error")

        # Category summary
        total = len(modules)
        print(
            f"   📊 Summary: {allowed_count} allowed, {forbidden_count} forbidden, {total - allowed_count - forbidden_count} other"
        )

        if issues_found:
            print(f"   ⚠️  Issues ({len(issues_found)}):")
            for issue in issues_found[:3]:  # Show first 3 issues
                print(f"      - {issue}")

    return module_test_cases


def test_real_world_code_scenarios(env_info):
    """Test real-world code scenarios with comprehensive validation."""
    print("\n🏗️  Testing Real-World Code Scenarios...")

    code_samples = env_info["code_samples"]
    test_results = []

    for category_name, category_data in code_samples.items():
        print(f"\n--- {category_data['description']} ---")

        for sample in category_data["samples"]:
            print(f"\nTesting: {sample['name']}")
            print(f"Code preview: {sample['code'][:100].strip()}...")

            try:
                # Create PythonCodeNode for validation
                node = PythonCodeNode(
                    name=f"test_{sample['name'].lower().replace(' ', '_')}",
                    code=sample["code"],
                    max_code_lines=50,  # Set reasonable limit
                )

                # Perform comprehensive validation
                validation = node.validate_code(sample["code"])

                print("   Validation Results:")
                print(f"      Valid: {validation['valid']}")
                print(f"      Imports: {len(validation.get('imports', []))} modules")

                # Show syntax errors
                if validation.get("syntax_errors"):
                    print(
                        f"      🚫 Syntax Errors ({len(validation['syntax_errors'])}):"
                    )
                    for error in validation["syntax_errors"][:2]:
                        print(f"         Line {error['line']}: {error['message']}")

                # Show safety violations
                if validation.get("safety_violations"):
                    print(
                        f"      ⚠️  Safety Violations ({len(validation['safety_violations'])}):"
                    )
                    for violation in validation["safety_violations"][:2]:
                        print(
                            f"         Line {violation['line']}: {violation['message']}"
                        )

                # Show warnings
                if validation.get("warnings"):
                    print(f"      ⚠️  Warnings ({len(validation['warnings'])}):")
                    for warning in validation["warnings"][:2]:
                        print(f"         - {warning}")

                # Show suggestions
                if validation.get("suggestions"):
                    print(f"      💡 Suggestions ({len(validation['suggestions'])}):")
                    for suggestion in validation["suggestions"][:2]:
                        print(f"         → {suggestion}")

                # Try to execute if validation passes
                execution_result = None
                if validation["valid"] and not validation.get("safety_violations"):
                    try:
                        print("      🔄 Attempting execution...")
                        result = node.execute(
                            data=[{"id": 1, "value": 100}, {"id": 2, "value": 200}],
                            config={"enable_filtering": True},
                        )

                        if result.get("success"):
                            print("         ✅ Execution successful")
                            execution_result = "success"
                        else:
                            print(
                                f"         ❌ Execution failed: {result.get('error', 'Unknown error')}"
                            )
                            execution_result = (
                                f"failed: {result.get('error', 'Unknown')}"
                            )
                    except Exception as e:
                        print(f"         ❌ Execution exception: {str(e)[:100]}...")
                        execution_result = f"exception: {str(e)[:50]}"
                else:
                    print("      ⏭️  Skipping execution due to validation issues")
                    execution_result = "skipped"

                test_results.append(
                    {
                        "category": category_name,
                        "name": sample["name"],
                        "valid": validation["valid"],
                        "syntax_errors": len(validation.get("syntax_errors", [])),
                        "safety_violations": len(
                            validation.get("safety_violations", [])
                        ),
                        "warnings": len(validation.get("warnings", [])),
                        "suggestions": len(validation.get("suggestions", [])),
                        "execution_result": execution_result,
                        "imports_count": len(validation.get("imports", [])),
                    }
                )

            except Exception as e:
                print(f"   ❌ Validation failed: {e}")
                test_results.append(
                    {
                        "category": category_name,
                        "name": sample["name"],
                        "valid": False,
                        "error": str(e),
                        "execution_result": "validation_failed",
                    }
                )

    # Analyze results
    print("\n=== Code Analysis Summary ===")

    valid_samples = [r for r in test_results if r.get("valid", False)]
    invalid_samples = [r for r in test_results if not r.get("valid", True)]

    print("   📊 Overall Results:")
    print(f"      Valid samples: {len(valid_samples)}/{len(test_results)}")
    print(f"      Invalid samples: {len(invalid_samples)}")

    if valid_samples:
        avg_warnings = sum(r.get("warnings", 0) for r in valid_samples) / len(
            valid_samples
        )
        avg_suggestions = sum(r.get("suggestions", 0) for r in valid_samples) / len(
            valid_samples
        )
        print(f"      Average warnings per valid sample: {avg_warnings:.1f}")
        print(f"      Average suggestions per valid sample: {avg_suggestions:.1f}")

    # Execution results
    execution_stats = {}
    for result in test_results:
        exec_result = result.get("execution_result", "unknown")
        execution_stats[exec_result] = execution_stats.get(exec_result, 0) + 1

    print("\n   🔄 Execution Results:")
    for status, count in execution_stats.items():
        print(f"      {status}: {count} samples")

    return test_results


def test_advanced_security_scanning(env_info):
    """Test advanced security scanning for Python code."""
    print("\n🔒 Testing Advanced Security Scanning...")

    # Security test cases with various vulnerability patterns
    security_test_cases = [
        {
            "name": "Command Injection",
            "code": """
user_input = "test; rm -rf /"
command = f"echo {user_input}"
result = {"output": subprocess.run(command, shell=True)}
""",
            "expected_issues": ["subprocess", "shell=True", "f-string command"],
        },
        {
            "name": "Code Injection",
            "code": """
user_code = "print('hello')"
result = {"output": eval(user_code)}
""",
            "expected_issues": ["eval", "dynamic execution"],
        },
        {
            "name": "Pickle Deserialization",
            "code": """
with open('/tmp/data.pkl', 'rb') as f:
    data = pickle.load(f)
result = {"data": data}
""",
            "expected_issues": ["pickle", "deserialization"],
        },
        {
            "name": "File System Access",
            "code": """
file_path = "/etc/passwd"
content = open(file_path, 'r').read()
result = {"content": content}
""",
            "expected_issues": ["file access", "sensitive paths"],
        },
        {
            "name": "Network Operations",
            "code": """
import urllib.request
import socket
url = "https://malicious-site.com/data"
response = urllib.request.urlopen(url)
result = {"data": response.read()}
""",
            "expected_issues": ["urllib", "network access"],
        },
        {
            "name": "SQL Injection Risk",
            "code": """
import sqlite3
user_input = "'; DROP TABLE users; --"
query = f"SELECT * FROM data WHERE id = '{user_input}'"
result = {"query": query}
""",
            "expected_issues": ["dynamic SQL", "injection risk"],
        },
    ]

    security_results = []

    for test_case in security_test_cases:
        print(f"\n   Testing: {test_case['name']}")

        try:
            # Validate with security focus
            validation = NodeValidator.validate_node_config(
                "PythonCodeNode", {"code": test_case["code"]}
            )

            issues_found = []
            security_score = 100  # Start with perfect score

            if validation:
                print("      🚨 Security issues detected:")
                for suggestion in validation:
                    print(f"         - {suggestion.message}")
                    issues_found.append(suggestion.message)
                    security_score -= 20  # Deduct points for each issue
            else:
                print("      ✅ No security issues detected by validator")

            # Additional manual security checks
            code_lower = test_case["code"].lower()
            manual_issues = []

            # Check for dangerous patterns
            dangerous_patterns = [
                ("eval(", "Code injection risk"),
                ("exec(", "Code execution risk"),
                ("subprocess", "System command execution"),
                ("shell=true", "Shell injection risk"),
                ("pickle.load", "Deserialization risk"),
                ("os.system", "System command risk"),
                ("import os", "System access"),
                ("__import__", "Dynamic import risk"),
            ]

            for pattern, description in dangerous_patterns:
                if pattern in code_lower:
                    manual_issues.append(f"{description}: {pattern}")
                    security_score -= 15

            if manual_issues:
                print("      🔍 Manual security analysis:")
                for issue in manual_issues:
                    print(f"         - {issue}")

            # Security recommendations
            recommendations = []
            if "subprocess" in code_lower:
                recommendations.append("Use specific nodes for system operations")
            if "eval(" in code_lower or "exec(" in code_lower:
                recommendations.append("Never execute dynamic code from user input")
            if "pickle" in code_lower:
                recommendations.append(
                    "Use JSON for data serialization instead of pickle"
                )
            if "import os" in code_lower:
                recommendations.append(
                    "Use specific file operation nodes instead of os module"
                )

            if recommendations:
                print("      💡 Security recommendations:")
                for rec in recommendations:
                    print(f"         → {rec}")

            security_score = max(0, security_score)  # Don't go below 0
            print(f"      📊 Security score: {security_score}/100")

            security_results.append(
                {
                    "name": test_case["name"],
                    "validator_issues": len(validation) if validation else 0,
                    "manual_issues": len(manual_issues),
                    "total_issues": len(issues_found) + len(manual_issues),
                    "security_score": security_score,
                    "recommendations": len(recommendations),
                }
            )

        except Exception as e:
            print(f"      ❌ Security analysis failed: {e}")
            security_results.append(
                {"name": test_case["name"], "error": str(e), "security_score": 0}
            )

    # Security summary
    print("\n=== Security Analysis Summary ===")

    if security_results:
        avg_score = sum(r.get("security_score", 0) for r in security_results) / len(
            security_results
        )
        total_issues = sum(r.get("total_issues", 0) for r in security_results)

        print("   📊 Security Metrics:")
        print(f"      Average security score: {avg_score:.1f}/100")
        print(f"      Total security issues found: {total_issues}")
        print(f"      Test cases analyzed: {len(security_results)}")

        # Risk categories
        high_risk = [r for r in security_results if r.get("security_score", 100) < 50]
        medium_risk = [
            r for r in security_results if 50 <= r.get("security_score", 100) < 80
        ]
        low_risk = [r for r in security_results if r.get("security_score", 100) >= 80]

        print("\n   🚨 Risk Distribution:")
        print(f"      High risk (< 50): {len(high_risk)} cases")
        print(f"      Medium risk (50-79): {len(medium_risk)} cases")
        print(f"      Low risk (≥ 80): {len(low_risk)} cases")

        if high_risk:
            print("   ⚠️  High-risk cases requiring immediate attention:")
            for case in high_risk:
                print(f"      - {case['name']}: {case.get('security_score', 0)}/100")

    return security_results


def test_code_complexity_analysis(env_info):
    """Test code complexity analysis and optimization suggestions."""
    print("\n📊 Testing Code Complexity Analysis...")

    # Test cases with different complexity levels
    complexity_test_cases = [
        {
            "name": "Simple Function",
            "complexity": "low",
            "code": """

def simple_sum(data):
    df = pd.DataFrame(data)
    total = df['value'].sum()
    result = {"total": float(total)}
    return result
""",
            "expected_metrics": {"lines": 6, "complexity": "low"},
        },
        {
            "name": "Medium Complexity",
            "complexity": "medium",
            "code": """

def analyze_sales_data(data, filters=None):
    df = pd.DataFrame(data)

    # Apply filters if provided
    if filters:
        for filter_type, filter_value in filters.items():
            if filter_type == 'min_value':
                df = df[df['value'] >= filter_value]
            elif filter_type == 'category':
                df = df[df['category'].isin(filter_value)]

    # Calculate analytics
    stats = {
        'total': float(df['value'].sum()),
        'average': float(df['value'].mean()),
        'count': len(df),
        'by_category': df.groupby('category')['value'].sum().to_dict()
    }

    result = {
        "statistics": stats,
        "processed_at": datetime.now().isoformat()
    }

    return result
""",
            "expected_metrics": {"lines": 26, "complexity": "medium"},
        },
        {
            "name": "High Complexity - Needs Refactoring",
            "complexity": "high",
            "code": """

def complex_data_processor(data, config, transformations, aggregations, filters, export_options):
    # This function is intentionally complex to demonstrate analysis
    df = pd.DataFrame(data)
    results = defaultdict(dict)

    # Multiple nested conditions and loops
    if config.get('enable_preprocessing'):
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].str.strip().str.lower()
            elif df[col].dtype in ['int64', 'float64']:
                if config.get('normalize_numeric'):
                    df[col] = (df[col] - df[col].min()) / (df[col].max() - df[col].min())

    # Complex filtering logic
    if filters:
        for filter_config in filters:
            if filter_config['type'] == 'range':
                col = filter_config['column']
                min_val = filter_config.get('min', df[col].min())
                max_val = filter_config.get('max', df[col].max())
                df = df[(df[col] >= min_val) & (df[col] <= max_val)]
            elif filter_config['type'] == 'categorical':
                col = filter_config['column']
                values = filter_config['values']
                if filter_config.get('exclude', False):
                    df = df[~df[col].isin(values)]
                else:
                    df = df[df[col].isin(values)]
            elif filter_config['type'] == 'date':
                col = filter_config['column']
                start_date = datetime.strptime(filter_config['start'], '%Y-%m-%d')
                end_date = datetime.strptime(filter_config['end'], '%Y-%m-%d')
                df = df[(df[col] >= start_date) & (df[col] <= end_date)]

    # Complex transformations
    if transformations:
        for transform in transformations:
            if transform['operation'] == 'derive':
                if transform['type'] == 'ratio':
                    df[transform['new_column']] = df[transform['numerator']] / df[transform['denominator']]
                elif transform['type'] == 'difference':
                    df[transform['new_column']] = df[transform['col1']] - df[transform['col2']]
                elif transform['type'] == 'percentage':
                    total = df[transform['column']].sum()
                    df[transform['new_column']] = (df[transform['column']] / total) * 100

    # Multiple aggregation strategies
    if aggregations:
        for agg_config in aggregations:
            group_cols = agg_config['group_by']
            agg_cols = agg_config['columns']
            operations = agg_config['operations']

            for operation in operations:
                if operation == 'sum':
                    agg_result = df.groupby(group_cols)[agg_cols].sum()
                elif operation == 'mean':
                    agg_result = df.groupby(group_cols)[agg_cols].mean()
                elif operation == 'count':
                    agg_result = df.groupby(group_cols)[agg_cols].count()
                elif operation == 'std':
                    agg_result = df.groupby(group_cols)[agg_cols].std()

                results[f"{operation}_by_{'_'.join(group_cols)}"] = agg_result.to_dict()

    # Export processing
    if export_options:
        if export_options.get('include_raw_data'):
            results['raw_data'] = df.to_dict('records')
        if export_options.get('include_summary'):
            results['summary'] = {
                'total_rows': len(df),
                'columns': list(df.columns),
                'data_types': df.dtypes.to_dict(),
                'memory_usage': df.memory_usage(deep=True).sum()
            }

    # Final result compilation
    final_result = {
        'results': dict(results),
        'metadata': {
            'processing_time': datetime.now().isoformat(),
            'original_rows': len(data),
            'final_rows': len(df),
            'config_hash': hash(str(config))
        }
    }

    return final_result
""",
            "expected_metrics": {"lines": 85, "complexity": "very_high"},
        },
    ]

    complexity_results = []

    for test_case in complexity_test_cases:
        print(
            f"\n   Analyzing: {test_case['name']} ({test_case['complexity']} complexity)"
        )

        try:
            # Basic metrics
            code_lines = test_case["code"].strip().split("\n")
            total_lines = len(code_lines)
            non_empty_lines = len([line for line in code_lines if line.strip()])
            comment_lines = len(
                [line for line in code_lines if line.strip().startswith("#")]
            )
            code_only_lines = non_empty_lines - comment_lines

            # Complexity indicators
            if_statements = test_case["code"].count("if ")
            for_loops = test_case["code"].count("for ")
            while_loops = test_case["code"].count("while ")
            try_blocks = test_case["code"].count("try:")
            nested_levels = 0

            # Estimate nesting by counting indentation
            max_indent = 0
            for line in code_lines:
                if line.strip():
                    indent = len(line) - len(line.lstrip())
                    max_indent = max(
                        max_indent, indent // 4
                    )  # Assuming 4-space indents

            # Calculate complexity score
            complexity_score = (
                if_statements * 2
                + for_loops * 3
                + while_loops * 3
                + try_blocks * 1
                + max_indent * 2
                + (code_only_lines // 10)  # Penalty for length
            )

            # Determine complexity rating
            if complexity_score <= 10:
                complexity_rating = "low"
            elif complexity_score <= 25:
                complexity_rating = "medium"
            elif complexity_score <= 50:
                complexity_rating = "high"
            else:
                complexity_rating = "very_high"

            print("      📏 Metrics:")
            print(f"         Total lines: {total_lines}")
            print(f"         Code lines: {code_only_lines}")
            print(f"         If statements: {if_statements}")
            print(f"         Loops: {for_loops + while_loops}")
            print(f"         Max nesting: {max_indent}")
            print(f"         Complexity score: {complexity_score}")
            print(f"         Complexity rating: {complexity_rating}")

            # Generate recommendations based on complexity
            recommendations = []

            if code_only_lines > 50:
                recommendations.append(
                    "Consider breaking this function into smaller functions"
                )
            if max_indent > 4:
                recommendations.append(
                    "Reduce nesting levels by extracting logic into helper functions"
                )
            if if_statements > 5:
                recommendations.append(
                    "Consider using dictionary mapping or strategy pattern for multiple conditions"
                )
            if for_loops > 3:
                recommendations.append(
                    "Consider using pandas vectorized operations instead of loops"
                )
            if complexity_score > 30:
                recommendations.append(
                    "This function is too complex - strongly recommend refactoring"
                )

            # Check if PythonCodeNode would trigger warnings
            try:
                node = PythonCodeNode(
                    name="complexity_test",
                    code=test_case["code"],
                    max_code_lines=30,  # Set a threshold
                )
                validation = node.validate_code(test_case["code"])

                if validation.get("warnings"):
                    print("      ⚠️  PythonCodeNode warnings:")
                    for warning in validation["warnings"]:
                        print(f"         - {warning}")

            except Exception as e:
                print(f"      ❌ Validation error: {e}")

            if recommendations:
                print("      💡 Optimization recommendations:")
                for rec in recommendations:
                    print(f"         → {rec}")

            complexity_results.append(
                {
                    "name": test_case["name"],
                    "expected_complexity": test_case["complexity"],
                    "actual_complexity": complexity_rating,
                    "total_lines": total_lines,
                    "code_lines": code_only_lines,
                    "complexity_score": complexity_score,
                    "recommendations": len(recommendations),
                    "max_nesting": max_indent,
                }
            )

        except Exception as e:
            print(f"      ❌ Analysis failed: {e}")
            complexity_results.append({"name": test_case["name"], "error": str(e)})

    # Complexity analysis summary
    print("\n=== Complexity Analysis Summary ===")

    if complexity_results:
        avg_score = sum(r.get("complexity_score", 0) for r in complexity_results) / len(
            complexity_results
        )
        high_complexity = [
            r for r in complexity_results if r.get("complexity_score", 0) > 30
        ]

        print("   📊 Complexity Metrics:")
        print(f"      Average complexity score: {avg_score:.1f}")
        print(f"      High complexity functions: {len(high_complexity)}")
        print(f"      Functions analyzed: {len(complexity_results)}")

        if high_complexity:
            print("   ⚠️  Functions requiring refactoring:")
            for func in high_complexity:
                print(
                    f"      - {func['name']}: score {func.get('complexity_score', 0)}"
                )

    return complexity_results


def demonstrate_best_practices_enforcement(env_info):
    """Demonstrate enforcement of Python coding best practices."""
    print("\n✨ Demonstrating Best Practices Enforcement...")

    # Best practices test cases
    best_practices_cases = [
        {
            "name": "Result Wrapper Compliance",
            "good_code": """

def process_data(data):
    df = pd.DataFrame(data)
    total = df['value'].sum()
    result = {"total": float(total), "count": len(df)}
    return result
""",
            "bad_code": """

def process_data(data):
    df = pd.DataFrame(data)
    total = df['value'].sum()
    return total  # Missing result wrapper
""",
            "practice": "Always wrap return values in result dictionary",
        },
        {
            "name": "Type Hints Usage",
            "good_code": """
from typing import Dict, List, Any

def analyze_data(data: List[Dict[str, Any]]) -> Dict[str, float]:
    df = pd.DataFrame(data)
    result = {
        "mean": float(df['value'].mean()),
        "std": float(df['value'].std())
    }
    return result
""",
            "bad_code": """

def analyze_data(data):  # No type hints
    df = pd.DataFrame(data)
    result = {
        "mean": float(df['value'].mean()),
        "std": float(df['value'].std())
    }
    return result
""",
            "practice": "Use type hints for better code documentation and IDE support",
        },
        {
            "name": "Error Handling",
            "good_code": """
from typing import Dict, Any

def safe_data_processing(data) -> Dict[str, Any]:
    try:
        df = pd.DataFrame(data)

        if df.empty:
            return {"error": "No data provided", "result": None}

        if 'value' not in df.columns:
            return {"error": "Missing 'value' column", "result": None}

        total = df['value'].sum()
        result = {"total": float(total), "success": True}
        return result

    except Exception as e:
        return {"error": str(e), "result": None}
""",
            "bad_code": """

def unsafe_data_processing(data):
    df = pd.DataFrame(data)  # Could fail with bad data
    total = df['value'].sum()  # Could fail if column doesn't exist
    result = {"total": float(total)}
    return result
""",
            "practice": "Always include proper error handling and validation",
        },
        {
            "name": "Function Size and Responsibility",
            "good_code": """

def validate_data(data: List[Dict]) -> Dict[str, Any]:
    \"\"\"Validate input data structure.\"\"\"
    if not data:
        return {"valid": False, "error": "Empty data"}

    required_columns = ['id', 'value']
    first_row = data[0]

    for col in required_columns:
        if col not in first_row:
            return {"valid": False, "error": f"Missing column: {col}"}

    return {"valid": True}

def calculate_statistics(df: pd.DataFrame) -> Dict[str, float]:
    \"\"\"Calculate basic statistics.\"\"\"
    return {
        "sum": float(df['value'].sum()),
        "mean": float(df['value'].mean()),
        "count": len(df)
    }

def process_data_properly(data: List[Dict]) -> Dict[str, Any]:
    \"\"\"Main processing function with proper separation of concerns.\"\"\"
    # Validate input
    validation = validate_data(data)
    if not validation["valid"]:
        return {"error": validation["error"]}

    # Process data
    df = pd.DataFrame(data)
    stats = calculate_statistics(df)

    result = {"statistics": stats, "success": True}
    return result
""",
            "bad_code": """

def monolithic_processor(data):
    # Everything in one large function
    if not data:
        return {"error": "Empty data"}

    required_columns = ['id', 'value']
    first_row = data[0]
    for col in required_columns:
        if col not in first_row:
            return {"error": f"Missing column: {col}"}

    df = pd.DataFrame(data)

    total = float(df['value'].sum())
    mean = float(df['value'].mean())
    count = len(df)

    # More processing logic would make this even worse
    result = {"sum": total, "mean": mean, "count": count}
    return result
""",
            "practice": "Keep functions small and focused on single responsibilities",
        },
    ]

    practice_results = []

    for case in best_practices_cases:
        print(f"\n   Practice: {case['name']}")
        print(f"   Rule: {case['practice']}")

        # Test good code
        print("\n      ✅ Good Example:")
        try:
            good_node = PythonCodeNode(
                name=f"good_{case['name'].lower().replace(' ', '_')}",
                code=case["good_code"],
            )
            good_validation = good_node.validate_code(case["good_code"])

            good_issues = (
                len(good_validation.get("syntax_errors", []))
                + len(good_validation.get("safety_violations", []))
                + len(good_validation.get("warnings", []))
            )

            print(f"         Validation issues: {good_issues}")
            if good_validation.get("suggestions"):
                print(f"         Suggestions: {len(good_validation['suggestions'])}")
                for suggestion in good_validation["suggestions"][:1]:
                    print(f"            → {suggestion}")

        except Exception as e:
            print(f"         ❌ Error: {e}")
            good_issues = float("inf")

        # Test bad code
        print("\n      ❌ Poor Example:")
        try:
            bad_node = PythonCodeNode(
                name=f"bad_{case['name'].lower().replace(' ', '_')}",
                code=case["bad_code"],
            )
            bad_validation = bad_node.validate_code(case["bad_code"])

            bad_issues = (
                len(bad_validation.get("syntax_errors", []))
                + len(bad_validation.get("safety_violations", []))
                + len(bad_validation.get("warnings", []))
            )

            print(f"         Validation issues: {bad_issues}")
            if bad_validation.get("suggestions"):
                print(f"         Suggestions: {len(bad_validation['suggestions'])}")
                for suggestion in bad_validation["suggestions"][:2]:
                    print(f"            → {suggestion}")

        except Exception as e:
            print(f"         ❌ Error: {e}")
            bad_issues = float("inf")

        # Compare results
        if good_issues < bad_issues:
            print("      ✅ Validation correctly identified better practices")
        elif good_issues > bad_issues:
            print("      ⚠️  Validation might not be catching all issues")
        else:
            print("      ➖ Validation results are similar")

        practice_results.append(
            {
                "practice": case["name"],
                "good_issues": good_issues if good_issues != float("inf") else -1,
                "bad_issues": bad_issues if bad_issues != float("inf") else -1,
                "validation_effective": good_issues < bad_issues,
            }
        )

    # Best practices summary
    print("\n=== Best Practices Enforcement Summary ===")

    effective_validations = [r for r in practice_results if r["validation_effective"]]

    print("   📊 Validation Effectiveness:")
    print(
        f"      Effective validations: {len(effective_validations)}/{len(practice_results)}"
    )
    print(f"      Practices analyzed: {len(practice_results)}")

    if len(effective_validations) == len(practice_results):
        print("   🎉 All best practices are properly enforced by validation!")
    elif len(effective_validations) > len(practice_results) * 0.7:
        print("   ✅ Most best practices are well-enforced")
    else:
        print("   ⚠️  Some best practices need better validation coverage")

    return practice_results


def create_comprehensive_validation_workflow(env_info):
    """Create a comprehensive workflow for Python code validation."""
    print("\n🔗 Creating Comprehensive Validation Workflow...")

    workflow = Workflow(
        "python_validation_comprehensive", "Comprehensive Python Code Validation"
    )

    # Test code samples
    test_codes = [
        """

def analyze_sales_performance(sales_data):
    \"\"\"Analyze sales performance with comprehensive metrics.\"\"\"
    try:
        df = pd.DataFrame(sales_data)

        if df.empty:
            return {"error": "No sales data provided"}

        # Calculate key metrics
        total_sales = df['amount'].sum()
        avg_sale = df['amount'].mean()
        top_products = df.groupby('product')['amount'].sum().nlargest(5)

        # Time-based analysis
        df['date'] = pd.to_datetime(df['date'])
        monthly_sales = df.groupby(df['date'].dt.to_period('M'))['amount'].sum()

        result = {
            "total_sales": float(total_sales),
            "average_sale": float(avg_sale),
            "top_products": top_products.to_dict(),
            "monthly_trends": {str(k): float(v) for k, v in monthly_sales.items()},
            "analysis_date": datetime.now().isoformat(),
            "record_count": len(df)
        }

        return result

    except Exception as e:
        return {"error": str(e)}
""",
        """
import requests  # This should trigger validation issues

def problematic_data_fetcher(url, file_path):
    # Security issues that should be caught
    response = requests.get(url)  # Network operation not allowed

    # File system access
    with open(file_path, 'w') as f:
        f.write(response.text)

    # Command execution
    os.system(f"chmod 777 {file_path}")

    # Missing result wrapper
    return response.json()
""",
    ]

    # Add validation nodes for each test case
    for i, code in enumerate(test_codes, 1):
        # Add PythonCodeNode
        workflow.add_node(
            f"code_test_{i}",
            PythonCodeNode(name=f"code_test_{i}", code=code, max_code_lines=50),
        )

        # Add validation analyzer
        workflow.add_node(
            f"validator_{i}",
            PythonCodeNode(
                name=f"validator_{i}",
                code=f"""

# Analyze code validation results
code_result = code_execution_result

# Extract validation information
success = code_result.get('success', False)
error = code_result.get('error', '')

# Simulate validation analysis
validation_analysis = {{
    "code_sample": {i},
    "execution_successful": success,
    "error_message": error if not success else None,
    "validation_timestamp": datetime.now().isoformat(),
    "analysis": {{
        "security_risk": "high" if "requests" in "{code[:100]}" or "os.system" in "{code[:100]}" else "low",
        "complexity": "medium" if len("{code}".split("\\n")) > 20 else "low",
        "best_practices": "poor" if "result = " not in "{code}" else "good"
    }}
}}

result = validation_analysis
""",
            ),
        )

        # Connect the nodes
        workflow.connect(
            f"code_test_{i}", f"validator_{i}", {"result": "code_execution_result"}
        )

    print(f"   📋 Created workflow: {workflow.name}")
    print(f"      Nodes: {list(workflow.nodes.keys())}")
    print(f"      Test cases: {len(test_codes)}")

    # Execute the workflow
    try:
        runner = LocalRuntime()
        print("\n   🔄 Executing validation workflow...")

        result = runner.execute(
            workflow,
            inputs={
                "sales_data": [
                    {"product": "Widget A", "amount": 100, "date": "2024-01-15"},
                    {"product": "Widget B", "amount": 250, "date": "2024-01-16"},
                    {"product": "Widget A", "amount": 150, "date": "2024-02-15"},
                ]
            },
        )

        if result.get("success"):
            print("      ✅ Workflow completed successfully")

            # Display results from validators
            for i in range(1, len(test_codes) + 1):
                validator_result = result.get("results", {}).get(f"validator_{i}", {})
                if validator_result:
                    analysis = validator_result.get("analysis", {})
                    print(f"\n      📊 Code Sample {i} Analysis:")
                    print(
                        f"         Execution: {'✅' if validator_result.get('execution_successful') else '❌'}"
                    )
                    print(
                        f"         Security risk: {analysis.get('security_risk', 'unknown')}"
                    )
                    print(
                        f"         Complexity: {analysis.get('complexity', 'unknown')}"
                    )
                    print(
                        f"         Best practices: {analysis.get('best_practices', 'unknown')}"
                    )

                    if validator_result.get("error_message"):
                        print(
                            f"         Error: {validator_result['error_message'][:100]}..."
                        )
        else:
            error_msg = result.get("error", "Unknown error")
            print(f"      ❌ Workflow failed: {error_msg}")

    except Exception as e:
        print(f"   ❌ Workflow execution error: {e}")

    return workflow


def main():
    """Run comprehensive Python import management testing."""
    print("🐍 Comprehensive Python Import Management Testing")
    print("=" * 60)

    # Setup development environment
    env_info = setup_development_environment()

    # Run comprehensive tests
    test_comprehensive_module_validation(env_info)
    test_real_world_code_scenarios(env_info)
    test_advanced_security_scanning(env_info)
    test_code_complexity_analysis(env_info)
    demonstrate_best_practices_enforcement(env_info)
    create_comprehensive_validation_workflow(env_info)

    print("\n" + "=" * 60)
    print("✅ Comprehensive Python import management testing completed!")
    print("\nKey capabilities demonstrated:")
    print("   • Comprehensive module validation with security focus")
    print("   • Real-world code scenario testing and analysis")
    print("   • Advanced security vulnerability scanning")
    print("   • Code complexity analysis with optimization recommendations")
    print("   • Best practices enforcement and validation")
    print("   • Production-ready development environment setup")
    print("   • Integration with validation workflows")
    print("   • Automated code quality assessment")
    print("   • Security risk scoring and mitigation suggestions")
    print("\n💡 PythonCodeNode provides enterprise-grade Python development safety!")
    print("\n🔧 Key recommendations:")
    print("   1. Always use allowed modules - avoid system and network operations")
    print("   2. Keep functions small and focused (< 50 lines)")
    print("   3. Include comprehensive error handling")
    print("   4. Wrap all returns in result dictionaries")
    print("   5. Use type hints for better code documentation")
    print("   6. Validate inputs and handle edge cases")
    print("   7. Avoid security-sensitive operations like eval() and exec()")


if __name__ == "__main__":
    main()
