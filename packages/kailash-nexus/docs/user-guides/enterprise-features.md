# Enterprise Features Guide

Master Nexus's production-grade enterprise capabilities that are enabled by default, not as add-ons.

## Overview

Unlike traditional platforms where enterprise features are expensive add-ons, Nexus includes production-grade capabilities by default. This guide covers authentication, monitoring, security, compliance, and scalability features that make Nexus enterprise-ready out of the box.

## Enterprise-Default Philosophy

### Built-In Production Features

```python
from nexus import Nexus

# Enterprise features enabled by default
app = Nexus()

# Check enterprise capabilities
health = app.health_check()
enterprise_features = health.get('revolutionary_capabilities', {})

print("🏢 Enterprise capabilities enabled by default:")
print(f"   • Durable-First Design: {enterprise_features.get('durable_first_design', False)}")
print(f"   • Multi-Channel Native: {enterprise_features.get('multi_channel_native', False)}")
print(f"   • Enterprise Default: {enterprise_features.get('enterprise_default', False)}")
print(f"   • Cross-Channel Sync: {enterprise_features.get('cross_channel_sync', False)}")
```

### Progressive Enhancement Architecture

```python
from nexus import Nexus

# Start with zero configuration
app = Nexus()

# Add enterprise features as needed
app.enable_auth()           # Add authentication
app.enable_monitoring()     # Add monitoring
app.use_plugin("audit")     # Add audit logging
app.use_plugin("compliance") # Add compliance features

# Enterprise features stack on top of solid foundation
print("✅ Enterprise features progressively enhanced")
```

## Authentication and Authorization

### Multi-Provider Authentication

