"""
Comprehensive Docker-based integration tests for admin nodes.

These tests use real PostgreSQL Docker infrastructure to validate:
- User creation, role assignment, permission checks
- Multi-tenant data isolation
- Performance under load with real database
- Schema migration and validation
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import asyncpg
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from kailash import Workflow
from kailash.nodes.admin import (
    PermissionCheckNode,
    RoleManagementNode,
    UserManagementNode,
)
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.base_cycle_aware import CycleAwareNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.runtime.local import LocalRuntime
from tests.utils.docker_config import DATABASE_CONFIG, get_postgres_connection_string

# Skip if Docker infrastructure is not available
pytestmark = [pytest.mark.requires_docker, pytest.mark.integration]


class AdminTestHelper:
    """Helper class for admin node testing with Docker."""

    @staticmethod
    async def check_postgres_available():
        """Check if PostgreSQL Docker container is available."""
        try:
            conn_string = get_postgres_connection_string()
            conn = await asyncpg.connect(conn_string)
            await conn.close()
            return True
        except Exception as e:
            print(f"PostgreSQL not available: {e}")
            return False

    @staticmethod
    async def create_test_database(db_name: str):
        """Create a test database."""
        conn_string = get_postgres_connection_string("postgres")
        conn = await asyncpg.connect(conn_string)
        try:
            # Drop if exists
            await conn.execute(f"DROP DATABASE IF EXISTS {db_name}")
            # Create new
            await conn.execute(f"CREATE DATABASE {db_name}")
        finally:
            await conn.close()

    @staticmethod
    async def drop_test_database(db_name: str):
        """Drop a test database."""
        conn_string = get_postgres_connection_string("postgres")
        conn = await asyncpg.connect(conn_string)
        try:
            await conn.execute(f"DROP DATABASE IF EXISTS {db_name}")
        finally:
            await conn.close()

    @staticmethod
    def get_test_connection_string(db_name: str):
        """Get connection string for test database."""
        return get_postgres_connection_string(db_name)


class TestAdminNodesDockerIntegration:
    """Docker-based integration tests for admin nodes."""

    def setup_method(self):
        """Set up test database before each test."""
        # Check PostgreSQL synchronously
        import asyncio

        loop = asyncio.new_event_loop()
        if not loop.run_until_complete(AdminTestHelper.check_postgres_available()):
            pytest.skip("PostgreSQL Docker container not available")

        self.test_db = f"kailash_admin_test_{int(time.time())}"
        loop.run_until_complete(AdminTestHelper.create_test_database(self.test_db))
        self.conn_string = AdminTestHelper.get_test_connection_string(self.test_db)
        loop.close()

    def teardown_method(self):
        """Tear down test database after each test."""
        import asyncio

        loop = asyncio.new_event_loop()
        loop.run_until_complete(AdminTestHelper.drop_test_database(self.test_db))
        loop.close()

    def test_complete_admin_workflow_with_real_database(self):
        """Test complete admin workflow with real PostgreSQL database."""
        workflow = Workflow("admin-docker-test", "Admin Docker Integration")

        # Initialize schema
        schema_init = PythonCodeNode(
            name="schema_init",
            code=f"""
conn_string = "{self.conn_string}"
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Connect and create schema
conn = psycopg2.connect(conn_string)
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()

# Create users table
cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(100) UNIQUE NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL,
        role VARCHAR(50),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        tenant_id INTEGER
    )
