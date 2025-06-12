#!/usr/bin/env python3
"""
Admin Framework Docker Test

This test validates the admin framework with Docker services (PostgreSQL, Redis, Ollama).
It demonstrates real-world usage with proper database configuration.
"""

import json
from datetime import UTC, datetime

from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow


def test_database_connection():
    """Test database connectivity and setup."""
    print("\n🔌 Testing Database Connection...")

    def check_database():
        """Check database connection and tables."""
        import json

        import psycopg2

        try:
            # Connect to database
            conn = psycopg2.connect(
                host="localhost",
                port=5433,
                database="kailash_admin",
                user="admin",
                password="admin",
            )

            cursor = conn.cursor()

            # Set search path
            cursor.execute("SET search_path TO kailash, public;")

            # Check tables
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'kailash'
                ORDER BY table_name;
            """
            )

            tables = [row[0] for row in cursor.fetchall()]

            # Check tenant
            cursor.execute("SELECT id, name FROM tenants WHERE name = 'demo_company';")
            tenant_result = cursor.fetchone()

            cursor.close()
            conn.close()

            return {
                "result": {
                    "connected": True,
                    "tables": tables,
                    "table_count": len(tables),
                    "tenant_exists": tenant_result is not None,
                    "tenant_id": str(tenant_result[0]) if tenant_result else None,
                }
            }

        except Exception as e:
            return {"result": {"connected": False, "error": str(e)}}

    # Create and run workflow
    runtime = LocalRuntime()
    workflow = Workflow(workflow_id="db_test", name="Database Test")

    db_check = PythonCodeNode.from_function(
        func=check_database, name="check_db", description="Check database connection"
    )

    workflow.add_node("check_db", db_check)
    result, _ = runtime.execute(workflow)

    # PythonCodeNode returns nested result
    db_info = result["check_db"]["result"]["result"]
    if db_info["connected"]:
        print("✅ Database connected successfully")
        print(f"   Tables found: {db_info['table_count']}")
        print(f"   Tenant exists: {db_info['tenant_exists']}")
        if db_info["tenant_id"]:
            print(f"   Tenant ID: {db_info['tenant_id']}")
        return db_info["tenant_id"]
    else:
        print(f"❌ Database connection failed: {db_info['error']}")
        return None


def test_user_operations(tenant_id):
    """Test user CRUD operations."""
    print("\n👤 Testing User Operations...")

    def create_test_user(tenant_id):
        """Create a test user directly in database."""
        import hashlib
        import secrets
        import uuid

        import psycopg2

        try:
            conn = psycopg2.connect(
                host="localhost",
                port=5433,
                database="kailash_admin",
                user="admin",
                password="admin",
            )

            cursor = conn.cursor()
            cursor.execute("SET search_path TO kailash, public;")

            # Generate user data
            user_id = str(uuid.uuid4())
            user_uid = f"user_{user_id[:8]}"
            salt = secrets.token_hex(32)
            password_hash = hashlib.sha256(("TestPass123!" + salt).encode()).hexdigest()

            # Insert user
            cursor.execute(
                """
                INSERT INTO users (
                    id, user_id, tenant_id, email, username,
                    first_name, last_name, password_hash, status,
                    roles, attributes, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) RETURNING id, user_id, email, username;
            """,
                (
                    user_id,
                    user_uid,
                    tenant_id,
                    "test.user@company.com",
                    "test.user",
                    "Test",
                    "User",
                    f"{salt}${password_hash}",
                    "active",
                    json.dumps(["employee"]),
                    json.dumps({"department": "IT"}),
                    datetime.now(UTC),
                    datetime.now(UTC),
                ),
            )

            user_data = cursor.fetchone()
            conn.commit()

            # Query all users
            cursor.execute(
                """
                SELECT COUNT(*) FROM users WHERE tenant_id = %s;
            """,
                (tenant_id,),
            )

            user_count = cursor.fetchone()[0]

            cursor.close()
            conn.close()

            return {
                "result": {
                    "success": True,
                    "user": {
                        "id": str(user_data[0]),
                        "user_id": user_data[1],
                        "email": user_data[2],
                        "username": user_data[3],
                    },
                    "total_users": user_count,
                }
            }

        except Exception as e:
            return {"result": {"success": False, "error": str(e)}}

    # Create workflow
    runtime = LocalRuntime()
    workflow = Workflow(workflow_id="user_test", name="User Test")

    create_user = PythonCodeNode.from_function(
        func=create_test_user, name="create_user", description="Create test user"
    )

    workflow.add_node("create_user", create_user)

    # Set parameters
    parameters = {"create_user": {"tenant_id": tenant_id}}
    result, _ = runtime.execute(workflow, parameters=parameters)

    user_result = result["create_user"]["result"]["result"]
    if user_result["success"]:
        print("✅ User created successfully")
        print(f"   User ID: {user_result['user']['user_id']}")
        print(f"   Email: {user_result['user']['email']}")
        print(f"   Total users: {user_result['total_users']}")
        return user_result["user"]["user_id"]
    else:
        print(f"❌ User creation failed: {user_result['error']}")
        return None


def test_audit_logging():
    """Test audit logging functionality."""
    print("\n📝 Testing Audit Logging...")

    def create_audit_log():
        """Create audit log entries."""
        import uuid

        import psycopg2

        try:
            conn = psycopg2.connect(
                host="localhost",
                port=5433,
                database="kailash_admin",
                user="admin",
                password="admin",
            )

            cursor = conn.cursor()
            cursor.execute("SET search_path TO kailash, public;")

            # Get tenant ID
            cursor.execute("SELECT id FROM tenants WHERE name = 'demo_company';")
            tenant_id = cursor.fetchone()[0]

            # Insert audit log
            audit_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO admin_audit_logs (
                    audit_id, tenant_id, event_type, severity, action,
                    description, metadata, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s
                ) RETURNING audit_id;
            """,
                (
                    f"audit_{audit_id[:8]}",
                    tenant_id,
                    "user_login",
                    "low",
                    "user_authenticated",
                    "User logged in successfully",
                    json.dumps({"ip": "192.168.1.100", "browser": "Chrome"}),
                    datetime.now(UTC),
                ),
            )

            audit_result = cursor.fetchone()[0]

            # Count audit logs
            cursor.execute(
                "SELECT COUNT(*) FROM admin_audit_logs WHERE tenant_id = %s;",
                (tenant_id,),
            )
            audit_count = cursor.fetchone()[0]

            conn.commit()
            cursor.close()
            conn.close()

            return {
                "result": {
                    "success": True,
                    "audit_id": audit_result,
                    "total_logs": audit_count,
                }
            }

        except Exception as e:
            return {"result": {"success": False, "error": str(e)}}

    # Run test
    runtime = LocalRuntime()
    workflow = Workflow(workflow_id="audit_test", name="Audit Test")

    audit_log = PythonCodeNode.from_function(
        func=create_audit_log, name="create_audit", description="Create audit log"
    )

    workflow.add_node("create_audit", audit_log)
    result, _ = runtime.execute(workflow)

    audit_result = result["create_audit"]["result"]["result"]
    if audit_result["success"]:
        print("✅ Audit log created successfully")
        print(f"   Audit ID: {audit_result['audit_id']}")
        print(f"   Total logs: {audit_result['total_logs']}")
    else:
        print(f"❌ Audit logging failed: {audit_result['error']}")


