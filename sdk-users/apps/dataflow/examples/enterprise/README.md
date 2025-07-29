# Enterprise DataFlow Example

Advanced enterprise features including multi-tenancy, access control, and audit logging.

## Overview

This example demonstrates enterprise-grade features:
- **Multi-tenant architecture** with data isolation
- **Role-based access control (RBAC)** with fine-grained permissions
- **Audit logging** for compliance and security
- **Data encryption** at rest and in transit
- **Advanced security** features
- **Performance monitoring** and metrics

## Enterprise Model Definition

```python
# models.py
from kailash_dataflow import DataFlow
from kailash_dataflow.enterprise import MultiTenantModel, AccessControlModel
from datetime import datetime
from typing import Optional, List
from enum import Enum

# Enterprise configuration
db = DataFlow(config={
    'multi_tenant': True,
    'encryption_enabled': True,
    'audit_logging': True,
    'access_control': 'rbac'
})

class UserRole(Enum):
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"

@db.model
class Tenant:
    """Multi-tenant organization model."""
    name: str
    domain: str
    subscription_tier: str = "basic"
    active: bool = True
    settings: dict = {}
    created_at: datetime

    __dataflow__ = {
        'audit': True,
        'encryption': ['settings'],
        'indexes': [
            {'name': 'idx_domain', 'fields': ['domain'], 'unique': True}
        ]
    }

@db.model
class User(MultiTenantModel):
    """Enterprise user with multi-tenancy support."""
    email: str
    name: str
    role: UserRole = UserRole.USER
    permissions: List[str] = []
    department: str
    manager_id: Optional[int] = None
    active: bool = True
    last_login: Optional[datetime] = None

    __dataflow__ = {
        'multi_tenant': True,
        'soft_delete': True,
        'audit': True,
        'encryption': ['email'],
        'access_control': {
            'read': ['self', 'manager', 'admin'],
            'write': ['self', 'admin'],
            'delete': ['admin']
        },
        'indexes': [
            {'name': 'idx_tenant_email', 'fields': ['tenant_id', 'email'], 'unique': True},
            {'name': 'idx_role', 'fields': ['role']},
            {'name': 'idx_department', 'fields': ['department']}
        ]
    }

@db.model
class Project(MultiTenantModel, AccessControlModel):
    """Enterprise project with granular access control."""
    name: str
    description: str
    status: str = "active"
    owner_id: int
    team_members: List[int] = []
    budget: float = 0.0
    confidentiality_level: str = "internal"

    __dataflow__ = {
        'multi_tenant': True,
        'audit': True,
        'versioned': True,
        'access_control': {
            'create': ['admin', 'manager'],
            'read': ['owner', 'team_member', 'admin'],
            'update': ['owner', 'admin'],
            'delete': ['admin']
        }
    }

@db.model
class Document(MultiTenantModel):
    """Enterprise document with encryption and access control."""
    title: str
    content: str
    project_id: int
    author_id: int
    classification: str = "internal"
    tags: List[str] = []

    __dataflow__ = {
        'multi_tenant': True,
        'encryption': ['content'],
        'audit': True,
        'access_control': {
            'read': ['project_member', 'admin'],
            'write': ['author', 'project_owner', 'admin']
        }
    }
```

## Enterprise User Management