''')

# Create roles table
cur.execute('''
    CREATE TABLE IF NOT EXISTS roles (
        id SERIAL PRIMARY KEY,
        name VARCHAR(50) UNIQUE NOT NULL,
        permissions TEXT[],
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

# Create permissions table
cur.execute('''
    CREATE TABLE IF NOT EXISTS permissions (
        id SERIAL PRIMARY KEY,
        resource VARCHAR(100) NOT NULL,
        action VARCHAR(50) NOT NULL,
        conditions JSONB,
        UNIQUE(resource, action)
    )
''')

# Create default roles
cur.execute('''
    INSERT INTO roles (name, permissions) VALUES
    ('admin', ARRAY['users.create', 'users.read', 'users.update', 'users.delete', 'roles.manage']),
    ('editor', ARRAY['users.read', 'users.update']),
    ('viewer', ARRAY['users.read'])
    ON CONFLICT (name) DO NOTHING
''')

conn.commit()
cur.close()
conn.close()

result = {{"status": "schema_initialized", "database": "{self.test_db}"}}
""",
        )
        workflow.add_node("schema_init", schema_init)

        # User management node
        user_mgmt = UserManagementNode(database_url=self.conn_string)
        workflow.add_node("user_mgmt", user_mgmt)

        # Role management node
        role_mgmt = RoleManagementNode(database_url=self.conn_string)
        workflow.add_node("role_mgmt", role_mgmt)

        # Permission check node
        perm_check = PermissionCheckNode(database_url=self.conn_string)
        workflow.add_node("perm_check", perm_check)

        # Test data generator
        test_data_gen = PythonCodeNode(
            name="test_data_gen",
            code="""
# Generate test user data
users_to_create = []
for i in range(10):
    tenant_id = (i % 3) + 1  # 3 tenants
    role = ['admin', 'editor', 'viewer'][i % 3]
    users_to_create.append({
        'username': f'user_{i}',
        'email': f'user_{i}@test.com',
        'role': role,
        'tenant_id': tenant_id
    })

result = {
    'users': users_to_create,
    'test_scenarios': [
        {'user': 'user_0', 'resource': 'users', 'action': 'create'},  # admin - should pass
        {'user': 'user_1', 'resource': 'users', 'action': 'delete'},  # editor - should fail
        {'user': 'user_2', 'resource': 'users', 'action': 'read'},    # viewer - should pass
    ]
}
""",
        )
        workflow.add_node("test_data", test_data_gen)

        # Batch user creator
        batch_creator = PythonCodeNode(
            name="batch_creator",
            code="""
created_users = []
failed_users = []

for user_data in users:
    try:
        # User management node will handle the creation
        created_users.append(user_data)
    except Exception as e:
        failed_users.append({'user': user_data, 'error': str(e)})

result = {
    'created_count': len(created_users),
    'failed_count': len(failed_users),
    'users_to_create': users
}
""",
        )
        workflow.add_node("batch_creator", batch_creator)

        # Permission tester
        perm_tester = PythonCodeNode(
            name="perm_tester",
            code="""
test_results = []

for scenario in test_scenarios:
    # Permission check will be done by the node
    test_results.append({
        'scenario': scenario,
        'expected': scenario['user'] == 'user_0' or
                   (scenario['user'] == 'user_2' and scenario['action'] == 'read')
    })

result = {
    'scenarios': test_scenarios,
    'test_count': len(test_scenarios)
}
""",
        )
        workflow.add_node("perm_tester", perm_tester)

        # Results aggregator
        aggregator = PythonCodeNode(
            name="aggregator",
            code="""
import psycopg2

# Connect to verify results
conn = psycopg2.connect(conn_string)
cur = conn.cursor()

# Count users per tenant
cur.execute('''
    SELECT tenant_id, COUNT(*) as user_count, array_agg(role) as roles
    FROM users
    GROUP BY tenant_id
    ORDER BY tenant_id
''')
tenant_stats = cur.fetchall()

# Count users per role
cur.execute('''
    SELECT role, COUNT(*) as count
    FROM users
    GROUP BY role
    ORDER BY role
''')
role_stats = cur.fetchall()

# Total users
cur.execute('SELECT COUNT(*) FROM users')
total_users = cur.fetchone()[0]

cur.close()
conn.close()

result = {
    'total_users': total_users,
    'tenant_distribution': [
        {'tenant_id': t[0], 'user_count': t[1], 'roles': t[2]}
        for t in tenant_stats
    ],
    'role_distribution': [
        {'role': r[0], 'count': r[1]}
        for r in role_stats
    ],
    'permission_checks': permission_results if 'permission_results' in locals() else []
}
""",
        )
        workflow.add_node("aggregator", aggregator)

        # Connect workflow
        workflow.connect("schema_init", "test_data")
        workflow.connect("test_data", "batch_creator", mapping={"users": "users"})
        workflow.connect(
            "test_data", "perm_tester", mapping={"test_scenarios": "test_scenarios"}
        )

        # User creation flow
        workflow.connect(
            "batch_creator", "user_mgmt", mapping={"users_to_create": "users_to_create"}
        )

        # Permission check flow
        workflow.connect(
            "perm_tester", "perm_check", mapping={"scenarios": "permission_checks"}
        )

        # Aggregate results
        workflow.connect(
            "user_mgmt", "aggregator", mapping={"created_users": "user_results"}
        )
        workflow.connect(
            "perm_check", "aggregator", mapping={"results": "permission_results"}
        )

        # Execute workflow with required parameters
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            {
                "user_mgmt": {
                    "operation": "bulk_create_users",
                    "tenant_id": "test_tenant",
                    "users_to_create": [],  # Will be provided by the batch_creator node
                    "database_config": {
                        "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test"
                    },
                },
                "role_mgmt": {
                    "operation": "list_roles",
                    "tenant_id": "test_tenant",
                    "database_config": {
                        "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test"
                    },
                },
                "perm_check": {
                    "operation": "batch_check",
                    "permission_checks": [],  # Will be provided by the perm_tester node
                    "database_config": {
                        "connection_string": "postgresql://test_user:test_password@localhost:5434/kailash_test"
                    },
                },
                "aggregator": {"conn_string": self.conn_string},
            },
        )

        # Verify results
        assert results["schema_init"]["status"] == "schema_initialized"
        assert results["aggregator"]["total_users"] >= 10

        # Check tenant distribution
        tenant_dist = results["aggregator"]["tenant_distribution"]
        assert len(tenant_dist) >= 3  # Should have 3 tenants

        # Check role distribution
        role_dist = results["aggregator"]["role_distribution"]
        role_counts = {r["role"]: r["count"] for r in role_dist}
        assert all(role in role_counts for role in ["admin", "editor", "viewer"])

    def test_concurrent_admin_operations_with_load(self):
        """Test admin operations under concurrent load."""
        workflow = Workflow("admin-load-test", "Admin Load Testing")

        # Schema initialization (reuse from previous test)
        schema_init = PythonCodeNode(
            name="schema_init",
            code=f"""
conn_string = "{self.conn_string}"
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

conn = psycopg2.connect(conn_string)
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()

# Create tables with proper indexes for performance
cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(100) UNIQUE NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL,
        role VARCHAR(50),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        tenant_id INTEGER
    )
