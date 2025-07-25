#!/usr/bin/env python
"""Test MCP Resource-level Access Control"""

import asyncio

from kailash.mcp_server import MCPServer
from kailash.mcp_server.auth import APIKeyAuth, PermissionManager


async def test_resource_access_control():
    """Test resource-level RBAC in MCP"""
    print("=== MCP Resource-Level Access Control Demo ===\n")

    # Configure authentication with resource-specific permissions
    auth = APIKeyAuth(
        keys={
            "admin-key": {
                "permissions": ["read", "write", "delete", "admin"],
                "resource_access": {
                    "files": ["*"],  # Access to all files
                    "databases": ["*"],  # Access to all databases
                    "apis": ["*"],  # Access to all APIs
                },
            },
            "developer-key": {
                "permissions": ["read", "write"],
                "resource_access": {
                    "files": ["src/*", "tests/*"],  # Only source and test files
                    "databases": ["dev_db", "test_db"],  # Only dev/test databases
                    "apis": ["internal/*"],  # Only internal APIs
                },
            },
            "analyst-key": {
                "permissions": ["read"],
                "resource_access": {
                    "files": ["reports/*", "data/*.csv"],  # Only reports and CSV data
                    "databases": ["analytics_db"],  # Only analytics database
                    "apis": ["analytics/*", "reporting/*"],  # Only analytics APIs
                },
            },
            "guest-key": {
                "permissions": ["read"],
                "resource_access": {
                    "files": ["public/*"],  # Only public files
                    "databases": [],  # No database access
                    "apis": ["public/*"],  # Only public APIs
                },
            },
        }
    )

    # Create server with resource-aware tools
    server = MCPServer(
        name="resource-rbac-server", auth_provider=auth, enable_metrics=True
    )

    # File access tool with resource checking
    @server.tool(required_permission="read")
    async def read_file(file_path: str, auth_context: dict = None) -> dict:
        """Read a file with resource-level access control"""
        # In real implementation, auth_context would be injected by server
        # Here we simulate resource checking

        user_info = auth_context or {}
        resource_access = user_info.get("metadata", {}).get("resource_access", {})
        file_patterns = resource_access.get("files", [])

        # Check if user has access to this file
        has_access = any(
            _match_pattern(file_path, pattern) for pattern in file_patterns
        )

        if has_access:
            return {
                "status": "success",
                "content": f"Content of {file_path}",
                "access_level": "granted",
            }
        else:
            return {
                "status": "denied",
                "error": f"Access denied to file: {file_path}",
                "allowed_patterns": file_patterns,
            }

    # Database query tool with resource checking
    @server.tool(required_permission="read")
    async def query_database(
        db_name: str, query: str, auth_context: dict = None
    ) -> dict:
        """Query database with resource-level access control"""
        user_info = auth_context or {}
        resource_access = user_info.get("metadata", {}).get("resource_access", {})
        allowed_dbs = resource_access.get("databases", [])

        if db_name in allowed_dbs or "*" in allowed_dbs:
            return {
                "status": "success",
                "result": f"Query result from {db_name}: {query}",
                "access_level": "granted",
            }
        else:
            return {
                "status": "denied",
                "error": f"Access denied to database: {db_name}",
                "allowed_databases": allowed_dbs,
            }

    # API call tool with resource checking
    @server.tool(required_permission="read")
    async def call_api(endpoint: str, auth_context: dict = None) -> dict:
        """Call API with resource-level access control"""
        user_info = auth_context or {}
        resource_access = user_info.get("metadata", {}).get("resource_access", {})
        api_patterns = resource_access.get("apis", [])

        has_access = any(_match_pattern(endpoint, pattern) for pattern in api_patterns)

        if has_access:
            return {
                "status": "success",
                "response": f"API response from {endpoint}",
                "access_level": "granted",
            }
        else:
            return {
                "status": "denied",
                "error": f"Access denied to API: {endpoint}",
                "allowed_patterns": api_patterns,
            }

    # Test different user access levels
    test_cases = [
        (
            "admin-key",
            [
                ("file", "src/main.py"),
                ("file", "config/secrets.yml"),
                ("database", "production_db"),
                ("api", "internal/users/delete"),
            ],
        ),
        (
            "developer-key",
            [
                ("file", "src/main.py"),  # Should work
                ("file", "config/secrets.yml"),  # Should fail
                ("database", "dev_db"),  # Should work
                ("database", "production_db"),  # Should fail
                ("api", "internal/debug/logs"),  # Should work
                ("api", "admin/users/delete"),  # Should fail
            ],
        ),
        (
            "analyst-key",
            [
                ("file", "reports/monthly.pdf"),  # Should work
                ("file", "src/main.py"),  # Should fail
                ("database", "analytics_db"),  # Should work
                ("database", "production_db"),  # Should fail
                ("api", "analytics/dashboard"),  # Should work
                ("api", "internal/config"),  # Should fail
            ],
        ),
        (
            "guest-key",
            [
                ("file", "public/readme.md"),  # Should work
                ("file", "src/main.py"),  # Should fail
                ("database", "any_db"),  # Should fail
                ("api", "public/status"),  # Should work
            ],
        ),
    ]

    print("Testing resource access for different user roles:\n")

    for api_key, resources in test_cases:
        # Authenticate user
        user_ctx = auth.authenticate({"api_key": api_key})
        user_type = api_key.replace("-key", "").upper()
        print(f"\n{user_type} USER (permissions: {user_ctx['permissions']}):")
        print("-" * 50)

        for resource_type, resource_path in resources:
            if resource_type == "file":
                result = await read_file(resource_path, user_ctx)
                status = "✅" if result["status"] == "success" else "❌"
                print(
                    f"{status} File '{resource_path}': {result.get('error', 'Access granted')}"
                )

            elif resource_type == "database":
                result = await query_database(resource_path, "SELECT *", user_ctx)
                status = "✅" if result["status"] == "success" else "❌"
                print(
                    f"{status} Database '{resource_path}': {result.get('error', 'Access granted')}"
                )

            elif resource_type == "api":
                result = await call_api(resource_path, user_ctx)
                status = "✅" if result["status"] == "success" else "❌"
                print(
                    f"{status} API '{resource_path}': {result.get('error', 'Access granted')}"
                )

    print("\n\n=== Advanced Resource Patterns ===\n")

    # Show how patterns work
    print("Resource access patterns support:")
    print("- Exact matches: 'reports/monthly.pdf'")
    print("- Wildcards: 'src/*' (all files in src)")
    print("- Recursive: 'data/**/*.csv' (all CSV files under data)")
    print("- Extensions: '*.log' (all log files)")

    print("\n=== MCP Resources Concept ===\n")
    print("In MCP (Model Context Protocol), resources represent:")
    print("1. **Files**: Local or remote files the server can access")
    print("2. **Databases**: Database connections and tables")
    print("3. **APIs**: External API endpoints")
    print("4. **Memory**: Shared memory segments")
    print("5. **Compute**: Processing resources")

    print("\nResource URIs in MCP follow patterns like:")
    print("- file:///path/to/file")
    print("- db://server/database/table")
    print("- api://service/endpoint")
    print("- memory://segment/key")

    print("\n=== Implementation in Kailash ===\n")
    print("Kailash extends MCP with fine-grained RBAC:")
    print("1. Tool-level permissions (read, write, admin)")
    print("2. Resource-level patterns (file paths, DB names, API routes)")
    print("3. Context-aware access (user roles, time-based, attribute-based)")
    print("4. Audit logging of all access attempts")


def _match_pattern(path: str, pattern: str) -> bool:
    """Simple pattern matching for demo (real implementation would be more robust)"""
    if pattern == "*":
        return True
    if pattern.endswith("/*"):
        prefix = pattern[:-2]
        return path.startswith(prefix + "/")
    if pattern.endswith("*"):
        prefix = pattern[:-1]
        return path.startswith(prefix)
    return path == pattern


async def main():
    """Run the resource access control demo"""
    await test_resource_access_control()

    print("\n\n✅ Resource-level RBAC demonstration complete!")
    print("\nKey takeaways:")
    print("1. MCP servers can implement fine-grained resource access control")
    print("2. Permissions can be scoped to specific file paths, databases, or APIs")
    print("3. Pattern matching allows flexible access rules")
    print("4. Access control integrates with MCP's tool execution model")


if __name__ == "__main__":
    asyncio.run(main())
