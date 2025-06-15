#!/usr/bin/env python3
"""
Comprehensive Enterprise Security Workflow

Purpose: Demonstrate a complete enterprise security solution that protects against threats,
manages user access, ensures compliance, and monitors performance.

SDK Features Demonstrated:
- ThreatDetectionNode: AI-powered security threat detection
- ABACPermissionEvaluatorNode: Attribute-based access control
- MultiFactorAuthNode: Enterprise MFA implementation
- BehaviorAnalysisNode: ML-based anomaly detection
- SessionManagementNode: Enterprise session tracking
- GDPRComplianceNode: Automated compliance
- PerformanceBenchmarkNode: Performance monitoring
- DataRetentionPolicyNode: Automated data lifecycle

Business Value:
- Complete security automation reducing manual oversight by 80%
- Real-time threat detection and response
- Automated compliance with GDPR/CCPA
- Performance monitoring ensuring <500ms response times
- Behavioral analysis detecting insider threats

Original Issues (from old implementation):
- Used custom Docker setup instead of SDK infrastructure
- Manual workflow orchestration instead of WorkflowBuilder
- Complex async coordination instead of LocalRuntime
- Custom result handling instead of SDK patterns

Refactored Approach:
- Use WorkflowBuilder.from_dict() for dynamic workflow creation
- Leverage LocalRuntime with enterprise features enabled
- Use SDK nodes without custom orchestration
- Let SDK handle all execution and result aggregation
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from kailash.nodes.security import UserContext
from kailash.runtime.local import LocalRuntime
from kailash.workflow import WorkflowBuilder


def create_enterprise_security_workflow():
    """
    Create a comprehensive enterprise security workflow using SDK best practices.

    This workflow demonstrates:
    1. User authentication with MFA
    2. Session management
    3. ABAC permission evaluation
    4. Behavior analysis
    5. Threat detection
    6. Compliance automation
    7. Performance monitoring
    8. Data retention policies
    """

    # Use WorkflowBuilder for dynamic workflow construction
    builder = WorkflowBuilder()

    # Define workflow configuration following SDK patterns
    workflow_config = {
        "id": "enterprise_security",
        "name": "Enterprise Security Workflow",
        "description": "Complete enterprise security solution",
        "nodes": [
            # User Authentication with MFA
            {
                "id": "mfa_auth",
                "type": "MultiFactorAuthNode",
                "config": {
                    "name": "mfa_authenticator",
                    "methods": ["totp", "sms", "email"],
                    "backup_codes": True,
                    "session_timeout_minutes": 30,
                    "require_all_methods": False,
                },
            },
            # Session Management
            {
                "id": "session_mgmt",
                "type": "SessionManagementNode",
                "config": {
                    "name": "session_manager",
                    "max_sessions": 3,
                    "idle_timeout_minutes": 30,
                    "track_devices": True,
                    "enforce_single_session": False,
                },
            },
            # ABAC Permission Evaluation
            {
                "id": "abac_eval",
                "type": "ABACPermissionEvaluatorNode",
                "config": {
                    "name": "permission_evaluator",
                    "ai_reasoning": True,
                    "cache_results": True,
                    "performance_target_ms": 50,
                    "policy_source": "enterprise_policies",
                },
            },
            # Behavior Analysis
            {
                "id": "behavior_analysis",
                "type": "BehaviorAnalysisNode",
                "config": {
                    "name": "behavior_analyzer",
                    "baseline_period_days": 30,
                    "anomaly_threshold": 0.8,
                    "learning_enabled": True,
                    "ml_model": "isolation_forest",
                },
            },
            # Threat Detection
            {
                "id": "threat_detection",
                "type": "ThreatDetectionNode",
                "config": {
                    "name": "threat_detector",
                    "detection_rules": [
                        "brute_force",
                        "privilege_escalation",
                        "data_exfiltration",
                    ],
                    "ai_model": "ollama:llama3.2:3b",
                    "response_actions": ["alert", "log", "block"],
                    "real_time": True,
                },
            },
            # GDPR Compliance
            {
                "id": "gdpr_compliance",
                "type": "GDPRComplianceNode",
                "config": {
                    "name": "compliance_manager",
                    "frameworks": ["gdpr", "ccpa", "sox"],
                    "auto_anonymize": True,
                    "consent_tracking": True,
                    "audit_logging": True,
                },
            },
            # Performance Monitoring
            {
                "id": "performance_monitor",
                "type": "PerformanceBenchmarkNode",
                "config": {
                    "name": "performance_tracker",
                    "targets": {
                        "authentication": "500ms",
                        "permission_check": "50ms",
                        "threat_detection": "200ms",
                    },
                    "auto_optimization": True,
                    "alert_threshold": 0.9,
                },
            },
            # Data Retention Policy
            {
                "id": "data_retention",
                "type": "DataRetentionPolicyNode",
                "config": {
                    "name": "retention_manager",
                    "policies": {
                        "user_data": {"retention_days": 365, "archive": True},
                        "logs": {"retention_days": 90, "archive": False},
                        "sessions": {"retention_days": 7, "archive": False},
                    },
                    "auto_delete": True,
                    "compliance_mode": True,
                },
            },
            # Security Aggregator (using PythonCodeNode to aggregate results)
            {
                "id": "security_aggregator",
                "type": "PythonCodeNode",
                "config": {
                    "name": "aggregate_security_status",
                    "code": """