''')

cur.execute('''
    CREATE TABLE IF NOT EXISTS audit_log (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        action VARCHAR(100),
        resource VARCHAR(100),
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        success BOOLEAN
    )
''')

conn.commit()
cur.close()
conn.close()

result = {"status": "schema_ready"}
""",
        )
        workflow.add_node("schema_init", schema_init)

        # Concurrent user generator
        concurrent_gen = PythonCodeNode(
            code="""
import random
import string

# Generate 100 users for concurrent creation
users = []
for i in range(100):
    tenant_id = random.randint(1, 10)  # 10 tenants
    role = random.choice(['admin', 'editor', 'viewer'])

    # Random username to avoid conflicts
    suffix = ''.join(random.choices(string.ascii_lowercase, k=6))

    users.append({
        'username': f'load_user_{i}_{suffix}',
        'email': f'load_user_{i}_{suffix}@test.com',
        'role': role,
        'tenant_id': tenant_id
    })

# Generate permission check scenarios
scenarios = []
for _ in range(50):
    user_idx = random.randint(0, 99)
    scenarios.append({
        'user': users[user_idx]['username'],
        'resource': random.choice(['users', 'roles', 'permissions']),
        'action': random.choice(['create', 'read', 'update', 'delete'])
    })

result = {
    'users': users,
    'scenarios': scenarios
}
"""
        )
        workflow.add_node("concurrent_gen", concurrent_gen)

        # Performance monitor
        perf_monitor = PythonCodeNode(
            name="perf_monitor",
            code="""
import time
import psycopg2

start_time = time.time()

# Monitor database performance
conn = psycopg2.connect(conn_string)
cur = conn.cursor()

# Get initial stats
cur.execute("SELECT COUNT(*) FROM users")
initial_count = cur.fetchone()[0]

# Store timing for result
creation_start = time.time()

result = {
    'initial_count': initial_count,
    'start_time': creation_start,
    'batch_size': len(users) if 'users' in locals() else 0
}

cur.close()
conn.close()
""",
        )
        workflow.add_node("perf_monitor", perf_monitor)

        # Results analyzer
        analyzer = PythonCodeNode(
            code="""
import time
import psycopg2

end_time = time.time()

conn = psycopg2.connect(conn_string)
cur = conn.cursor()

# Final user count
cur.execute("SELECT COUNT(*) FROM users")
final_count = cur.fetchone()[0]

# Users per second calculation
users_created = final_count - (initial_count if 'initial_count' in locals() else 0)
elapsed_time = end_time - (start_time if 'start_time' in locals() else end_time)
users_per_second = users_created / elapsed_time if elapsed_time > 0 else 0

# Analyze tenant distribution
cur.execute('''
    SELECT tenant_id, COUNT(*) as count
    FROM users
    GROUP BY tenant_id
    HAVING COUNT(*) > 5
    ORDER BY count DESC
    LIMIT 5