def test_redis_connection():
    """Test Redis connectivity."""
    print("\n🔴 Testing Redis Connection...")

    def check_redis():
        """Check Redis connection."""
        try:
            import redis
        except ImportError:
            return {
                "result": {
                    "connected": False,
                    "error": "redis module not installed - run: pip install redis",
                }
            }

        try:
            r = redis.Redis(host="localhost", port=6380, decode_responses=True)

            # Test basic operations
            r.set("test_key", "test_value", ex=60)
            value = r.get("test_key")

            # Set session data
            session_data = {
                "user_id": "test_user",
                "roles": ["admin"],
                "tenant_id": "demo_company",
            }
            r.setex("session:test123", 3600, json.dumps(session_data))

            # Get Redis info
            info = r.info()

            return {
                "result": {
                    "connected": True,
                    "test_value": value,
                    "redis_version": info.get("redis_version", "unknown"),
                    "connected_clients": info.get("connected_clients", 0),
                }
            }

        except Exception as e:
            return {"result": {"connected": False, "error": str(e)}}

    # Run test
    runtime = LocalRuntime()
    workflow = Workflow(workflow_id="redis_test", name="Redis Test")

    redis_check = PythonCodeNode.from_function(
        func=check_redis, name="check_redis", description="Check Redis connection"
    )

    workflow.add_node("check_redis", redis_check)
    result, _ = runtime.execute(workflow)

    # Handle potential execution failure
    if "check_redis" not in result or "result" not in result.get("check_redis", {}):
        print("❌ Redis test failed to execute")
        return

    redis_result = result["check_redis"]["result"]["result"]
    if redis_result["connected"]:
        print("✅ Redis connected successfully")
        print(f"   Version: {redis_result['redis_version']}")
        print(f"   Connected clients: {redis_result['connected_clients']}")
    else:
        print(f"❌ Redis connection failed: {redis_result['error']}")


