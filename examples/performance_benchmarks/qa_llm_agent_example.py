"""
QA LLM Agent Test for Admin Tool Framework

This example creates an LLM agent that roleplays as a QA tester to test the
robustness of the admin system by performing various test scenarios.
"""

import json
import random
from datetime import datetime, timedelta

from examples.utils.data_paths import get_test_data_path
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.logic import MergeNode, SwitchNode
from kailash.workflow import Workflow


def create_qa_test_scenarios():
    """Generate various QA test scenarios"""
    scenarios = [
        # Authentication & Authorization Tests
        {
            "category": "authentication",
            "tests": [
                "Try to access admin endpoints without authentication",
                "Use expired JWT tokens",
                "Use malformed JWT tokens",
                "Attempt SQL injection in login fields",
                "Try XSS attacks in username/password fields",
                "Test with very long passwords (>1000 chars)",
                "Test with special characters in passwords",
                "Attempt concurrent logins from multiple locations",
                "Test password reset with non-existent email",
                "Try to brute force login (rate limiting test)",
            ],
        },
        # User Management Tests
        {
            "category": "user_management",
            "tests": [
                "Create users with duplicate emails",
                "Create users with invalid email formats",
                "Update non-existent users",
                "Delete system admin user",
                "Assign non-existent roles to users",
                "Create users with empty required fields",
                "Test pagination with 0 users",
                "Test pagination with 10,000+ users",
                "Search users with SQL injection attempts",
                "Bulk delete users including active sessions",
                "Create user with role higher than current user",
                "Test Unicode characters in user names",
            ],
        },
        # Permission & Role Tests
        {
            "category": "permissions",
            "tests": [
                "Grant permissions to non-existent roles",
                "Create circular role hierarchies",
                "Delete role with active users",
                "Modify system roles",
                "Test permission inheritance edge cases",
                "Assign conflicting permissions",
                "Test with 1000+ permissions per role",
                "Remove all permissions from admin role",
                "Test permission caching after updates",
                "Create role with duplicate name",
            ],
        },
        # Audit Log Tests
        {
            "category": "audit_logs",
            "tests": [
                "Query audit logs with invalid date ranges",
                "Export 1 million audit logs",
                "Filter by non-existent event types",
                "Test audit log retention policies",
                "Verify audit logs are immutable",
                "Test audit log encryption",
                "Query logs with SQL injection",
                "Test concurrent audit log writes",
                "Verify failed actions are logged",
                "Test audit log backup and restore",
            ],
        },
        # Security Dashboard Tests
        {
            "category": "security",
            "tests": [
                "Trigger security alerts artificially",
                "Test real-time metric updates",
                "Simulate DDoS attack patterns",
                "Test anomaly detection thresholds",
                "Verify security event prioritization",
                "Test alert notification system",
                "Simulate data breach scenarios",
                "Test compliance score calculations",
                "Verify security scan scheduling",
                "Test incident response workflows",
            ],
        },
        # Multi-tenant Tests
        {
            "category": "multi_tenant",
            "tests": [
                "Access data across tenant boundaries",
                "Create tenant with duplicate subdomain",
                "Exceed tenant resource limits",
                "Test tenant isolation in database",
                "Delete tenant with active users",
                "Test tenant data migration",
                "Suspend tenant during active operations",
                "Test tenant backup isolation",
                "Verify tenant-specific configurations",
                "Test cross-tenant user switching",
            ],
        },
        # Performance & Stress Tests
        {
            "category": "performance",
            "tests": [
                "Create 10,000 users simultaneously",
                "Query permissions for user with 1000 roles",
                "Load permission matrix with 10,000 permissions",
                "Test API response times under load",
                "Simulate 1000 concurrent admin sessions",
                "Test database connection pool limits",
                "Measure memory usage during bulk operations",
                "Test cache invalidation performance",
                "Simulate network latency scenarios",
                "Test system behavior at resource limits",
            ],
        },
        # Edge Cases & Error Handling
        {
            "category": "edge_cases",
            "tests": [
                "Submit forms with null/undefined values",
                "Test with network disconnections mid-operation",
                "Submit conflicting concurrent updates",
                "Test timezone handling across regions",
                "Use expired CSRF tokens",
                "Test with browser back button after operations",
                "Submit forms multiple times rapidly",
                "Test with cookies disabled",
                "Use outdated API versions",
                "Test graceful degradation scenarios",
            ],
        },
    ]
    return scenarios