```python
from nexus import Nexus

app = Nexus(enable_auth=True)

class EnterpriseAuthManager:
    """Enterprise-grade authentication management"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.auth_providers = {}
        self.user_sessions = {}
        self.permissions = {}

    def configure_oauth2(self, provider_name, config):
        """Configure OAuth2 provider"""

        self.auth_providers[provider_name] = {
            "type": "oauth2",
            "client_id": config.get("client_id"),
            "client_secret": config.get("client_secret"),
            "authorization_url": config.get("auth_url"),
            "token_url": config.get("token_url"),
            "user_info_url": config.get("user_info_url"),
            "scopes": config.get("scopes", ["openid", "profile", "email"])
        }

        print(f"✅ OAuth2 provider configured: {provider_name}")

    def configure_ldap(self, config):
        """Configure LDAP authentication"""

        self.auth_providers["ldap"] = {
            "type": "ldap",
            "server": config.get("server"),
            "port": config.get("port", 389),
            "base_dn": config.get("base_dn"),
            "user_filter": config.get("user_filter", "(uid={username})"),
            "group_filter": config.get("group_filter", "(member={user_dn})"),
            "use_ssl": config.get("use_ssl", False)
        }

        print("✅ LDAP authentication configured")

    def configure_saml(self, config):
        """Configure SAML authentication"""

        self.auth_providers["saml"] = {
            "type": "saml",
            "entity_id": config.get("entity_id"),
            "sso_url": config.get("sso_url"),
            "x509_cert": config.get("x509_cert"),
            "private_key": config.get("private_key"),
            "name_id_format": config.get("name_id_format", "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress")
        }

        print("✅ SAML authentication configured")

    def authenticate_user(self, username, credentials, provider="local"):
        """Authenticate user with specified provider"""

        if provider not in self.auth_providers and provider != "local":
            return {"success": False, "error": "Unknown authentication provider"}

        # Simulate authentication
        if provider == "local":
            # Local authentication
            user_info = self._authenticate_local(username, credentials)
        elif self.auth_providers[provider]["type"] == "oauth2":
            user_info = self._authenticate_oauth2(username, credentials, provider)
        elif self.auth_providers[provider]["type"] == "ldap":
            user_info = self._authenticate_ldap(username, credentials)
        elif self.auth_providers[provider]["type"] == "saml":
            user_info = self._authenticate_saml(credentials)
        else:
            return {"success": False, "error": "Unsupported provider type"}

        if user_info:
            # Create session
            session_id = self.app.create_session(channel="api")
            self.user_sessions[session_id] = {
                "user": user_info,
                "provider": provider,
                "authenticated_at": __import__('time').time(),
                "permissions": self._get_user_permissions(user_info)
            }

            return {"success": True, "session_id": session_id, "user": user_info}

        return {"success": False, "error": "Authentication failed"}

    def _authenticate_local(self, username, credentials):
        """Local authentication simulation"""
        if username == "admin" and credentials.get("password") == "admin123":
            return {
                "username": username,
                "email": f"{username}@company.com",
                "roles": ["admin"],
                "groups": ["administrators"]
            }
        return None

    def _authenticate_oauth2(self, username, credentials, provider):
        """OAuth2 authentication simulation"""
        # In real implementation, this would handle OAuth2 flow
        return {
            "username": username,
            "email": f"{username}@oauth-provider.com",
            "roles": ["user"],
            "groups": ["oauth-users"],
            "provider": provider
        }

    def _authenticate_ldap(self, username, credentials):
        """LDAP authentication simulation"""
        return {
            "username": username,
            "email": f"{username}@company.com",
            "roles": ["employee"],
            "groups": ["staff", "ldap-users"],
            "dn": f"uid={username},ou=people,dc=company,dc=com"
        }

    def _authenticate_saml(self, saml_response):
        """SAML authentication simulation"""
        # Parse SAML response
        return {
            "username": "saml_user",
            "email": "saml_user@company.com",
            "roles": ["employee"],
            "groups": ["saml-users"],
            "attributes": {"department": "IT", "title": "Developer"}
        }

    def _get_user_permissions(self, user_info):
        """Get user permissions based on roles and groups"""
        permissions = set()

        for role in user_info.get("roles", []):
            if role == "admin":
                permissions.update(["read", "write", "delete", "admin"])
            elif role == "employee":
                permissions.update(["read", "write"])
            elif role == "user":
                permissions.update(["read"])

        return list(permissions)

    def authorize_action(self, session_id, action, resource=None):
        """Authorize user action"""

        if session_id not in self.user_sessions:
            return {"authorized": False, "reason": "Invalid session"}

        session = self.user_sessions[session_id]
        user_permissions = session["permissions"]

        # Simple permission check
        if action in user_permissions:
            return {"authorized": True, "user": session["user"]["username"]}

        return {"authorized": False, "reason": "Insufficient permissions"}

# Usage example
auth_manager = EnterpriseAuthManager(app)

# Configure multiple authentication providers
auth_manager.configure_oauth2("google", {
    "client_id": "google_client_id",
    "client_secret": "google_client_secret",
    "auth_url": "https://accounts.google.com/o/oauth2/auth",
    "token_url": "https://oauth2.googleapis.com/token",
    "user_info_url": "https://www.googleapis.com/oauth2/v2/userinfo"
})

auth_manager.configure_ldap({
    "server": "ldap.company.com",
    "base_dn": "dc=company,dc=com",
    "user_filter": "(uid={username})"
})

auth_manager.configure_saml({
    "entity_id": "https://company.com/saml",
    "sso_url": "https://idp.company.com/sso",
    "x509_cert": "certificate_content"
})

# Test authentication
local_auth = auth_manager.authenticate_user("admin", {"password": "admin123"}, "local")
print(f"Local authentication: {local_auth['success']}")

oauth_auth = auth_manager.authenticate_user("john.doe", {"token": "oauth_token"}, "google")
print(f"OAuth authentication: {oauth_auth['success']}")
```

### Role-Based Access Control (RBAC)