def aggregate_security_results(mfa_result, session_result, abac_result,
                             behavior_result, threat_result, gdpr_result,
                             performance_result, retention_result):
    '''Aggregate all security check results into a comprehensive status.'''

    # Calculate overall security score
    checks_passed = sum([
        mfa_result.get('authenticated', False),
        session_result.get('session_valid', False),
        abac_result.get('access_granted', False),
        behavior_result.get('behavior_normal', True),
        not threat_result.get('threats_detected', False),
        gdpr_result.get('compliant', False),
        performance_result.get('within_targets', False),
        retention_result.get('policies_enforced', False)
    ])

    security_score = (checks_passed / 8) * 100

    # Determine security level
    if security_score >= 90:
        security_level = "HIGH"
    elif security_score >= 70:
        security_level = "MEDIUM"
    else:
        security_level = "LOW"

    # Compile security report
    return {
        "result": {
            "timestamp": datetime.now().isoformat(),
            "security_score": security_score,
            "security_level": security_level,
            "checks": {
                "authentication": mfa_result.get('authenticated', False),
                "session_valid": session_result.get('session_valid', False),
                "access_granted": abac_result.get('access_granted', False),
                "behavior_normal": behavior_result.get('behavior_normal', True),
                "threats_detected": threat_result.get('threats_detected', False),
                "compliance_status": gdpr_result.get('compliant', False),
                "performance_ok": performance_result.get('within_targets', False),
                "retention_active": retention_result.get('policies_enforced', False)
            },
            "recommendations": _get_recommendations(security_score),
            "alerts": _collect_alerts(threat_result, behavior_result)
        }
    }

def _get_recommendations(score):
    '''Generate security recommendations based on score.'''
    if score < 70:
        return [
            "Enable all MFA methods",
            "Review access permissions",
            "Investigate anomalous behavior",
            "Update threat detection rules"
        ]
    elif score < 90:
        return [
            "Consider stricter session policies",
            "Enable AI-powered threat detection",
            "Review compliance settings"
        ]
    return ["Security posture is strong - maintain current policies"]

def _collect_alerts(threat_result, behavior_result):
    '''Collect all security alerts.'''
    alerts = []
    if threat_result.get('threats_detected'):
        alerts.extend(threat_result.get('alerts', []))
    if not behavior_result.get('behavior_normal', True):
        alerts.append({
            "type": "anomaly",
            "severity": "medium",
            "message": "Unusual behavior detected"
        })
    return alerts