def create_qa_agent_workflow():
    """Create a workflow with QA LLM Agent"""
    workflow = Workflow(name="admin_qa_test_workflow")

    # Generate test scenarios
    scenario_generator = PythonCodeNode.from_function(
        name="scenario_generator", func=create_qa_test_scenarios
    )

    # QA Agent that acts like a thorough tester
    qa_agent = LLMAgentNode(
        name="qa_tester_agent",
        model="gpt-4",
        system_prompt="""You are an experienced QA engineer testing an admin tool framework.
Your personality traits:
- Meticulous and thorough
- Creative in finding edge cases
- Persistent in breaking things
- Professional in reporting issues

Your testing approach:
1. Start with basic functionality tests
2. Progress to edge cases and error scenarios
3. Try to break the system in creative ways
4. Test security vulnerabilities
5. Verify data integrity
6. Test performance under stress
7. Document all findings clearly

For each test scenario provided, you should:
- Describe what you're testing
- Explain your approach
- Predict expected behavior
- Note any potential issues
- Suggest additional test cases
- Rate severity of any issues found (Critical/High/Medium/Low)

Be specific about:
- Input values you would use
- Expected vs actual behavior
- Steps to reproduce issues
- Impact on users
- Recommended fixes
""",
        prompt_template="""Test Category: {category}
Test Scenarios: {tests}

Please analyze these test scenarios as a QA engineer. For each test:
1. Explain how you would execute it
2. What specific inputs/actions you would use
3. What vulnerabilities you're looking for
4. Expected system behavior
5. Potential issues and their severity

Also suggest 3 additional creative test cases for this category that might reveal hidden issues.""",
    )

    # Categorize findings by severity
    severity_classifier = PythonCodeNode(
        name="severity_classifier",
        code="""

# Parse QA agent's findings
findings = json.loads(input_data) if isinstance(input_data, str) else input_data

# Categorize by severity
categorized = {
    "critical": [],
    "high": [],
    "medium": [],
    "low": [],
    "info": []
}

# Keywords for severity classification
severity_keywords = {
    "critical": ["data breach", "authentication bypass", "sql injection", "privilege escalation", "data loss"],
    "high": ["xss", "csrf", "dos", "unauthorized access", "data corruption"],
    "medium": ["performance", "validation", "error handling", "rate limiting"],
    "low": ["ui issue", "typo", "formatting", "minor bug"],
}

# Process findings (this is simplified - real implementation would parse QA output)
for test_type in ["authentication", "permissions", "security"]:
    if any(keyword in str(findings).lower() for keyword in severity_keywords["critical"]):
        categorized["critical"].append({
            "type": test_type,
            "description": "Potential critical security issue found",
            "action": "Immediate investigation required"
        })

result = {
    "summary": categorized,
    "total_issues": sum(len(v) for v in categorized.values()),
    "requires_immediate_action": len(categorized["critical"]) > 0
}
""",
    )

    # Generate detailed test report
    report_generator = PythonCodeNode(
        name="report_generator",
        code="""
from datetime import datetime

# Compile comprehensive test report
report = {
    "test_execution_date": datetime.now().isoformat(),
    "test_framework": "Admin Tool Framework QA Suite",
    "tester": "AI QA Agent",
    "test_categories": input_data.get("categories", []),
    "findings": input_data.get("findings", {}),
    "severity_summary": input_data.get("severity", {}),
    "recommendations": [
        "Implement input validation on all forms",
        "Add rate limiting to prevent brute force",
        "Enhance audit logging for security events",
        "Implement proper error handling",
        "Add integration tests for edge cases",
        "Set up continuous security scanning",
        "Implement automated regression testing"
    ],
    "next_steps": [
        "Address critical issues immediately",
        "Schedule fixes for high-priority issues",
        "Plan improvements for medium/low issues",
        "Enhance test coverage",
        "Set up monitoring for identified patterns"
    ]
}

# Format as readable report
formatted_report = f\"\"\"
# Admin Tool Framework QA Test Report

**Date**: {report['test_execution_date']}
**Tester**: {report['tester']}

## Executive Summary
- Total test categories: {len(report['test_categories'])}
- Critical issues found: {report['severity_summary'].get('critical_count', 0)}
- High priority issues: {report['severity_summary'].get('high_count', 0)}
- Medium priority issues: {report['severity_summary'].get('medium_count', 0)}
- Low priority issues: {report['severity_summary'].get('low_count', 0)}

## Key Findings
{json.dumps(report['findings'], indent=2)}

## Recommendations
{chr(10).join(f"- {rec}" for rec in report['recommendations'])}

## Next Steps
{chr(10).join(f"{i+1}. {step}" for i, step in enumerate(report['next_steps']))}
\"\"\"

result = {
    "report": formatted_report,
    "data": report
}
""",
    )

    # Security-specific tester
    security_specialist = LLMAgentNode(
        name="security_specialist",
        model="gpt-4",
        system_prompt="""You are a security specialist focusing on penetration testing and vulnerability assessment.
Focus on:
- OWASP Top 10 vulnerabilities
- Authentication and authorization flaws
- Data exposure risks
- Injection attacks
- Session management issues
- Cryptographic weaknesses
- Business logic flaws

Be specific about attack vectors and provide proof-of-concept examples where appropriate.""",
        prompt_template="""Perform a security-focused analysis of the admin tool framework.
Consider these attack vectors:
{attack_vectors}

Provide specific examples of how each could be exploited and recommendations for mitigation.""",
    )

    # Performance tester
    performance_tester = PythonCodeNode(
        name="performance_tester",
        code="""
import time

# Simulate performance testing scenarios
test_results = {
    "load_tests": {
        "concurrent_users": [10, 100, 1000, 10000],
        "response_times": [],
        "error_rates": [],
        "throughput": []
    },
    "stress_tests": {
        "breaking_point": None,
        "resource_usage": {},
        "bottlenecks": []
    },
    "endurance_tests": {
        "duration_hours": 24,
        "memory_leaks": False,
        "performance_degradation": False
    }
}

# Simulate load test results
for users in test_results["load_tests"]["concurrent_users"]:
    # Simulate response time increase with load
    base_response = 100  # ms
    response_time = base_response * (1 + (users / 1000))
    test_results["load_tests"]["response_times"].append({
        "users": users,
        "avg_response_ms": response_time,
        "p95_response_ms": response_time * 1.5,
        "p99_response_ms": response_time * 2
    })

    # Simulate error rates
    error_rate = min(0.1, (users / 100000))  # Error rate increases with load
    test_results["load_tests"]["error_rates"].append({
        "users": users,
        "error_percentage": error_rate * 100
    })

# Identify bottlenecks
if max(r["avg_response_ms"] for r in test_results["load_tests"]["response_times"]) > 1000:
    test_results["stress_tests"]["bottlenecks"].append("Database connection pool exhaustion")
    test_results["stress_tests"]["bottlenecks"].append("API rate limiting needed")

result = test_results
""",
    )

    # Connect nodes
    workflow.add_node(scenario_generator)
    workflow.add_node(qa_agent)
    workflow.add_node(severity_classifier)
    workflow.add_node(report_generator)
    workflow.add_node(security_specialist)
    workflow.add_node(performance_tester)

    # Create test flow
    workflow.connect(scenario_generator.name, qa_agent.name, {"result": "tests"})
    workflow.connect(qa_agent.name, severity_classifier.name, {"result": "input_data"})
    workflow.connect(
        severity_classifier.name, report_generator.name, {"result": "severity"}
    )

    # Parallel security and performance testing
    workflow.connect(
        scenario_generator.name, security_specialist.name, {"result": "attack_vectors"}
    )
    workflow.connect(scenario_generator.name, performance_tester.name)

    # Merge all results for final report
    merge_results = MergeNode(name="merge_test_results")
    workflow.add_node(merge_results)

    workflow.connect(report_generator.name, merge_results.name, {"result": "qa_report"})
    workflow.connect(
        security_specialist.name, merge_results.name, {"result": "security_report"}
    )
    workflow.connect(
        performance_tester.name, merge_results.name, {"result": "performance_report"}
    )

    return workflow


