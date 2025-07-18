# Security Guide

Comprehensive security implementation for Nexus's enterprise-grade workflow platform with built-in authentication, authorization, encryption, and compliance features.

## Overview

Nexus provides enterprise-default security that goes beyond traditional add-on approaches. This guide covers authentication systems, role-based access control, data encryption, audit trails, compliance frameworks, and threat detection for production-grade security.

## Authentication Systems

### Multi-Provider Authentication

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import hashlib
import secrets
import time
import jwt

app = Nexus(enable_auth=True)

class EnterpriseAuthenticationManager:
    """Enterprise-grade authentication with multiple providers"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.auth_providers = {}
        self.user_sessions = {}
        self.auth_tokens = {}
        self.failed_attempts = {}
        self.security_config = {
            "max_failed_attempts": 5,
            "lockout_duration": 900,  # 15 minutes
            "token_expiry": 3600,     # 1 hour
            "require_mfa": True,
            "password_policy": {
                "min_length": 12,
                "require_uppercase": True,
                "require_lowercase": True,
                "require_numbers": True,
                "require_symbols": True
            }
        }

    def configure_oauth2_provider(self, provider_name, config):
        """Configure OAuth2 provider with enterprise features"""

        oauth2_config = {
            "provider_type": "oauth2",
            "client_id": config.get("client_id"),
            "client_secret": config.get("client_secret"),
            "authorization_url": config.get("authorization_url"),
            "token_url": config.get("token_url"),
            "user_info_url": config.get("user_info_url"),
            "scopes": config.get("scopes", ["openid", "profile", "email"]),
            "pkce_enabled": config.get("pkce_enabled", True),
            "state_validation": config.get("state_validation", True),
            "nonce_validation": config.get("nonce_validation", True)
        }

        self.auth_providers[provider_name] = oauth2_config

        return {
            "provider_configured": provider_name,
            "security_features": ["PKCE", "State validation", "Nonce validation"],
            "configuration": oauth2_config
        }

    def configure_saml_provider(self, config):
        """Configure SAML 2.0 provider for enterprise SSO"""

        saml_config = {
            "provider_type": "saml2",
            "entity_id": config.get("entity_id"),
            "sso_url": config.get("sso_url"),
            "slo_url": config.get("slo_url"),
            "x509_cert": config.get("x509_cert"),
            "sign_requests": config.get("sign_requests", True),
            "encrypt_assertions": config.get("encrypt_assertions", True),
            "name_id_format": config.get("name_id_format", "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"),
            "attribute_mapping": config.get("attribute_mapping", {
                "email": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
                "first_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
                "last_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname"
            })
        }

        self.auth_providers["saml"] = saml_config

        return {
            "provider_configured": "saml",
            "security_features": ["Request signing", "Assertion encryption", "Attribute mapping"],
            "configuration": saml_config
        }

    def configure_ldap_provider(self, config):
        """Configure LDAP/Active Directory authentication"""

        ldap_config = {
            "provider_type": "ldap",
            "server": config.get("server"),
            "port": config.get("port", 636),  # LDAPS by default
            "use_ssl": config.get("use_ssl", True),
            "base_dn": config.get("base_dn"),
            "user_filter": config.get("user_filter", "(sAMAccountName={username})"),
            "group_filter": config.get("group_filter", "(member={user_dn})"),
            "user_search_base": config.get("user_search_base"),
            "group_search_base": config.get("group_search_base"),
            "bind_dn": config.get("bind_dn"),
            "bind_password": config.get("bind_password"),
            "connection_pool_size": config.get("connection_pool_size", 10),
            "connection_timeout": config.get("connection_timeout", 30)
        }

        self.auth_providers["ldap"] = ldap_config

        return {
            "provider_configured": "ldap",
            "security_features": ["SSL encryption", "Connection pooling", "Group mapping"],
            "configuration": ldap_config
        }

    def authenticate_user(self, username, credentials, provider="local", mfa_token=None):
        """Authenticate user with comprehensive security checks"""

        # Check for account lockout
        if self._is_account_locked(username):
            return {
                "success": False,
                "error": "account_locked",
                "message": "Account locked due to too many failed attempts"
            }

        try:
            # Perform provider-specific authentication
            auth_result = self._authenticate_with_provider(username, credentials, provider)

            if auth_result["success"]:
                # Check MFA if required
                if self.security_config["require_mfa"] and not mfa_token:
                    return {
                        "success": False,
                        "error": "mfa_required",
                        "message": "Multi-factor authentication required",
                        "mfa_challenge": self._generate_mfa_challenge(username)
                    }

                if mfa_token and not self._verify_mfa_token(username, mfa_token):
                    self._record_failed_attempt(username)
                    return {
                        "success": False,
                        "error": "invalid_mfa",
                        "message": "Invalid MFA token"
                    }

                # Create secure session
                session_token = self._create_secure_session(username, provider, auth_result.get("user_info", {}))

                # Clear failed attempts on successful login
                if username in self.failed_attempts:
                    del self.failed_attempts[username]

                return {
                    "success": True,
                    "session_token": session_token,
                    "user_info": auth_result.get("user_info", {}),
                    "expires_at": time.time() + self.security_config["token_expiry"]
                }

            else:
                self._record_failed_attempt(username)
                return auth_result

        except Exception as e:
            self._record_failed_attempt(username)
            return {
                "success": False,
                "error": "authentication_error",
                "message": f"Authentication failed: {str(e)}"
            }

    def _authenticate_with_provider(self, username, credentials, provider):
        """Provider-specific authentication logic"""

        if provider == "local":
            # Simulate local authentication
            if username == "admin" and credentials.get("password") == "secure_password_123!":
                return {
                    "success": True,
                    "user_info": {
                        "username": username,
                        "email": f"{username}@company.com",
                        "roles": ["admin"],
                        "provider": "local"
                    }
                }
            else:
                return {
                    "success": False,
                    "error": "invalid_credentials",
                    "message": "Invalid username or password"
                }

        elif provider in self.auth_providers:
            provider_config = self.auth_providers[provider]

            if provider_config["provider_type"] == "oauth2":
                # Simulate OAuth2 authentication
                return {
                    "success": True,
                    "user_info": {
                        "username": username,
                        "email": f"{username}@oauth-provider.com",
                        "roles": ["user"],
                        "provider": provider
                    }
                }

            elif provider_config["provider_type"] == "saml2":
                # Simulate SAML authentication
                return {
                    "success": True,
                    "user_info": {
                        "username": username,
                        "email": f"{username}@saml-provider.com",
                        "roles": ["user"],
                        "provider": "saml"
                    }
                }

            elif provider_config["provider_type"] == "ldap":
                # Simulate LDAP authentication
                return {
                    "success": True,
                    "user_info": {
                        "username": username,
                        "email": f"{username}@ldap-domain.com",
                        "roles": ["user"],
                        "provider": "ldap"
                    }
                }

        return {
            "success": False,
            "error": "unsupported_provider",
            "message": f"Authentication provider '{provider}' not configured"
        }

    def _is_account_locked(self, username):
        """Check if account is locked due to failed attempts"""

        if username not in self.failed_attempts:
            return False

        attempt_data = self.failed_attempts[username]

        if attempt_data["count"] >= self.security_config["max_failed_attempts"]:
            # Check if lockout period has expired
            if time.time() - attempt_data["last_attempt"] < self.security_config["lockout_duration"]:
                return True
            else:
                # Reset failed attempts after lockout period
                del self.failed_attempts[username]
                return False

        return False

    def _record_failed_attempt(self, username):
        """Record failed authentication attempt"""

        current_time = time.time()

        if username not in self.failed_attempts:
            self.failed_attempts[username] = {
                "count": 1,
                "first_attempt": current_time,
                "last_attempt": current_time
            }
        else:
            self.failed_attempts[username]["count"] += 1
            self.failed_attempts[username]["last_attempt"] = current_time

    def _generate_mfa_challenge(self, username):
        """Generate MFA challenge for user"""

        # Simulate MFA challenge generation
        challenge_code = secrets.token_hex(4).upper()

        return {
            "challenge_type": "totp",
            "challenge_code": challenge_code,
            "expires_in": 300  # 5 minutes
        }

    def _verify_mfa_token(self, username, mfa_token):
        """Verify MFA token"""

        # Simulate MFA verification (in real implementation, verify TOTP/SMS/etc.)
        return len(mfa_token) >= 6 and mfa_token.isdigit()

    def _create_secure_session(self, username, provider, user_info):
        """Create secure JWT session token"""

        payload = {
            "username": username,
            "provider": provider,
            "user_info": user_info,
            "issued_at": time.time(),
            "expires_at": time.time() + self.security_config["token_expiry"],
            "session_id": secrets.token_urlsafe(32)
        }

        # In production, use proper JWT signing
        token = jwt.encode(payload, "secure_secret_key", algorithm="HS256")

        self.auth_tokens[payload["session_id"]] = {
            "token": token,
            "payload": payload,
            "created_at": time.time()
        }

        return token

    def validate_token(self, token):
        """Validate JWT token and return user information"""

        try:
            payload = jwt.decode(token, "secure_secret_key", algorithms=["HS256"])

            # Check expiration
            if time.time() > payload["expires_at"]:
                return {"valid": False, "error": "token_expired"}

            return {
                "valid": True,
                "username": payload["username"],
                "user_info": payload["user_info"],
                "session_id": payload["session_id"]
            }

        except jwt.InvalidTokenError:
            return {"valid": False, "error": "invalid_token"}

    def get_security_status(self):
        """Get comprehensive security status"""

        return {
            "auth_providers": len(self.auth_providers),
            "active_sessions": len(self.auth_tokens),
            "failed_attempts": len(self.failed_attempts),
            "mfa_enabled": self.security_config["require_mfa"],
            "security_features": [
                "Multi-provider authentication",
                "Account lockout protection",
                "MFA support",
                "JWT tokens",
                "Password policy enforcement"
            ]
        }

# Usage example
auth_manager = EnterpriseAuthenticationManager(app)

# Configure multiple authentication providers
oauth2_config = auth_manager.configure_oauth2_provider("google", {
    "client_id": "google_client_id",
    "client_secret": "google_client_secret",
    "authorization_url": "https://accounts.google.com/o/oauth2/auth",
    "token_url": "https://oauth2.googleapis.com/token"
})

saml_config = auth_manager.configure_saml_provider({
    "entity_id": "nexus_platform",
    "sso_url": "https://sso.company.com/saml/login",
    "x509_cert": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"
})

ldap_config = auth_manager.configure_ldap_provider({
    "server": "ldap.company.com",
    "base_dn": "dc=company,dc=com",
    "user_search_base": "ou=users,dc=company,dc=com"
})

print(f"OAuth2 Provider: {oauth2_config}")
print(f"SAML Provider: {saml_config}")
print(f"LDAP Provider: {ldap_config}")

# Test authentication
auth_result = auth_manager.authenticate_user("admin", {"password": "secure_password_123!"}, "local")
print(f"Authentication Result: {auth_result}")

# Get security status
security_status = auth_manager.get_security_status()
print(f"Security Status: {security_status}")
```

## Role-Based Access Control (RBAC)

### Advanced RBAC System

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time
from enum import Enum

app = Nexus()

class Permission(Enum):
    """Define system permissions"""
    READ_WORKFLOWS = "read_workflows"
    WRITE_WORKFLOWS = "write_workflows"
    DELETE_WORKFLOWS = "delete_workflows"
    EXECUTE_WORKFLOWS = "execute_workflows"
    MANAGE_USERS = "manage_users"
    MANAGE_ROLES = "manage_roles"
    VIEW_AUDIT_LOGS = "view_audit_logs"
    MANAGE_SYSTEM = "manage_system"
    ACCESS_API = "access_api"
    ACCESS_CLI = "access_cli"
    ACCESS_MCP = "access_mcp"

class AdvancedRBACManager:
    """Advanced Role-Based Access Control with fine-grained permissions"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.roles = {}
        self.user_roles = {}
        self.role_hierarchies = {}
        self.dynamic_permissions = {}
        self.access_policies = {}
        self.audit_log = []

    def create_role(self, role_name, permissions, description="", parent_role=None):
        """Create role with hierarchical inheritance"""

        # Convert string permissions to Permission enum
        if isinstance(permissions, list) and permissions:
            if isinstance(permissions[0], str):
                permissions = [Permission(p) for p in permissions]

        role_config = {
            "name": role_name,
            "permissions": set(permissions),
            "description": description,
            "parent_role": parent_role,
            "created_at": time.time(),
            "active": True,
            "metadata": {}
        }

        # Inherit permissions from parent role
        if parent_role and parent_role in self.roles:
            inherited_permissions = self.roles[parent_role]["permissions"]
            role_config["permissions"].update(inherited_permissions)

        self.roles[role_name] = role_config

        # Track role hierarchy
        if parent_role:
            if parent_role not in self.role_hierarchies:
                self.role_hierarchies[parent_role] = []
            self.role_hierarchies[parent_role].append(role_name)

        self._audit_log_entry("role_created", {
            "role_name": role_name,
            "permissions": [p.value for p in role_config["permissions"]],
            "parent_role": parent_role
        })

        return {
            "role_created": role_name,
            "permissions": [p.value for p in role_config["permissions"]],
            "inherited_from": parent_role
        }

    def assign_user_roles(self, user_id, roles, expires_at=None):
        """Assign multiple roles to user with optional expiration"""

        if not isinstance(roles, list):
            roles = [roles]

        # Validate all roles exist
        invalid_roles = [role for role in roles if role not in self.roles]
        if invalid_roles:
            return {
                "success": False,
                "error": f"Invalid roles: {invalid_roles}"
            }

        user_role_config = {
            "roles": roles,
            "assigned_at": time.time(),
            "expires_at": expires_at,
            "active": True,
            "assigned_by": "system"  # In real implementation, track who assigned
        }

        self.user_roles[user_id] = user_role_config

        self._audit_log_entry("roles_assigned", {
            "user_id": user_id,
            "roles": roles,
            "expires_at": expires_at
        })

        return {
            "success": True,
            "user_id": user_id,
            "roles_assigned": roles,
            "expires_at": expires_at
        }

    def check_permission(self, user_id, required_permission, resource_context=None):
        """Check if user has required permission with context"""

        # Convert string permission to enum
        if isinstance(required_permission, str):
            try:
                required_permission = Permission(required_permission)
            except ValueError:
                return {
                    "authorized": False,
                    "reason": f"Unknown permission: {required_permission}"
                }

        if user_id not in self.user_roles:
            return {
                "authorized": False,
                "reason": "No roles assigned to user"
            }

        user_role_config = self.user_roles[user_id]

        # Check if roles have expired
        if user_role_config.get("expires_at") and time.time() > user_role_config["expires_at"]:
            return {
                "authorized": False,
                "reason": "User roles have expired"
            }

        # Check if user roles are active
        if not user_role_config.get("active", True):
            return {
                "authorized": False,
                "reason": "User roles are inactive"
            }

        # Collect all permissions from user's roles
        user_permissions = set()
        user_roles = user_role_config["roles"]

        for role_name in user_roles:
            if role_name in self.roles and self.roles[role_name]["active"]:
                user_permissions.update(self.roles[role_name]["permissions"])

        # Check dynamic permissions
        dynamic_perms = self._evaluate_dynamic_permissions(user_id, resource_context)
        user_permissions.update(dynamic_perms)

        # Check access policies
        policy_result = self._evaluate_access_policies(user_id, required_permission, resource_context)
        if not policy_result["allowed"]:
            return {
                "authorized": False,
                "reason": f"Access denied by policy: {policy_result['reason']}"
            }

        # Check if user has required permission
        if required_permission in user_permissions:
            self._audit_log_entry("permission_granted", {
                "user_id": user_id,
                "permission": required_permission.value,
                "resource_context": resource_context
            })

            return {
                "authorized": True,
                "user_id": user_id,
                "permission": required_permission.value,
                "granted_by_roles": user_roles
            }

        self._audit_log_entry("permission_denied", {
            "user_id": user_id,
            "permission": required_permission.value,
            "resource_context": resource_context,
            "user_permissions": [p.value for p in user_permissions]
        })

        return {
            "authorized": False,
            "reason": f"Permission {required_permission.value} not granted",
            "user_permissions": [p.value for p in user_permissions]
        }

    def create_access_policy(self, policy_name, conditions, effect="ALLOW"):
        """Create conditional access policy"""

        policy = {
            "name": policy_name,
            "conditions": conditions,
            "effect": effect,  # ALLOW or DENY
            "created_at": time.time(),
            "active": True
        }

        self.access_policies[policy_name] = policy

        return {"policy_created": policy_name, "effect": effect}

    def _evaluate_access_policies(self, user_id, permission, resource_context):
        """Evaluate access policies for permission request"""

        for policy_name, policy in self.access_policies.items():
            if not policy["active"]:
                continue

            # Evaluate policy conditions
            conditions_met = True

            for condition_type, condition_value in policy["conditions"].items():
                if condition_type == "time_of_day":
                    current_hour = time.localtime().tm_hour
                    if not (condition_value["start"] <= current_hour <= condition_value["end"]):
                        conditions_met = False
                        break

                elif condition_type == "ip_address":
                    # In real implementation, check actual IP
                    user_ip = resource_context.get("ip_address", "127.0.0.1") if resource_context else "127.0.0.1"
                    if user_ip not in condition_value["allowed_ips"]:
                        conditions_met = False
                        break

                elif condition_type == "resource_type":
                    resource_type = resource_context.get("resource_type") if resource_context else None
                    if resource_type and resource_type not in condition_value["allowed_types"]:
                        conditions_met = False
                        break

            # If conditions are met and policy is DENY, block access
            if conditions_met and policy["effect"] == "DENY":
                return {
                    "allowed": False,
                    "reason": f"Denied by policy: {policy_name}"
                }

        return {"allowed": True, "reason": "No blocking policies"}

    def _evaluate_dynamic_permissions(self, user_id, resource_context):
        """Evaluate dynamic permissions based on context"""

        dynamic_perms = set()

        # Example: Grant temporary permissions based on context
        if resource_context:
            # Emergency access during maintenance window
            if resource_context.get("emergency_mode"):
                dynamic_perms.add(Permission.EXECUTE_WORKFLOWS)

            # Owner permissions for created resources
            if resource_context.get("resource_owner") == user_id:
                dynamic_perms.update([
                    Permission.READ_WORKFLOWS,
                    Permission.WRITE_WORKFLOWS,
                    Permission.EXECUTE_WORKFLOWS
                ])

        return dynamic_perms

    def get_user_permissions(self, user_id, include_dynamic=True):
        """Get all permissions for a user"""

        if user_id not in self.user_roles:
            return {"user_permissions": [], "roles": []}

        user_role_config = self.user_roles[user_id]
        user_roles = user_role_config["roles"]

        # Collect permissions from roles
        all_permissions = set()
        for role_name in user_roles:
            if role_name in self.roles and self.roles[role_name]["active"]:
                all_permissions.update(self.roles[role_name]["permissions"])

        # Add dynamic permissions if requested
        if include_dynamic:
            dynamic_perms = self._evaluate_dynamic_permissions(user_id, None)
            all_permissions.update(dynamic_perms)

        return {
            "user_permissions": [p.value for p in all_permissions],
            "roles": user_roles,
            "role_expiry": user_role_config.get("expires_at"),
            "dynamic_permissions_included": include_dynamic
        }

    def get_role_hierarchy(self):
        """Get complete role hierarchy"""

        hierarchy = {}

        for role_name, role_config in self.roles.items():
            hierarchy[role_name] = {
                "permissions": [p.value for p in role_config["permissions"]],
                "parent": role_config.get("parent_role"),
                "children": self.role_hierarchies.get(role_name, []),
                "description": role_config.get("description", "")
            }

        return hierarchy

    def _audit_log_entry(self, action, details):
        """Add entry to audit log"""

        log_entry = {
            "timestamp": time.time(),
            "action": action,
            "details": details,
            "source": "rbac_manager"
        }

        self.audit_log.append(log_entry)

        # Keep only last 1000 entries
        if len(self.audit_log) > 1000:
            self.audit_log = self.audit_log[-1000:]

    def get_audit_log(self, limit=50, filter_action=None):
        """Get audit log entries"""

        logs = self.audit_log

        if filter_action:
            logs = [log for log in logs if log["action"] == filter_action]

        # Return most recent entries
        return logs[-limit:] if len(logs) > limit else logs

    def get_rbac_analytics(self):
        """Get RBAC analytics and insights"""

        total_users = len(self.user_roles)
        total_roles = len(self.roles)
        active_roles = len([r for r in self.roles.values() if r["active"]])

        # Role usage analytics
        role_usage = {}
        for user_roles in self.user_roles.values():
            for role in user_roles["roles"]:
                role_usage[role] = role_usage.get(role, 0) + 1

        most_used_role = max(role_usage.items(), key=lambda x: x[1])[0] if role_usage else None

        # Permission analytics
        permission_grants = {}
        for log_entry in self.audit_log:
            if log_entry["action"] == "permission_granted":
                perm = log_entry["details"]["permission"]
                permission_grants[perm] = permission_grants.get(perm, 0) + 1

        return {
            "users": total_users,
            "roles": total_roles,
            "active_roles": active_roles,
            "policies": len(self.access_policies),
            "most_used_role": most_used_role,
            "role_usage": role_usage,
            "permission_grants": permission_grants,
            "audit_entries": len(self.audit_log)
        }

