"""
Test for circular imports in middleware auth module.

This test verifies that the auth refactoring successfully
resolved the circular import issues.
"""

import sys
import traceback


def test_import_jwt_auth_manager():
    """Test that JWTAuthManager can be imported without circular import errors."""
    print("Testing JWTAuthManager import...")
    try:
        from kailash.middleware.auth import JWTAuthManager

        print("✅ JWTAuthManager imported successfully")
        assert True  # Import succeeded
    except ImportError as e:
        print(f"❌ Failed to import JWTAuthManager: {e}")
        traceback.print_exc()
        assert False, f"Failed to import JWTAuthManager: {e}"


def test_import_api_gateway():
    """Test that APIGateway can be imported without circular import errors."""
    print("\nTesting APIGateway import...")
    try:
        from kailash.middleware.communication.api_gateway import APIGateway

        print("✅ APIGateway imported successfully")
        assert True  # Import succeeded
    except ImportError as e:
        print(f"❌ Failed to import APIGateway: {e}")
        traceback.print_exc()
        assert False, f"Failed to import APIGateway: {e}"


def test_create_gateway_with_auth():
    """Test that create_gateway can use auth without circular imports."""
    print("\nTesting create_gateway with auth...")
    try:
        from kailash.middleware.auth import JWTAuthManager
        from kailash.middleware.communication.api_gateway import create_gateway

        # Create auth manager
        auth = JWTAuthManager(secret_key="test-secret", algorithm="HS256")

        # Create gateway with auth
        gateway = create_gateway(title="Test Gateway", auth_manager=auth)

        print("✅ create_gateway works with JWTAuthManager")
        print(f"✅ Gateway auth_manager type: {type(gateway.auth_manager).__name__}")
        assert gateway.auth_manager is not None
        assert isinstance(gateway.auth_manager, JWTAuthManager)
    except Exception as e:
        print(f"❌ Failed to create gateway with auth: {e}")
        traceback.print_exc()
        assert False, f"Failed to create gateway with auth: {e}"


def test_middleware_imports():
    """Test that all middleware components can be imported."""
    print("\nTesting middleware imports...")

    imports_to_test = [
        ("kailash.middleware", "__init__"),
        ("kailash.middleware.auth", "JWTAuthManager"),
        ("kailash.middleware.auth.models", "JWTConfig"),
        ("kailash.middleware.auth.exceptions", "AuthenticationError"),
        ("kailash.middleware.auth.utils", "generate_secret_key"),
        ("kailash.middleware.communication.api_gateway", "APIGateway"),
        ("kailash.middleware.core.agent_ui", "AgentUIMiddleware"),
    ]

    failed_imports = []
    for module_path, component in imports_to_test:
        try:
            if component == "__init__":
                exec(f"import {module_path}")
            else:
                exec(f"from {module_path} import {component}")
            print(f"✅ {module_path}.{component}")
        except Exception as e:
            print(f"❌ {module_path}.{component}: {e}")
            failed_imports.append(f"{module_path}.{component}: {e}")

    assert len(failed_imports) == 0, f"Failed imports: {failed_imports}"


def test_jwt_functionality():
    """Test basic JWT functionality to ensure it works after refactoring."""
    print("\nTesting JWT functionality...")
    try:
        from kailash.middleware.auth import JWTAuthManager

        # Create manager
        auth = JWTAuthManager(secret_key="test-key")

        # Create token
        token = auth.create_access_token(
            user_id="test-user", permissions=["read", "write"], roles=["user"]
        )
        print("✅ Token created successfully")

        # Verify token
        payload = auth.verify_token(token)
        assert payload["sub"] == "test-user"
        assert "read" in payload.get("permissions", [])
        print("✅ Token verified successfully")

        # Create token pair
        token_pair = auth.create_token_pair(
            user_id="test-user-2", tenant_id="tenant-123"
        )
        assert hasattr(token_pair, "access_token")
        assert hasattr(token_pair, "refresh_token")
        assert token_pair.access_token is not None
        assert token_pair.refresh_token is not None
        print("✅ Token pair created successfully")

    except Exception as e:
        print(f"❌ JWT functionality test failed: {e}")
        traceback.print_exc()
        assert False, f"JWT functionality test failed: {e}"


# For direct execution (not pytest)
if __name__ == "__main__":
    print("🔄 Running Circular Import Tests\n")
    print("=" * 50)

    tests = [
        test_import_jwt_auth_manager,
        test_import_api_gateway,
        test_create_gateway_with_auth,
        test_middleware_imports,
        test_jwt_functionality,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"❌ Test {test.__name__} failed: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            failed += 1
        print()

    # Summary
    total = len(tests)

    print("=" * 50)
    print(f"\n📊 Test Summary: {passed}/{total} passed")

    if passed == total:
        print("✅ All circular import tests passed!")
        print("🎉 Auth refactoring successfully resolved circular dependencies")
    else:
        print("❌ Some tests failed")
        sys.exit(1)