def main():
    """Run QA testing workflow"""
    print("🧪 Starting Admin Tool Framework QA Testing...")
    print("=" * 50)

    # Create and run workflow
    workflow = create_qa_agent_workflow()

    # Execute QA tests
    result = workflow.execute()

    # Display results
    if result.is_success:
        print("\n✅ QA Testing Complete!")
        print("\n📊 Test Results:")

        merged_results = result.node_results.get("merge_test_results", {})

        # Show QA report
        if "qa_report" in merged_results:
            print("\n📋 QA Test Report:")
            print(merged_results["qa_report"].get("report", "No report generated"))

        # Show security findings
        if "security_report" in merged_results:
            print("\n🔒 Security Analysis:")
            print(
                merged_results["security_report"].get(
                    "result", "No security issues found"
                )
            )

        # Show performance results
        if "performance_report" in merged_results:
            print("\n⚡ Performance Test Results:")
            perf_data = merged_results["performance_report"]
            if isinstance(perf_data, dict) and "load_tests" in perf_data:
                print(
                    f"- Tested up to {perf_data['load_tests']['concurrent_users'][-1]} concurrent users"
                )
                print(
                    f"- Bottlenecks found: {len(perf_data['stress_tests']['bottlenecks'])}"
                )
    else:
        print(f"\n❌ QA Testing failed: {result.error}")


if __name__ == "__main__":
    main()