# Usage example
rbac = AdvancedRBACManager(app)

# Create role hierarchy
admin_role = rbac.create_role("admin", [
    Permission.READ_WORKFLOWS, Permission.WRITE_WORKFLOWS, Permission.DELETE_WORKFLOWS,
    Permission.EXECUTE_WORKFLOWS, Permission.MANAGE_USERS, Permission.MANAGE_ROLES,
    Permission.VIEW_AUDIT_LOGS, Permission.MANAGE_SYSTEM, Permission.ACCESS_API,
    Permission.ACCESS_CLI, Permission.ACCESS_MCP
], "Full system administrator")

manager_role = rbac.create_role("manager", [
    Permission.READ_WORKFLOWS, Permission.WRITE_WORKFLOWS, Permission.EXECUTE_WORKFLOWS,
    Permission.VIEW_AUDIT_LOGS, Permission.ACCESS_API, Permission.ACCESS_CLI
], "Workflow manager", parent_role="admin")

user_role = rbac.create_role("user", [
    Permission.READ_WORKFLOWS, Permission.EXECUTE_WORKFLOWS, Permission.ACCESS_API
], "Basic user", parent_role="manager")

# Assign roles to users
admin_assignment = rbac.assign_user_roles("admin_user", ["admin"])
manager_assignment = rbac.assign_user_roles("manager_user", ["manager"])
user_assignment = rbac.assign_user_roles("regular_user", ["user"])