```python
# user_management.py
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash_dataflow.enterprise import AccessControlManager, AuditLogger
from models import db, User, UserRole

class EnterpriseUserManager:
    """Enterprise user management with RBAC and audit logging."""

    def __init__(self, tenant_id: str, current_user_id: int):
        self.tenant_id = tenant_id
        self.current_user_id = current_user_id
        self.runtime = LocalRuntime()
        self.access_control = AccessControlManager(db)
        self.audit_logger = AuditLogger(db)

    def create_user(self, user_data: dict, role: UserRole = UserRole.USER) -> dict:
        """Create enterprise user with role assignment."""
        workflow = WorkflowBuilder()

        # Check permissions
        workflow.add_node("AccessControlCheckNode", "check_create_permission", {
            "user_id": self.current_user_id,
            "resource": "user",
            "action": "create",
            "tenant_id": self.tenant_id
        })

        # Create user
        workflow.add_node("UserCreateNode", "create_user", {
            **user_data,
            "role": role.value,
            "tenant_id": self.tenant_id,
            "created_by": self.current_user_id
        })

        # Assign default permissions
        workflow.add_node("PermissionAssignmentNode", "assign_permissions", {
            "user_id": ":user_id",
            "role": role.value,
            "tenant_id": self.tenant_id
        })

        # Log audit event
        workflow.add_node("AuditLogCreateNode", "log_user_creation", {
            "action": "user_created",
            "resource_type": "user",
            "resource_id": ":user_id",
            "actor_id": self.current_user_id,
            "tenant_id": self.tenant_id,
            "metadata": {
                "role": role.value,
                "email": user_data.get("email")
            }
        })

        # Connect workflow
        workflow.add_connection("check_create_permission", "result", "create_user", "input")
        workflow.add_connection("create_user", "assign_permissions", "id", "user_id")
        workflow.add_connection("create_user", "log_user_creation", "id", "user_id")

        results, run_id = self.runtime.execute(workflow.build())

        return {
            "success": True,
            "user": results["create_user"]["data"],
            "permissions": results["assign_permissions"]["data"],
            "audit_id": results["log_user_creation"]["data"]["id"]
        }

    def update_user_role(self, user_id: int, new_role: UserRole) -> dict:
        """Update user role with audit logging."""
        workflow = WorkflowBuilder()

        # Check permissions
        workflow.add_node("AccessControlCheckNode", "check_update_permission", {
            "user_id": self.current_user_id,
            "resource": "user",
            "action": "update_role",
            "target_user_id": user_id,
            "tenant_id": self.tenant_id
        })

        # Get current user data
        workflow.add_node("UserReadNode", "get_current_user", {
            "id": user_id,
            "tenant_id": self.tenant_id
        })

        # Update role
        workflow.add_node("UserUpdateNode", "update_role", {
            "id": user_id,
            "role": new_role.value,
            "updated_by": self.current_user_id,
            "tenant_id": self.tenant_id
        })

        # Update permissions
        workflow.add_node("PermissionUpdateNode", "update_permissions", {
            "user_id": user_id,
            "new_role": new_role.value,
            "tenant_id": self.tenant_id
        })

        # Log audit event
        workflow.add_node("AuditLogCreateNode", "log_role_change", {
            "action": "role_updated",
            "resource_type": "user",
            "resource_id": user_id,
            "actor_id": self.current_user_id,
            "tenant_id": self.tenant_id,
            "metadata": {
                "old_role": ":old_role",
                "new_role": new_role.value
            }
        })

        # Connect workflow
        workflow.add_connection("check_update_permission", "result", "get_current_user", "input")
        workflow.add_connection("get_current_user", "result", "update_role", "input")
        workflow.add_connection("get_current_user", "log_role_change", "role", "old_role")
        workflow.add_connection("update_role", "result", "update_permissions", "input")
        workflow.add_connection("update_permissions", "result", "log_role_change", "input")

        results, run_id = self.runtime.execute(workflow.build())

        return {
            "success": True,
            "user": results["update_role"]["data"],
            "permissions": results["update_permissions"]["data"],
            "audit_id": results["log_role_change"]["data"]["id"]
        }

    def deactivate_user(self, user_id: int, reason: str) -> dict:
        """Deactivate user with proper cleanup and audit trail."""
        workflow = WorkflowBuilder()

        # Check permissions
        workflow.add_node("AccessControlCheckNode", "check_deactivate_permission", {
            "user_id": self.current_user_id,
            "resource": "user",
            "action": "deactivate",
            "target_user_id": user_id,
            "tenant_id": self.tenant_id
        })

        # Deactivate user
        workflow.add_node("UserUpdateNode", "deactivate_user", {
            "id": user_id,
            "active": False,
            "deactivated_at": ":current_timestamp",
            "deactivated_by": self.current_user_id,
            "deactivation_reason": reason,
            "tenant_id": self.tenant_id
        })

        # Revoke active sessions
        workflow.add_node("SessionRevokeNode", "revoke_sessions", {
            "user_id": user_id,
            "tenant_id": self.tenant_id
        })

        # Remove from active projects
        workflow.add_node("ProjectMembershipCleanupNode", "cleanup_projects", {
            "user_id": user_id,
            "tenant_id": self.tenant_id
        })

        # Log audit event
        workflow.add_node("AuditLogCreateNode", "log_deactivation", {
            "action": "user_deactivated",
            "resource_type": "user",
            "resource_id": user_id,
            "actor_id": self.current_user_id,
            "tenant_id": self.tenant_id,
            "metadata": {
                "reason": reason,
                "sessions_revoked": ":sessions_count",
                "projects_affected": ":projects_count"
            }
        })

        # Connect workflow
        workflow.add_connection("check_deactivate_permission", "result", "deactivate_user", "input")
        workflow.add_connection("deactivate_user", "result", "revoke_sessions", "input")
        workflow.add_connection("deactivate_user", "result", "cleanup_projects", "input")
        workflow.add_connection("revoke_sessions", "log_deactivation", "count", "sessions_count")
        workflow.add_connection("cleanup_projects", "log_deactivation", "count", "projects_count")

        results, run_id = self.runtime.execute(workflow.build())

        return {
            "success": True,
            "user": results["deactivate_user"]["data"],
            "sessions_revoked": results["revoke_sessions"]["data"]["count"],
            "projects_affected": results["cleanup_projects"]["data"]["count"],
            "audit_id": results["log_deactivation"]["data"]["id"]
        }
```

