#!/usr/bin/env python3
"""
End-to-end test of JWT authentication and tenant isolation for Kailash Workflow Studio.

This example demonstrates:
1. User registration and login
2. JWT token generation and validation
3. Tenant isolation of workflows
4. API key authentication
5. Permission-based access control

Prerequisites:
    pip install requests

Usage:
    # Start the API server first:
    python -m kailash.api.studio_secure

    # Then run this test:
    python test_jwt_auth.py
"""

import time
from typing import Any

import requests

# API base URL
BASE_URL = "http://localhost:8000"


class StudioAPIClient:
    """Client for testing the secure Workflow Studio API"""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.tenant_id: str | None = None
        self.user_email: str | None = None

    def register(self, email: str, username: str, password: str) -> dict[str, Any]:
        """Register a new user"""
        response = requests.post(
            f"{self.base_url}/api/auth/register",
            json={"email": email, "username": username, "password": password},
        )
        response.raise_for_status()

        data = response.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]

        return data

    def login(self, email: str, password: str) -> dict[str, Any]:
        """Login with existing credentials"""
        response = requests.post(
            f"{self.base_url}/api/auth/login",
            json={"email": email, "password": password},
        )
        response.raise_for_status()

        data = response.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.user_email = email

        return data

    def refresh_access_token(self) -> dict[str, Any]:
        """Refresh the access token using refresh token"""
        response = requests.post(
            f"{self.base_url}/api/auth/refresh",
            json={"refresh_token": self.refresh_token},
        )
        response.raise_for_status()

        data = response.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]

        return data

    def get_current_user(self) -> dict[str, Any]:
        """Get current user information"""
        response = requests.get(
            f"{self.base_url}/api/auth/me", headers=self._auth_headers()
        )
        response.raise_for_status()

        data = response.json()
        self.tenant_id = data["tenant"]["id"]

        return data

    def create_workflow(
        self, name: str, description: str, definition: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a new workflow"""
        response = requests.post(
            f"{self.base_url}/api/workflows",
            headers=self._auth_headers(),
            json={"name": name, "description": description, "definition": definition},
        )
        response.raise_for_status()
        return response.json()

    def list_workflows(self) -> list[dict[str, Any]]:
        """List workflows for the current tenant"""
        response = requests.get(
            f"{self.base_url}/api/workflows", headers=self._auth_headers()
        )
        response.raise_for_status()
        return response.json()

    def execute_workflow(
        self, workflow_id: str, parameters: dict[str, Any] = None
    ) -> dict[str, Any]:
        """Execute a workflow"""
        response = requests.post(
            f"{self.base_url}/api/workflows/{workflow_id}/execute",
            headers=self._auth_headers(),
            json={"parameters": parameters or {}},
        )
        response.raise_for_status()
        return response.json()

    def get_execution_status(self, execution_id: str) -> dict[str, Any]:
        """Get execution status"""
        response = requests.get(
            f"{self.base_url}/api/executions/{execution_id}",
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        return response.json()

    def create_api_key(self, name: str, scopes: list[str] = None) -> dict[str, Any]:
        """Create an API key"""
        response = requests.post(
            f"{self.base_url}/api/apikeys",
            headers=self._auth_headers(),
            json={
                "name": name,
                "scopes": scopes or ["read:workflows", "execute:workflows"],
            },
        )
        response.raise_for_status()
        return response.json()

    def list_api_keys(self) -> list[dict[str, Any]]:
        """List API keys"""
        response = requests.get(
            f"{self.base_url}/api/apikeys", headers=self._auth_headers()
        )
        response.raise_for_status()
        return response.json()

    def create_custom_node(self, node_config: dict[str, Any]) -> dict[str, Any]:
        """Create a custom node"""
        response = requests.post(
            f"{self.base_url}/api/custom-nodes",
            headers=self._auth_headers(),
            json=node_config,
        )
        response.raise_for_status()
        return response.json()

    def _auth_headers(self) -> dict[str, str]:
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }


def test_user_registration_and_login():
    """Test user registration and login flow"""
    print("\n=== Testing User Registration and Login ===")

    client = StudioAPIClient()

    # Register new user
    print("1. Registering new user...")
    import uuid

    unique_id = str(uuid.uuid4())[:8]
    register_data = client.register(
        email=f"test_{unique_id}@example.com",
        username=f"testuser_{unique_id}",
        password="SecurePassword123!",
    )
    print(
        f"   ✓ Registration successful, got access token: {register_data['access_token'][:20]}..."
    )

    # Get user info
    print("2. Getting current user info...")
    user_info = client.get_current_user()
    print(f"   ✓ User: {user_info['user']['email']}")
    print(
        f"   ✓ Tenant: {user_info['tenant']['name']} (ID: {user_info['tenant']['id']})"
    )

    # Test login
    print("3. Testing login with same credentials...")
    login_data = client.login(
        email=f"test_{unique_id}@example.com", password="SecurePassword123!"
    )
    print(
        f"   ✓ Login successful, got new access token: {login_data['access_token'][:20]}..."
    )

    # Test token refresh
    print("4. Testing token refresh...")
    refresh_data = client.refresh_access_token()
    print(
        f"   ✓ Token refresh successful, got new access token: {refresh_data['access_token'][:20]}..."
    )

    return client


def test_workflow_tenant_isolation():
    """Test that workflows are isolated between tenants"""
    print("\n=== Testing Workflow Tenant Isolation ===")

    # Create two users in different tenants
    print("1. Creating User A...")
    client_a = StudioAPIClient()
    import uuid

    unique_id_a = str(uuid.uuid4())[:8]
    client_a.register(
        email=f"user_a_{unique_id_a}@example.com",
        username=f"user_a_{unique_id_a}",
        password="Password123!",
    )
    user_a_info = client_a.get_current_user()
    tenant_a_id = user_a_info["tenant"]["id"]
    print(f"   ✓ User A in tenant: {tenant_a_id}")

    print("2. Creating User B...")
    client_b = StudioAPIClient()
    unique_id_b = str(uuid.uuid4())[:8]
    client_b.register(
        email=f"user_b_{unique_id_b}@example.com",
        username=f"user_b_{unique_id_b}",
        password="Password123!",
    )
    user_b_info = client_b.get_current_user()
    tenant_b_id = user_b_info["tenant"]["id"]
    print(f"   ✓ User B in tenant: {tenant_b_id}")

    # Verify different tenants
    assert tenant_a_id != tenant_b_id, "Users should be in different tenants"
    print("   ✓ Users are in different tenants")

    # User A creates a workflow
    print("3. User A creates a workflow...")
    workflow_a = client_a.create_workflow(
        name="User A's Private Workflow",
        description="This should only be visible to User A",
        definition={
            "nodes": {
                "input": {"type": "input", "config": {}},
                "output": {"type": "output", "config": {}},
            },
            "edges": [{"source": "input", "target": "output"}],
        },
    )
    print(f"   ✓ Created workflow: {workflow_a['id']}")

    # User B creates a workflow
    print("4. User B creates a workflow...")
    workflow_b = client_b.create_workflow(
        name="User B's Private Workflow",
        description="This should only be visible to User B",
        definition={
            "nodes": {
                "input": {"type": "input", "config": {}},
                "output": {"type": "output", "config": {}},
            },
            "edges": [{"source": "input", "target": "output"}],
        },
    )
    print(f"   ✓ Created workflow: {workflow_b['id']}")

    # User A lists workflows (should only see their own)
    print("5. User A lists workflows...")
    workflows_a = client_a.list_workflows()
    print(f"   ✓ User A sees {len(workflows_a)} workflow(s)")
    assert len(workflows_a) == 1, "User A should only see their own workflow"
    assert (
        workflows_a[0]["id"] == workflow_a["id"]
    ), "User A should see their own workflow"

    # User B lists workflows (should only see their own)
    print("6. User B lists workflows...")
    workflows_b = client_b.list_workflows()
    print(f"   ✓ User B sees {len(workflows_b)} workflow(s)")
    assert len(workflows_b) == 1, "User B should only see their own workflow"
    assert (
        workflows_b[0]["id"] == workflow_b["id"]
    ), "User B should see their own workflow"

    # User A tries to access User B's workflow (should fail)
    print("7. User A tries to access User B's workflow...")
    try:
        response = requests.get(
            f"{BASE_URL}/api/workflows/{workflow_b['id']}",
            headers={"Authorization": f"Bearer {client_a.access_token}"},
        )
        if response.status_code == 404:
            print("   ✓ Access denied as expected (404 Not Found)")
        else:
            print(f"   ✗ Unexpected response: {response.status_code}")
    except Exception as e:
        print(f"   ✗ Error: {e}")

    return client_a, client_b


def test_api_key_authentication():
    """Test API key authentication"""
    print("\n=== Testing API Key Authentication ===")

    # Create user and login
    client = StudioAPIClient()
    import uuid

    unique_id = str(uuid.uuid4())[:8]
    client.register(
        email=f"apikey_test_{unique_id}@example.com",
        username=f"apikey_test_{unique_id}",
        password="Password123!",
    )
    client.get_current_user()

    # Create API key
    print("1. Creating API key...")
    api_key_data = client.create_api_key(
        name="Test API Key", scopes=["read:workflows", "execute:workflows"]
    )
    api_key = api_key_data["key"]
    print(f"   ✓ Created API key: {api_key[:20]}...")

    # List API keys
    print("2. Listing API keys...")
    api_keys = client.list_api_keys()
    print(f"   ✓ Found {len(api_keys)} API key(s)")

    # Use API key to access workflows
    print("3. Using API key to list workflows...")
    response = requests.get(f"{BASE_URL}/api/workflows", headers={"X-API-Key": api_key})

    if response.status_code == 200:
        print("   ✓ API key authentication successful")
        workflows = response.json()
        print(f"   ✓ Retrieved {len(workflows)} workflow(s)")
    else:
        print(f"   ✗ API key authentication failed: {response.status_code}")

    return client


def test_custom_node_creation():
    """Test custom node creation with tenant isolation"""
    print("\n=== Testing Custom Node Creation ===")

    client = StudioAPIClient()
    import uuid

    unique_id = str(uuid.uuid4())[:8]
    client.register(
        email=f"node_test_{unique_id}@example.com",
        username=f"node_test_{unique_id}",
        password="Password123!",
    )
    client.get_current_user()

    # Create a Python-based custom node
    print("1. Creating Python-based custom node...")
    python_node = client.create_custom_node(
        {
            "name": "DataMultiplier",
            "category": "custom",
            "description": "Multiplies input data by a factor",
            "icon": "calculator",
            "color": "#4CAF50",
            "parameters": [
                {
                    "name": "factor",
                    "type": "float",
                    "required": True,
                    "description": "Multiplication factor",
                    "default": 2.0,
                }
            ],
            "inputs": [{"name": "value", "type": "float", "required": True}],
            "outputs": [{"name": "result", "type": "float"}],
            "implementation_type": "python",
            "implementation": {
                "code": """
def run(value, factor=2.0):
    return {"result": value * factor}
""",
                "inputs": ["value"],
                "outputs": ["result"],
            },
        }
    )
    print(f"   ✓ Created custom node: {python_node['id']}")

    # Create an API-based custom node
    print("2. Creating API-based custom node...")
    api_node = client.create_custom_node(
        {
            "name": "WeatherFetcher",
            "category": "custom",
            "description": "Fetches weather data from API",
            "icon": "cloud",
            "color": "#2196F3",
            "parameters": [
                {
                    "name": "city",
                    "type": "string",
                    "required": True,
                    "description": "City name",
                }
            ],
            "inputs": [],
            "outputs": [{"name": "weather", "type": "object"}],
            "implementation_type": "api",
            "implementation": {
                "api": {
                    "url": "https://api.openweathermap.org/data/2.5/weather",
                    "method": "GET",
                    "headers": {"Content-Type": "application/json"},
                    "timeout": 30,
                }
            },
        }
    )
    print(f"   ✓ Created custom node: {api_node['id']}")

    # Test the Python custom node
    print("3. Testing Python custom node...")
    try:
        test_result = requests.post(
            f"{BASE_URL}/api/custom-nodes/{python_node['id']}/test",
            headers={"Authorization": f"Bearer {client.access_token}"},
            json={"value": 10.0, "factor": 3.0},
        )
        if test_result.status_code == 200:
            result_data = test_result.json()
            print(f"   ✓ Test result: {result_data}")
        else:
            print(f"   ✗ Test failed: {test_result.status_code}")
    except Exception as e:
        print(f"   ✗ Error testing node: {e}")

    return client


def test_workflow_execution_with_auth():
    """Test workflow execution with authentication"""
    print("\n=== Testing Workflow Execution with Auth ===")

    client = StudioAPIClient()
    import uuid

    unique_id = str(uuid.uuid4())[:8]
    client.register(
        email=f"exec_test_{unique_id}@example.com",
        username=f"exec_test_{unique_id}",
        password="Password123!",
    )
    client.get_current_user()

    # Create a simple workflow
    print("1. Creating workflow...")
    workflow = client.create_workflow(
        name="Test Execution Workflow",
        description="Simple workflow for testing execution",
        definition={
            "nodes": {
                "input": {"type": "kailash.nodes.base.InputNode", "config": {}},
                "multiply": {
                    "type": "kailash.nodes.transform.processors.DataTransformer",
                    "config": {
                        "transform_type": "custom",
                        "custom_function": "lambda x: x * 2",
                    },
                },
                "output": {"type": "kailash.nodes.base.OutputNode", "config": {}},
            },
            "edges": [
                {"source": "input", "target": "multiply"},
                {"source": "multiply", "target": "output"},
            ],
        },
    )
    print(f"   ✓ Created workflow: {workflow['id']}")

    # Execute workflow
    print("2. Executing workflow...")
    execution = client.execute_workflow(workflow["id"], parameters={"input_data": 42})
    print(f"   ✓ Started execution: {execution['id']}")
    print(f"   Status: {execution['status']}")

    # Poll for completion
    print("3. Waiting for execution to complete...")
    max_attempts = 10
    for i in range(max_attempts):
        time.sleep(1)
        status = client.get_execution_status(execution["id"])
        print(f"   Status: {status['status']}")

        if status["status"] == "completed":
            print("   ✓ Execution completed successfully")
            print(f"   Result: {status.get('result', 'No result')}")
            break
        elif status["status"] == "failed":
            print(f"   ✗ Execution failed: {status.get('error', 'Unknown error')}")
            break

    return client


def main():
    """Run all tests"""
    print("Kailash Workflow Studio - JWT Authentication & Tenant Isolation Tests")
    print("=" * 70)

    try:
        # Check if API is running
        print("\nChecking API health...")
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print("✓ API is running")
        else:
            print(
                "✗ API is not responding. Please start it with: python -m kailash.api.studio_secure"
            )
            return
    except requests.exceptions.ConnectionError:
        print(
            "✗ Cannot connect to API. Please start it with: python -m kailash.api.studio_secure"
        )
        return

    # Run tests
    try:
        # Test 1: User registration and login
        test_user_registration_and_login()

        # Test 2: Workflow tenant isolation
        test_workflow_tenant_isolation()

        # Test 3: API key authentication
        test_api_key_authentication()

        # Test 4: Custom node creation
        test_custom_node_creation()

        # Test 5: Workflow execution
        test_workflow_execution_with_auth()

        print("\n" + "=" * 70)
        print("✓ All tests completed successfully!")

    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
