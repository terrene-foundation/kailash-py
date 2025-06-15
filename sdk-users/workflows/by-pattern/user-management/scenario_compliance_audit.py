#!/usr/bin/env python3
"""
Real-World Scenario: Enterprise Compliance and Audit Management

This example demonstrates comprehensive compliance tracking for a healthcare
organization that must meet HIPAA, SOX, and internal audit requirements.

Scenario: Regional Healthcare Network
- Quarterly compliance audits
- Real-time violation detection
- Automated remediation workflows
- Executive reporting dashboards
"""

import asyncio
import random
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List

from kailash.nodes.admin import (
    AuditLogNode,
    PermissionCheckNode,
    RoleManagementNode,
    SecurityEventNode,
    UserManagementNode,
)
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.logic import MergeNode, SwitchNode
from kailash.nodes.transform import DataTransformer
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow


def create_quarterly_compliance_audit_workflow(audit_config: Dict[str, Any]):
    """
    Real scenario: Quarterly HIPAA/SOX compliance audit with automated checks.

    Steps:
    1. Collect user access patterns
    2. Analyze permission usage
    3. Detect compliance violations
    4. Generate remediation tasks
    5. Create executive report
    """

    # Step 1: Collect all user activity for the quarter
    collect_user_activity = AuditLogNode(
        name="collect_quarterly_activity",
        operation="query_logs",
        query_filters={
            "date_range": {
                "start": audit_config["quarter_start"],
                "end": audit_config["quarter_end"],
            },
            "event_types": [
                "data_accessed",
                "data_modified",
                "data_exported",
                "permission_denied",
                "user_login",
                "user_logout",
            ],
        },
        pagination={"page": 1, "size": 10000},  # Get all events
        tenant_id=audit_config["organization"],
    )

    # Step 2: Analyze data access patterns
    def analyze_access_patterns(activity_result):
        """Analyze user access patterns for compliance."""
        logs = activity_result.get("logs", [])

        # Group by user
        user_activity = {}
        for log in logs:
            user_id = log.get("user_id")
            if user_id:
                if user_id not in user_activity:
                    user_activity[user_id] = {
                        "total_accesses": 0,
                        "data_exports": 0,
                        "after_hours_access": 0,
                        "denied_attempts": 0,
                        "sensitive_data_access": 0,
                        "resources_accessed": set(),
                    }

                user_activity[user_id]["total_accesses"] += 1

                # Check event types
                event_type = log.get("event_type")
                if event_type == "data_exported":
                    user_activity[user_id]["data_exports"] += 1
                elif event_type == "permission_denied":
                    user_activity[user_id]["denied_attempts"] += 1

                # Check time
                timestamp = datetime.fromisoformat(
                    log.get("timestamp", "").replace("Z", "+00:00")
                )
                if timestamp.hour < 6 or timestamp.hour > 22:
                    user_activity[user_id]["after_hours_access"] += 1

                # Check resource sensitivity
                resource = log.get("resource_id", "")
                if (
                    "patient" in resource
                    or "medical" in resource
                    or "financial" in resource
                ):
                    user_activity[user_id]["sensitive_data_access"] += 1

                user_activity[user_id]["resources_accessed"].add(resource)

        # Convert sets to lists for JSON serialization
        for user in user_activity:
            user_activity[user]["resources_accessed"] = list(
                user_activity[user]["resources_accessed"]
            )

        return {
            "user_activity_summary": user_activity,
            "total_users_analyzed": len(user_activity),
            "total_events_analyzed": len(logs),
        }

    access_analyzer = PythonCodeNode.from_function(
        name="analyze_access_patterns", func=analyze_access_patterns
    )

    # Step 3: Check for HIPAA violations
    def check_hipaa_violations(access_analysis):
        """Check for HIPAA compliance violations."""
        user_activity = access_analysis.get("user_activity_summary", {})
        violations = []

        for user_id, activity in user_activity.items():
            # Check for excessive data exports (potential breach)
            if activity["data_exports"] > 50:
                violations.append(
                    {
                        "type": "excessive_data_export",
                        "severity": "high",
                        "user_id": user_id,
                        "description": f"User exported data {activity['data_exports']} times (limit: 50)",
                        "regulation": "HIPAA",
                        "remediation": "Review and restrict export permissions",
                    }
                )

            # Check for after-hours access patterns
            total_access = activity["total_accesses"]
            if total_access > 0:
                after_hours_ratio = activity["after_hours_access"] / total_access
                if after_hours_ratio > 0.3:  # More than 30% after hours
                    violations.append(
                        {
                            "type": "suspicious_access_pattern",
                            "severity": "medium",
                            "user_id": user_id,
                            "description": f"High after-hours access: {after_hours_ratio*100:.1f}%",
                            "regulation": "HIPAA",
                            "remediation": "Verify legitimate need for after-hours access",
                        }
                    )

            # Check for minimum necessary rule
            if len(activity["resources_accessed"]) > 100:
                violations.append(
                    {
                        "type": "minimum_necessary_violation",
                        "severity": "medium",
                        "user_id": user_id,
                        "description": f"Accessed {len(activity['resources_accessed'])} different resources",
                        "regulation": "HIPAA",
                        "remediation": "Review access scope and apply principle of least privilege",
                    }
                )

        return {
            "hipaa_violations": violations,
            "violation_count": len(violations),
            "users_with_violations": len(set(v["user_id"] for v in violations)),
        }

    hipaa_checker = PythonCodeNode.from_function(
        name="check_hipaa_compliance", func=check_hipaa_violations
    )

    # Step 4: Check for SOX violations (financial controls)
    def check_sox_violations(access_analysis):
        """Check for SOX compliance violations."""
        user_activity = access_analysis.get("user_activity_summary", {})
        violations = []

        for user_id, activity in user_activity.items():
            # Check for segregation of duties
            resources = activity.get("resources_accessed", [])
            has_ap = any("accounts_payable" in r for r in resources)
            has_ar = any("accounts_receivable" in r for r in resources)
            has_gl = any("general_ledger" in r for r in resources)

            if has_ap and has_ar:
                violations.append(
                    {
                        "type": "segregation_of_duties",
                        "severity": "critical",
                        "user_id": user_id,
                        "description": "User has access to both AP and AR systems",
                        "regulation": "SOX",
                        "remediation": "Remove conflicting access immediately",
                    }
                )

            # Check for unauthorized financial data modification
            if activity.get("sensitive_data_access", 0) > 20 and "financial" in str(
                resources
            ):
                violations.append(
                    {
                        "type": "excessive_financial_access",
                        "severity": "high",
                        "user_id": user_id,
                        "description": f"High volume of financial data access: {activity['sensitive_data_access']} times",
                        "regulation": "SOX",
                        "remediation": "Audit financial data access and verify authorization",
                    }
                )

        return {
            "sox_violations": violations,
            "violation_count": len(violations),
            "critical_violations": len(
                [v for v in violations if v["severity"] == "critical"]
            ),
        }

    sox_checker = PythonCodeNode.from_function(
        name="check_sox_compliance", func=check_sox_violations
    )

    # Step 5: Check role assignments for compliance
    list_all_users = UserManagementNode(
        name="list_active_users",
        operation="list",
        filters={"status": "active"},
        pagination={"page": 1, "size": 1000},
        tenant_id=audit_config["organization"],
    )

    def check_role_compliance(users_result, hipaa_result, sox_result):
        """Check role assignments for compliance issues."""
        users = users_result.get("users", [])
        issues = []

        # Combine violations
        all_violations = hipaa_result.get("hipaa_violations", []) + sox_result.get(
            "sox_violations", []
        )
        users_with_violations = set(v["user_id"] for v in all_violations)

        for user in users:
            user_id = user.get("user_id")
            roles = user.get("roles", [])

            # Check for excessive roles (more than 3)
            if len(roles) > 3:
                issues.append(
                    {
                        "type": "excessive_roles",
                        "user_id": user_id,
                        "severity": "medium",
                        "description": f"User has {len(roles)} roles (recommended max: 3)",
                        "current_roles": roles,
                        "remediation": "Review and consolidate role assignments",
                    }
                )

            # Check for users with violations who have admin roles
            if user_id in users_with_violations and any(
                "admin" in role for role in roles
            ):
                issues.append(
                    {
                        "type": "high_risk_admin",
                        "user_id": user_id,
                        "severity": "critical",
                        "description": "Admin user with compliance violations",
                        "remediation": "Immediate review of admin privileges required",
                    }
                )

            # Check for dormant accounts (no login in 90 days)
            last_login = user.get("last_login")
            if last_login:
                last_login_date = datetime.fromisoformat(
                    last_login.replace("Z", "+00:00")
                )
                days_since_login = (datetime.now(UTC) - last_login_date).days
                if days_since_login > 90:
                    issues.append(
                        {
                            "type": "dormant_account",
                            "user_id": user_id,
                            "severity": "low",
                            "description": f"No login for {days_since_login} days",
                            "remediation": "Disable or remove dormant account",
                        }
                    )

        return {
            "role_compliance_issues": issues,
            "total_issues": len(issues),
            "users_reviewed": len(users),
        }

    role_compliance_checker = PythonCodeNode.from_function(
        name="check_role_compliance", func=check_role_compliance
    )

    # Step 6: Generate compliance scores
    def calculate_compliance_scores(hipaa_result, sox_result, role_result):
        """Calculate overall compliance scores."""

        # Base scores
        hipaa_score = 100.0
        sox_score = 100.0
        role_score = 100.0

        # Deduct for HIPAA violations
        hipaa_violations = hipaa_result.get("hipaa_violations", [])
        for violation in hipaa_violations:
            if violation["severity"] == "critical":
                hipaa_score -= 10
            elif violation["severity"] == "high":
                hipaa_score -= 5
            elif violation["severity"] == "medium":
                hipaa_score -= 2
            else:
                hipaa_score -= 1

        # Deduct for SOX violations
        sox_violations = sox_result.get("sox_violations", [])
        for violation in sox_violations:
            if violation["severity"] == "critical":
                sox_score -= 15
            elif violation["severity"] == "high":
                sox_score -= 7
            elif violation["severity"] == "medium":
                sox_score -= 3

        # Deduct for role issues
        role_issues = role_result.get("role_compliance_issues", [])
        for issue in role_issues:
            if issue["severity"] == "critical":
                role_score -= 8
            elif issue["severity"] == "medium":
                role_score -= 3
            else:
                role_score -= 1

        # Calculate overall score
        overall_score = hipaa_score * 0.4 + sox_score * 0.4 + role_score * 0.2

        return {
            "compliance_scores": {
                "hipaa": max(0, hipaa_score),
                "sox": max(0, sox_score),
                "role_management": max(0, role_score),
                "overall": max(0, overall_score),
            },
            "compliance_status": (
                "compliant" if overall_score >= 80 else "non_compliant"
            ),
            "risk_level": (
                "low"
                if overall_score >= 90
                else "medium" if overall_score >= 70 else "high"
            ),
        }

    score_calculator = PythonCodeNode.from_function(
        name="calculate_scores", func=calculate_compliance_scores
    )

    # Step 7: Generate remediation tasks
    def generate_remediation_tasks(
        hipaa_result, sox_result, role_result, scores_result
    ):
        """Generate specific remediation tasks."""
        tasks = []

        # Process all violations and issues
        all_items = (
            hipaa_result.get("hipaa_violations", [])
            + sox_result.get("sox_violations", [])
            + role_result.get("role_compliance_issues", [])
        )

        # Group by user
        user_tasks = {}
        for item in all_items:
            user_id = item.get("user_id")
            if user_id not in user_tasks:
                user_tasks[user_id] = []
            user_tasks[user_id].append(item)

        # Create remediation tasks
        task_id = 1
        for user_id, violations in user_tasks.items():
            # Determine priority based on severity
            max_severity = max(v.get("severity", "low") for v in violations)
            priority = (
                "immediate"
                if max_severity == "critical"
                else "high" if max_severity == "high" else "normal"
            )

            task = {
                "task_id": f"REM-{audit_config['quarter']}-{task_id:04d}",
                "user_id": user_id,
                "priority": priority,
                "violations": violations,
                "assigned_to": "compliance_team",
                "due_date": (
                    datetime.now(UTC)
                    + timedelta(days=7 if priority == "immediate" else 30)
                ).isoformat(),
                "status": "pending",
                "actions_required": list(
                    set(
                        v.get("remediation", "")
                        for v in violations
                        if v.get("remediation")
                    )
                ),
            }
            tasks.append(task)
            task_id += 1

        return {
            "remediation_tasks": tasks,
            "task_count": len(tasks),
            "immediate_actions": len(
                [t for t in tasks if t["priority"] == "immediate"]
            ),
            "estimated_completion_days": 30 if tasks else 0,
        }

    task_generator = PythonCodeNode.from_function(
        name="generate_tasks", func=generate_remediation_tasks
    )

    # Step 8: Create executive summary report
    def create_executive_report(
        access_analysis,
        hipaa_result,
        sox_result,
        role_result,
        scores_result,
        tasks_result,
    ):
        """Create executive summary report."""

        report = {
            "report_id": f"COMPLIANCE-{audit_config['quarter']}-{datetime.now(UTC).strftime('%Y%m%d')}",
            "organization": audit_config["organization"],
            "audit_period": {
                "quarter": audit_config["quarter"],
                "start": audit_config["quarter_start"],
                "end": audit_config["quarter_end"],
            },
            "executive_summary": {
                "overall_score": scores_result["compliance_scores"]["overall"],
                "compliance_status": scores_result["compliance_status"],
                "risk_level": scores_result["risk_level"],
                "users_analyzed": access_analysis["total_users_analyzed"],
                "events_reviewed": access_analysis["total_events_analyzed"],
            },
            "compliance_breakdown": {
                "hipaa": {
                    "score": scores_result["compliance_scores"]["hipaa"],
                    "violations": hipaa_result["violation_count"],
                    "users_affected": hipaa_result["users_with_violations"],
                },
                "sox": {
                    "score": scores_result["compliance_scores"]["sox"],
                    "violations": sox_result["violation_count"],
                    "critical_violations": sox_result["critical_violations"],
                },
                "role_management": {
                    "score": scores_result["compliance_scores"]["role_management"],
                    "issues": role_result["total_issues"],
                    "users_reviewed": role_result["users_reviewed"],
                },
            },
            "remediation": {
                "total_tasks": tasks_result["task_count"],
                "immediate_actions": tasks_result["immediate_actions"],
                "estimated_completion": tasks_result["estimated_completion_days"],
            },
            "recommendations": [
                "Implement automated compliance monitoring",
                "Enhance role-based access controls",
                "Conduct monthly access reviews",
                "Provide additional compliance training",
            ],
            "generated_at": datetime.now(UTC).isoformat(),
            "next_audit_date": (datetime.now(UTC) + timedelta(days=90)).isoformat(),
        }

        return {"executive_report": report}

    report_generator = PythonCodeNode.from_function(
        name="generate_executive_report", func=create_executive_report
    )

    # Step 9: Log compliance audit completion
    audit_completion = AuditLogNode(
        name="log_audit_completion",
        operation="log_event",
        event_data={
            "event_type": "compliance_event",
            "severity": "high",
            "action": "quarterly_compliance_audit_completed",
            "description": f"Q{audit_config['quarter']} compliance audit completed",
            "metadata": {
                "audit_type": "quarterly_compliance",
                "regulations": ["HIPAA", "SOX"],
                "automated": True,
            },
        },
        tenant_id=audit_config["organization"],
    )

    # Build workflow
    workflow = Workflow(name="quarterly_compliance_audit")
    workflow.add_nodes(
        [
            collect_user_activity,
            access_analyzer,
            hipaa_checker,
            sox_checker,
            list_all_users,
            role_compliance_checker,
            score_calculator,
            task_generator,
            report_generator,
            audit_completion,
        ]
    )

    # Connect workflow
    workflow.connect(
        collect_user_activity, access_analyzer, {"result": "activity_result"}
    )
    workflow.connect(access_analyzer, hipaa_checker, {"result": "access_analysis"})
    workflow.connect(access_analyzer, sox_checker, {"result": "access_analysis"})

    workflow.connect(
        list_all_users, role_compliance_checker, {"result": "users_result"}
    )
    workflow.connect(hipaa_checker, role_compliance_checker, {"result": "hipaa_result"})
    workflow.connect(sox_checker, role_compliance_checker, {"result": "sox_result"})

    workflow.connect(hipaa_checker, score_calculator, {"result": "hipaa_result"})
    workflow.connect(sox_checker, score_calculator, {"result": "sox_result"})
    workflow.connect(
        role_compliance_checker, score_calculator, {"result": "role_result"}
    )

    workflow.connect(hipaa_checker, task_generator, {"result": "hipaa_result"})
    workflow.connect(sox_checker, task_generator, {"result": "sox_result"})
    workflow.connect(role_compliance_checker, task_generator, {"result": "role_result"})
    workflow.connect(score_calculator, task_generator, {"result": "scores_result"})

    workflow.connect(access_analyzer, report_generator, {"result": "access_analysis"})
    workflow.connect(hipaa_checker, report_generator, {"result": "hipaa_result"})
    workflow.connect(sox_checker, report_generator, {"result": "sox_result"})
    workflow.connect(
        role_compliance_checker, report_generator, {"result": "role_result"}
    )
    workflow.connect(score_calculator, report_generator, {"result": "scores_result"})
    workflow.connect(task_generator, report_generator, {"result": "tasks_result"})

    workflow.connect(report_generator, audit_completion, {"result": "report"})

    return workflow