```python
from nexus import Nexus

app = Nexus()

class RBACManager:
    """Role-Based Access Control for enterprise workflows"""

    def __init__(self):
        self.roles = {}
        self.permissions = {}
        self.user_roles = {}
        self.role_hierarchy = {}

    def define_role(self, role_name, permissions, description=""):
        """Define a role with specific permissions"""

        self.roles[role_name] = {
            "permissions": set(permissions),
            "description": description,
            "created_at": __import__('time').time()
        }

        print(f"✅ Role defined: {role_name}")

    def create_role_hierarchy(self, parent_role, child_roles):
        """Create role hierarchy (inheritance)"""

        self.role_hierarchy[parent_role] = child_roles

        # Child roles inherit parent permissions
        if parent_role in self.roles:
            parent_permissions = self.roles[parent_role]["permissions"]

            for child_role in child_roles:
                if child_role in self.roles:
                    self.roles[child_role]["permissions"].update(parent_permissions)

    def assign_user_role(self, user_id, roles):
        """Assign roles to user"""

        if not isinstance(roles, list):
            roles = [roles]

        self.user_roles[user_id] = roles
        print(f"✅ Roles assigned to {user_id}: {roles}")

    def check_permission(self, user_id, required_permission, resource=None):
        """Check if user has required permission"""

        if user_id not in self.user_roles:
            return {"authorized": False, "reason": "No roles assigned"}

        user_permissions = set()

        # Collect all permissions from user's roles
        for role_name in self.user_roles[user_id]:
            if role_name in self.roles:
                user_permissions.update(self.roles[role_name]["permissions"])

        # Check permission
        if required_permission in user_permissions:
            return {
                "authorized": True,
                "user_id": user_id,
                "permission": required_permission,
                "resource": resource
            }

        return {
            "authorized": False,
            "reason": f"Missing permission: {required_permission}",
            "user_permissions": list(user_permissions)
        }

    def get_user_permissions(self, user_id):
        """Get all permissions for a user"""

        if user_id not in self.user_roles:
            return []

        all_permissions = set()

        for role_name in self.user_roles[user_id]:
            if role_name in self.roles:
                all_permissions.update(self.roles[role_name]["permissions"])

        return list(all_permissions)

# Define enterprise RBAC structure
rbac = RBACManager()

# Define roles
rbac.define_role("super_admin", [
    "read", "write", "delete", "admin", "user_management",
    "system_config", "workflow_admin"
], "Super administrator with all permissions")

rbac.define_role("workflow_admin", [
    "read", "write", "workflow_create", "workflow_delete",
    "workflow_execute", "workflow_monitor"
], "Workflow administrator")

rbac.define_role("data_analyst", [
    "read", "workflow_execute", "data_export", "report_generate"
], "Data analyst with execution rights")

rbac.define_role("viewer", [
    "read", "workflow_view"
], "Read-only access")

# Create role hierarchy
rbac.create_role_hierarchy("super_admin", ["workflow_admin"])
rbac.create_role_hierarchy("workflow_admin", ["data_analyst"])
rbac.create_role_hierarchy("data_analyst", ["viewer"])

# Assign roles to users
rbac.assign_user_role("admin_user", ["super_admin"])
rbac.assign_user_role("john_doe", ["workflow_admin"])
rbac.assign_user_role("jane_smith", ["data_analyst"])
rbac.assign_user_role("guest_user", ["viewer"])

# Test permissions
test_cases = [
    ("admin_user", "system_config"),
    ("john_doe", "workflow_create"),
    ("jane_smith", "data_export"),
    ("guest_user", "workflow_delete")
]

for user_id, permission in test_cases:
    result = rbac.check_permission(user_id, permission)
    status = "✅" if result["authorized"] else "❌"
    print(f"{status} {user_id} -> {permission}: {result['authorized']}")
```

## Monitoring and Observability

### Comprehensive Monitoring Stack

