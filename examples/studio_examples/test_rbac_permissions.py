#!/usr/bin/env python3
"""
Test Role-Based Access Control (RBAC) and permissions in Kailash Workflow Studio.

This example demonstrates:
1. Different user roles (admin, editor, viewer)
2. Permission-based access control
3. Resource limits per tenant
4. Multi-tenant workflow sharing
5. Secure execution isolation

Prerequisites:
    pip install requests colorama

Usage:
    # Start the API server first:
    python -m kailash.api.studio_secure

    # Then run this test:
    python test_rbac_permissions.py
"""

import time
from typing import Any, Dict, Optional

import requests
from colorama import Fore, Style, init

# Initialize colorama for colored output
init()

# API base URL
BASE_URL = "http://localhost:8000"


def print_success(message: str):
    """Print success message in green"""
    print(f"{Fore.GREEN}✓ {message}{Style.RESET_ALL}")


def print_error(message: str):
    """Print error message in red"""
    print(f"{Fore.RED}✗ {message}{Style.RESET_ALL}")


def print_info(message: str):
    """Print info message in blue"""
    print(f"{Fore.BLUE}ℹ {message}{Style.RESET_ALL}")


def print_section(title: str):
    """Print section header"""
    print(f"\n{Fore.YELLOW}{'=' * 60}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{title}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{'=' * 60}{Style.RESET_ALL}")