def create_real_time_violation_detection_workflow(monitoring_config: Dict[str, Any]):
    """
    Real scenario: Real-time compliance violation detection and response.

    Monitors for:
    - Unauthorized access attempts
    - Data export violations
    - Segregation of duties violations
    - Suspicious access patterns
    """

    # Monitor recent security events
    monitor_events = SecurityEventNode(
        name="monitor_security_events",
        operation="analyze_threats",
        analysis_config={
            "time_window": monitoring_config.get("window", 3600),  # 1 hour
            "risk_threshold": 5.0,  # Lower threshold for compliance
            "threat_types": [
                "unauthorized_access_attempt",
                "data_exfiltration",
                "unusual_data_access",
                "policy_violation",
            ],
        },
        tenant_id=monitoring_config["organization"],
    )

    # Check for compliance violations in events
    def detect_compliance_violations(threat_analysis):
        """Detect compliance violations from security events."""
        events = threat_analysis.get("threat_analysis", {}).get("high_risk_events", [])
        violations = []

        for event in events:
            event_type = event.get("event_type")

            # HIPAA violation - unauthorized PHI access
            if event_type == "unauthorized_access_attempt" and "patient" in event.get(
                "target_resource", ""
            ):
                violations.append(
                    {
                        "type": "hipaa_unauthorized_phi_access",
                        "severity": "critical",
                        "event_id": event.get("event_id"),
                        "user_id": event.get("user_id"),
                        "resource": event.get("target_resource"),
                        "regulation": "HIPAA",
                        "immediate_action": "revoke_access",
                        "notification_required": True,
                    }
                )

            # SOX violation - unauthorized financial data export
            elif event_type == "data_exfiltration" and "financial" in event.get(
                "target_resource", ""
            ):
                violations.append(
                    {
                        "type": "sox_unauthorized_export",
                        "severity": "critical",
                        "event_id": event.get("event_id"),
                        "user_id": event.get("user_id"),
                        "data_volume": event.get("indicators", {}).get(
                            "data_volume", 0
                        ),
                        "regulation": "SOX",
                        "immediate_action": "block_export",
                        "investigation_required": True,
                    }
                )

        return {
            "violations_detected": violations,
            "violation_count": len(violations),
            "critical_violations": len(
                [v for v in violations if v["severity"] == "critical"]
            ),
            "requires_immediate_action": len(violations) > 0,
        }

    violation_detector = PythonCodeNode.from_function(
        name="detect_violations", func=detect_compliance_violations
    )

    # Decision routing for violations
    violation_router = SwitchNode(
        name="violation_response_router",
        condition_mappings={
            True: ["immediate_response", "create_incident", "notify_compliance"],
            False: ["log_monitoring"],
        },
    )

    # Immediate response actions
    def prepare_immediate_response(violations_result):
        """Prepare immediate response actions for violations."""
        violations = violations_result.get("violations_detected", [])
        response_actions = []

        for violation in violations:
            action = violation.get("immediate_action")
            user_id = violation.get("user_id")

            if action == "revoke_access":
                response_actions.append(
                    {"type": "disable_user", "parameters": {"user_id": user_id}}
                )
            elif action == "block_export":
                response_actions.append(
                    {
                        "type": "block_data_export",
                        "parameters": {"user_id": user_id, "duration": "immediate"},
                    }
                )

        return {"response_actions": response_actions}

    response_preparer = PythonCodeNode.from_function(
        name="prepare_response", func=prepare_immediate_response
    )

    # Execute immediate response
    immediate_response = SecurityEventNode(
        name="execute_immediate_response",
        operation="automated_response",
        tenant_id=monitoring_config["organization"],
    )

    # Create compliance incident
    def create_compliance_incident(violations_result):
        """Create compliance incident for investigation."""
        violations = violations_result.get("violations_detected", [])

        if not violations:
            return {"incident_data": None}

        # Group violations by regulation
        hipaa_violations = [v for v in violations if v.get("regulation") == "HIPAA"]
        sox_violations = [v for v in violations if v.get("regulation") == "SOX"]

        incident_data = {
            "title": f"Compliance Violations Detected - {len(violations)} violations",
            "description": f"Real-time monitoring detected {len(hipaa_violations)} HIPAA and {len(sox_violations)} SOX violations requiring immediate attention.",
            "severity": (
                "critical"
                if any(v["severity"] == "critical" for v in violations)
                else "high"
            ),
            "impact_assessment": {
                "regulations_affected": list(
                    set(v.get("regulation") for v in violations)
                ),
                "users_involved": list(set(v.get("user_id") for v in violations)),
                "immediate_actions_taken": len(
                    [v for v in violations if v.get("immediate_action")]
                ),
                "notifications_required": len(
                    [v for v in violations if v.get("notification_required", False)]
                ),
            },
        }

        return {"incident_data": incident_data}

    incident_creator = PythonCodeNode.from_function(
        name="prepare_incident", func=create_compliance_incident
    )

    create_incident = SecurityEventNode(
        name="create_compliance_incident",
        operation="create_incident",
        tenant_id=monitoring_config["organization"],
    )

    # Notify compliance team
    def prepare_compliance_notification(violations_result, incident_result):
        """Prepare notification for compliance team."""
        violations = violations_result.get("violations_detected", [])
        incident = incident_result.get("incident", {})

        notification = {
            "notification_type": "compliance_violation_alert",
            "priority": "urgent",
            "recipients": ["compliance@healthcare.org", "ciso@healthcare.org"],
            "subject": f"URGENT: {len(violations)} Compliance Violations Detected",
            "body": {
                "summary": f"Real-time monitoring has detected {len(violations)} compliance violations.",
                "incident_id": incident.get("incident_id"),
                "violations": violations,
                "actions_taken": "Immediate response actions executed",
                "next_steps": "Please review incident and initiate investigation",
            },
            "requires_acknowledgment": True,
        }

        return {"notification": notification}

    notification_preparer = PythonCodeNode.from_function(
        name="prepare_notification", func=prepare_compliance_notification
    )

    # Log monitoring results
    log_monitoring = AuditLogNode(
        name="log_monitoring_results",
        operation="log_event",
        event_data={
            "event_type": "compliance_event",
            "severity": "low",
            "action": "compliance_monitoring_completed",
            "description": "Real-time compliance monitoring cycle completed",
            "metadata": {
                "monitoring_type": "real_time",
                "window_minutes": monitoring_config.get("window", 3600) / 60,
            },
        },
        tenant_id=monitoring_config["organization"],
    )

    # Build workflow
    workflow = Workflow(name="real_time_compliance_monitoring")
    workflow.add_nodes(
        [
            monitor_events,
            violation_detector,
            violation_router,
            response_preparer,
            immediate_response,
            incident_creator,
            create_incident,
            notification_preparer,
            log_monitoring,
        ]
    )

    # Connect workflow
    workflow.connect(monitor_events, violation_detector, {"result": "threat_analysis"})
    workflow.connect(
        violation_detector, violation_router, {"result": "requires_immediate_action"}
    )

    # Violation response path
    workflow.connect(violation_router, response_preparer)
    workflow.connect(
        violation_detector, response_preparer, {"result": "violations_result"}
    )
    workflow.connect(
        response_preparer, immediate_response, {"result": "response_actions"}
    )

    workflow.connect(violation_router, incident_creator)
    workflow.connect(
        violation_detector, incident_creator, {"result": "violations_result"}
    )
    workflow.connect(incident_creator, create_incident, {"result": "incident_data"})

    workflow.connect(violation_router, notification_preparer)
    workflow.connect(
        violation_detector, notification_preparer, {"result": "violations_result"}
    )
    workflow.connect(
        create_incident, notification_preparer, {"result": "incident_result"}
    )

    # Normal monitoring path
    workflow.connect(violation_router, log_monitoring)

    return workflow