```python
from nexus import Nexus
import time
from collections import defaultdict

app = Nexus(enable_monitoring=True)

class EnterpriseMonitoring:
    """Enterprise monitoring and observability"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.metrics = defaultdict(list)
        self.alerts = []
        self.dashboards = {}
        self.health_checks = {}

    def track_metric(self, metric_name, value, labels=None):
        """Track custom metrics"""

        metric_entry = {
            "timestamp": time.time(),
            "value": value,
            "labels": labels or {},
            "source": "nexus"
        }

        self.metrics[metric_name].append(metric_entry)

        # Check for alerts
        self._check_metric_alerts(metric_name, value, labels)

    def _check_metric_alerts(self, metric_name, value, labels):
        """Check if metric value triggers alerts"""

        # Define alert thresholds
        alert_rules = {
            "workflow_execution_time": {"threshold": 30, "operator": ">"},
            "error_rate": {"threshold": 0.05, "operator": ">"},
            "memory_usage": {"threshold": 0.8, "operator": ">"},
            "cpu_usage": {"threshold": 0.9, "operator": ">"}
        }

        if metric_name in alert_rules:
            rule = alert_rules[metric_name]
            threshold = rule["threshold"]
            operator = rule["operator"]

            triggered = False
            if operator == ">" and value > threshold:
                triggered = True
            elif operator == "<" and value < threshold:
                triggered = True
            elif operator == "==" and value == threshold:
                triggered = True

            if triggered:
                self._create_alert(metric_name, value, threshold, labels)

    def _create_alert(self, metric_name, value, threshold, labels):
        """Create alert for metric threshold breach"""

        alert = {
            "id": f"alert_{int(time.time())}",
            "metric": metric_name,
            "value": value,
            "threshold": threshold,
            "labels": labels,
            "severity": self._get_alert_severity(metric_name, value, threshold),
            "created_at": time.time(),
            "status": "firing"
        }

        self.alerts.append(alert)
        print(f"🚨 Alert: {metric_name} = {value} (threshold: {threshold})")

    def _get_alert_severity(self, metric_name, value, threshold):
        """Determine alert severity"""

        critical_metrics = ["error_rate", "cpu_usage", "memory_usage"]

        if metric_name in critical_metrics:
            if isinstance(value, (int, float)) and isinstance(threshold, (int, float)):
                if value > threshold * 1.5:
                    return "critical"
                elif value > threshold * 1.2:
                    return "warning"
            return "info"

        return "info"

    def create_dashboard(self, dashboard_name, widgets):
        """Create monitoring dashboard"""

        self.dashboards[dashboard_name] = {
            "widgets": widgets,
            "created_at": time.time(),
            "last_updated": time.time()
        }

        print(f"📊 Dashboard created: {dashboard_name}")

    def get_metrics_summary(self, time_range_minutes=60):
        """Get metrics summary for time range"""

        cutoff_time = time.time() - (time_range_minutes * 60)
        summary = {}

        for metric_name, entries in self.metrics.items():
            recent_entries = [e for e in entries if e["timestamp"] > cutoff_time]

            if recent_entries:
                values = [e["value"] for e in recent_entries]
                summary[metric_name] = {
                    "count": len(values),
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "latest": values[-1]
                }

        return summary

    def setup_health_checks(self):
        """Setup comprehensive health checks"""

        self.health_checks = {
            "database_connection": self._check_database,
            "external_apis": self._check_external_apis,
            "memory_usage": self._check_memory,
            "disk_space": self._check_disk_space,
            "workflow_performance": self._check_workflow_performance
        }

        print("✅ Health checks configured")

    def _check_database(self):
        """Check database connectivity"""
        # Simulate database check
        return {"status": "healthy", "response_time_ms": 15}

    def _check_external_apis(self):
        """Check external API connectivity"""
        return {"status": "healthy", "apis_checked": 3, "avg_response_time": 120}

    def _check_memory(self):
        """Check memory usage"""
        # Simulate memory check
        import psutil
        try:
            memory = psutil.virtual_memory()
            return {
                "status": "healthy" if memory.percent < 80 else "warning",
                "usage_percent": memory.percent,
                "available_gb": memory.available / (1024**3)
            }
        except:
            return {"status": "unknown", "usage_percent": 50}

    def _check_disk_space(self):
        """Check disk space"""
        return {"status": "healthy", "usage_percent": 45, "available_gb": 100}

    def _check_workflow_performance(self):
        """Check workflow performance metrics"""
        summary = self.get_metrics_summary(30)  # Last 30 minutes

        workflow_metrics = {k: v for k, v in summary.items() if "workflow" in k}

        if workflow_metrics:
            avg_times = [v["avg"] for v in workflow_metrics.values()]
            overall_avg = sum(avg_times) / len(avg_times)

            return {
                "status": "healthy" if overall_avg < 10 else "warning",
                "avg_execution_time": overall_avg,
                "workflows_monitored": len(workflow_metrics)
            }

        return {"status": "unknown", "workflows_monitored": 0}

    def run_health_check(self):
        """Run all health checks"""

        results = {}
        overall_status = "healthy"

        for check_name, check_function in self.health_checks.items():
            try:
                result = check_function()
                results[check_name] = result

                if result["status"] == "warning":
                    overall_status = "warning"
                elif result["status"] == "critical":
                    overall_status = "critical"

            except Exception as e:
                results[check_name] = {"status": "error", "error": str(e)}
                overall_status = "warning"

        return {
            "overall_status": overall_status,
            "timestamp": time.time(),
            "checks": results
        }

# Setup enterprise monitoring
monitoring = EnterpriseMonitoring(app)
monitoring.setup_health_checks()

# Create dashboards
monitoring.create_dashboard("System Overview", [
    {"type": "metric", "metric": "cpu_usage", "chart": "line"},
    {"type": "metric", "metric": "memory_usage", "chart": "gauge"},
    {"type": "metric", "metric": "workflow_execution_time", "chart": "histogram"},
    {"type": "alerts", "severity": ["critical", "warning"]}
])

monitoring.create_dashboard("Workflow Performance", [
    {"type": "metric", "metric": "workflow_execution_time", "chart": "line"},
    {"type": "metric", "metric": "workflow_success_rate", "chart": "gauge"},
    {"type": "metric", "metric": "workflow_throughput", "chart": "bar"}
])

# Simulate metrics collection
monitoring.track_metric("workflow_execution_time", 25.5, {"workflow": "data-processor"})
monitoring.track_metric("cpu_usage", 0.65, {"instance": "nexus-1"})
monitoring.track_metric("memory_usage", 0.75, {"instance": "nexus-1"})
monitoring.track_metric("error_rate", 0.02, {"service": "nexus"})

# Run health check
health_status = monitoring.run_health_check()
print(f"🩺 Health Status: {health_status['overall_status']}")

# Get metrics summary
metrics_summary = monitoring.get_metrics_summary(60)
print(f"📊 Metrics Summary: {len(metrics_summary)} metrics tracked")
```