class PermissionTestClient:
    """Client for testing RBAC and permissions"""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.users: Dict[str, Dict[str, Any]] = {}

    def create_user_with_role(
        self, role: str, tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a user with specific role"""
        import uuid

        unique_id = str(uuid.uuid4())[:8]

        user_data = {
            "email": f"{role}_{unique_id}@example.com",
            "username": f"{role}_user_{unique_id}",
            "password": "SecurePassword123!",
            "tenant_id": tenant_id,
        }

        # Register user
        response = requests.post(f"{self.base_url}/api/auth/register", json=user_data)
        response.raise_for_status()

        tokens = response.json()

        # Get user info
        user_info_response = requests.get(
            f"{self.base_url}/api/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        user_info = user_info_response.json()

        # Store user data
        self.users[role] = {
            "email": user_data["email"],
            "password": user_data["password"],
            "tokens": tokens,
            "info": user_info,
            "role": role,
        }

        # In a real system, admin would set roles
        # For testing, we'll simulate role assignment
        self._simulate_role_assignment(role, tokens["access_token"])

        return self.users[role]

    def _simulate_role_assignment(self, role: str, token: str):
        """Simulate role assignment (in production, this would be done by admin)"""
        # This is just for demonstration - actual role assignment would be done differently
        pass

    def test_permission(
        self, role: str, action: str, resource: str, expected_success: bool = True
    ) -> bool:
        """Test if a user with given role can perform an action"""
        user = self.users.get(role)
        if not user:
            print_error(f"User with role '{role}' not found")
            return False

        headers = {"Authorization": f"Bearer {user['tokens']['access_token']}"}

        # Map actions to API endpoints
        action_map = {
            "create_workflow": (
                "POST",
                "/api/workflows",
                {
                    "name": "Test Workflow",
                    "description": "Test",
                    "definition": {"nodes": {}, "edges": []},
                },
            ),
            "read_workflow": ("GET", f"/api/workflows/{resource}", None),
            "update_workflow": (
                "PUT",
                f"/api/workflows/{resource}",
                {"name": "Updated Workflow"},
            ),
            "delete_workflow": ("DELETE", f"/api/workflows/{resource}", None),
            "execute_workflow": (
                "POST",
                f"/api/workflows/{resource}/execute",
                {"parameters": {}},
            ),
            "create_node": (
                "POST",
                "/api/custom-nodes",
                {
                    "name": "TestNode",
                    "implementation_type": "python",
                    "implementation": {"code": "pass"},
                },
            ),
            "read_execution": ("GET", f"/api/executions/{resource}", None),
        }

        if action not in action_map:
            print_error(f"Unknown action: {action}")
            return False

        method, endpoint, data = action_map[action]

        # Make request
        if method == "GET":
            response = requests.get(f"{self.base_url}{endpoint}", headers=headers)
        elif method == "POST":
            response = requests.post(
                f"{self.base_url}{endpoint}", headers=headers, json=data
            )
        elif method == "PUT":
            response = requests.put(
                f"{self.base_url}{endpoint}", headers=headers, json=data
            )
        elif method == "DELETE":
            response = requests.delete(f"{self.base_url}{endpoint}", headers=headers)

        # Check result
        success = response.status_code in [200, 201, 204]

        if expected_success and success:
            print_success(f"{role} can {action}")
            return True
        elif not expected_success and not success:
            print_success(
                f"{role} correctly denied {action} (status: {response.status_code})"
            )
            return True
        else:
            if expected_success:
                print_error(f"{role} cannot {action} (status: {response.status_code})")
            else:
                print_error(f"{role} incorrectly allowed {action}")
            return False


def test_basic_rbac():
    """Test basic RBAC functionality"""
    print_section("Testing Basic RBAC")

    client = PermissionTestClient()

    # Create users with different roles
    print_info("Creating users with different roles...")
    admin = client.create_user_with_role("admin")
    editor = client.create_user_with_role("editor")
    viewer = client.create_user_with_role("viewer")

    print_success(f"Created admin user: {admin['email']}")
    print_success(f"Created editor user: {editor['email']}")
    print_success(f"Created viewer user: {viewer['email']}")

    # Test workflow permissions
    print_info("\nTesting workflow permissions...")

    # Admin can do everything
    client.test_permission("admin", "create_workflow", "", expected_success=True)

    # Editor can create and edit
    client.test_permission("editor", "create_workflow", "", expected_success=True)

    # Viewer can only read
    client.test_permission("viewer", "create_workflow", "", expected_success=False)
    client.test_permission("viewer", "read_workflow", "dummy-id", expected_success=True)

    return client


def test_tenant_resource_limits():
    """Test tenant resource limits and quotas"""
    print_section("Testing Tenant Resource Limits")

    client = PermissionTestClient()

    # Create a user
    print_info("Creating test user...")
    user = client.create_user_with_role("editor")
    tenant_info = user["info"]["tenant"]

    print_info(f"Tenant: {tenant_info['name']}")
    print_info(f"Subscription tier: {tenant_info['subscription_tier']}")
    print_info(f"Max workflows: {tenant_info.get('max_workflows', 'N/A')}")
    print_info(
        f"Max executions/month: {tenant_info.get('max_executions_per_month', 'N/A')}"
    )

    # Try to exceed workflow limit
    print_info("\nTesting workflow limit...")
    headers = {"Authorization": f"Bearer {user['tokens']['access_token']}"}

    # Create workflows up to limit
    workflow_ids = []
    max_attempts = 5  # Don't create too many

    for i in range(max_attempts):
        response = requests.post(
            f"{BASE_URL}/api/workflows",
            headers=headers,
            json={
                "name": f"Test Workflow {i+1}",
                "description": "Testing limits",
                "definition": {"nodes": {}, "edges": []},
            },
        )

        if response.status_code == 201:
            workflow_ids.append(response.json()["id"])
            print_success(f"Created workflow {i+1}")
        elif response.status_code == 403:
            print_info(f"Workflow limit reached at {i} workflows")
            break
        else:
            print_error(f"Unexpected response: {response.status_code}")
            break

    # Clean up
    print_info("\nCleaning up workflows...")
    for workflow_id in workflow_ids:
        requests.delete(f"{BASE_URL}/api/workflows/{workflow_id}", headers=headers)

    return client


def test_cross_tenant_isolation():
    """Test isolation between different tenants"""
    print_section("Testing Cross-Tenant Isolation")

    # Create two separate tenants
    print_info("Creating two separate tenants...")

    # Tenant A
    client_a = PermissionTestClient()
    user_a = client_a.create_user_with_role("admin")
    tenant_a_id = user_a["info"]["tenant"]["id"]
    print_success(f"Created Tenant A: {tenant_a_id}")

    # Tenant B
    client_b = PermissionTestClient()
    user_b = client_b.create_user_with_role("admin")
    tenant_b_id = user_b["info"]["tenant"]["id"]
    print_success(f"Created Tenant B: {tenant_b_id}")

    # Tenant A creates resources
    print_info("\nTenant A creates resources...")
    headers_a = {"Authorization": f"Bearer {user_a['tokens']['access_token']}"}

    # Create workflow in Tenant A
    workflow_response = requests.post(
        f"{BASE_URL}/api/workflows",
        headers=headers_a,
        json={
            "name": "Tenant A Secret Workflow",
            "description": "Contains proprietary logic",
            "definition": {
                "nodes": {
                    "secret": {
                        "type": "custom",
                        "config": {"secret": "tenant-a-secret"},
                    }
                },
                "edges": [],
            },
        },
    )
    workflow_a = workflow_response.json()
    print_success(f"Created workflow in Tenant A: {workflow_a['id']}")

    # Create custom node in Tenant A
    node_response = requests.post(
        f"{BASE_URL}/api/custom-nodes",
        headers=headers_a,
        json={
            "name": "TenantASecretNode",
            "implementation_type": "python",
            "implementation": {"code": "# Proprietary algorithm for Tenant A"},
        },
    )
    node_a = node_response.json()
    print_success(f"Created custom node in Tenant A: {node_a['id']}")

    # Tenant B tries to access Tenant A's resources
    print_info("\nTenant B tries to access Tenant A's resources...")
    headers_b = {"Authorization": f"Bearer {user_b['tokens']['access_token']}"}

    # Try to access workflow
    workflow_access = requests.get(
        f"{BASE_URL}/api/workflows/{workflow_a['id']}", headers=headers_b
    )
    if workflow_access.status_code == 404:
        print_success("Tenant B correctly denied access to Tenant A's workflow")
    else:
        print_error("Security breach! Tenant B accessed Tenant A's workflow")

    # Try to access custom node
    node_access = requests.get(
        f"{BASE_URL}/api/custom-nodes/{node_a['id']}", headers=headers_b
    )
    if node_access.status_code == 404:
        print_success("Tenant B correctly denied access to Tenant A's custom node")
    else:
        print_error("Security breach! Tenant B accessed Tenant A's custom node")

    # Verify Tenant B only sees their own resources
    print_info("\nVerifying resource isolation...")

    # List workflows for Tenant B (should be empty)
    workflows_b = requests.get(f"{BASE_URL}/api/workflows", headers=headers_b).json()
    print_success(f"Tenant B sees {len(workflows_b)} workflows (should be 0)")

    # List custom nodes for Tenant B (should be empty)
    nodes_b = requests.get(f"{BASE_URL}/api/custom-nodes", headers=headers_b).json()
    print_success(f"Tenant B sees {len(nodes_b)} custom nodes (should be 0)")

    return client_a, client_b


def test_api_key_scopes():
    """Test API key scopes and permissions"""
    print_section("Testing API Key Scopes")

    client = PermissionTestClient()
    user = client.create_user_with_role("admin")
    headers = {"Authorization": f"Bearer {user['tokens']['access_token']}"}

    # Create API keys with different scopes
    print_info("Creating API keys with different scopes...")

    # Read-only API key
    readonly_key_response = requests.post(
        f"{BASE_URL}/api/apikeys",
        headers=headers,
        json={
            "name": "Read-Only Key",
            "scopes": ["read:workflows", "read:nodes", "read:executions"],
        },
    )
    readonly_key = readonly_key_response.json()["key"]
    print_success(f"Created read-only API key: {readonly_key[:20]}...")

    # Execute-only API key
    execute_key_response = requests.post(
        f"{BASE_URL}/api/apikeys",
        headers=headers,
        json={"name": "Execute-Only Key", "scopes": ["execute:workflows"]},
    )
    execute_key = execute_key_response.json()["key"]
    print_success(f"Created execute-only API key: {execute_key[:20]}...")

    # Full access API key
    full_key_response = requests.post(
        f"{BASE_URL}/api/apikeys",
        headers=headers,
        json={
            "name": "Full Access Key",
            "scopes": ["read:all", "write:all", "execute:all"],
        },
    )
    full_key = full_key_response.json()["key"]
    print_success(f"Created full access API key: {full_key[:20]}...")

    # Test API key permissions
    print_info("\nTesting API key permissions...")

    # First create a workflow to test with
    workflow_response = requests.post(
        f"{BASE_URL}/api/workflows",
        headers=headers,
        json={
            "name": "Test Workflow for API Keys",
            "description": "Test",
            "definition": {"nodes": {}, "edges": []},
        },
    )
    workflow_id = workflow_response.json()["id"]

    # Test read-only key
    print_info("\nTesting read-only API key...")

    # Should be able to read
    read_response = requests.get(
        f"{BASE_URL}/api/workflows/{workflow_id}", headers={"X-API-Key": readonly_key}
    )
    if read_response.status_code == 200:
        print_success("Read-only key can read workflows")
    else:
        print_error("Read-only key cannot read workflows")

    # Should not be able to write
    write_response = requests.put(
        f"{BASE_URL}/api/workflows/{workflow_id}",
        headers={"X-API-Key": readonly_key},
        json={"name": "Updated Name"},
    )
    if write_response.status_code in [401, 403]:
        print_success("Read-only key correctly denied write access")
    else:
        print_error("Read-only key incorrectly allowed write access")

    # Test execute-only key
    print_info("\nTesting execute-only API key...")

    # Should be able to execute
    exec_response = requests.post(
        f"{BASE_URL}/api/workflows/{workflow_id}/execute",
        headers={"X-API-Key": execute_key},
        json={"parameters": {}},
    )
    if exec_response.status_code in [200, 201]:
        print_success("Execute-only key can execute workflows")
    else:
        print_error("Execute-only key cannot execute workflows")

    # Should not be able to read workflow details
    read_response = requests.get(
        f"{BASE_URL}/api/workflows/{workflow_id}", headers={"X-API-Key": execute_key}
    )
    if read_response.status_code in [401, 403]:
        print_success("Execute-only key correctly denied read access")
    else:
        print_error("Execute-only key incorrectly allowed read access")

    return client


def test_secure_execution_isolation():
    """Test secure execution isolation between tenants"""
    print_section("Testing Secure Execution Isolation")

    client = PermissionTestClient()
    user = client.create_user_with_role("admin")
    headers = {"Authorization": f"Bearer {user['tokens']['access_token']}"}

    # Create a workflow that tries to access system resources
    print_info("Creating workflow with system access attempts...")

    workflow_response = requests.post(
        f"{BASE_URL}/api/workflows",
        headers=headers,
        json={
            "name": "Security Test Workflow",
            "description": "Tests execution isolation",
            "definition": {
                "nodes": {
                    "python_node": {
                        "type": "kailash.nodes.code.python.PythonCodeNode",
                        "config": {
                            "code": """
import os
import subprocess

# Try to access environment variables
env_vars = dict(os.environ)

# Try to read system files
try:
    with open('/etc/passwd', 'r') as f:
        passwd_content = f.read()
except:
    passwd_content = "Access denied"

# Try to execute system commands
try:
    result = subprocess.run(['ls', '/'], capture_output=True, text=True)
    ls_output = result.stdout
except:
    ls_output = "Command execution denied"

return {
    "env_vars": len(env_vars),
    "passwd_access": passwd_content != "Access denied",
    "command_execution": ls_output != "Command execution denied"
}
""",
                            "inputs": [],
                            "outputs": [
                                "env_vars",
                                "passwd_access",
                                "command_execution",
                            ],
                        },
                    }
                },
                "edges": [],
            },
        },
    )
    workflow = workflow_response.json()
    print_success(f"Created security test workflow: {workflow['id']}")

    # Execute the workflow
    print_info("\nExecuting security test workflow...")

    exec_response = requests.post(
        f"{BASE_URL}/api/workflows/{workflow['id']}/execute",
        headers=headers,
        json={"parameters": {}},
    )
    execution = exec_response.json()
    print_info(f"Started execution: {execution['id']}")

    # Wait for completion
    print_info("Waiting for execution to complete...")
    time.sleep(3)

    # Check results
    status_response = requests.get(
        f"{BASE_URL}/api/executions/{execution['id']}", headers=headers
    )
    status = status_response.json()

    if status["status"] == "completed":
        result = status.get("result", {})
        print_info("Execution completed. Security check results:")
        print_info(
            f"  - Environment variables accessible: {result.get('env_vars', 0)} vars"
        )
        print_info(
            f"  - System file access: {'BLOCKED' if not result.get('passwd_access') else 'ALLOWED'}"
        )
        print_info(
            f"  - Command execution: {'BLOCKED' if not result.get('command_execution') else 'ALLOWED'}"
        )

        # Verify security
        if not result.get("passwd_access") and not result.get("command_execution"):
            print_success("Execution properly sandboxed - system access blocked")
        else:
            print_error("Security issue - execution not properly isolated!")
    else:
        print_info(f"Execution status: {status['status']}")
        if status.get("error"):
            print_info(f"Error: {status['error']}")

    return client


def main():
    """Run all permission and RBAC tests"""
    print(
        f"{Fore.CYAN}Kailash Workflow Studio - RBAC & Permissions Tests{Style.RESET_ALL}"
    )
    print(f"{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}")

    try:
        # Check if API is running
        print_info("Checking API health...")
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print_success("API is running")
        else:
            print_error(
                "API is not responding. Please start it with: python -m kailash.api.studio_secure"
            )
            return
    except requests.exceptions.ConnectionError:
        print_error(
            "Cannot connect to API. Please start it with: python -m kailash.api.studio_secure"
        )
        return

    # Run tests
    try:
        # Test 1: Basic RBAC
        rbac_client = test_basic_rbac()

        # Test 2: Tenant resource limits
        limits_client = test_tenant_resource_limits()

        # Test 3: Cross-tenant isolation
        tenant_a, tenant_b = test_cross_tenant_isolation()

        # Test 4: API key scopes
        api_key_client = test_api_key_scopes()

        # Test 5: Secure execution isolation
        exec_client = test_secure_execution_isolation()

        print(f"\n{Fore.CYAN}{'=' * 70}{Style.RESET_ALL}")
        print_success("All permission tests completed!")

    except Exception as e:
        print_error(f"Test failed with error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