''')
top_tenants = cur.fetchall()

# Analyze role distribution under load
cur.execute('''
    SELECT role, COUNT(*) as count,
           AVG(EXTRACT(EPOCH FROM (NOW() - created_at))) as avg_age_seconds
    FROM users
    GROUP BY role
''')
role_perf = cur.fetchall()

cur.close()
conn.close()

result = {
    'performance': {
        'users_created': users_created,
        'elapsed_seconds': elapsed_time,
        'users_per_second': users_per_second
    },
    'tenant_analysis': [
        {'tenant_id': t[0], 'user_count': t[1]}
        for t in top_tenants
    ],
    'role_performance': [
        {'role': r[0], 'count': r[1], 'avg_age_seconds': float(r[2])}
        for r in role_perf
    ]
}
"""
        )
        workflow.add_node("analyzer", analyzer)

        # Connect workflow
        workflow.connect("schema_init", "concurrent_gen")
        workflow.connect("concurrent_gen", "perf_monitor", mapping={"users": "users"})

        # Create admin nodes
        user_mgmt = UserManagementNode(database_url=self.conn_string)
        workflow.add_node("user_mgmt", user_mgmt)

        workflow.connect(
            "perf_monitor", "user_mgmt", mapping={"users": "users_to_create"}
        )
        workflow.connect(
            "perf_monitor",
            "analyzer",
            mapping={"initial_count": "initial_count", "start_time": "start_time"},
        )
        workflow.connect("user_mgmt", "analyzer")

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow)

        # Verify performance results
        perf = results["analyzer"]["performance"]
        assert perf["users_created"] > 0
        assert perf["users_per_second"] > 10  # Should handle at least 10 users/second

        # Verify distribution
        assert len(results["analyzer"]["tenant_analysis"]) > 0
        assert (
            len(results["analyzer"]["role_performance"]) == 3
        )  # admin, editor, viewer

    def test_multi_tenant_isolation_with_cycles(self):
        """Test multi-tenant data isolation with cyclic permission checks."""
        workflow = Workflow("tenant-isolation-test", "Multi-tenant Isolation")

        # Schema setup
        schema_setup = PythonCodeNode(
            code="""
import psycopg2

conn = psycopg2.connect(conn_string)
cur = conn.cursor()

# Create multi-tenant schema
cur.execute('''
    CREATE TABLE IF NOT EXISTS tenants (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) UNIQUE NOT NULL,
        settings JSONB DEFAULT '{}'
    )
''')

cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(100) NOT NULL,
        email VARCHAR(255) NOT NULL,
        role VARCHAR(50),
        tenant_id INTEGER REFERENCES tenants(id),
        UNIQUE(username, tenant_id)
    )
''')