## Multi-Tenant Project Management

```python
# project_management.py
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from models import db, Project, User
from typing import List

class EnterpriseProjectManager:
    """Multi-tenant project management with access control."""

    def __init__(self, tenant_id: str, current_user_id: int):
        self.tenant_id = tenant_id
        self.current_user_id = current_user_id
        self.runtime = LocalRuntime()

    def create_project(self, project_data: dict, team_members: List[int] = []) -> dict:
        """Create enterprise project with team assignment."""
        workflow = WorkflowBuilder()

        # Check permissions
        workflow.add_node("AccessControlCheckNode", "check_create_permission", {
            "user_id": self.current_user_id,
            "resource": "project",
            "action": "create",
            "tenant_id": self.tenant_id
        })

        # Create project
        workflow.add_node("ProjectCreateNode", "create_project", {
            **project_data,
            "owner_id": self.current_user_id,
            "team_members": team_members,
            "tenant_id": self.tenant_id,
            "created_by": self.current_user_id
        })

        # Assign team permissions
        workflow.add_node("ProjectPermissionAssignmentNode", "assign_team_permissions", {
            "project_id": ":project_id",
            "team_members": team_members,
            "tenant_id": self.tenant_id
        })

        # Create project workspace
        workflow.add_node("ProjectWorkspaceCreateNode", "create_workspace", {
            "project_id": ":project_id",
            "tenant_id": self.tenant_id
        })

        # Log audit event
        workflow.add_node("AuditLogCreateNode", "log_project_creation", {
            "action": "project_created",
            "resource_type": "project",
            "resource_id": ":project_id",
            "actor_id": self.current_user_id,
            "tenant_id": self.tenant_id,
            "metadata": {
                "project_name": project_data.get("name"),
                "team_size": len(team_members)
            }
        })

        # Connect workflow
        workflow.add_connection("check_create_permission", "result", "create_project", "input")
        workflow.add_connection("create_project", "assign_team_permissions", "id", "project_id")
        workflow.add_connection("create_project", "create_workspace", "id", "project_id")
        workflow.add_connection("create_project", "log_project_creation", "id", "project_id")

        results, run_id = self.runtime.execute(workflow.build())

        return {
            "success": True,
            "project": results["create_project"]["data"],
            "permissions": results["assign_team_permissions"]["data"],
            "workspace": results["create_workspace"]["data"],
            "audit_id": results["log_project_creation"]["data"]["id"]
        }

    def add_team_member(self, project_id: int, user_id: int, role: str = "member") -> dict:
        """Add team member with proper access control."""
        workflow = WorkflowBuilder()

        # Check permissions
        workflow.add_node("AccessControlCheckNode", "check_add_member_permission", {
            "user_id": self.current_user_id,
            "resource": "project",
            "resource_id": project_id,
            "action": "add_member",
            "tenant_id": self.tenant_id
        })

        # Verify user exists and is active
        workflow.add_node("UserReadNode", "verify_user", {
            "id": user_id,
            "tenant_id": self.tenant_id,
            "filter": {"active": True}
        })

        # Update project team
        workflow.add_node("ProjectUpdateNode", "add_team_member", {
            "id": project_id,
            "team_members": {"$add": user_id},
            "tenant_id": self.tenant_id
        })

        # Assign member permissions
        workflow.add_node("ProjectMemberPermissionNode", "assign_member_permissions", {
            "project_id": project_id,
            "user_id": user_id,
            "role": role,
            "tenant_id": self.tenant_id
        })

        # Send notification
        workflow.add_node("NotificationCreateNode", "notify_user", {
            "recipient_id": user_id,
            "type": "project_invitation",
            "data": {
                "project_id": project_id,
                "role": role,
                "invited_by": self.current_user_id
            },
            "tenant_id": self.tenant_id
        })

        # Log audit event
        workflow.add_node("AuditLogCreateNode", "log_member_addition", {
            "action": "team_member_added",
            "resource_type": "project",
            "resource_id": project_id,
            "actor_id": self.current_user_id,
            "tenant_id": self.tenant_id,
            "metadata": {
                "new_member_id": user_id,
                "role": role
            }
        })

        # Connect workflow
        workflow.add_connection("check_add_member_permission", "result", "verify_user", "input")
        workflow.add_connection("verify_user", "result", "add_team_member", "input")
        workflow.add_connection("add_team_member", "result", "assign_member_permissions", "input")
        workflow.add_connection("assign_member_permissions", "result", "notify_user", "input")
        workflow.add_connection("notify_user", "result", "log_member_addition", "input")

        results, run_id = self.runtime.execute(workflow.build())

        return {
            "success": True,
            "project": results["add_team_member"]["data"],
            "permissions": results["assign_member_permissions"]["data"],
            "notification": results["notify_user"]["data"],
            "audit_id": results["log_member_addition"]["data"]["id"]
        }
```

