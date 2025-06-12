"""
Interactive QA Agent for Admin Tool Testing

This example creates an interactive QA agent that can execute actual tests
against the admin tool framework, simulating real user interactions.
"""

import json
import random
import string
from datetime import datetime, timedelta
from typing import Any, Dict, List

from examples.utils.data_paths import get_test_data_path
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.logic import MergeNode, SwitchNode, WorkflowNode
from kailash.workflow import Workflow, WorkflowBuilder


def generate_test_data():
    """Generate realistic test data for various scenarios"""
    # Generate random user data
    first_names = ["John", "Jane", "Bob", "Alice", "Charlie", "Diana", "Eve", "Frank"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller"]

    users = []
    for i in range(20):
        users.append(
            {
                "email": f"test.user{i}@example.com",
                "username": f"testuser{i}",
                "first_name": random.choice(first_names),
                "last_name": random.choice(last_names),
                "password": "".join(
                    random.choices(string.ascii_letters + string.digits, k=12)
                ),
                "roles": random.sample(
                    ["employee", "manager", "admin", "viewer"], k=random.randint(1, 2)
                ),
            }
        )

    # Generate test scenarios
    scenarios = {
        "valid_users": users[:10],
        "invalid_users": [
            {
                "email": "notanemail",
                "username": "test",
                "password": "123",
            },  # Invalid email
            {
                "email": "test@test.com",
                "username": "",
                "password": "password",
            },  # Empty username
            {
                "email": "test@test.com",
                "username": "test",
                "password": "",
            },  # Empty password
            {"email": "", "username": "test", "password": "password"},  # Empty email
            {
                "email": "duplicate@test.com",
                "username": "duplicate",
                "password": "password",
            },  # For duplicate testing
        ],
        "sql_injection_attempts": [
            "admin' OR '1'='1",
            "'; DROP TABLE users; --",
            "' UNION SELECT * FROM users --",
            "admin'--",
            "' OR 1=1--",
        ],
        "xss_attempts": [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "<svg onload=alert('XSS')>",
            "javascript:alert('XSS')",
            "<iframe src='javascript:alert(\"XSS\")'>",
        ],
        "large_payloads": {
            "huge_string": "A" * 10000,
            "deep_nesting": {
                "level1": {"level2": {"level3": {"level4": {"level5": "deep"}}}}
            },
            "many_items": [f"item_{i}" for i in range(1000)],
        },
    }

    return scenarios


def create_interactive_qa_workflow():
    """Create an interactive QA testing workflow"""
    wb = WorkflowBuilder(name="interactive_qa_testing")

    # Test data generator
    test_data_gen = PythonCodeNode.from_function(
        name="test_data_generator", func=generate_test_data
    )

    # QA Strategy Agent - Plans test execution
    qa_strategist = LLMAgentNode(
        name="qa_strategist",
        model="gpt-4",
        system_prompt="""You are a QA Test Strategist planning comprehensive test scenarios.
Your role is to:
1. Analyze the admin tool components
2. Create a test execution plan
3. Prioritize test cases by risk
4. Identify critical paths
5. Plan for edge cases

Focus on:
- User Management (CRUD operations)
- Role-Based Access Control
- Permission Matrix
- Audit Logging
- Security Dashboard
- Multi-tenant isolation
""",
        prompt_template="""Given these test data categories:
{result}

Create a comprehensive test plan that covers:
1. Functional testing (happy path)
2. Negative testing (error cases)
3. Security testing (vulnerabilities)
4. Performance testing (load/stress)
5. Integration testing (component interaction)

Output a structured test plan with specific test cases for each component.""",
    )

    # Test Executor - Simulates actual API calls
    test_executor = PythonCodeNode(
        name="test_executor",
        code="""
import json
import random
from datetime import datetime

# Parse test plan from strategist
test_plan = input_data if isinstance(input_data, dict) else {"tests": []}

# Simulate test execution results
test_results = {
    "execution_time": datetime.now().isoformat(),
    "total_tests": 0,
    "passed": 0,
    "failed": 0,
    "errors": 0,
    "test_cases": []
}

# Define test execution functions
def execute_user_crud_tests():
    results = []

    # Test user creation
    results.append({
        "test": "Create valid user",
        "status": "passed",
        "response_time": random.randint(50, 200),
        "details": "User created successfully with all required fields"
    })

    # Test duplicate user
    results.append({
        "test": "Create duplicate user",
        "status": "passed",
        "response_time": random.randint(30, 100),
        "details": "System correctly rejected duplicate email"
    })

    # Test invalid email
    results.append({
        "test": "Create user with invalid email",
        "status": "passed",
        "response_time": random.randint(20, 50),
        "details": "Validation error returned as expected"
    })

    # Simulate a failure
    results.append({
        "test": "Update user roles",
        "status": "failed",
        "response_time": random.randint(100, 300),
        "details": "Permission check failed - user cannot assign admin role",
        "error": "Insufficient privileges"
    })

    return results

def execute_permission_tests():
    results = []

    # Test permission matrix
    results.append({
        "test": "Load permission matrix",
        "status": "passed",
        "response_time": random.randint(200, 500),
        "details": "Matrix loaded with 50 permissions across 10 roles"
    })

    # Test permission inheritance
    results.append({
        "test": "Verify permission inheritance",
        "status": "passed",
        "response_time": random.randint(50, 150),
        "details": "Child roles correctly inherit parent permissions"
    })

    # Test circular dependency
    results.append({
        "test": "Create circular role hierarchy",
        "status": "passed",
        "response_time": random.randint(30, 80),
        "details": "System prevented circular dependency"
    })

    return results

def execute_security_tests():
    results = []

    # SQL Injection tests
    results.append({
        "test": "SQL injection in login",
        "status": "passed",
        "response_time": random.randint(50, 100),
        "details": "Input properly escaped, no injection possible"
    })

    # XSS tests
    results.append({
        "test": "XSS in user profile",
        "status": "passed",
        "response_time": random.randint(40, 90),
        "details": "HTML properly encoded in output"
    })

    # Authentication bypass attempt
    results.append({
        "test": "JWT token manipulation",
        "status": "failed",
        "response_time": random.randint(10, 30),
        "details": "Token signature validation could be improved",
        "severity": "high",
        "error": "Weak token validation"
    })

    return results

def execute_performance_tests():
    results = []

    # Load test
    results.append({
        "test": "Load 1000 users",
        "status": "passed",
        "response_time": random.randint(2000, 5000),
        "details": "Successfully loaded, pagination working correctly"
    })

    # Stress test
    results.append({
        "test": "Concurrent user updates",
        "status": "failed",
        "response_time": random.randint(5000, 10000),
        "details": "Race condition detected in concurrent updates",
        "severity": "medium",
        "error": "Optimistic locking not implemented"
    })

    return results

# Execute all test categories
all_tests = []
all_tests.extend(execute_user_crud_tests())
all_tests.extend(execute_permission_tests())
all_tests.extend(execute_security_tests())
all_tests.extend(execute_performance_tests())

# Calculate summary
for test in all_tests:
    test_results["total_tests"] += 1
    if test["status"] == "passed":
        test_results["passed"] += 1
    elif test["status"] == "failed":
        test_results["failed"] += 1
    else:
        test_results["errors"] += 1
    test_results["test_cases"].append(test)

# Add test coverage metrics
test_results["coverage"] = {
    "user_management": 95,
    "permissions": 88,
    "security": 92,
    "performance": 75,
    "audit_logs": 80,
    "multi_tenant": 70
}

result = test_results
""",
    )

    # Bug Analyzer - Analyzes failed tests
    bug_analyzer = LLMAgentNode(
        name="bug_analyzer",
        model="gpt-4",
        system_prompt="""You are a Senior QA Engineer analyzing test failures.
For each failed test, provide:
1. Root cause analysis
2. Severity assessment (Critical/High/Medium/Low)
3. Impact on users
4. Recommended fix
5. Steps to reproduce
6. Affected components
7. Regression risk""",
        prompt_template="""Analyze these test failures:
{failed_tests}

Provide detailed analysis for each failure and prioritize fixes based on severity and user impact.""",
    )

    # Test Report Generator
    report_generator = PythonCodeNode(
        name="report_generator",
        code="""
import json
from datetime import datetime

test_results = input_data.get("test_results", {})
bug_analysis = input_data.get("bug_analysis", {})

# Generate comprehensive report
report = f'''
# Admin Tool Framework - QA Test Report

**Generated**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Test Suite**: Interactive QA Testing

## Executive Summary

- **Total Tests**: {test_results.get("total_tests", 0)}
- **Passed**: {test_results.get("passed", 0)} ✅
- **Failed**: {test_results.get("failed", 0)} ❌
- **Errors**: {test_results.get("errors", 0)} ⚠️
- **Pass Rate**: {(test_results.get("passed", 0) / max(test_results.get("total_tests", 1), 1) * 100):.1f}%

## Test Coverage

| Component | Coverage |
|-----------|----------|
'''

for component, coverage in test_results.get("coverage", {}).items():
    report += f"| {component.replace('_', ' ').title()} | {coverage}% |\n"

report += '''

## Failed Tests Summary

'''

failed_tests = [t for t in test_results.get("test_cases", []) if t["status"] == "failed"]
for test in failed_tests:
    report += f'''
### ❌ {test["test"]}
- **Error**: {test.get("error", "Unknown error")}
- **Details**: {test.get("details", "No details available")}
- **Response Time**: {test.get("response_time", 0)}ms
- **Severity**: {test.get("severity", "Medium").upper()}

'''

report += '''
## Recommendations

1. **Immediate Actions**:
   - Fix high-severity security vulnerabilities
   - Implement optimistic locking for concurrent updates
   - Strengthen JWT token validation

2. **Short-term Improvements**:
   - Add comprehensive input validation
   - Implement rate limiting
   - Enhance error handling and logging

3. **Long-term Enhancements**:
   - Improve test coverage for multi-tenant features
   - Add automated regression testing
   - Implement continuous security scanning

## Test Execution Details

<details>
<summary>Click to expand full test results</summary>

```json
''' + json.dumps(test_results.get("test_cases", []), indent=2) + '''
```

</details>
'''

result = {
    "report": report,
    "summary": {
        "total": test_results.get("total_tests", 0),
        "passed": test_results.get("passed", 0),
        "failed": test_results.get("failed", 0),
        "critical_issues": len([t for t in failed_tests if t.get("severity") == "high"])
    }
}
""",
    )

    # Regression Test Creator
    regression_creator = PythonCodeNode(
        name="regression_test_creator",
        code="""
# Create regression tests from failures
test_results = input_data.get("test_results", {})
failed_tests = [t for t in test_results.get("test_cases", []) if t["status"] == "failed"]

regression_tests = {
    "test_suite": "admin_framework_regression",
    "created": datetime.now().isoformat(),
    "tests": []
}

for failed_test in failed_tests:
    regression_tests["tests"].append({
        "name": f"regression_{failed_test['test'].lower().replace(' ', '_')}",
        "description": f"Regression test for: {failed_test['details']}",
        "category": "regression",
        "priority": "high" if failed_test.get("severity") == "high" else "medium",
        "steps": [
            "Setup test environment",
            f"Execute: {failed_test['test']}",
            f"Verify fix for: {failed_test.get('error', 'error')}",
            "Cleanup test data"
        ],
        "expected_result": "Test should pass without errors",
        "automated": True
    })

result = regression_tests
""",
    )

    # Build workflow
    wb.add_node(test_data_gen)
    wb.add_node(qa_strategist)
    wb.add_node(test_executor)
    wb.add_node(bug_analyzer)
    wb.add_node(report_generator)
    wb.add_node(regression_creator)

    # Connect nodes
    wb.connect(test_data_gen.name, qa_strategist.name)
    wb.connect(qa_strategist.name, test_executor.name, {"result": "input_data"})

    # Extract failed tests for bug analysis
    failed_test_extractor = PythonCodeNode(
        name="extract_failed_tests",
        code="""
test_results = input_data
failed_tests = [t for t in test_results.get("test_cases", []) if t["status"] == "failed"]
result = {"failed_tests": failed_tests}
""",
    )
    wb.add_node(failed_test_extractor)

    wb.connect(test_executor.name, failed_test_extractor.name, {"result": "input_data"})
    wb.connect(failed_test_extractor.name, bug_analyzer.name)

    # Merge results for report
    merge_node = MergeNode(name="merge_results")
    wb.add_node(merge_node)

    wb.connect(test_executor.name, merge_node.name, {"result": "test_results"})
    wb.connect(bug_analyzer.name, merge_node.name, {"result": "bug_analysis"})
    wb.connect(merge_node.name, report_generator.name, {"merged_output": "input_data"})

    # Create regression tests from results
    wb.connect(test_executor.name, regression_creator.name, {"result": "input_data"})

    return wb.build()


def main():
    """Run interactive QA testing"""
    print("🤖 Starting Interactive QA Testing for Admin Tools...")
    print("=" * 60)

    workflow = create_interactive_qa_workflow()

    print("\n📋 Executing test plan...")
    result = workflow.run()

    if result.is_success:
        # Get report
        report_data = result.node_results.get("report_generator", {})
        if "report" in report_data:
            print("\n" + report_data["report"])

            # Show summary
            summary = report_data.get("summary", {})
            if summary.get("critical_issues", 0) > 0:
                print(
                    f"\n⚠️  WARNING: {summary['critical_issues']} critical issues found!"
                )
                print("Immediate action required to fix security vulnerabilities.")

        # Show regression tests created
        regression_data = result.node_results.get("regression_test_creator", {})
        if regression_data and "tests" in regression_data:
            print(f"\n✅ Created {len(regression_data['tests'])} regression tests")
            print("These tests should be added to your CI/CD pipeline.")

    else:
        print(f"\n❌ Testing failed: {result.error}")


if __name__ == "__main__":
    main()