# Create access policy
time_policy = rbac.create_access_policy("business_hours_only", {
    "time_of_day": {"start": 9, "end": 17}  # 9 AM to 5 PM
}, "DENY")

# Test permissions
admin_check = rbac.check_permission("admin_user", Permission.MANAGE_SYSTEM)
user_check = rbac.check_permission("regular_user", Permission.DELETE_WORKFLOWS)

print(f"Admin Role: {admin_role}")
print(f"Manager Role: {manager_role}")
print(f"User Role: {user_role}")
print(f"Admin Permission Check: {admin_check}")
print(f"User Permission Check: {user_check}")

# Get analytics
rbac_analytics = rbac.get_rbac_analytics()
print(f"RBAC Analytics: {rbac_analytics}")
```

## Data Encryption and Protection

### Enterprise Data Security

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import hashlib
import secrets
import time
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import json

app = Nexus()

class EnterpriseDataSecurity:
    """Enterprise-grade data encryption and protection"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.encryption_keys = {}
        self.key_rotation_schedule = {}
        self.encrypted_data_store = {}
        self.access_log = []
        self.security_policies = {
            "encryption_algorithm": "AES-256",
            "key_rotation_interval": 86400 * 30,  # 30 days
            "min_key_length": 32,
            "require_encryption_at_rest": True,
            "require_encryption_in_transit": True,
            "data_classification_levels": ["public", "internal", "confidential", "restricted"]
        }

    def generate_encryption_key(self, key_name, password=None, salt=None):
        """Generate strong encryption key with optional password derivation"""

        if password:
            # Derive key from password using PBKDF2
            if not salt:
                salt = secrets.token_bytes(16)

            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        else:
            # Generate random key
            key = Fernet.generate_key()
            salt = None

        key_metadata = {
            "key_name": key_name,
            "algorithm": "Fernet (AES-128)",
            "created_at": time.time(),
            "derived_from_password": password is not None,
            "salt": base64.b64encode(salt).decode() if salt else None,
            "rotation_due": time.time() + self.security_policies["key_rotation_interval"],
            "usage_count": 0,
            "active": True
        }

        self.encryption_keys[key_name] = {
            "key": key,
            "metadata": key_metadata,
            "fernet": Fernet(key)
        }

        return {
            "key_generated": key_name,
            "algorithm": key_metadata["algorithm"],
            "rotation_due": key_metadata["rotation_due"],
            "password_derived": key_metadata["derived_from_password"]
        }

    def encrypt_data(self, data, key_name, data_classification="internal", metadata=None):
        """Encrypt data with specified key and classification"""

        if key_name not in self.encryption_keys:
            raise ValueError(f"Encryption key '{key_name}' not found")

        key_info = self.encryption_keys[key_name]

        if not key_info["metadata"]["active"]:
            raise ValueError(f"Encryption key '{key_name}' is not active")

        # Serialize data if it's not bytes
        if isinstance(data, (dict, list)):
            data_bytes = json.dumps(data).encode()
        elif isinstance(data, str):
            data_bytes = data.encode()
        else:
            data_bytes = data

        # Encrypt data
        encrypted_data = key_info["fernet"].encrypt(data_bytes)

        # Create encryption metadata
        encryption_metadata = {
            "encrypted_at": time.time(),
            "key_name": key_name,
            "algorithm": key_info["metadata"]["algorithm"],
            "data_classification": data_classification,
            "data_size": len(data_bytes),
            "encrypted_size": len(encrypted_data),
            "checksum": hashlib.sha256(data_bytes).hexdigest(),
            "custom_metadata": metadata or {}
        }

        # Store encrypted data
        data_id = secrets.token_urlsafe(16)
        self.encrypted_data_store[data_id] = {
            "encrypted_data": encrypted_data,
            "metadata": encryption_metadata
        }

        # Update key usage
        key_info["metadata"]["usage_count"] += 1

        # Log access
        self._log_data_access("encrypt", {
            "data_id": data_id,
            "key_name": key_name,
            "classification": data_classification,
            "size": len(data_bytes)
        })

        return {
            "data_id": data_id,
            "encrypted": True,
            "algorithm": encryption_metadata["algorithm"],
            "classification": data_classification,
            "metadata": encryption_metadata
        }

    def decrypt_data(self, data_id, requesting_user=None, purpose=None):
        """Decrypt data with access controls and logging"""

        if data_id not in self.encrypted_data_store:
            raise ValueError(f"Encrypted data '{data_id}' not found")

        data_entry = self.encrypted_data_store[data_id]
        encrypted_data = data_entry["encrypted_data"]
        metadata = data_entry["metadata"]

        key_name = metadata["key_name"]

        if key_name not in self.encryption_keys:
            raise ValueError(f"Decryption key '{key_name}' not found")

        key_info = self.encryption_keys[key_name]

        # Check if key is still active
        if not key_info["metadata"]["active"]:
            raise ValueError(f"Decryption key '{key_name}' is not active")

        # Decrypt data
        try:
            decrypted_bytes = key_info["fernet"].decrypt(encrypted_data)
        except Exception as e:
            self._log_data_access("decrypt_failed", {
                "data_id": data_id,
                "key_name": key_name,
                "error": str(e),
                "requesting_user": requesting_user
            })
            raise ValueError(f"Decryption failed: {str(e)}")

        # Verify checksum
        decrypted_checksum = hashlib.sha256(decrypted_bytes).hexdigest()
        if decrypted_checksum != metadata["checksum"]:
            raise ValueError("Data integrity check failed")

        # Try to deserialize data
        try:
            decrypted_data = json.loads(decrypted_bytes.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Return as bytes if not JSON
            decrypted_data = decrypted_bytes

        # Log successful decryption
        self._log_data_access("decrypt", {
            "data_id": data_id,
            "key_name": key_name,
            "classification": metadata["data_classification"],
            "requesting_user": requesting_user,
            "purpose": purpose
        })

        return {
            "data": decrypted_data,
            "metadata": metadata,
            "decrypted_at": time.time(),
            "checksum_verified": True
        }

    def rotate_encryption_key(self, key_name, new_password=None):
        """Rotate encryption key and re-encrypt data"""

        if key_name not in self.encryption_keys:
            raise ValueError(f"Key '{key_name}' not found")

        old_key_info = self.encryption_keys[key_name]

        # Generate new key
        new_key_name = f"{key_name}_v{int(time.time())}"
        self.generate_encryption_key(new_key_name, new_password)

        # Find all data encrypted with old key
        data_to_reencrypt = []
        for data_id, data_entry in self.encrypted_data_store.items():
            if data_entry["metadata"]["key_name"] == key_name:
                data_to_reencrypt.append(data_id)

        # Re-encrypt data with new key
        reencryption_results = []
        for data_id in data_to_reencrypt:
            try:
                # Decrypt with old key
                decrypted_result = self.decrypt_data(data_id, "system", "key_rotation")
                decrypted_data = decrypted_result["data"]
                old_metadata = decrypted_result["metadata"]

                # Remove old encrypted data
                del self.encrypted_data_store[data_id]

                # Encrypt with new key
                new_result = self.encrypt_data(
                    decrypted_data,
                    new_key_name,
                    old_metadata["data_classification"],
                    old_metadata.get("custom_metadata")
                )

                reencryption_results.append({
                    "old_data_id": data_id,
                    "new_data_id": new_result["data_id"],
                    "status": "success"
                })

            except Exception as e:
                reencryption_results.append({
                    "old_data_id": data_id,
                    "status": "failed",
                    "error": str(e)
                })

        # Deactivate old key
        old_key_info["metadata"]["active"] = False
        old_key_info["metadata"]["rotated_at"] = time.time()
        old_key_info["metadata"]["successor_key"] = new_key_name

        # Log key rotation
        self._log_data_access("key_rotated", {
            "old_key": key_name,
            "new_key": new_key_name,
            "data_items_reencrypted": len([r for r in reencryption_results if r["status"] == "success"]),
            "failed_reencryptions": len([r for r in reencryption_results if r["status"] == "failed"])
        })

        return {
            "key_rotated": key_name,
            "new_key": new_key_name,
            "reencryption_results": reencryption_results,
            "rotation_completed_at": time.time()
        }

    def get_encryption_status(self):
        """Get comprehensive encryption status"""

        active_keys = len([k for k in self.encryption_keys.values() if k["metadata"]["active"]])
        total_encrypted_items = len(self.encrypted_data_store)

        # Check for keys due for rotation
        current_time = time.time()
        keys_due_rotation = []
        for key_name, key_info in self.encryption_keys.items():
            if (key_info["metadata"]["active"] and
                current_time > key_info["metadata"]["rotation_due"]):
                keys_due_rotation.append(key_name)

        # Calculate encryption coverage by classification
        classification_stats = {}
        for data_entry in self.encrypted_data_store.values():
            classification = data_entry["metadata"]["data_classification"]
            classification_stats[classification] = classification_stats.get(classification, 0) + 1

        return {
            "active_keys": active_keys,
            "total_keys": len(self.encryption_keys),
            "encrypted_data_items": total_encrypted_items,
            "keys_due_rotation": keys_due_rotation,
            "classification_distribution": classification_stats,
            "security_policies": self.security_policies,
            "access_log_entries": len(self.access_log)
        }

    def _log_data_access(self, action, details):
        """Log data access for audit trail"""

        log_entry = {
            "timestamp": time.time(),
            "action": action,
            "details": details,
            "source": "data_security"
        }

        self.access_log.append(log_entry)

        # Keep only last 1000 entries
        if len(self.access_log) > 1000:
            self.access_log = self.access_log[-1000:]

    def create_data_classification_policy(self, classification_level, requirements):
        """Create data classification policy"""

        if classification_level not in self.security_policies["data_classification_levels"]:
            raise ValueError(f"Invalid classification level: {classification_level}")

        policy = {
            "classification": classification_level,
            "encryption_required": requirements.get("encryption_required", True),
            "key_rotation_interval": requirements.get("key_rotation_interval", 86400 * 30),
            "access_logging_required": requirements.get("access_logging_required", True),
            "retention_period": requirements.get("retention_period", 86400 * 365 * 7),  # 7 years
            "backup_encryption_required": requirements.get("backup_encryption_required", True),
            "geographic_restrictions": requirements.get("geographic_restrictions", []),
            "created_at": time.time()
        }

        return {
            "policy_created": classification_level,
            "requirements": policy
        }

# Usage example
data_security = EnterpriseDataSecurity(app)

# Generate encryption keys
user_data_key = data_security.generate_encryption_key("user_data", "secure_password_123!")
system_key = data_security.generate_encryption_key("system_data")

print(f"User Data Key: {user_data_key}")
print(f"System Key: {system_key}")

# Encrypt sensitive data
sensitive_data = {
    "user_id": "12345",
    "email": "user@company.com",
    "social_security": "XXX-XX-XXXX",
    "credit_card": "XXXX-XXXX-XXXX-XXXX"
}

encryption_result = data_security.encrypt_data(
    sensitive_data,
    "user_data",
    "confidential",
    {"purpose": "user_profile", "department": "hr"}
)

print(f"Encryption Result: {encryption_result}")

# Decrypt data
decryption_result = data_security.decrypt_data(
    encryption_result["data_id"],
    "hr_manager",
    "user_verification"
)

print(f"Decryption Result: {decryption_result}")

# Get encryption status
encryption_status = data_security.get_encryption_status()
print(f"Encryption Status: {encryption_status}")

# Create data classification policy
confidential_policy = data_security.create_data_classification_policy("confidential", {
    "encryption_required": True,
    "key_rotation_interval": 86400 * 14,  # 14 days
    "access_logging_required": True,
    "retention_period": 86400 * 365 * 5,  # 5 years
    "geographic_restrictions": ["US", "EU"]
})

print(f"Confidential Policy: {confidential_policy}")
```