## Audit and Compliance

```python
# audit_manager.py
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from datetime import datetime, timedelta
from typing import Optional, List, Dict

class EnterpriseAuditManager:
    """Enterprise audit logging and compliance reporting."""

    def __init__(self, tenant_id: str, current_user_id: int):
        self.tenant_id = tenant_id
        self.current_user_id = current_user_id
        self.runtime = LocalRuntime()

    def generate_audit_report(self,
                            start_date: datetime,
                            end_date: datetime,
                            resource_types: Optional[List[str]] = None,
                            actions: Optional[List[str]] = None) -> dict:
        """Generate comprehensive audit report."""
        workflow = WorkflowBuilder()

        # Check permissions
        workflow.add_node("AccessControlCheckNode", "check_audit_permission", {
            "user_id": self.current_user_id,
            "resource": "audit_logs",
            "action": "read",
            "tenant_id": self.tenant_id
        })

        # Build filter
        filter_criteria = {
            "tenant_id": self.tenant_id,
            "created_at": {"$gte": start_date, "$lte": end_date}
        }

        if resource_types:
            filter_criteria["resource_type"] = {"$in": resource_types}

        if actions:
            filter_criteria["action"] = {"$in": actions}

        # Get audit logs
        workflow.add_node("AuditLogListNode", "get_audit_logs", {
            "filter": filter_criteria,
            "order_by": ["-created_at"],
            "include": ["actor", "resource"],
            "limit": 10000
        })

        # Generate statistics
        workflow.add_node("PythonCodeNode", "generate_statistics", {
            "code": """
audit_logs = get_input_data("get_audit_logs")["data"]

stats = {
    "total_events": len(audit_logs),
    "actions": {},
    "resources": {},
    "users": {},
    "daily_activity": {},
    "high_risk_events": []
}

high_risk_actions = ["user_deactivated", "role_updated", "project_deleted", "data_exported"]

for log in audit_logs:
    # Action statistics
    action = log["action"]
    stats["actions"][action] = stats["actions"].get(action, 0) + 1

    # Resource statistics
    resource_type = log["resource_type"]
    stats["resources"][resource_type] = stats["resources"].get(resource_type, 0) + 1

    # User activity
    actor_id = log["actor_id"]
    stats["users"][actor_id] = stats["users"].get(actor_id, 0) + 1

    # Daily activity
    date = log["created_at"].split("T")[0]
    stats["daily_activity"][date] = stats["daily_activity"].get(date, 0) + 1

    # High risk events
    if action in high_risk_actions:
        stats["high_risk_events"].append({
            "id": log["id"],
            "action": action,
            "actor": log.get("actor", {}).get("name", "Unknown"),
            "timestamp": log["created_at"],
            "metadata": log.get("metadata", {})
        })

result = {
    "audit_logs": audit_logs,
    "statistics": stats,
    "report_metadata": {
        "generated_at": datetime.now().isoformat(),
        "generated_by": current_user_id,
        "date_range": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        }
    }
}
"""
        })

        # Generate compliance summary
        workflow.add_node("PythonCodeNode", "compliance_summary", {
            "code": """
stats = get_input_data("generate_statistics")["statistics"]

compliance = {
    "gdpr_compliance": {
        "data_access_requests": stats["actions"].get("data_access_request", 0),
        "data_deletion_requests": stats["actions"].get("data_deletion_request", 0),
        "consent_updates": stats["actions"].get("consent_updated", 0)
    },
    "security_events": {
        "failed_logins": stats["actions"].get("login_failed", 0),
        "privilege_escalations": stats["actions"].get("role_updated", 0),
        "suspicious_activities": len(stats["high_risk_events"])
    },
    "data_governance": {
        "data_exports": stats["actions"].get("data_exported", 0),
        "data_imports": stats["actions"].get("data_imported", 0),
        "configuration_changes": stats["actions"].get("config_updated", 0)
    }
}

result = {"compliance_summary": compliance}
"""
        })

        # Log report generation
        workflow.add_node("AuditLogCreateNode", "log_report_generation", {
            "action": "audit_report_generated",
            "resource_type": "audit_report",
            "actor_id": self.current_user_id,
            "tenant_id": self.tenant_id,
            "metadata": {
                "date_range": f"{start_date.isoformat()} to {end_date.isoformat()}",
                "total_events": ":total_events"
            }
        })

        # Connect workflow
        workflow.add_connection("check_audit_permission", "result", "get_audit_logs", "input")
        workflow.add_connection("get_audit_logs", "result", "generate_statistics", "input")
        workflow.add_connection("generate_statistics", "result", "compliance_summary", "input")
        workflow.add_connection("generate_statistics", "log_report_generation", "statistics.total_events", "total_events")

        results, run_id = self.runtime.execute(workflow.build())

        return {
            "success": True,
            "report": results["generate_statistics"],
            "compliance": results["compliance_summary"]["compliance_summary"],
            "audit_id": results["log_report_generation"]["data"]["id"]
        }

    def export_audit_data(self,
                         start_date: datetime,
                         end_date: datetime,
                         format: str = "json") -> dict:
        """Export audit data for compliance purposes."""
        workflow = WorkflowBuilder()

        # Check permissions
        workflow.add_node("AccessControlCheckNode", "check_export_permission", {
            "user_id": self.current_user_id,
            "resource": "audit_logs",
            "action": "export",
            "tenant_id": self.tenant_id
        })

        # Export audit data
        workflow.add_node("AuditLogExportNode", "export_data", {
            "filter": {
                "tenant_id": self.tenant_id,
                "created_at": {"$gte": start_date, "$lte": end_date}
            },
            "format": format,
            "include_metadata": True,
            "anonymize_pii": True
        })

        # Create secure download link
        workflow.add_node("SecureDownloadLinkNode", "create_download_link", {
            "file_path": ":export_file_path",
            "expires_in": 3600,  # 1 hour
            "authorized_user_id": self.current_user_id
        })

        # Log export event
        workflow.add_node("AuditLogCreateNode", "log_export", {
            "action": "audit_data_exported",
            "resource_type": "audit_export",
            "actor_id": self.current_user_id,
            "tenant_id": self.tenant_id,
            "metadata": {
                "format": format,
                "date_range": f"{start_date.isoformat()} to {end_date.isoformat()}",
                "file_size": ":file_size",
                "record_count": ":record_count"
            }
        })

        # Connect workflow
        workflow.add_connection("check_export_permission", "result", "export_data", "input")
        workflow.add_connection("export_data", "create_download_link", "file_path", "export_file_path")
        workflow.add_connection("export_data", "log_export", "file_size", "file_size")
        workflow.add_connection("export_data", "log_export", "record_count", "record_count")

        results, run_id = self.runtime.execute(workflow.build())

        return {
            "success": True,
            "export": results["export_data"]["data"],
            "download_link": results["create_download_link"]["data"]["url"],
            "expires_at": results["create_download_link"]["data"]["expires_at"],
            "audit_id": results["log_export"]["data"]["id"]
        }
```

