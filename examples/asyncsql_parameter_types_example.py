"""
AsyncSQL Parameter Type Inference Example

This example demonstrates how to use the parameter_types feature to solve
PostgreSQL parameter type inference issues with JSONB and complex type contexts.

Bug: PostgreSQL's asyncpg driver sometimes cannot infer parameter types when
used in complex contexts like jsonb_build_object or COALESCE, resulting in:
"could not determine data type of parameter $N"

Solution: Use the parameter_types option to provide explicit type hints.
"""

import asyncio

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode


async def main():
    # Create AsyncSQL node
    node = AsyncSQLDatabaseNode(
        name="pg_db",
        database_type="postgresql",
        host="localhost",
        port=5432,
        database="test_db",
        user="postgres",
        password="postgres",
        validate_queries=False,  # Disable for DDL
    )

    # Example 1: JSONB build_object with type hints
    print("Example 1: JSONB build_object with parameter types")
    try:
        result = await node.async_run(
            query="""
                INSERT INTO audit_logs (action, details, created_by)
                VALUES (
                    :action,
                    jsonb_build_object(
                        'role_id', :role_id,
                        'granted_by', :granted_by,
                        'permissions', :permissions::jsonb,
                        'metadata', jsonb_build_object(
                            'timestamp', :timestamp,
                            'ip_address', :ip_address
                        )
                    ),
                    :created_by
                )
                RETURNING id
            """,
            params={
                "action": "role_assigned",
                "role_id": "admin-001",
                "granted_by": "system",
                "permissions": '["read", "write", "delete"]',
                "timestamp": "2024-01-01T00:00:00Z",
                "ip_address": "192.168.1.1",
                "created_by": "system",
            },
            parameter_types={
                "action": "text",
                "role_id": "text",
                "granted_by": "text",
                "permissions": "jsonb",
                "timestamp": "timestamptz",
                "ip_address": "inet",
                "created_by": "text",
            },
        )
        print(f"✓ Inserted audit log with ID: {result['result']['data'][0]['id']}")
    except Exception as e:
        print(f"✗ Error: {e}")

    # Example 2: COALESCE with NULL handling
    print("\nExample 2: COALESCE with NULL values")
    try:
        result = await node.async_run(
            query="""
                UPDATE users
                SET preferences = jsonb_set(
                    COALESCE(preferences, '{}'),
                    '{notifications}',
                    :notification_settings::jsonb
                )
                WHERE user_id = :user_id
                RETURNING user_id, preferences
            """,
            params={
                "notification_settings": '{"email": true, "sms": false, "push": true}',
                "user_id": "user-123",
            },
            parameter_types={"notification_settings": "jsonb", "user_id": "text"},
        )
        if result["result"]["data"]:
            print(
                f"✓ Updated preferences for user: {result['result']['data'][0]['user_id']}"
            )
    except Exception as e:
        print(f"✗ Error: {e}")

    # Example 3: Configuration-based type hints
    print("\nExample 3: Configuration-based parameter types")

    # Create node with default parameter types
    configured_node = AsyncSQLDatabaseNode(
        name="configured_db",
        database_type="postgresql",
        host="localhost",
        port=5432,
        database="test_db",
        user="postgres",
        password="postgres",
        parameter_types={
            "metadata": "jsonb",
            "user_id": "uuid",
            "created_at": "timestamptz",
            "ip_address": "inet",
        },
    )

    try:
        # These parameter types are automatically applied
        result = await configured_node.async_run(
            query="""
                INSERT INTO activity_logs (user_id, metadata, ip_address, created_at)
                VALUES (:user_id, :metadata, :ip_address, :created_at)
                RETURNING id
            """,
            params={
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "metadata": {"action": "login", "device": "mobile"},
                "ip_address": "10.0.0.1",
                "created_at": "2024-01-01T12:00:00Z",
            },
        )
        print(f"✓ Inserted activity log with ID: {result['result']['data'][0]['id']}")
    except Exception as e:
        print(f"✗ Error: {e}")

    # Example 4: Complex nested JSONB operations
    print("\nExample 4: Complex nested JSONB operations")
    try:
        result = await node.async_run(
            query="""
                WITH user_data AS (
                    SELECT
                        id,
                        jsonb_build_object(
                            'profile', jsonb_build_object(
                                'name', :name,
                                'email', :email,
                                'settings', :settings::jsonb
                            ),
                            'metadata', jsonb_build_object(
                                'created_by', :created_by,
                                'tags', :tags::jsonb
                            )
                        ) as data
                    FROM users
                    WHERE id = :user_id
                )
                UPDATE users u
                SET extended_data = ud.data
                FROM user_data ud
                WHERE u.id = ud.id
                RETURNING u.id
            """,
            params={
                "user_id": 123,
                "name": "John Doe",
                "email": "john@example.com",
                "settings": '{"theme": "dark", "language": "en"}',
                "created_by": "admin",
                "tags": '["premium", "verified"]',
            },
            parameter_types={
                "user_id": "integer",
                "name": "text",
                "email": "text",
                "settings": "jsonb",
                "created_by": "text",
                "tags": "jsonb",
            },
        )
        if result["result"]["data"]:
            print(
                f"✓ Updated extended data for user ID: {result['result']['data'][0]['id']}"
            )
    except Exception as e:
        print(f"✗ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