# Import at execution time
from datetime import datetime
                    """,
                },
            },
        ],
        # Define connections between nodes
        "connections": [
            # All security checks feed into the aggregator
            {
                "from": "mfa_auth",
                "to": "security_aggregator",
                "mapping": {"result": "mfa_result"},
            },
            {
                "from": "session_mgmt",
                "to": "security_aggregator",
                "mapping": {"result": "session_result"},
            },
            {
                "from": "abac_eval",
                "to": "security_aggregator",
                "mapping": {"result": "abac_result"},
            },
            {
                "from": "behavior_analysis",
                "to": "security_aggregator",
                "mapping": {"result": "behavior_result"},
            },
            {
                "from": "threat_detection",
                "to": "security_aggregator",
                "mapping": {"result": "threat_result"},
            },
            {
                "from": "gdpr_compliance",
                "to": "security_aggregator",
                "mapping": {"result": "gdpr_result"},
            },
            {
                "from": "performance_monitor",
                "to": "security_aggregator",
                "mapping": {"result": "performance_result"},
            },
            {
                "from": "data_retention",
                "to": "security_aggregator",
                "mapping": {"result": "retention_result"},
            },
        ],
    }

    # Build workflow using SDK pattern
    workflow = builder.from_dict(workflow_config)
    return workflow


def run_security_demo():
    """
    Execute the enterprise security workflow with sample data.

    Demonstrates:
    - Unified LocalRuntime with enterprise features
    - Proper parameter passing
    - Result handling following SDK patterns
    """

    # Create workflow
    workflow = create_enterprise_security_workflow()

    # Initialize runtime with enterprise features
    runtime = LocalRuntime(
        enable_monitoring=True,  # Performance tracking
        enable_security=True,  # Security enforcement
        enable_audit=True,  # Compliance logging
        enable_async=True,  # Async node support
        user_context=UserContext(  # User context for ABAC
            user_id="demo_user",
            roles=["employee", "analyst"],
            attributes={
                "department": "security",
                "clearance_level": "high",
                "location": "headquarters",
            },
        ),
    )

    # Prepare input parameters for all nodes
    parameters = {
        "mfa_auth": {
            "user_id": "demo_user",
            "auth_methods": {"totp": "123456", "email": "verified"},
        },
        "session_mgmt": {
            "user_id": "demo_user",
            "device_id": "laptop_001",
            "ip_address": "192.168.1.100",
        },
        "abac_eval": {
            "user_id": "demo_user",
            "resource": "financial_data",
            "action": "read",
            "context": {"time": datetime.now().isoformat(), "location": "headquarters"},
        },
        "behavior_analysis": {
            "user_id": "demo_user",
            "actions": [
                {"action": "login", "timestamp": datetime.now().isoformat()},
                {"action": "access_data", "timestamp": datetime.now().isoformat()},
                {"action": "download_report", "timestamp": datetime.now().isoformat()},
            ],
        },
        "threat_detection": {
            "events": [
                {
                    "type": "login_attempt",
                    "source_ip": "192.168.1.100",
                    "user": "demo_user",
                    "success": True,
                }
            ]
        },
        "gdpr_compliance": {
            "data_operations": [
                {
                    "type": "access",
                    "data_category": "personal_data",
                    "purpose": "analysis",
                    "user_consent": True,
                }
            ]
        },
        "performance_monitor": {
            "operations": [
                {"name": "authentication", "duration_ms": 450},
                {"name": "permission_check", "duration_ms": 35},
                {"name": "threat_detection", "duration_ms": 180},
            ]
        },
        "data_retention": {
            "data_inventory": [
                {"type": "user_data", "age_days": 30},
                {"type": "logs", "age_days": 95},
                {"type": "sessions", "age_days": 10},
            ]
        },
    }

    # Execute workflow
    print("\n🚀 Executing Enterprise Security Workflow...")
    print("=" * 60)

    try:
        results, execution_id = runtime.execute(workflow, parameters)

        # Extract the aggregated security report
        security_report = results.get("security_aggregator", {}).get("result", {})

        # Display results
        print("\n✅ Workflow Execution Complete!")
        print(f"   Execution ID: {execution_id}")
        print("\n📊 Security Assessment:")
        print(f"   Security Score: {security_report.get('security_score', 0):.1f}%")
        print(f"   Security Level: {security_report.get('security_level', 'UNKNOWN')}")

        print("\n🔍 Security Checks:")
        checks = security_report.get("checks", {})
        for check, status in checks.items():
            status_icon = "✅" if status else "❌"
            print(f"   {status_icon} {check.replace('_', ' ').title()}: {status}")

        print("\n💡 Recommendations:")
        for rec in security_report.get("recommendations", []):
            print(f"   • {rec}")

        alerts = security_report.get("alerts", [])
        if alerts:
            print("\n⚠️  Security Alerts:")
            for alert in alerts:
                print(
                    f"   • [{alert.get('severity', 'unknown').upper()}] {alert.get('message', 'Unknown alert')}"
                )

        # Save detailed report
        output_path = Path("data/outputs/enterprise_security_report.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(
                {
                    "execution_id": execution_id,
                    "timestamp": datetime.now().isoformat(),
                    "security_report": security_report,
                    "full_results": results,
                },
                f,
                indent=2,
            )

        print(f"\n📄 Detailed report saved to: {output_path}")

    except Exception as e:
        print(f"\n❌ Error executing workflow: {e}")
        raise

    print("\n" + "=" * 60)
    print("🏁 Enterprise Security Demo Complete!")


if __name__ == "__main__":
    run_security_demo()