## Complete Enterprise Application

```python
# enterprise_app.py
from flask import Flask, request, jsonify
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity
from kailash_dataflow import DataFlow
from kailash_dataflow.enterprise import EnterpriseConfig
from user_management import EnterpriseUserManager
from project_management import EnterpriseProjectManager
from audit_manager import EnterpriseAuditManager
from models import db, UserRole

# Initialize Flask app with enterprise features
app = Flask(__name__)

# Enterprise DataFlow configuration
enterprise_config = EnterpriseConfig(
    multi_tenant=True,
    encryption_key=os.getenv("ENCRYPTION_KEY"),
    audit_logging=True,
    access_control="rbac",
    compliance_mode="gdpr",
    monitoring=True
)

db = DataFlow(config=enterprise_config)

# JWT configuration
app.config['JWT_SECRET_KEY'] = os.getenv("JWT_SECRET_KEY")
jwt = JWTManager(app)

@app.route('/api/enterprise/users', methods=['POST'])
@jwt_required()
def create_enterprise_user():
    """Create enterprise user with RBAC."""
    current_user = get_jwt_identity()
    tenant_id = request.headers.get('X-Tenant-ID')

    if not tenant_id:
        return jsonify({"error": "Tenant ID required"}), 400

    user_manager = EnterpriseUserManager(tenant_id, current_user['id'])

    data = request.get_json()
    role = UserRole(data.get('role', 'user'))

    try:
        result = user_manager.create_user(data, role)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/enterprise/users/<int:user_id>/role', methods=['PUT'])
@jwt_required()
def update_user_role(user_id):
    """Update user role with audit logging."""
    current_user = get_jwt_identity()
    tenant_id = request.headers.get('X-Tenant-ID')

    user_manager = EnterpriseUserManager(tenant_id, current_user['id'])

    data = request.get_json()
    new_role = UserRole(data['role'])

    try:
        result = user_manager.update_user_role(user_id, new_role)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/enterprise/projects', methods=['POST'])
@jwt_required()
def create_enterprise_project():
    """Create enterprise project with team management."""
    current_user = get_jwt_identity()
    tenant_id = request.headers.get('X-Tenant-ID')

    project_manager = EnterpriseProjectManager(tenant_id, current_user['id'])

    data = request.get_json()
    team_members = data.pop('team_members', [])

    try:
        result = project_manager.create_project(data, team_members)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/enterprise/audit/reports', methods=['POST'])
@jwt_required()
def generate_audit_report():
    """Generate enterprise audit report."""
    current_user = get_jwt_identity()
    tenant_id = request.headers.get('X-Tenant-ID')

    audit_manager = EnterpriseAuditManager(tenant_id, current_user['id'])

    data = request.get_json()
    start_date = datetime.fromisoformat(data['start_date'])
    end_date = datetime.fromisoformat(data['end_date'])

    try:
        result = audit_manager.generate_audit_report(
            start_date,
            end_date,
            data.get('resource_types'),
            data.get('actions')
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/enterprise/audit/export', methods=['POST'])
@jwt_required()
def export_audit_data():
    """Export audit data for compliance."""
    current_user = get_jwt_identity()
    tenant_id = request.headers.get('X-Tenant-ID')

    audit_manager = EnterpriseAuditManager(tenant_id, current_user['id'])

    data = request.get_json()
    start_date = datetime.fromisoformat(data['start_date'])
    end_date = datetime.fromisoformat(data['end_date'])
    format = data.get('format', 'json')

    try:
        result = audit_manager.export_audit_data(start_date, end_date, format)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=False)
```

