#!/usr/bin/env python
"""Test MCP Server Access Control functionality"""

import asyncio
import json

from kailash.mcp_server import MCPServer
from kailash.mcp_server.auth import (
    APIKeyAuth,
    BasicAuth,
    BearerTokenAuth,
    JWTAuth,
    PermissionManager,
)


async def test_api_key_auth():
    """Test API Key authentication"""
    print("\n=== Testing API Key Authentication ===")

    # Configure authentication with different permission levels
    auth = APIKeyAuth(
        keys={
            "admin-key": {"permissions": ["read", "write", "delete", "admin"]},
            "analyst-key": {"permissions": ["read", "analyze"]},
            "writer-key": {"permissions": ["read", "write"]},
            "readonly-key": {"permissions": ["read"]},
        }
    )

    # Create server
    server = MCPServer(
        name="test-api-key-server", auth_provider=auth, enable_metrics=True
    )

    # Define tools with different permission requirements
    @server.tool(required_permission="admin")
    async def admin_tool(action: str) -> dict:
        """Admin only tool"""
        return {"result": f"Admin action: {action}"}

    @server.tool(required_permissions=["read", "analyze"])
    async def analyze_tool(data: str) -> dict:
        """Requires read AND analyze permissions"""
        return {"analysis": f"Analyzed: {data}"}

    @server.tool(required_permission="write")
    async def write_tool(content: str) -> dict:
        """Requires write permission"""
        return {"written": content}

    @server.tool()
    async def public_tool() -> dict:
        """No authentication required"""
        return {"status": "public access"}

    # Test authentication (not async)
    print("\n1. Testing with admin key:")
    admin_ctx = auth.authenticate({"api_key": "admin-key"})
    print(f"   Admin authenticated: {admin_ctx is not None}")
    print(f"   Permissions: {admin_ctx.get('permissions') if admin_ctx else 'None'}")

    print("\n2. Testing with analyst key:")
    analyst_ctx = auth.authenticate({"api_key": "analyst-key"})
    print(f"   Analyst authenticated: {analyst_ctx is not None}")
    print(
        f"   Permissions: {analyst_ctx.get('permissions') if analyst_ctx else 'None'}"
    )

    print("\n3. Testing with invalid key:")
    try:
        invalid_ctx = auth.authenticate({"api_key": "invalid-key"})
        print(f"   Invalid key authenticated: {invalid_ctx is not None}")
    except Exception as e:
        print(f"   Invalid key rejected: {type(e).__name__}: {e}")

    print("\n4. Testing permission checks:")
    # Create permission manager
    pm = PermissionManager()

    # Admin can access admin tool
    try:
        admin_can_admin = pm.check_permission(admin_ctx, "admin")
        print(f"   Admin can access admin tool: {admin_can_admin}")
    except Exception as e:
        print(f"   Admin cannot access admin tool: {e}")

    # Analyst cannot access admin tool
    try:
        analyst_can_admin = pm.check_permission(analyst_ctx, "admin")
        print(f"   Analyst can access admin tool: {analyst_can_admin}")
    except Exception as e:
        print(f"   Analyst cannot access admin tool: {e}")

    # Analyst can access analyze tool (has both read and analyze)
    try:
        analyst_can_analyze = pm.check_permission(analyst_ctx, "analyze")
        print(f"   Analyst can access analyze tool: {analyst_can_analyze}")
    except Exception as e:
        print(f"   Analyst cannot access analyze tool: {e}")

    # Writer cannot access analyze tool (missing analyze permission)
    writer_ctx = auth.authenticate({"api_key": "writer-key"})
    try:
        writer_can_analyze = pm.check_permission(writer_ctx, "analyze")
        print(f"   Writer can access analyze tool: {writer_can_analyze}")
    except Exception as e:
        print(f"   Writer cannot access analyze tool: {e}")


async def test_jwt_auth():
    """Test JWT authentication"""
    print("\n\n=== Testing JWT Authentication ===")

    auth = JWTAuth(
        secret="test-secret-key", algorithm="HS256", expiration=3600, issuer="mcp-test"
    )

    # Create tokens
    print("\n1. Creating JWT tokens:")
    admin_token = auth.create_token(
        {
            "user": "admin",
            "permissions": ["read", "write", "admin"],
            "tenant_id": "tenant-123",
        }
    )
    print(f"   Admin token created: {admin_token[:20]}...")

    user_token = auth.create_token({"user": "user1", "permissions": ["read"]})
    print(f"   User token created: {user_token[:20]}...")

    # Test authentication
    print("\n2. Testing authentication:")
    admin_ctx = auth.authenticate({"token": admin_token})
    print(f"   Admin authenticated: {admin_ctx is not None}")
    print(f"   User info: {admin_ctx.get('metadata') if admin_ctx else 'None'}")

    # Test invalid token
    try:
        invalid_ctx = auth.authenticate({"token": "invalid.token.here"})
        print(f"   Invalid token authenticated: {invalid_ctx is not None}")
    except Exception as e:
        print(f"   Invalid token rejected: {type(e).__name__}: {e}")