## Security and Compliance

### Enterprise Security Framework

```python
from nexus import Nexus
import hashlib
import hmac
import secrets

app = Nexus()

class EnterpriseSecurity:
    """Enterprise security and compliance framework"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.encryption_keys = {}
        self.audit_log = []
        self.security_policies = {}
        self.compliance_rules = {}

    def configure_encryption(self, key_name, key_type="AES-256"):
        """Configure encryption keys"""

        # Generate secure encryption key
        if key_type == "AES-256":
            key = secrets.token_bytes(32)  # 256 bits
        elif key_type == "AES-128":
            key = secrets.token_bytes(16)  # 128 bits
        else:
            raise ValueError(f"Unsupported key type: {key_type}")

        self.encryption_keys[key_name] = {
            "key": key,
            "type": key_type,
            "created_at": __import__('time').time(),
            "rotation_due": __import__('time').time() + (90 * 24 * 3600)  # 90 days
        }

        print(f"🔐 Encryption key configured: {key_name} ({key_type})")

    def encrypt_data(self, data, key_name):
        """Encrypt sensitive data"""

        if key_name not in self.encryption_keys:
            raise ValueError(f"Encryption key not found: {key_name}")

        # Simplified encryption simulation
        import base64

        data_str = str(data)
        encoded = base64.b64encode(data_str.encode()).decode()

        encrypted_data = {
            "encrypted": encoded,
            "key_name": key_name,
            "algorithm": self.encryption_keys[key_name]["type"],
            "encrypted_at": __import__('time').time()
        }

        # Log encryption event
        self.log_security_event("data_encrypted", {
            "key_name": key_name,
            "data_size": len(data_str)
        })

        return encrypted_data

    def decrypt_data(self, encrypted_data):
        """Decrypt sensitive data"""

        key_name = encrypted_data["key_name"]

        if key_name not in self.encryption_keys:
            raise ValueError(f"Decryption key not found: {key_name}")

        # Simplified decryption simulation
        import base64

        decoded = base64.b64decode(encrypted_data["encrypted"].encode()).decode()

        # Log decryption event
        self.log_security_event("data_decrypted", {
            "key_name": key_name
        })

        return decoded

    def log_security_event(self, event_type, details):
        """Log security events for audit trail"""

        event = {
            "timestamp": __import__('time').time(),
            "event_type": event_type,
            "details": details,
            "session_id": getattr(self, '_current_session', None),
            "user_id": getattr(self, '_current_user', None),
            "ip_address": getattr(self, '_current_ip', None)
        }

        self.audit_log.append(event)

    def configure_security_policy(self, policy_name, rules):
        """Configure security policies"""

        self.security_policies[policy_name] = {
            "rules": rules,
            "created_at": __import__('time').time(),
            "active": True
        }

        print(f"🛡️  Security policy configured: {policy_name}")

    def check_security_policy(self, policy_name, context):
        """Check if context meets security policy"""

        if policy_name not in self.security_policies:
            return {"compliant": False, "reason": "Policy not found"}

        policy = self.security_policies[policy_name]

        if not policy["active"]:
            return {"compliant": True, "reason": "Policy disabled"}

        violations = []

        for rule in policy["rules"]:
            if not self._evaluate_security_rule(rule, context):
                violations.append(rule["name"])

        if violations:
            self.log_security_event("policy_violation", {
                "policy": policy_name,
                "violations": violations
            })

            return {
                "compliant": False,
                "violations": violations,
                "policy": policy_name
            }

        return {"compliant": True, "policy": policy_name}

    def _evaluate_security_rule(self, rule, context):
        """Evaluate individual security rule"""

        rule_type = rule["type"]

        if rule_type == "password_strength":
            password = context.get("password", "")
            return len(password) >= rule["min_length"] and any(c.isdigit() for c in password)

        elif rule_type == "session_timeout":
            session_age = context.get("session_age", 0)
            return session_age < rule["max_age_minutes"] * 60

        elif rule_type == "ip_whitelist":
            ip_address = context.get("ip_address", "")
            return ip_address in rule["allowed_ips"]

        elif rule_type == "data_classification":
            data_level = context.get("data_classification", "public")
            return data_level in rule["allowed_levels"]

        return True

    def configure_compliance_rules(self, standard, rules):
        """Configure compliance rules (GDPR, SOX, HIPAA, etc.)"""

        self.compliance_rules[standard] = {
            "rules": rules,
            "configured_at": __import__('time').time(),
            "last_audit": None
        }

        print(f"📋 Compliance rules configured: {standard}")

    def run_compliance_audit(self, standard):
        """Run compliance audit for specific standard"""

        if standard not in self.compliance_rules:
            return {"error": f"Compliance standard not configured: {standard}"}

        compliance_config = self.compliance_rules[standard]
        audit_results = []

        for rule in compliance_config["rules"]:
            result = self._audit_compliance_rule(rule)
            audit_results.append(result)

        # Update last audit time
        compliance_config["last_audit"] = __import__('time').time()

        # Calculate compliance score
        passed_rules = len([r for r in audit_results if r["compliant"]])
        total_rules = len(audit_results)
        compliance_score = (passed_rules / total_rules) * 100 if total_rules > 0 else 0

        audit_summary = {
            "standard": standard,
            "compliance_score": compliance_score,
            "total_rules": total_rules,
            "passed_rules": passed_rules,
            "failed_rules": total_rules - passed_rules,
            "audit_timestamp": __import__('time').time(),
            "results": audit_results
        }

        # Log compliance audit
        self.log_security_event("compliance_audit", {
            "standard": standard,
            "score": compliance_score
        })

        return audit_summary

    def _audit_compliance_rule(self, rule):
        """Audit individual compliance rule"""

        rule_id = rule["id"]
        rule_description = rule["description"]

        # Simulate compliance checks
        if rule_id == "gdpr_data_retention":
            compliant = len(self.audit_log) < 10000  # Example check
        elif rule_id == "sox_audit_trail":
            compliant = len(self.audit_log) > 0
        elif rule_id == "hipaa_encryption":
            compliant = len(self.encryption_keys) > 0
        else:
            compliant = True  # Default to compliant for unknown rules

        return {
            "rule_id": rule_id,
            "description": rule_description,
            "compliant": compliant,
            "checked_at": __import__('time').time()
        }

    def get_security_dashboard(self):
        """Get security dashboard data"""

        recent_events = [e for e in self.audit_log if e["timestamp"] > __import__('time').time() - 3600]

        dashboard = {
            "encryption_keys": len(self.encryption_keys),
            "security_policies": len(self.security_policies),
            "compliance_standards": len(self.compliance_rules),
            "recent_events": len(recent_events),
            "key_rotation_due": len([k for k in self.encryption_keys.values()
                                   if k["rotation_due"] < __import__('time').time()]),
            "policy_violations": len([e for e in recent_events
                                    if e["event_type"] == "policy_violation"])
        }

        return dashboard

# Configure enterprise security
security = EnterpriseSecurity(app)

# Setup encryption
security.configure_encryption("user_data", "AES-256")
security.configure_encryption("session_data", "AES-128")

# Configure security policies
security.configure_security_policy("password_policy", [
    {"name": "min_length", "type": "password_strength", "min_length": 8},
    {"name": "session_timeout", "type": "session_timeout", "max_age_minutes": 60}
])

security.configure_security_policy("data_access_policy", [
    {"name": "ip_restriction", "type": "ip_whitelist", "allowed_ips": ["10.0.0.0/8", "192.168.1.0/24"]},
    {"name": "data_classification", "type": "data_classification", "allowed_levels": ["public", "internal"]}
])

# Configure compliance
security.configure_compliance_rules("GDPR", [
    {"id": "gdpr_data_retention", "description": "Data retention limits"},
    {"id": "gdpr_user_consent", "description": "User consent tracking"},
    {"id": "gdpr_data_portability", "description": "Data export capabilities"}
])

security.configure_compliance_rules("SOX", [
    {"id": "sox_audit_trail", "description": "Complete audit trail"},
    {"id": "sox_access_controls", "description": "Access control documentation"},
    {"id": "sox_change_management", "description": "Change management process"}
])

# Test security features
test_data = {"username": "john.doe", "email": "john@company.com"}
encrypted = security.encrypt_data(test_data, "user_data")
decrypted = security.decrypt_data(encrypted)

policy_check = security.check_security_policy("password_policy", {
    "password": "secure123",
    "session_age": 3000
})

gdpr_audit = security.run_compliance_audit("GDPR")
dashboard = security.get_security_dashboard()

print(f"🔐 Encryption test: {test_data == eval(decrypted)}")
print(f"🛡️  Policy compliance: {policy_check['compliant']}")
print(f"📋 GDPR compliance: {gdpr_audit['compliance_score']:.1f}%")
print(f"📊 Security dashboard: {dashboard['recent_events']} recent events")
```