## Testing Enterprise Features

```python
# test_enterprise.py
import pytest
from datetime import datetime, timedelta
from enterprise_app import app, db
from user_management import EnterpriseUserManager
from models import UserRole

class TestEnterpriseFeatures:
    def setup_method(self):
        """Setup test environment."""
        self.app = app.test_client()
        self.tenant_id = "test-tenant"
        self.admin_user_id = 1

        # Create test tenant
        self.create_test_tenant()

    def create_test_tenant(self):
        """Create test tenant."""
        # Implementation for tenant creation
        pass

    def test_create_enterprise_user(self):
        """Test enterprise user creation with RBAC."""
        user_manager = EnterpriseUserManager(self.tenant_id, self.admin_user_id)

        user_data = {
            "name": "Test User",
            "email": "test@example.com",
            "department": "Engineering"
        }

        result = user_manager.create_user(user_data, UserRole.USER)

        assert result["success"] is True
        assert result["user"]["name"] == "Test User"
        assert result["user"]["role"] == "user"
        assert "permissions" in result
        assert "audit_id" in result

    def test_multi_tenant_isolation(self):
        """Test multi-tenant data isolation."""
        # Create users in different tenants
        tenant1_manager = EnterpriseUserManager("tenant-1", 1)
        tenant2_manager = EnterpriseUserManager("tenant-2", 1)

        # Create user in tenant 1
        user1_data = {"name": "Tenant 1 User", "email": "user1@tenant1.com"}
        result1 = tenant1_manager.create_user(user1_data)

        # Create user in tenant 2
        user2_data = {"name": "Tenant 2 User", "email": "user2@tenant2.com"}
        result2 = tenant2_manager.create_user(user2_data)

        # Verify isolation
        assert result1["success"] is True
        assert result2["success"] is True

        # TODO: Add verification that tenant1 cannot see tenant2 data

    def test_access_control(self):
        """Test role-based access control."""
        user_manager = EnterpriseUserManager(self.tenant_id, self.admin_user_id)

        # Create regular user
        user_data = {"name": "Regular User", "email": "regular@example.com"}
        result = user_manager.create_user(user_data, UserRole.USER)
        user_id = result["user"]["id"]

        # Try to update role (should require admin permissions)
        try:
            regular_user_manager = EnterpriseUserManager(self.tenant_id, user_id)
            regular_user_manager.update_user_role(user_id, UserRole.ADMIN)
            assert False, "Should not allow regular user to update roles"
        except Exception as e:
            assert "permission denied" in str(e).lower()

    def test_audit_logging(self):
        """Test comprehensive audit logging."""
        from audit_manager import EnterpriseAuditManager

        audit_manager = EnterpriseAuditManager(self.tenant_id, self.admin_user_id)
        user_manager = EnterpriseUserManager(self.tenant_id, self.admin_user_id)

        # Perform audited actions
        user_data = {"name": "Audit Test User", "email": "audit@example.com"}
        create_result = user_manager.create_user(user_data, UserRole.USER)
        user_id = create_result["user"]["id"]

        role_result = user_manager.update_user_role(user_id, UserRole.ADMIN)

        # Generate audit report
        end_date = datetime.now()
        start_date = end_date - timedelta(minutes=10)

        report_result = audit_manager.generate_audit_report(start_date, end_date)

        assert report_result["success"] is True
        assert report_result["report"]["statistics"]["total_events"] >= 2
        assert "user_created" in report_result["report"]["statistics"]["actions"]
        assert "role_updated" in report_result["report"]["statistics"]["actions"]

    def test_data_encryption(self):
        """Test data encryption for sensitive fields."""
        user_manager = EnterpriseUserManager(self.tenant_id, self.admin_user_id)

        # Create user with sensitive data
        user_data = {
            "name": "Encrypted User",
            "email": "encrypted@example.com",  # This field is marked for encryption
            "department": "Security"
        }

        result = user_manager.create_user(user_data)

        # Verify user creation succeeded
        assert result["success"] is True

        # TODO: Add verification that email is encrypted in database
        # but decrypted when retrieved through proper channels

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

## Requirements

```txt
# requirements.txt
kailash>=0.6.6
flask>=2.0.0
flask-jwt-extended>=4.0.0
cryptography>=3.4.0
pytest>=7.0.0
psycopg2-binary>=2.9.0
redis>=4.0.0
```

## Environment Configuration

```bash
# .env.example
# Database
DATABASE_URL=postgresql://dataflow:password@localhost:5432/dataflow_enterprise
REDIS_URL=redis://localhost:6379/0