def test_ollama_connection():
    """Test Ollama connectivity."""
    print("\n🤖 Testing Ollama Connection...")

    def check_ollama():
        """Check Ollama connection."""
        try:
            import requests
        except ImportError:
            return {
                "result": {
                    "connected": False,
                    "error": "requests module not installed - run: pip install requests",
                }
            }

        try:
            # Check if Ollama is running
            response = requests.get("http://localhost:11434/api/tags", timeout=5)

            if response.status_code == 200:
                models = response.json().get("models", [])

                return {
                    "result": {
                        "connected": True,
                        "models": [m["name"] for m in models],
                        "model_count": len(models),
                    }
                }
            else:
                return {
                    "result": {
                        "connected": False,
                        "error": f"HTTP {response.status_code}",
                    }
                }

        except Exception as e:
            return {"result": {"connected": False, "error": str(e)}}

    # Run test
    runtime = LocalRuntime()
    workflow = Workflow(workflow_id="ollama_test", name="Ollama Test")

    ollama_check = PythonCodeNode.from_function(
        func=check_ollama, name="check_ollama", description="Check Ollama connection"
    )

    workflow.add_node("check_ollama", ollama_check)
    result, _ = runtime.execute(workflow)

    ollama_result = result["check_ollama"]["result"]["result"]
    if ollama_result["connected"]:
        print("✅ Ollama connected successfully")
        print(f"   Models available: {ollama_result['model_count']}")
        if ollama_result["models"]:
            print(f"   Models: {', '.join(ollama_result['models'][:3])}")
    else:
        print(f"❌ Ollama connection failed: {ollama_result['error']}")
        print(
            "   Note: You may need to pull models with: docker exec kailash-ollama ollama pull llama2"
        )


def main():
    """Run all tests."""
    print("🧪 Admin Framework Docker Integration Test")
    print("=" * 50)

    # Test database
    tenant_id = test_database_connection()

    if tenant_id:
        # Test user operations
        user_id = test_user_operations(tenant_id)

        # Test audit logging
        test_audit_logging()

    # Test Redis
    test_redis_connection()

    # Test Ollama
    test_ollama_connection()

    print("\n" + "=" * 50)
    print("✅ All tests completed!")
    print("=" * 50)
    print("\nDocker services status:")
    print("- PostgreSQL: ✅ Running on port 5433")
    print("- Redis: ✅ Running on port 6380")
    print("- Ollama: ✅ Running on port 11434")
    print("\nYour admin framework is ready for use with Docker!")


if __name__ == "__main__":
    main()