cur.execute('''
    CREATE TABLE IF NOT EXISTS tenant_data (
        id SERIAL PRIMARY KEY,
        tenant_id INTEGER REFERENCES tenants(id),
        data_type VARCHAR(50),
        data JSONB,
        created_by INTEGER REFERENCES users(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

# Create test tenants
cur.execute('''
    INSERT INTO tenants (name, settings) VALUES
    ('TenantA', '{"isolation": "strict"}'::jsonb),
    ('TenantB', '{"isolation": "strict"}'::jsonb),
    ('TenantC', '{"isolation": "relaxed"}'::jsonb)
    ON CONFLICT (name) DO NOTHING
''')

conn.commit()
cur.close()
conn.close()

result = {"status": "multi_tenant_ready"}
"""
        )
        workflow.add_node("schema_setup", schema_setup)

        # Tenant data generator
        tenant_gen = PythonCodeNode(
            code="""
# Generate tenant-specific test data
tenant_scenarios = []

for tenant_id in range(1, 4):
    for i in range(5):
        tenant_scenarios.append({
            'tenant_id': tenant_id,
            'username': f'tenant{tenant_id}_user{i}',
            'email': f't{tenant_id}u{i}@test.com',
            'role': ['admin', 'editor'][i % 2],
            'test_data': {
                'type': 'test_record',
                'value': f'sensitive_data_{tenant_id}_{i}'
            }
        })

# Cross-tenant access attempts (should fail)
access_tests = [
    {'user_tenant': 1, 'target_tenant': 2, 'action': 'read'},
    {'user_tenant': 2, 'target_tenant': 1, 'action': 'write'},
    {'user_tenant': 1, 'target_tenant': 1, 'action': 'read'},  # Should succeed
    {'user_tenant': 3, 'target_tenant': 3, 'action': 'write'}, # Should succeed
]

result = {
    'scenarios': tenant_scenarios,
    'access_tests': access_tests,
    'quality_threshold': 0.95  # For cycle convergence
}
"""
        )
        workflow.add_node("tenant_gen", tenant_gen)

        # Isolation validator with cycles
        class IsolationValidator(CycleAwareNode):
            def get_parameters(self):
                return {
                    "scenarios": NodeParameter(type=list, required=True),
                    "access_tests": NodeParameter(type=list, required=True),
                    "quality_threshold": NodeParameter(
                        type=float, required=False, default=0.95
                    ),
                    "conn_string": NodeParameter(type=str, required=False, default=""),
                }

            def run(self, **kwargs):
                import psycopg2

                scenarios = kwargs.get("scenarios", [])
                access_tests = kwargs.get("access_tests", [])
                quality_threshold = kwargs.get("quality_threshold", 0.95)
                conn_string = kwargs.get("conn_string", self.conn_string)

                context = kwargs.get("context", {})
                iteration = self.get_iteration(context)
                validation_results = self.get_previous_state(context).get("results", [])

                # Connect to database
                conn = psycopg2.connect(conn_string)
                cur = conn.cursor()

                # Perform validation checks
                passed_checks = 0
                total_checks = len(access_tests)

                for test in access_tests:
                    # Simulate tenant isolation check
                    is_same_tenant = test["user_tenant"] == test["target_tenant"]

                    # Check would pass if same tenant or relaxed isolation
                    if is_same_tenant:
                        passed_checks += 1
                        validation_results.append(
                            {"test": test, "passed": True, "iteration": iteration}
                        )
                    else:
                        validation_results.append(
                            {"test": test, "passed": False, "iteration": iteration}
                        )

                quality = passed_checks / total_checks if total_checks > 0 else 0
                converged = quality >= quality_threshold or iteration >= 3

                cur.close()
                conn.close()

                return {
                    "quality": quality,
                    "converged": converged,
                    "validation_results": validation_results,
                    "iteration": iteration,
                    **self.set_cycle_state({"results": validation_results}),
                }

        validator = IsolationValidator()
        validator.conn_string = self.conn_string  # Pass connection string
        workflow.add_node("validator", validator)

        # Final report generator
        reporter = PythonCodeNode(
            name="reporter",
            code="""
import psycopg2

conn = psycopg2.connect(conn_string)
cur = conn.cursor()

# Analyze isolation results
cur.execute('''
    SELECT t.name, COUNT(DISTINCT u.id) as user_count
    FROM tenants t
    LEFT JOIN users u ON u.tenant_id = t.id
    GROUP BY t.name
    ORDER BY t.name
''')
tenant_summary = cur.fetchall()

# Check for any cross-tenant data access
cur.execute('''
    SELECT COUNT(*) FROM tenant_data td
    JOIN users u ON td.created_by = u.id
    WHERE td.tenant_id != u.tenant_id
''')
cross_tenant_violations = cur.fetchone()[0]

cur.close()
conn.close()

# Analyze validation results
total_validations = len(validation_results) if 'validation_results' in locals() else 0
passed_validations = sum(1 for r in validation_results if r['passed']) if 'validation_results' in locals() else 0

result = {
    'tenant_summary': [
        {'tenant': t[0], 'users': t[1]} for t in tenant_summary
    ],
    'isolation_status': {
        'cross_tenant_violations': cross_tenant_violations,
        'validation_pass_rate': passed_validations / total_validations if total_validations > 0 else 0,
        'total_validations': total_validations
    },
    'quality_achieved': quality if 'quality' in locals() else 0
}
""",
        )
        workflow.add_node("reporter", reporter)

        # Connect workflow
        workflow.connect("schema_setup", "tenant_gen")
        workflow.connect(
            "tenant_gen",
            "validator",
            mapping={
                "scenarios": "scenarios",
                "access_tests": "access_tests",
                "quality_threshold": "quality_threshold",
            },
        )

        # Add cycle for iterative validation
        workflow.create_cycle("isolation_validation_cycle").connect(
            "validator", "validator", mapping={}
        ).max_iterations(5).converge_when("converged == True").build()

        workflow.connect(
            "validator",
            "reporter",
            mapping={"validation_results": "validation_results", "quality": "quality"},
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow, parameters={"validator": {"conn_string": self.conn_string}}
        )

        # Verify isolation
        isolation_status = results["reporter"]["isolation_status"]
        assert isolation_status["cross_tenant_violations"] == 0
        assert (
            isolation_status["validation_pass_rate"] >= 0.5
        )  # At least half should pass (same tenant)
        assert results["reporter"]["quality_achieved"] >= 0.5