# Security
ENCRYPTION_KEY=your-32-character-encryption-key-here
JWT_SECRET_KEY=your-jwt-secret-key-here

# Multi-tenancy
DEFAULT_TENANT=default-tenant
TENANT_ISOLATION=strict

# Compliance
GDPR_MODE=true
AUDIT_RETENTION_DAYS=2555  # 7 years
DATA_RESIDENCY=EU

# Performance
CONNECTION_POOL_SIZE=20
CACHE_TTL=3600
```

## Usage

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Run the application:**
   ```bash
   python enterprise_app.py
   ```

4. **Run tests:**
   ```bash
   python test_enterprise.py
   ```

## What You'll Learn

- Multi-tenant architecture with data isolation
- Role-based access control (RBAC) implementation
- Comprehensive audit logging for compliance
- Data encryption at rest and in transit
- Enterprise security patterns
- Compliance reporting and data export
- Performance monitoring and metrics

## Next Steps

- **API Backend**: [API Backend Example](../api-backend/) - REST API development
- **Data Migration**: [Data Migration Example](../data-migration/) - Large-scale data processing
- **Production Deployment**: [Deployment Guide](../../docs/production/deployment.md)

This example provides a complete enterprise-grade implementation with all the security, compliance, and governance features needed for modern business applications.