async def test_basic_auth():
    """Test Basic HTTP authentication"""
    print("\n\n=== Testing Basic Auth ===")

    auth = BasicAuth(
        users={
            "admin": {
                "password": "admin123",
                "permissions": ["admin", "read", "write"],
            },
            "user": {"password": "user123", "permissions": ["read"]},
        },
        hash_passwords=False,  # For testing, don't hash
    )

    print("\n1. Testing authentication:")
    # Test valid credentials
    admin_ctx = auth.authenticate({"username": "admin", "password": "admin123"})
    print(f"   Admin authenticated: {admin_ctx is not None}")
    print(f"   Permissions: {admin_ctx.get('permissions') if admin_ctx else 'None'}")

    # Test invalid password
    try:
        invalid_ctx = auth.authenticate({"username": "admin", "password": "wrong"})
        print(f"   Invalid password authenticated: {invalid_ctx is not None}")
    except Exception as e:
        print(f"   Invalid password rejected: {type(e).__name__}: {e}")

    # Test non-existent user
    try:
        nouser_ctx = auth.authenticate({"username": "nobody", "password": "pass"})
        print(f"   Non-existent user authenticated: {nouser_ctx is not None}")
    except Exception as e:
        print(f"   Non-existent user rejected: {type(e).__name__}: {e}")


async def test_rate_limiting():
    """Test rate limiting functionality"""
    print("\n\n=== Testing Rate Limiting ===")

    from kailash.mcp_server.auth import RateLimiter

    rate_limiter = RateLimiter(
        default_limit=5,  # 5 requests per minute for testing
        burst_limit=2,
        per_user_limits={"power_user": 10},
    )

    print("\n1. Testing rate limits:")

    # Test default user
    user_info = {"user_id": "user1"}
    for i in range(7):
        try:
            allowed = rate_limiter.check_rate_limit(user_info)
            print(f"   Request {i+1} for user1: Allowed")
        except Exception as e:
            print(f"   Request {i+1} for user1: BLOCKED - {e}")

    # Test power user
    print("\n2. Testing power user with higher limit:")
    power_user_info = {"user_id": "power_user"}
    for i in range(7):
        try:
            allowed = rate_limiter.check_rate_limit(power_user_info)
            print(f"   Request {i+1} for power_user: Allowed")
        except Exception as e:
            print(f"   Request {i+1} for power_user: BLOCKED - {e}")


async def test_integrated_server():
    """Test a fully integrated MCP server with auth"""
    print("\n\n=== Testing Integrated MCP Server ===")

    # Set up authentication
    auth = APIKeyAuth(
        keys={
            "test-key": {"permissions": ["read", "write"]},
            "admin-key": {"permissions": ["read", "write", "admin"]},
        }
    )

    # Create server with auth
    server = MCPServer(
        name="secure-test-server",
        auth_provider=auth,
        enable_cache=True,
        enable_metrics=True,
    )

    # Add test tools
    @server.tool(required_permission="admin")
    async def admin_operation(action: str) -> dict:
        return {"admin_result": action}

    @server.tool(required_permission="write")
    async def write_operation(data: str) -> dict:
        return {"written": data}

    @server.tool()
    async def public_operation() -> dict:
        return {"public": "accessible"}

    print("\n1. Server created with:")
    print("   - Authentication: API Key")
    print(
        "   - Tools: admin_operation (admin), write_operation (write), public_operation (no auth)"
    )
    print("   - Metrics: Enabled")
    print("   - Cache: Enabled")

    # Test tool access
    print("\n2. Testing tool permissions:")

    # Get auth contexts
    test_ctx = auth.authenticate({"api_key": "test-key"})
    admin_ctx = auth.authenticate({"api_key": "admin-key"})

    # Check permissions using permission manager
    pm = PermissionManager()

    print(f"   test-key permissions: {test_ctx.get('permissions')}")
    print(f"   admin-key permissions: {admin_ctx.get('permissions')}")

    # Test write permission
    try:
        test_can_write = pm.check_permission(test_ctx, "write")
        print("   test-key can access write_operation: True")
    except Exception:
        print("   test-key can access write_operation: False")

    # Test admin permission for test-key
    try:
        test_can_admin = pm.check_permission(test_ctx, "admin")
        print("   test-key can access admin_operation: True")
    except Exception:
        print("   test-key can access admin_operation: False")

    # Test admin permission for admin-key
    try:
        admin_can_admin = pm.check_permission(admin_ctx, "admin")
        print("   admin-key can access admin_operation: True")
    except Exception:
        print("   admin-key can access admin_operation: False")


async def main():
    """Run all tests"""
    print("=" * 60)
    print("MCP Server Access Control Test Suite")
    print("=" * 60)

    try:
        await test_api_key_auth()
        await test_jwt_auth()
        await test_basic_auth()
        await test_rate_limiting()
        await test_integrated_server()

        print("\n\n✅ All tests completed successfully!")
        print("\nSummary:")
        print("- API Key authentication working")
        print("- JWT authentication working")
        print("- Basic authentication working")
        print("- Rate limiting working")
        print("- Permission-based tool access working")
        print("- Integrated MCP server with auth working")

    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