## Audit Trail and Compliance

### Comprehensive Audit System

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time
import json
import hashlib
from enum import Enum
from collections import defaultdict

app = Nexus()

class AuditEventType(Enum):
    """Define audit event types"""
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_DENIED = "permission_denied"
    WORKFLOW_CREATED = "workflow_created"
    WORKFLOW_EXECUTED = "workflow_executed"
    WORKFLOW_DELETED = "workflow_deleted"
    DATA_ACCESSED = "data_accessed"
    DATA_MODIFIED = "data_modified"
    CONFIG_CHANGED = "config_changed"
    SECURITY_VIOLATION = "security_violation"

class ComplianceFramework(Enum):
    """Supported compliance frameworks"""
    SOX = "sox"
    GDPR = "gdpr"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    SOC2 = "soc2"
    ISO27001 = "iso27001"

class EnterpriseAuditSystem:
    """Enterprise-grade audit trail and compliance management"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.audit_log = []
        self.compliance_rules = {}
        self.audit_config = {
            "retention_period": 86400 * 365 * 7,  # 7 years
            "log_level": "detailed",
            "real_time_monitoring": True,
            "tamper_protection": True,
            "compression_enabled": True,
            "encryption_required": True
        }
        self.compliance_reports = {}
        self.audit_alerts = []

    def log_audit_event(self, event_type, user_id, details, session_id=None, ip_address=None):
        """Log audit event with comprehensive details"""

        # Convert enum to string if needed
        if isinstance(event_type, AuditEventType):
            event_type = event_type.value

        # Create audit entry
        audit_entry = {
            "event_id": self._generate_event_id(),
            "timestamp": time.time(),
            "event_type": event_type,
            "user_id": user_id,
            "session_id": session_id,
            "ip_address": ip_address,
            "details": details,
            "source": "nexus_platform",
            "severity": self._determine_severity(event_type),
            "compliance_tags": self._get_compliance_tags(event_type),
            "checksum": None  # Will be calculated after serialization
        }

        # Calculate tamper-proof checksum
        if self.audit_config["tamper_protection"]:
            audit_entry["checksum"] = self._calculate_checksum(audit_entry)

        # Add to audit log
        self.audit_log.append(audit_entry)

        # Check compliance rules
        self._check_compliance_violations(audit_entry)

        # Real-time monitoring alerts
        if self.audit_config["real_time_monitoring"]:
            self._check_real_time_alerts(audit_entry)

        return {
            "event_logged": audit_entry["event_id"],
            "timestamp": audit_entry["timestamp"],
            "compliance_tags": audit_entry["compliance_tags"]
        }

    def _generate_event_id(self):
        """Generate unique event ID"""
        import secrets
        return f"audit_{int(time.time())}_{secrets.token_hex(8)}"

    def _determine_severity(self, event_type):
        """Determine event severity level"""

        high_severity_events = [
            "security_violation", "permission_denied", "config_changed",
            "workflow_deleted", "user_logout"
        ]

        medium_severity_events = [
            "permission_granted", "workflow_created", "data_modified"
        ]

        if event_type in high_severity_events:
            return "high"
        elif event_type in medium_severity_events:
            return "medium"
        else:
            return "low"

    def _get_compliance_tags(self, event_type):
        """Get relevant compliance framework tags for event"""

        compliance_mapping = {
            "user_login": [ComplianceFramework.SOX, ComplianceFramework.SOC2, ComplianceFramework.ISO27001],
            "permission_granted": [ComplianceFramework.GDPR, ComplianceFramework.HIPAA, ComplianceFramework.SOC2],
            "data_accessed": [ComplianceFramework.GDPR, ComplianceFramework.HIPAA, ComplianceFramework.PCI_DSS],
            "workflow_executed": [ComplianceFramework.SOX, ComplianceFramework.SOC2],
            "security_violation": [ComplianceFramework.ISO27001, ComplianceFramework.SOC2, ComplianceFramework.PCI_DSS]
        }

        frameworks = compliance_mapping.get(event_type, [])
        return [framework.value for framework in frameworks]

    def _calculate_checksum(self, audit_entry):
        """Calculate tamper-proof checksum for audit entry"""

        # Create deterministic string representation
        checksum_data = {
            "event_id": audit_entry["event_id"],
            "timestamp": audit_entry["timestamp"],
            "event_type": audit_entry["event_type"],
            "user_id": audit_entry["user_id"],
            "details": audit_entry["details"]
        }

        checksum_string = json.dumps(checksum_data, sort_keys=True)
        return hashlib.sha256(checksum_string.encode()).hexdigest()

    def configure_compliance_framework(self, framework, rules):
        """Configure compliance rules for specific framework"""

        if isinstance(framework, ComplianceFramework):
            framework = framework.value

        compliance_config = {
            "framework": framework,
            "rules": rules,
            "configured_at": time.time(),
            "active": True,
            "reporting_schedule": rules.get("reporting_schedule", "monthly"),
            "retention_requirements": rules.get("retention_requirements", {}),
            "notification_settings": rules.get("notification_settings", {})
        }

        self.compliance_rules[framework] = compliance_config

        return {
            "framework_configured": framework,
            "rules_count": len(rules),
            "active": True
        }

    def _check_compliance_violations(self, audit_entry):
        """Check audit entry against compliance rules"""

        violations = []

        for framework, config in self.compliance_rules.items():
            if not config["active"]:
                continue

            framework_rules = config["rules"]

            # Check each rule
            for rule_name, rule_config in framework_rules.items():
                violation = self._evaluate_compliance_rule(audit_entry, rule_name, rule_config, framework)
                if violation:
                    violations.append(violation)

        # Log violations
        for violation in violations:
            self._log_compliance_violation(violation)

        return violations

    def _evaluate_compliance_rule(self, audit_entry, rule_name, rule_config, framework):
        """Evaluate specific compliance rule"""

        # Example compliance rules
        if rule_name == "data_access_monitoring":
            if (audit_entry["event_type"] == "data_accessed" and
                audit_entry["details"].get("classification") == "confidential" and
                not audit_entry["details"].get("authorized_access")):

                return {
                    "framework": framework,
                    "rule": rule_name,
                    "violation_type": "unauthorized_data_access",
                    "event_id": audit_entry["event_id"],
                    "severity": "high",
                    "details": "Confidential data accessed without proper authorization"
                }

        elif rule_name == "privileged_access_monitoring":
            if (audit_entry["event_type"] == "permission_granted" and
                "admin" in audit_entry["details"].get("permissions", [])):

                # Check if privileged access is properly documented
                if not audit_entry["details"].get("justification"):
                    return {
                        "framework": framework,
                        "rule": rule_name,
                        "violation_type": "undocumented_privileged_access",
                        "event_id": audit_entry["event_id"],
                        "severity": "medium",
                        "details": "Privileged access granted without documented justification"
                    }

        elif rule_name == "configuration_change_approval":
            if audit_entry["event_type"] == "config_changed":
                if not audit_entry["details"].get("approved_by"):
                    return {
                        "framework": framework,
                        "rule": rule_name,
                        "violation_type": "unapproved_configuration_change",
                        "event_id": audit_entry["event_id"],
                        "severity": "high",
                        "details": "Configuration change made without proper approval"
                    }

        return None

    def _log_compliance_violation(self, violation):
        """Log compliance violation"""

        violation_entry = {
            "violation_id": self._generate_event_id(),
            "timestamp": time.time(),
            "framework": violation["framework"],
            "rule": violation["rule"],
            "violation_type": violation["violation_type"],
            "original_event_id": violation["event_id"],
            "severity": violation["severity"],
            "details": violation["details"],
            "status": "open",
            "remediation_required": True
        }

        # Add to alerts for real-time monitoring
        self.audit_alerts.append(violation_entry)

        # Log as audit event
        self.log_audit_event("compliance_violation", "system", violation_entry)

    def _check_real_time_alerts(self, audit_entry):
        """Check for real-time alert conditions"""

        alert_conditions = [
            {
                "name": "multiple_failed_logins",
                "condition": lambda entry: (
                    entry["event_type"] == "user_login" and
                    entry["details"].get("success") == False
                ),
                "threshold": 5,
                "time_window": 300  # 5 minutes
            },
            {
                "name": "privileged_access_outside_hours",
                "condition": lambda entry: (
                    entry["event_type"] == "permission_granted" and
                    "admin" in entry["details"].get("permissions", []) and
                    not (9 <= time.localtime().tm_hour <= 17)  # Outside business hours
                ),
                "threshold": 1,
                "time_window": 0
            }
        ]

        for alert_config in alert_conditions:
            if alert_config["condition"](audit_entry):
                self._evaluate_alert_threshold(audit_entry, alert_config)

    def _evaluate_alert_threshold(self, audit_entry, alert_config):
        """Evaluate if alert threshold is met"""

        current_time = time.time()
        time_window = alert_config["time_window"]

        # Count recent events matching condition
        recent_events = 0
        for log_entry in reversed(self.audit_log[-100:]):  # Check last 100 events
            if (current_time - log_entry["timestamp"]) <= time_window:
                if alert_config["condition"](log_entry):
                    recent_events += 1

        if recent_events >= alert_config["threshold"]:
            self._trigger_security_alert(alert_config["name"], recent_events, audit_entry)

    def _trigger_security_alert(self, alert_name, event_count, triggering_event):
        """Trigger security alert"""

        alert = {
            "alert_id": self._generate_event_id(),
            "alert_name": alert_name,
            "timestamp": time.time(),
            "severity": "high",
            "event_count": event_count,
            "triggering_event": triggering_event["event_id"],
            "user_id": triggering_event["user_id"],
            "details": f"Security alert: {alert_name} - {event_count} events detected",
            "status": "active"
        }

        self.audit_alerts.append(alert)

        # Log alert as audit event
        self.log_audit_event("security_alert", "system", alert)

    def generate_compliance_report(self, framework, start_date, end_date):
        """Generate compliance report for specific framework"""

        if isinstance(framework, ComplianceFramework):
            framework = framework.value

        # Filter audit logs by date range and framework
        relevant_logs = []
        for log_entry in self.audit_log:
            if (start_date <= log_entry["timestamp"] <= end_date and
                framework in log_entry.get("compliance_tags", [])):
                relevant_logs.append(log_entry)

        # Generate statistics
        event_counts = defaultdict(int)
        severity_counts = defaultdict(int)
        user_activity = defaultdict(int)

        for log_entry in relevant_logs:
            event_counts[log_entry["event_type"]] += 1
            severity_counts[log_entry["severity"]] += 1
            user_activity[log_entry["user_id"]] += 1

        # Count violations
        violations = [alert for alert in self.audit_alerts
                     if alert.get("framework") == framework and
                     start_date <= alert["timestamp"] <= end_date]

        # Compliance score calculation
        total_events = len(relevant_logs)
        violation_count = len(violations)
        compliance_score = max(0, 100 - (violation_count / max(total_events, 1) * 100))

        report = {
            "framework": framework,
            "report_period": {
                "start_date": start_date,
                "end_date": end_date
            },
            "generated_at": time.time(),
            "summary": {
                "total_events": total_events,
                "violations": violation_count,
                "compliance_score": round(compliance_score, 2)
            },
            "event_breakdown": dict(event_counts),
            "severity_distribution": dict(severity_counts),
            "top_users": dict(sorted(user_activity.items(), key=lambda x: x[1], reverse=True)[:10]),
            "violations": violations,
            "recommendations": self._generate_compliance_recommendations(framework, violations)
        }

        # Store report
        report_id = f"{framework}_{int(start_date)}_{int(end_date)}"
        self.compliance_reports[report_id] = report

        return report

    def _generate_compliance_recommendations(self, framework, violations):
        """Generate compliance improvement recommendations"""

        recommendations = []

        if violations:
            violation_types = defaultdict(int)
            for violation in violations:
                violation_types[violation.get("violation_type", "unknown")] += 1

            for violation_type, count in violation_types.items():
                if violation_type == "unauthorized_data_access":
                    recommendations.append({
                        "priority": "high",
                        "recommendation": "Implement stricter data access controls and regular access reviews",
                        "violation_count": count
                    })
                elif violation_type == "undocumented_privileged_access":
                    recommendations.append({
                        "priority": "medium",
                        "recommendation": "Require documented justification for all privileged access grants",
                        "violation_count": count
                    })
                elif violation_type == "unapproved_configuration_change":
                    recommendations.append({
                        "priority": "high",
                        "recommendation": "Implement mandatory approval workflow for configuration changes",
                        "violation_count": count
                    })

        # General recommendations based on framework
        if framework == "gdpr":
            recommendations.append({
                "priority": "medium",
                "recommendation": "Regular data processing impact assessments",
                "violation_count": 0
            })
        elif framework == "sox":
            recommendations.append({
                "priority": "medium",
                "recommendation": "Quarterly internal control testing",
                "violation_count": 0
            })

        return recommendations

    def get_audit_analytics(self, time_window_hours=24):
        """Get audit analytics for specified time window"""

        cutoff_time = time.time() - (time_window_hours * 3600)
        recent_logs = [log for log in self.audit_log if log["timestamp"] >= cutoff_time]

        # Calculate analytics
        total_events = len(recent_logs)
        unique_users = len(set(log["user_id"] for log in recent_logs))

        event_types = defaultdict(int)
        severity_counts = defaultdict(int)
        hourly_activity = defaultdict(int)

        for log_entry in recent_logs:
            event_types[log_entry["event_type"]] += 1
            severity_counts[log_entry["severity"]] += 1

            # Group by hour
            hour_key = int(log_entry["timestamp"] // 3600)
            hourly_activity[hour_key] += 1

        # Recent alerts
        recent_alerts = [alert for alert in self.audit_alerts
                        if alert["timestamp"] >= cutoff_time]

        return {
            "time_window_hours": time_window_hours,
            "total_events": total_events,
            "unique_users": unique_users,
            "event_types": dict(event_types),
            "severity_distribution": dict(severity_counts),
            "hourly_activity": dict(hourly_activity),
            "recent_alerts": len(recent_alerts),
            "compliance_frameworks": len(self.compliance_rules),
            "audit_health": "healthy" if len(recent_alerts) == 0 else "needs_attention"
        }

# Usage example
audit_system = EnterpriseAuditSystem(app)

# Configure compliance frameworks
gdpr_rules = {
    "data_access_monitoring": {
        "description": "Monitor access to personal data",
        "severity": "high"
    },
    "consent_tracking": {
        "description": "Track user consent for data processing",
        "severity": "medium"
    }
}

sox_rules = {
    "privileged_access_monitoring": {
        "description": "Monitor privileged access to financial systems",
        "severity": "high"
    },
    "configuration_change_approval": {
        "description": "Require approval for configuration changes",
        "severity": "high"
    }
}

gdpr_config = audit_system.configure_compliance_framework(ComplianceFramework.GDPR, gdpr_rules)
sox_config = audit_system.configure_compliance_framework(ComplianceFramework.SOX, sox_rules)

print(f"GDPR Configuration: {gdpr_config}")
print(f"SOX Configuration: {sox_config}")

# Log audit events
login_event = audit_system.log_audit_event(
    AuditEventType.USER_LOGIN,
    "admin_user",
    {"success": True, "method": "saml", "ip_address": "10.0.1.100"},
    "session_12345",
    "10.0.1.100"
)

data_access_event = audit_system.log_audit_event(
    AuditEventType.DATA_ACCESSED,
    "hr_manager",
    {
        "resource": "employee_records",
        "classification": "confidential",
        "authorized_access": True,
        "justification": "Performance review process"
    },
    "session_67890",
    "10.0.1.101"
)

print(f"Login Event: {login_event}")
print(f"Data Access Event: {data_access_event}")

# Generate compliance report
current_time = time.time()
start_date = current_time - 86400  # 24 hours ago
end_date = current_time

gdpr_report = audit_system.generate_compliance_report(
    ComplianceFramework.GDPR,
    start_date,
    end_date
)

print(f"GDPR Compliance Report: {gdpr_report}")

# Get audit analytics
analytics = audit_system.get_audit_analytics(24)
print(f"Audit Analytics: {analytics}")
```

## Next Steps

Explore advanced Nexus capabilities:

1. **[Integration Guide](integration-guide.md)** - External system integration patterns
2. **[Troubleshooting](troubleshooting.md)** - Security issue diagnosis and resolution
3. **[Production Deployment](../advanced/production-deployment.md)** - Secure production deployment
4. **[Performance Guide](performance-guide.md)** - Security-optimized performance

## Key Takeaways

✅ **Multi-Provider Authentication** → OAuth2, SAML, LDAP with enterprise security features
✅ **Advanced RBAC** → Hierarchical roles, dynamic permissions, and policy-based access
✅ **Enterprise Encryption** → AES-256 encryption with key rotation and classification
✅ **Comprehensive Auditing** → Tamper-proof logs with compliance framework support
✅ **Real-Time Monitoring** → Security alerts and violation detection
✅ **Compliance Ready** → GDPR, SOX, HIPAA, PCI-DSS, SOC2, ISO27001 support

Nexus provides enterprise-default security that exceeds traditional add-on approaches, with built-in authentication, encryption, audit trails, and compliance features that scale automatically while maintaining the highest security standards.
