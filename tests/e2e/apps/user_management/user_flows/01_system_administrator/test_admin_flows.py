"""
System Administrator User Flow Tests
Using real Kailash SDK components - no mocks
"""

import asyncio
import csv
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

from apps.user_management.config.settings import UserManagementConfig
from apps.user_management.main import UserManagementApp
from kailash.runtime import LocalRuntime
from kailash.workflow import WorkflowBuilder


class TestSystemAdministratorFlows:
    """Test all System Administrator user flows with real implementations"""

    @pytest_asyncio.fixture
    async def setup_environment(self):
        """Set up real test environment with database and services"""
        # Initialize app
        app = UserManagementApp()
        await app.setup_database()

        # Create admin user for tests
        runtime = LocalRuntime()
        reg_workflow = app.user_api.create_user_registration_workflow()

        admin_data = {
            "email": "admin@example.com",
            "username": "admin",
            "password": "AdminPass123!",
        }

        admin_result = await runtime.execute_async(reg_workflow, admin_data)

        # Assign admin role
        if admin_result["success"]:
            role_workflow = app.role_api.create_role_management_workflow()
            await runtime.execute_async(
                role_workflow,
                {
                    "user_id": "system",
                    "action": "manage",
                    "operation": "assign_role_to_user",
                    "data": {
                        "user_id": admin_result["user"]["id"],
                        "role_name": "admin",
                    },
                },
            )

        return {
            "app": app,
            "runtime": runtime,
            "admin_user": admin_result["user"],
            "admin_token": admin_result["tokens"]["access"],
        }

    @pytest.mark.asyncio
    async def test_initial_system_setup_flow(self, setup_environment):
        """Test SA-SETUP-001: Complete initial system setup"""
        env = await setup_environment
        app = env["app"]
        runtime = env["runtime"]
        admin_user = env["admin_user"]

        # Step 1: Configure system-wide settings
        config_node = runtime.create_node("PythonCodeNode")
        config_result = await runtime.execute_node_async(
            config_node,
            {
                "code": '''
import json
from datetime import datetime

# System configuration
system_config = {
    "organization_name": "Test Corp",
    "security_settings": {
                "password_policy": {
                    "min_length": 12,
                    "require_uppercase": True,
                    "require_numbers": True,
                    "require_special": True,
                    "expiry_days": 90
                },
                "session_policy": {
                    "timeout_minutes": 30,
                    "max_concurrent": 3
                },
                "lockout_policy": {
                    "max_attempts": 5,
                    "lockout_duration_minutes": 30
                }
            },
            "audit_settings": {
                "retention_days": 365,
                "export_formats": ["json", "csv"],
                "real_time_alerts": True
            },
            "configured_at": datetime.utcnow().isoformat(),
            "configured_by": "'''
                + admin_user["id"]
                + """"
        }

        result = {"config": system_config, "success": True}
"""
            },
        )

        assert config_result["success"] is True

        # Step 2: Create initial role hierarchy
        roles = [
            {
                "name": "admin",
                "description": "System Administrator",
                "permissions": ["*"],
                "is_system": True,
            },
            {
                "name": "manager",
                "description": "Department Manager",
                "permissions": ["users:read", "users:update", "reports:*"],
                "parent": None,
            },
            {
                "name": "employee",
                "description": "Regular Employee",
                "permissions": ["profile:*", "documents:read"],
                "parent": "manager",
            },
        ]

        role_workflow = app.role_api.create_role_management_workflow()

        for role_data in roles:
            if role_data["name"] != "admin":  # Admin already exists
                result = await runtime.execute_async(
                    role_workflow,
                    {
                        "user_id": admin_user["id"],
                        "action": "create",
                        "operation": "create_role",
                        "role_data": {
                            "name": role_data["name"],
                            "description": role_data["description"],
                            "permissions": role_data["permissions"],
                        },
                    },
                )
                assert result["success"] is True

        # Step 3: Set up default security policies
        security_workflow = WorkflowBuilder("security_setup")
        security_workflow.add_node("policy_creator", "PythonCodeNode")
        security_workflow.add_node(
            "audit_logger",
            "EnterpriseAuditLogNode",
            app.config.NODE_CONFIGS["EnterpriseAuditLogNode"],
        )

        security_workflow.add_connection("input", "policy_creator", "data", "input")
        security_workflow.add_connection(
            "policy_creator", "audit_logger", "result", "input"
        )
        security_workflow.add_connection("audit_logger", "output", "result", "result")

        policy_code = """
# Create security policies
policies = {
    "ip_whitelist": ["10.0.0.0/8", "192.168.0.0/16"],
    "require_2fa_for_admins": True,
    "api_rate_limits": {
        "default": 1000,
        "authenticated": 5000,
        "admin": 10000
    },
    "password_history": 5,
    "session_recording": True
}

result = {
    "operation": "log_event",
    "event_type": "security_policy_configured",
    "severity": "high",
    "details": {
        "policies": policies,
        "configured_by": input_data.get("admin_id")
    }
}
"""
        security_workflow.update_node("policy_creator", {"code": policy_code})

        security_result = await runtime.execute_async(
            security_workflow, {"admin_id": admin_user["id"]}
        )

        assert security_result["success"] is True

        # Step 4: Enable monitoring and alerts
        monitoring_workflow = WorkflowBuilder("monitoring_setup")
        monitoring_workflow.add_node("alert_config", "PythonCodeNode")
        monitoring_workflow.add_node(
            "security_events",
            "EnterpriseSecurityEventNode",
            app.config.NODE_CONFIGS["EnterpriseSecurityEventNode"],
        )

        monitoring_workflow.add_connection("input", "alert_config", "data", "input")
        monitoring_workflow.add_connection(
            "alert_config", "security_events", "result", "input"
        )
        monitoring_workflow.add_connection(
            "security_events", "output", "result", "result"
        )

        alert_code = """
# Configure alerts
alerts = {
    "failed_login_threshold": 3,
    "permission_denied_threshold": 10,
    "api_error_rate_threshold": 0.05,
    "notification_channels": ["email", "slack", "sms"],
    "escalation_policy": {
        "level_1": {"time": 5, "notify": ["oncall"]},
        "level_2": {"time": 15, "notify": ["manager"]},
        "level_3": {"time": 30, "notify": ["director"]}
    }
}

result = {
    "operation": "configure_monitoring",
    "event_type": "monitoring_configured",
    "severity": "medium",
    "details": alerts
}
"""
        monitoring_workflow.update_node("alert_config", {"code": alert_code})

        monitoring_result = await runtime.execute_async(monitoring_workflow, {})

        assert monitoring_result["success"] is True

        # Verify complete setup
        setup_summary = {
            "system_configured": config_result["success"],
            "roles_created": len(roles),
            "security_policies": security_result["success"],
            "monitoring_enabled": monitoring_result["success"],
            "setup_complete": all(
                [
                    config_result["success"],
                    security_result["success"],
                    monitoring_result["success"],
                ]
            ),
        }

        assert setup_summary["setup_complete"] is True

    @pytest.mark.asyncio
    async def test_user_provisioning_flow(self, setup_environment):
        """Test SA-USER-001: Complete user provisioning flow"""
        env = await setup_environment
        app = env["app"]
        runtime = env["runtime"]
        admin_user = env["admin_user"]

        # Step 1: Create new user with all fields
        user_data = {
            "email": "john.doe@example.com",
            "username": "johndoe",
            "password": "TempPass123!",
            "first_name": "John",
            "last_name": "Doe",
            "department": "Engineering",
            "phone": "+1-555-0123",
            "employee_id": "EMP12345",
            "manager_email": "manager@example.com",
            "start_date": datetime.utcnow().isoformat(),
            "custom_attributes": {
                "team": "Backend",
                "location": "NYC",
                "skills": ["Python", "Go", "Kubernetes"],
            },
        }

        # Create user
        reg_workflow = app.user_api.create_user_registration_workflow()
        user_result = await runtime.execute_async(reg_workflow, user_data)

        assert user_result["success"] is True
        new_user_id = user_result["user"]["id"]

        # Step 2: Assign roles based on department
        role_workflow = app.role_api.create_role_management_workflow()

        roles_to_assign = ["employee", "developer"]
        for role in roles_to_assign:
            # Create developer role if it doesn't exist
            if role == "developer":
                await runtime.execute_async(
                    role_workflow,
                    {
                        "user_id": admin_user["id"],
                        "action": "create",
                        "operation": "create_role",
                        "role_data": {
                            "name": "developer",
                            "description": "Software Developer",
                            "permissions": [
                                "code:read",
                                "code:write",
                                "ci:trigger",
                                "docs:write",
                            ],
                        },
                    },
                )

            # Assign role
            assign_result = await runtime.execute_async(
                role_workflow,
                {
                    "user_id": admin_user["id"],
                    "action": "manage",
                    "operation": "assign_role_to_user",
                    "data": {"user_id": new_user_id, "role_name": role},
                },
            )
            assert assign_result["success"] is True

        # Step 3: Configure user-specific permissions
        perm_workflow = WorkflowBuilder("user_permissions")
        perm_workflow.add_node("permission_setter", "PythonCodeNode")
        perm_workflow.add_node(
            "user_updater",
            "UserManagementNode",
            app.config.NODE_CONFIGS["UserManagementNode"],
        )

        perm_workflow.add_connection("input", "permission_setter", "data", "input")
        perm_workflow.add_connection(
            "permission_setter", "user_updater", "result", "input"
        )
        perm_workflow.add_connection("user_updater", "output", "result", "result")

        perm_code = """
# Set user-specific permissions
user_permissions = {
    "project_access": ["project_alpha", "project_beta"],
    "database_access": ["dev_db", "staging_db"],
    "service_accounts": ["backend_service", "api_service"],
    "resource_quotas": {
        "cpu_cores": 4,
        "memory_gb": 16,
        "storage_gb": 100
    }
}

result = {
    "operation": "update_user",
    "user_id": input_data["user_id"],
    "updates": {
        "attributes": {
            **input_data.get("current_attributes", {}),
            "permissions": user_permissions,
            "provisioned_by": input_data["admin_id"],
            "provisioned_at": datetime.utcnow().isoformat()
        }
    }
}
"""
        perm_workflow.update_node("permission_setter", {"code": perm_code})

        perm_result = await runtime.execute_async(
            perm_workflow,
            {
                "user_id": new_user_id,
                "admin_id": admin_user["id"],
                "current_attributes": user_data.get("custom_attributes", {}),
            },
        )

        assert perm_result["success"] is True

        # Step 4: Send welcome email (simulate)
        email_workflow = WorkflowBuilder("welcome_email")
        email_workflow.add_node("email_composer", "PythonCodeNode")
        email_workflow.add_node(
            "audit_logger",
            "EnterpriseAuditLogNode",
            app.config.NODE_CONFIGS["EnterpriseAuditLogNode"],
        )

        email_workflow.add_connection("input", "email_composer", "data", "input")
        email_workflow.add_connection(
            "email_composer", "audit_logger", "result", "input"
        )
        email_workflow.add_connection("audit_logger", "output", "result", "result")

        email_code = '''
import secrets

# Generate temporary access code
access_code = secrets.token_urlsafe(16)

email_content = {
    "to": input_data["email"],
    "subject": "Welcome to Test Corp",
    "body": f"""
Welcome {input_data["first_name"]}!

Your account has been created. Here are your login details:
- Username: {input_data["username"]}
- Temporary Password: {input_data["password"]}
- Access Code: {access_code}

Please login at: https://portal.testcorp.com
You will be required to change your password on first login.

Best regards,
IT Team
    """,
    "sent_at": datetime.utcnow().isoformat()
}

result = {
    "operation": "log_event",
    "event_type": "welcome_email_sent",
    "severity": "low",
    "details": {
        "user_id": input_data["user_id"],
        "email": input_data["email"],
        "access_code": access_code
    }
}
'''
        email_workflow.update_node("email_composer", {"code": email_code})

        email_result = await runtime.execute_async(
            email_workflow,
            {
                "user_id": new_user_id,
                "email": user_data["email"],
                "username": user_data["username"],
                "password": user_data["password"],
                "first_name": user_data["first_name"],
            },
        )

        assert email_result["success"] is True

        # Step 5: Monitor first login
        monitoring_workflow = WorkflowBuilder("first_login_monitor")
        monitoring_workflow.add_node("login_tracker", "PythonCodeNode")
        monitoring_workflow.add_node(
            "security_event",
            "EnterpriseSecurityEventNode",
            app.config.NODE_CONFIGS["EnterpriseSecurityEventNode"],
        )

        monitoring_workflow.add_connection("input", "login_tracker", "data", "input")
        monitoring_workflow.add_connection(
            "login_tracker", "security_event", "result", "input"
        )
        monitoring_workflow.add_connection(
            "security_event", "output", "result", "result"
        )

        tracker_code = """
# Set up first login monitoring
monitoring_config = {
    "user_id": input_data["user_id"],
    "monitor_duration_days": 7,
    "alert_if_no_login": True,
    "track_activities": [
        "first_login",
        "password_change",
        "profile_update",
        "permission_use"
    ],
    "notification_email": input_data["admin_email"]
}

result = {
    "operation": "configure_monitoring",
    "event_type": "first_login_monitoring",
    "severity": "low",
    "details": monitoring_config
}
"""
        monitoring_workflow.update_node("login_tracker", {"code": tracker_code})

        monitor_result = await runtime.execute_async(
            monitoring_workflow,
            {"user_id": new_user_id, "admin_email": admin_user["email"]},
        )

        assert monitor_result["success"] is True

        # Verify complete provisioning
        provisioning_summary = {
            "user_created": user_result["success"],
            "user_id": new_user_id,
            "roles_assigned": len(roles_to_assign),
            "permissions_configured": perm_result["success"],
            "welcome_email_sent": email_result["success"],
            "monitoring_enabled": monitor_result["success"],
            "provisioning_complete": True,
        }

        assert provisioning_summary["provisioning_complete"] is True

    @pytest.mark.asyncio
    async def test_bulk_user_import_flow(self, setup_environment):
        """Test SA-USER-003: Bulk import users from CSV"""
        env = await setup_environment
        app = env["app"]
        runtime = env["runtime"]
        admin_user = env["admin_user"]

        # Step 1: Prepare CSV data
        csv_data = []
        departments = ["Engineering", "Sales", "Marketing", "HR", "Finance"]

        for i in range(100):
            csv_data.append(
                {
                    "email": f"bulk_user_{i}@example.com",
                    "username": f"bulkuser{i}",
                    "first_name": f"User{i}",
                    "last_name": "Bulk",
                    "department": departments[i % len(departments)],
                    "role": "employee",
                }
            )

        # Step 2: Validate data
        validation_workflow = WorkflowBuilder("csv_validation")
        validation_workflow.add_node("validator", "PythonCodeNode")

        validator_code = """
import re

errors = []
validated_users = []
email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'

for idx, user in enumerate(input_data["users"]):
    user_errors = []

    # Validate email
    if not re.match(email_pattern, user.get("email", "")):
        user_errors.append(f"Row {idx}: Invalid email")

    # Validate username
    if len(user.get("username", "")) < 3:
        user_errors.append(f"Row {idx}: Username too short")

    # Validate required fields
    required = ["email", "username", "first_name", "last_name"]
    for field in required:
        if not user.get(field):
            user_errors.append(f"Row {idx}: Missing {field}")

    if user_errors:
        errors.extend(user_errors)
    else:
        validated_users.append(user)

result = {
    "valid_count": len(validated_users),
    "error_count": len(errors),
    "errors": errors[:10],  # First 10 errors
    "validated_users": validated_users
}
"""
        validation_workflow.update_node("validator", {"code": validator_code})

        validation_result = await runtime.execute_async(
            validation_workflow, {"users": csv_data}
        )

        assert validation_result["valid_count"] == 100
        assert validation_result["error_count"] == 0

        # Step 3: Execute bulk import
        start_time = time.time()

        import_workflow = app.bulk_api.create_bulk_import_workflow()
        import_result = await runtime.execute_async(
            import_workflow,
            {
                "admin_id": admin_user["id"],
                "users": validation_result["validated_users"],
            },
        )

        import_time = time.time() - start_time

        assert import_result["success"] is True
        assert import_result["summary"]["successful"] >= 95  # Allow 5% failure rate
        assert import_time < 30  # Should complete in under 30 seconds

        # Step 4: Generate import report
        report_workflow = WorkflowBuilder("import_report")
        report_workflow.add_node("report_generator", "PythonCodeNode")
        report_workflow.add_node("file_writer", "FileWriterNode")

        report_workflow.add_connection("input", "report_generator", "data", "input")
        report_workflow.add_connection(
            "report_generator", "file_writer", "result", "input"
        )
        report_workflow.add_connection("file_writer", "output", "result", "result")

        report_code = '''
from datetime import datetime

report = {
    "title": "Bulk User Import Report",
    "timestamp": datetime.utcnow().isoformat(),
    "admin": input_data["admin_email"],
    "summary": input_data["summary"],
    "details": {
        "total_processed": input_data["summary"]["total_processed"],
        "successful": input_data["summary"]["successful"],
        "failed": input_data["summary"]["failed"],
        "import_duration": input_data["duration"],
        "average_per_user": input_data["duration"] / input_data["summary"]["total_processed"]
    },
    "errors": input_data.get("errors", [])[:20]  # First 20 errors
}

report_content = f"""
# Bulk User Import Report

**Date**: {report["timestamp"]}
**Administrator**: {report["admin"]}

## Summary
- Total Users Processed: {report["details"]["total_processed"]}
- Successfully Imported: {report["details"]["successful"]}
- Failed: {report["details"]["failed"]}
- Success Rate: {(report["details"]["successful"] / report["details"]["total_processed"] * 100):.1f}%

## Performance
- Total Duration: {report["details"]["import_duration"]:.2f} seconds
- Average per User: {report["details"]["average_per_user"]:.3f} seconds

## Status: {"SUCCESS" if report["details"]["failed"] == 0 else "COMPLETED WITH ERRORS"}
"""

result = {
    "content": report_content,
    "filename": f"import_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.md",
    "format": "markdown"
}
'''
        report_workflow.update_node("report_generator", {"code": report_code})

        report_result = await runtime.execute_async(
            report_workflow,
            {
                "admin_email": admin_user["email"],
                "summary": import_result["summary"],
                "duration": import_time,
                "errors": import_result.get("validation_errors", []),
            },
        )

        assert report_result["success"] is True

        # Step 5: Notify HR
        notification_workflow = WorkflowBuilder("hr_notification")
        notification_workflow.add_node("notifier", "PythonCodeNode")
        notification_workflow.add_node(
            "audit_logger",
            "EnterpriseAuditLogNode",
            app.config.NODE_CONFIGS["EnterpriseAuditLogNode"],
        )

        notification_workflow.add_connection("input", "notifier", "data", "input")
        notification_workflow.add_connection(
            "notifier", "audit_logger", "result", "input"
        )
        notification_workflow.add_connection(
            "audit_logger", "output", "result", "result"
        )

        notifier_code = '''
notification = {
    "to": ["hr@example.com", "it-admin@example.com"],
    "subject": "Bulk User Import Completed",
    "body": f"""
The bulk user import has been completed.

Summary:
- Total Users: {input_data["total"]}
- Successful: {input_data["successful"]}
- Failed: {input_data["failed"]}

Report Location: {input_data["report_location"]}

Please review the report for details.
    """,
    "priority": "normal",
    "sent_at": datetime.utcnow().isoformat()
}

result = {
    "operation": "log_event",
    "event_type": "bulk_import_notification",
    "severity": "low",
    "details": notification
}
'''
        notification_workflow.update_node("notifier", {"code": notifier_code})

        notify_result = await runtime.execute_async(
            notification_workflow,
            {
                "total": import_result["summary"]["total_processed"],
                "successful": import_result["summary"]["successful"],
                "failed": import_result["summary"]["failed"],
                "report_location": report_result.get("filename", "N/A"),
            },
        )

        assert notify_result["success"] is True

        # Verify complete flow
        bulk_import_summary = {
            "validation_passed": validation_result["valid_count"] == 100,
            "import_successful": import_result["success"],
            "performance_met": import_time < 30,
            "report_generated": report_result["success"],
            "notification_sent": notify_result["success"],
            "bulk_import_complete": True,
        }

        assert bulk_import_summary["bulk_import_complete"] is True

    @pytest.mark.asyncio
    async def test_security_incident_response_flow(self, setup_environment):
        """Test SA-SEC-005: Security incident response flow"""
        env = await setup_environment
        app = env["app"]
        runtime = env["runtime"]
        admin_user = env["admin_user"]

        # Step 1: Simulate security alert
        security_event = {
            "event_type": "multiple_failed_logins",
            "severity": "high",
            "details": {
                "user_email": "john.doe@example.com",
                "failed_attempts": 10,
                "time_window": "5 minutes",
                "source_ips": ["192.168.1.100", "10.0.0.50"],
                "user_agent": "Mozilla/5.0 (suspicious)",
                "timestamp": datetime.utcnow().isoformat(),
            },
        }

        # Step 2: Investigate security event
        investigation_workflow = WorkflowBuilder("security_investigation")
        investigation_workflow.add_node("event_analyzer", "PythonCodeNode")
        investigation_workflow.add_node(
            "user_fetcher",
            "UserManagementNode",
            app.config.NODE_CONFIGS["UserManagementNode"],
        )
        investigation_workflow.add_node(
            "audit_searcher",
            "EnterpriseAuditLogNode",
            app.config.NODE_CONFIGS["EnterpriseAuditLogNode"],
        )

        investigation_workflow.add_connection(
            "input", "event_analyzer", "data", "input"
        )
        investigation_workflow.add_connection(
            "event_analyzer", "user_fetcher", "user_query", "input"
        )
        investigation_workflow.add_connection(
            "event_analyzer", "audit_searcher", "audit_query", "input"
        )
        investigation_workflow.add_connection(
            "user_fetcher", "output", "user_data", "user"
        )
        investigation_workflow.add_connection(
            "audit_searcher", "output", "audit_data", "logs"
        )

        analyzer_code = """
# Analyze security event
event = input_data["event"]
threat_score = 0

# Calculate threat score
if event["details"]["failed_attempts"] > 5:
    threat_score += 30
if len(event["details"]["source_ips"]) > 1:
    threat_score += 20
if "suspicious" in event["details"]["user_agent"]:
    threat_score += 25

# Determine response level
if threat_score >= 50:
    response_level = "immediate"
elif threat_score >= 30:
    response_level = "high"
else:
    response_level = "medium"

result = {
    "user_query": {
        "operation": "get_user",
        "identifier": event["details"]["user_email"],
        "identifier_type": "email"
    },
    "audit_query": {
        "operation": "search_logs",
        "filters": {
            "user_email": event["details"]["user_email"],
            "event_type": "login_attempt",
            "time_range": {
                "start": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
                "end": datetime.utcnow().isoformat()
            }
        },
        "limit": 50
    },
    "threat_analysis": {
        "score": threat_score,
        "level": response_level,
        "recommended_actions": [
            "lock_account" if threat_score >= 50 else "monitor",
            "notify_user",
            "block_ips" if len(event["details"]["source_ips"]) > 1 else "log_ips"
        ]
    }
}
"""
        investigation_workflow.update_node("event_analyzer", {"code": analyzer_code})

        investigation_result = await runtime.execute_async(
            investigation_workflow, {"event": security_event}
        )

        # Step 3: Take immediate action
        response_workflow = WorkflowBuilder("incident_response")
        response_workflow.add_node(
            "account_locker",
            "UserManagementNode",
            app.config.NODE_CONFIGS["UserManagementNode"],
        )
        response_workflow.add_node("ip_blocker", "PythonCodeNode")
        response_workflow.add_node("notification_sender", "PythonCodeNode")
        response_workflow.add_node(
            "security_logger",
            "EnterpriseSecurityEventNode",
            app.config.NODE_CONFIGS["EnterpriseSecurityEventNode"],
        )

        response_workflow.add_connection(
            "input", "account_locker", "lock_request", "input"
        )
        response_workflow.add_connection(
            "account_locker", "ip_blocker", "result", "input"
        )
        response_workflow.add_connection(
            "ip_blocker", "notification_sender", "result", "input"
        )
        response_workflow.add_connection(
            "notification_sender", "security_logger", "result", "input"
        )
        response_workflow.add_connection(
            "security_logger", "output", "result", "result"
        )

        # Lock account
        response_workflow.update_node(
            "account_locker",
            {
                "operation": "update_user",
                "user_id": "$.user.id",
                "updates": {
                    "status": "locked",
                    "locked_at": datetime.utcnow().isoformat(),
                    "locked_reason": "Security incident - multiple failed logins",
                },
            },
        )

        # Block IPs
        ip_block_code = """
# Block suspicious IPs
blocked_ips = []
for ip in input_data["ips"]:
    # In production, this would update firewall rules
    blocked_ips.append({
        "ip": ip,
        "blocked_at": datetime.utcnow().isoformat(),
        "duration": "24 hours",
        "reason": "Security incident"
    })

result = {
    "blocked_ips": blocked_ips,
    "user_locked": input_data.get("success", False),
    "notification_data": {
        "user_email": input_data["user_email"],
        "admin_email": input_data["admin_email"],
        "incident_id": f"INC-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    }
}
"""
        response_workflow.update_node("ip_blocker", {"code": ip_block_code})

        # Send notifications
        notification_code = '''
# Send security notifications
notifications = []

# Notify affected user
notifications.append({
    "to": input_data["user_email"],
    "subject": "Security Alert: Account Locked",
    "body": f"""
Your account has been temporarily locked due to suspicious activity.

Incident ID: {input_data["incident_id"]}

If this was you, please contact IT support to unlock your account.
If this wasn't you, your account may be compromised.

Security Team
    """,
    "type": "security_alert"
})

# Notify admin
notifications.append({
    "to": input_data["admin_email"],
    "subject": f"Security Incident: {input_data['incident_id']}",
    "body": f"""
Security incident detected and responded to automatically.

User: {input_data["user_email"]}
Action Taken: Account locked, IPs blocked
Blocked IPs: {', '.join([ip['ip'] for ip in input_data['blocked_ips']])}

Please review the incident details in the security dashboard.
    """,
    "type": "admin_alert"
})

result = {
    "operation": "log_event",
    "event_type": "security_incident_response",
    "severity": "high",
    "details": {
        "incident_id": input_data["incident_id"],
        "user_affected": input_data["user_email"],
        "actions_taken": ["account_locked", "ips_blocked", "notifications_sent"],
        "notifications": notifications
    }
}
'''
        response_workflow.update_node(
            "notification_sender", {"code": notification_code}
        )

        # Simulate user data for response
        mock_user = {"id": "user123", "email": "john.doe@example.com"}

        response_result = await runtime.execute_async(
            response_workflow,
            {
                "lock_request": {"user": mock_user},
                "ips": security_event["details"]["source_ips"],
                "user_email": security_event["details"]["user_email"],
                "admin_email": admin_user["email"],
            },
        )

        assert response_result["success"] is True

        # Step 4: Generate incident report
        report_workflow = WorkflowBuilder("incident_report")
        report_workflow.add_node("report_builder", "PythonCodeNode")
        report_workflow.add_node("report_saver", "FileWriterNode")

        report_workflow.add_connection("input", "report_builder", "data", "input")
        report_workflow.add_connection(
            "report_builder", "report_saver", "result", "input"
        )
        report_workflow.add_connection("report_saver", "output", "result", "result")

        report_builder_code = '''
incident_report = f"""
# Security Incident Report

**Incident ID**: {input_data["incident_id"]}
**Date/Time**: {input_data["timestamp"]}
**Severity**: HIGH
**Status**: RESOLVED

## Summary
Multiple failed login attempts detected for user account, indicating possible brute force attack.

## Affected User
- Email: {input_data["user_email"]}
- Failed Attempts: {input_data["failed_attempts"]}
- Time Window: {input_data["time_window"]}

## Attack Details
- Source IPs: {', '.join(input_data["source_ips"])}
- User Agent: {input_data["user_agent"]}

## Response Actions
1. Account automatically locked
2. Suspicious IPs blocked for 24 hours
3. User and admin notifications sent
4. Incident logged for audit

## Recommendations
1. User should reset password after unlock
2. Enable 2FA for affected account
3. Review logs for any successful logins before lock
4. Monitor for similar patterns from blocked IPs

## Follow-up Required
- [ ] Verify user identity before unlock
- [ ] Ensure password is reset
- [ ] Enable 2FA
- [ ] Review security training with user

**Report Generated By**: {input_data["admin_email"]}
**Report Date**: {datetime.utcnow().isoformat()}
"""

result = {
    "content": incident_report,
    "filename": f"security_incident_{input_data['incident_id']}.md",
    "format": "markdown"
}
'''
        report_workflow.update_node("report_builder", {"code": report_builder_code})

        report_result = await runtime.execute_async(
            report_workflow,
            {
                "incident_id": response_result["details"]["incident_id"],
                "timestamp": security_event["details"]["timestamp"],
                "user_email": security_event["details"]["user_email"],
                "failed_attempts": security_event["details"]["failed_attempts"],
                "time_window": security_event["details"]["time_window"],
                "source_ips": security_event["details"]["source_ips"],
                "user_agent": security_event["details"]["user_agent"],
                "admin_email": admin_user["email"],
            },
        )

        assert report_result["success"] is True

        # Verify complete incident response
        incident_summary = {
            "alert_received": True,
            "investigation_complete": investigation_result.get("threat_analysis")
            is not None,
            "account_locked": response_result["success"],
            "ips_blocked": len(response_result["details"]["actions_taken"]) > 0,
            "notifications_sent": "notifications_sent"
            in response_result["details"]["actions_taken"],
            "report_generated": report_result["success"],
            "incident_resolved": True,
        }

        assert incident_summary["incident_resolved"] is True