## Scalability and Performance

### Auto-Scaling Infrastructure

```python
from nexus import Nexus
import time
from threading import Thread

app = Nexus()

class AutoScaler:
    """Enterprise auto-scaling for Nexus platform"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.instances = {}
        self.scaling_policies = {}
        self.metrics_history = []
        self.scaling_events = []
        self.min_instances = 1
        self.max_instances = 10

    def configure_scaling_policy(self, policy_name, config):
        """Configure auto-scaling policy"""

        self.scaling_policies[policy_name] = {
            "metric": config["metric"],
            "scale_up_threshold": config["scale_up_threshold"],
            "scale_down_threshold": config["scale_down_threshold"],
            "scale_up_cooldown": config.get("scale_up_cooldown", 300),  # 5 minutes
            "scale_down_cooldown": config.get("scale_down_cooldown", 600),  # 10 minutes
            "scaling_increment": config.get("scaling_increment", 1),
            "enabled": True
        }

        print(f"📈 Scaling policy configured: {policy_name}")

    def monitor_metrics(self):
        """Monitor system metrics for scaling decisions"""

        current_metrics = self._collect_current_metrics()
        self.metrics_history.append(current_metrics)

        # Keep only last 100 metrics entries
        if len(self.metrics_history) > 100:
            self.metrics_history.pop(0)

        # Check scaling policies
        for policy_name, policy in self.scaling_policies.items():
            if policy["enabled"]:
                self._evaluate_scaling_policy(policy_name, policy, current_metrics)

    def _collect_current_metrics(self):
        """Collect current system metrics"""

        # Simulate metric collection
        import random

        metrics = {
            "timestamp": time.time(),
            "cpu_usage": random.uniform(0.2, 0.9),
            "memory_usage": random.uniform(0.3, 0.8),
            "request_rate": random.uniform(10, 200),
            "response_time": random.uniform(50, 500),
            "active_sessions": random.randint(5, 50),
            "workflow_queue_depth": random.randint(0, 20)
        }

        return metrics

    def _evaluate_scaling_policy(self, policy_name, policy, current_metrics):
        """Evaluate if scaling action is needed"""

        metric_name = policy["metric"]
        metric_value = current_metrics.get(metric_name, 0)

        current_instances = len(self.instances)

        # Check for scale up
        if (metric_value > policy["scale_up_threshold"] and
            current_instances < self.max_instances):

            last_scale_up = self._get_last_scaling_event("scale_up")
            cooldown = policy["scale_up_cooldown"]

            if not last_scale_up or time.time() - last_scale_up > cooldown:
                self._scale_up(policy_name, policy["scaling_increment"])

        # Check for scale down
        elif (metric_value < policy["scale_down_threshold"] and
              current_instances > self.min_instances):

            last_scale_down = self._get_last_scaling_event("scale_down")
            cooldown = policy["scale_down_cooldown"]

            if not last_scale_down or time.time() - last_scale_down > cooldown:
                self._scale_down(policy_name, policy["scaling_increment"])

    def _get_last_scaling_event(self, event_type):
        """Get timestamp of last scaling event of specific type"""

        for event in reversed(self.scaling_events):
            if event["action"] == event_type:
                return event["timestamp"]

        return None

    def _scale_up(self, policy_name, increment):
        """Scale up instances"""

        for i in range(increment):
            if len(self.instances) >= self.max_instances:
                break

            instance_id = f"nexus-{len(self.instances) + 1}"
            self.instances[instance_id] = {
                "id": instance_id,
                "created_at": time.time(),
                "status": "running",
                "cpu_limit": "2 cores",
                "memory_limit": "4GB"
            }

        scaling_event = {
            "timestamp": time.time(),
            "action": "scale_up",
            "policy": policy_name,
            "instances_added": increment,
            "total_instances": len(self.instances)
        }

        self.scaling_events.append(scaling_event)
        print(f"📈 Scaled up: {increment} instances (total: {len(self.instances)})")

    def _scale_down(self, policy_name, decrement):
        """Scale down instances"""

        instances_to_remove = min(decrement, len(self.instances) - self.min_instances)

        for i in range(instances_to_remove):
            # Remove the most recently created instance
            if self.instances:
                instance_id = max(self.instances.keys())
                del self.instances[instance_id]

        scaling_event = {
            "timestamp": time.time(),
            "action": "scale_down",
            "policy": policy_name,
            "instances_removed": instances_to_remove,
            "total_instances": len(self.instances)
        }

        self.scaling_events.append(scaling_event)
        print(f"📉 Scaled down: {instances_to_remove} instances (total: {len(self.instances)})")

    def get_scaling_status(self):
        """Get current scaling status"""

        recent_events = [e for e in self.scaling_events
                        if e["timestamp"] > time.time() - 3600]  # Last hour

        status = {
            "current_instances": len(self.instances),
            "min_instances": self.min_instances,
            "max_instances": self.max_instances,
            "active_policies": len([p for p in self.scaling_policies.values() if p["enabled"]]),
            "recent_scaling_events": len(recent_events),
            "instances": list(self.instances.keys())
        }

        return status

    def start_monitoring(self):
        """Start auto-scaling monitoring"""

        def monitoring_loop():
            while True:
                self.monitor_metrics()
                time.sleep(30)  # Check every 30 seconds

        monitor_thread = Thread(target=monitoring_loop, daemon=True)
        monitor_thread.start()
        print("🔍 Auto-scaling monitoring started")

# Configure auto-scaling
autoscaler = AutoScaler(app)

# Configure scaling policies
autoscaler.configure_scaling_policy("cpu_based", {
    "metric": "cpu_usage",
    "scale_up_threshold": 0.7,
    "scale_down_threshold": 0.3,
    "scale_up_cooldown": 180,    # 3 minutes
    "scale_down_cooldown": 300   # 5 minutes
})

autoscaler.configure_scaling_policy("request_based", {
    "metric": "request_rate",
    "scale_up_threshold": 100,
    "scale_down_threshold": 20,
    "scaling_increment": 2
})

autoscaler.configure_scaling_policy("queue_based", {
    "metric": "workflow_queue_depth",
    "scale_up_threshold": 10,
    "scale_down_threshold": 2
})

# Start initial instance
autoscaler.instances["nexus-1"] = {
    "id": "nexus-1",
    "created_at": time.time(),
    "status": "running"
}

# Start monitoring (commented out to avoid infinite loop in docs)
# autoscaler.start_monitoring()

# Simulate scaling scenario
for i in range(5):
    autoscaler.monitor_metrics()
    time.sleep(1)

scaling_status = autoscaler.get_scaling_status()
print(f"📊 Scaling Status: {scaling_status['current_instances']} instances running")
```

## Next Steps

Explore advanced technical topics:

1. **[Architecture Overview](../technical/architecture-overview.md)** - Deep technical understanding
2. **[Performance Guide](../technical/performance-guide.md)** - Optimization techniques
3. **[Security Guide](../technical/security-guide.md)** - Advanced security patterns
4. **[Production Deployment](../advanced/production-deployment.md)** - Enterprise deployment

## Key Takeaways

✅ **Enterprise-Default Philosophy** → Production features included, not add-ons
✅ **Multi-Provider Authentication** → OAuth2, LDAP, SAML out of the box
✅ **Comprehensive Monitoring** → Metrics, alerts, dashboards, health checks
✅ **Security Framework** → Encryption, audit trails, compliance automation
✅ **Auto-Scaling** → Intelligent scaling based on multiple metrics
✅ **Progressive Enhancement** → Add capabilities without breaking changes

Nexus revolutionizes enterprise software by making production-grade features the default experience, not expensive add-ons. This enterprise-first approach ensures your platform scales from development to production without architectural rewrites.