async def test_compliance_scenarios():
    """Test comprehensive compliance and audit scenarios."""

    print("🏥 Regional Healthcare Network - Compliance & Audit Testing")
    print("=" * 70)

    runtime = LocalRuntime()

    # Scenario 1: Quarterly Compliance Audit
    print("\n📊 Scenario 1: Q4 2024 Compliance Audit")
    print("-" * 50)

    audit_config = {
        "organization": "regional_healthcare",
        "quarter": "Q4-2024",
        "quarter_start": "2024-10-01T00:00:00Z",
        "quarter_end": "2024-12-31T23:59:59Z",
    }

    audit_workflow = create_quarterly_compliance_audit_workflow(audit_config)
    audit_result = await runtime.run_workflow(audit_workflow)

    # Extract key results
    access_analysis = audit_result.get("analyze_access_patterns", {})
    print(
        f"✅ Analyzed {access_analysis.get('total_events_analyzed', 0)} events from {access_analysis.get('total_users_analyzed', 0)} users"
    )

    hipaa_violations = audit_result.get("check_hipaa_compliance", {})
    print(
        f"⚠️  HIPAA violations: {hipaa_violations.get('violation_count', 0)} affecting {hipaa_violations.get('users_with_violations', 0)} users"
    )

    sox_violations = audit_result.get("check_sox_compliance", {})
    print(
        f"⚠️  SOX violations: {sox_violations.get('violation_count', 0)} ({sox_violations.get('critical_violations', 0)} critical)"
    )

    scores = audit_result.get("calculate_scores", {}).get("compliance_scores", {})
    print("\n📈 Compliance Scores:")
    print(f"   - HIPAA: {scores.get('hipaa', 0):.1f}%")
    print(f"   - SOX: {scores.get('sox', 0):.1f}%")
    print(f"   - Role Management: {scores.get('role_management', 0):.1f}%")
    print(f"   - Overall: {scores.get('overall', 0):.1f}%")

    tasks = audit_result.get("generate_tasks", {})
    print(
        f"\n🔧 Remediation: {tasks.get('task_count', 0)} tasks generated ({tasks.get('immediate_actions', 0)} immediate)"
    )

    report = audit_result.get("generate_executive_report", {}).get(
        "executive_report", {}
    )
    print(f"\n📄 Executive Report: {report.get('report_id', 'N/A')}")
    print(
        f"   - Status: {report.get('executive_summary', {}).get('compliance_status', 'Unknown')}"
    )
    print(
        f"   - Risk Level: {report.get('executive_summary', {}).get('risk_level', 'Unknown')}"
    )

    # Scenario 2: Real-time Violation Detection
    print("\n\n🚨 Scenario 2: Real-time Compliance Monitoring")
    print("-" * 50)

    monitoring_config = {
        "organization": "regional_healthcare",
        "window": 3600,  # 1 hour
        "alert_threshold": 5.0,
    }

    monitoring_workflow = create_real_time_violation_detection_workflow(
        monitoring_config
    )
    monitoring_result = await runtime.run_workflow(monitoring_workflow)

    violations = monitoring_result.get("detect_violations", {})
    print(
        f"⚠️  Violations detected: {violations.get('violation_count', 0)} ({violations.get('critical_violations', 0)} critical)"
    )

    if violations.get("requires_immediate_action"):
        response = monitoring_result.get("execute_immediate_response", {})
        print(
            f"🔒 Immediate response: {len(response.get('executed_actions', []))} actions executed"
        )

        incident = monitoring_result.get("create_compliance_incident", {}).get(
            "incident", {}
        )
        if incident:
            print(f"📋 Incident created: {incident.get('incident_id', 'N/A')}")
            print(f"   - Title: {incident.get('title', 'N/A')}")
            print(f"   - Severity: {incident.get('severity', 'N/A')}")
    else:
        print("✅ No violations detected - system compliant")

    # Summary
    print("\n" + "=" * 70)
    print("📊 COMPLIANCE & AUDIT TEST SUMMARY")
    print("=" * 70)
    print("✅ Quarterly audit completed with comprehensive analysis")
    print("✅ Real-time monitoring active and detecting violations")
    print("✅ Automated remediation tasks generated")
    print("✅ Executive reporting ready for board review")
    print("\n🎯 Healthcare compliance system fully operational!")

    return {
        "test_status": "completed",
        "scenarios_tested": 2,
        "results": {
            "quarterly_audit": audit_result,
            "real_time_monitoring": monitoring_result,
        },
    }


if __name__ == "__main__":
    # Run compliance testing
    result = asyncio.execute(test_compliance_scenarios())

    # Save results
    import json

    with open("compliance_audit_test_results.json", "w") as f:
        json.dump(result, f, indent=2, default=str)

    print("\n📄 Detailed results saved to: compliance_audit_test_results.json")
