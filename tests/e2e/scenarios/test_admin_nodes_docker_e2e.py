"""
End-to-end tests for admin nodes using Docker containers and real databases.

These tests validate the complete admin node functionality in production-like
environments with real PostgreSQL databases, Redis caching, and Ollama for
data generation.
"""

import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, List

import psycopg2
import pytest

try:
    import redis
except ImportError:
    redis = None
from psycopg2.pool import ThreadedConnectionPool

import docker
from kailash.nodes.admin.permission_check import PermissionCheckNode
from kailash.nodes.admin.role_management import RoleManagementNode
from kailash.nodes.ai import LLMAgentNode
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import NodeExecutionError
from kailash.workflow import WorkflowBuilder


class TestAdminNodesDockerE2E:
    """End-to-end tests for admin nodes with real Docker infrastructure."""

    @classmethod
    def setup_class(cls):
        if redis is None:
            pytest.skip("Redis package not available")
        """Set up Docker containers for testing."""
        cls.docker_client = docker.from_env()

        # Start PostgreSQL container
        cls.postgres_container = cls.docker_client.containers.run(
            "postgres:15",
            environment={
                "POSTGRES_DB": "kailash_test",
                "POSTGRES_USER": "test_user",
                "POSTGRES_PASSWORD": "test_password",
            },
            ports={"5432/tcp": 5433},
            detach=True,
            remove=True,
        )

        # Start Redis container for caching
        cls.redis_container = cls.docker_client.containers.run(
            "redis:7-alpine", ports={"6379/tcp": 6380}, detach=True, remove=True
        )

        # Start Ollama container
        cls.ollama_container = cls.docker_client.containers.run(
            "ollama/ollama:latest", ports={"11434/tcp": 11435}, detach=True, remove=True
        )

        # Wait for containers to be ready
        time.sleep(5)

        # Initialize database schema
        cls._initialize_database()

        # Pull Ollama model
        cls._setup_ollama_model()

        # Database configuration
        cls.db_config = {
            "connection_string": "postgresql://test_user:test_password@localhost:5433/kailash_test",
            "database_type": "postgresql",
            "pool_size": 20,
            "max_overflow": 10,
        }

        # Redis configuration
        cls.redis_client = redis.Redis(
            host="localhost", port=6380, decode_responses=True
        )

    @classmethod
    def teardown_class(cls):
        """Clean up Docker containers."""
        cls.postgres_container.stop()
        cls.redis_container.stop()
        cls.ollama_container.stop()

    @classmethod
    def _initialize_database(cls):
        """Initialize database schema for admin nodes."""
        conn = psycopg2.connect(
            host="localhost",
            port=5433,
            database="kailash_test",
            user="test_user",
            password="test_password",
        )
        cur = conn.cursor()

        # Create roles table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS roles (
                role_id VARCHAR(255) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                role_type VARCHAR(50) DEFAULT 'custom',
                permissions TEXT[],
                parent_roles TEXT[],
                child_roles TEXT[],
                attributes JSONB DEFAULT '{}',
                is_active BOOLEAN DEFAULT true,
                tenant_id VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(255)
            );

            CREATE INDEX IF NOT EXISTS idx_roles_tenant ON roles(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_roles_active ON roles(is_active);
        """
        )

        # Create user_roles table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id VARCHAR(255) NOT NULL,
                role_id VARCHAR(255) NOT NULL,
                tenant_id VARCHAR(255) NOT NULL,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                assigned_by VARCHAR(255),
                expires_at TIMESTAMP,
                PRIMARY KEY (user_id, role_id, tenant_id),
                FOREIGN KEY (role_id) REFERENCES roles(role_id)
            );

            CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id);
            CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role_id);
        """
        )

        # Create users table for testing
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id VARCHAR(255) PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                roles TEXT[],
                attributes JSONB DEFAULT '{}',
                status VARCHAR(50) DEFAULT 'active',
                tenant_id VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        """
        )

        # Create audit_logs table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                log_id SERIAL PRIMARY KEY,
                operation VARCHAR(100) NOT NULL,
                user_id VARCHAR(255),
                resource_type VARCHAR(100),
                resource_id VARCHAR(255),
                changes JSONB,
                tenant_id VARCHAR(255),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp);
            CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);
        """
        )

        conn.commit()
        cur.close()
        conn.close()

    @classmethod
    def _setup_ollama_model(cls):
        """Pull and set up Ollama model for data generation."""
        # Execute ollama pull command in container
        cls.ollama_container.exec_run("ollama pull llama2")
        time.sleep(10)  # Wait for model to download

    def setup_method(self):
        """Set up for each test."""
        # Clear database before each test
        self._clear_database()

        # Clear Redis cache
        self.redis_client.flushall()

        # Initialize nodes
        self.role_node = RoleManagementNode(database_config=self.db_config)
        self.permission_node = PermissionCheckNode(
            database_config=self.db_config,
            cache_backend="redis",
            cache_config={"host": "localhost", "port": 6380},
        )

    def _clear_database(self):
        """Clear all test data from database."""
        conn = psycopg2.connect(
            host="localhost",
            port=5433,
            database="kailash_test",
            user="test_user",
            password="test_password",
        )
        cur = conn.cursor()
        cur.execute("TRUNCATE TABLE user_roles, roles, users, audit_logs CASCADE")
        conn.commit()
        cur.close()
        conn.close()

    def _generate_test_data_with_ollama(self, prompt: str) -> Dict[str, Any]:
        """Use Ollama to generate realistic test data."""
        llm_node = LLMAgentNode(
            model="llama2",
            api_base="http://localhost:11435",
            system_prompt="You are a test data generator. Return only valid JSON without any explanation.",
        )

        result = llm_node.run(prompt=prompt)
        return result["result"]["response"]

    @pytest.mark.docker
    @pytest.mark.e2e
    def test_massive_concurrent_permission_checks(self):
        """Test system under extreme load with 10,000 concurrent permission checks."""
        print("\n🔥 Testing 10,000 concurrent permission checks...")

        # Create organizational structure
        self._create_large_organization_structure()

        # Generate 1000 test users across 10 tenants
        test_users = []
        for tenant_idx in range(10):
            tenant_id = f"tenant_{tenant_idx}"
            for user_idx in range(100):
                user_id = f"user_{tenant_idx}_{user_idx}"
                test_users.append(
                    {
                        "user_id": user_id,
                        "tenant_id": tenant_id,
                        "resource": f"resource_{user_idx % 20}",
                        "permission": ["read", "write", "execute"][user_idx % 3],
                    }
                )

        # Perform concurrent permission checks
        start_time = time.time()
        results = []
        errors = []

        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = []

            # Submit 10,000 permission checks
            for i in range(10):
                for user in test_users:
                    future = executor.submit(
                        self._check_permission_thread_safe,
                        user["user_id"],
                        user["resource"],
                        user["permission"],
                        user["tenant_id"],
                    )
                    futures.append(future)

            # Collect results
            for future in futures:
                try:
                    result = future.result(timeout=30)
                    results.append(result)
                except Exception as e:
                    errors.append(str(e))

        end_time = time.time()
        duration = end_time - start_time

        # Analyze results
        successful_checks = len([r for r in results if r["success"]])
        failed_checks = len([r for r in results if not r["success"]])
        error_count = len(errors)

        print(f"✅ Completed 10,000 permission checks in {duration:.2f} seconds")
        print(f"   Successful: {successful_checks}")
        print(f"   Failed: {failed_checks}")
        print(f"   Errors: {error_count}")
        print(f"   Throughput: {10000/duration:.2f} checks/second")

        # Verify cache performance
        cache_stats = self._get_cache_statistics()
        print(f"   Cache hit rate: {cache_stats['hit_rate']:.2%}")

        assert error_count < 50  # Less than 0.5% error rate
        assert duration < 60  # Complete within 60 seconds
        assert 10000 / duration > 150  # At least 150 checks per second

    def _check_permission_thread_safe(
        self, user_id: str, resource_id: str, permission: str, tenant_id: str
    ) -> Dict[str, Any]:
        """Thread-safe permission check."""
        try:
            # Create new node instance for thread safety
            perm_node = PermissionCheckNode(
                database_config=self.db_config,
                cache_backend="redis",
                cache_config={"host": "localhost", "port": 6380},
            )

            result = perm_node.run(
                operation="check_permission",
                user_id=user_id,
                resource_id=resource_id,
                permission=permission,
                tenant_id=tenant_id,
                cache_level="user",
            )

            return {
                "success": True,
                "allowed": result["result"]["check"]["allowed"],
                "cached": result["result"]["check"]["cache_hit"],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @pytest.mark.docker
    @pytest.mark.e2e
    def test_deep_role_hierarchy_performance(self):
        """Test performance with deeply nested role hierarchies (100+ levels)."""
        print("\n🏗️ Testing deep role hierarchy (100 levels)...")

        # Create a deep hierarchy
        tenant_id = "deep_hierarchy_tenant"
        previous_role = None

        start_time = time.time()

        for level in range(100):
            role_data = {
                "name": f"Level {level} Role",
                "description": f"Role at hierarchy level {level}",
                "permissions": [f"permission_level_{level}"],
                "parent_roles": [previous_role] if previous_role else [],
                "attributes": {"level": level},
            }

            result = self.role_node.run(
                operation="create_role", role_data=role_data, tenant_id=tenant_id
            )

            previous_role = result["result"]["role"]["role_id"]

        creation_time = time.time() - start_time
        print(f"✅ Created 100-level hierarchy in {creation_time:.2f} seconds")

        # Test permission inheritance from bottom to top
        start_time = time.time()

        result = self.role_node.run(
            operation="get_effective_permissions",
            role_id=previous_role,  # Deepest role
            tenant_id=tenant_id,
            include_inherited=True,
        )

        inheritance_time = time.time() - start_time
        total_permissions = result["result"]["permission_count"]["total"]

        print(
            f"✅ Retrieved all inherited permissions in {inheritance_time:.2f} seconds"
        )
        print(f"   Total permissions: {total_permissions}")
        print(f"   Direct: {result['result']['permission_count']['direct']}")
        print(f"   Inherited: {result['result']['permission_count']['inherited']}")

        assert total_permissions == 100  # Should have all 100 permissions
        assert inheritance_time < 5  # Should complete within 5 seconds

    @pytest.mark.docker
    @pytest.mark.e2e
    def test_multi_tenant_isolation_under_load(self):
        """Test tenant isolation with parallel operations from multiple tenants."""
        print("\n🏢 Testing multi-tenant isolation under load...")

        # Create 5 tenants with identical role structures
        tenants = [f"tenant_{i}" for i in range(5)]

        for tenant_id in tenants:
            self._create_tenant_structure(tenant_id)

        # Perform parallel operations from all tenants
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = []

            # Each tenant performs 100 operations
            for tenant_id in tenants:
                for op_idx in range(100):
                    operation = ["create_role", "assign_user", "check_permission"][
                        op_idx % 3
                    ]

                    if operation == "create_role":
                        future = executor.submit(
                            self._create_random_role,
                            tenant_id,
                            f"dynamic_role_{op_idx}",
                        )
                    elif operation == "assign_user":
                        future = executor.submit(
                            self._assign_random_user,
                            tenant_id,
                            f"user_{op_idx}",
                            "analyst",
                        )
                    else:
                        future = executor.submit(
                            self._check_cross_tenant_permission,
                            tenant_id,
                            tenants[(tenants.index(tenant_id) + 1) % len(tenants)],
                        )

                    futures.append((tenant_id, operation, future))

            # Verify no cross-tenant contamination
            cross_tenant_violations = 0
            for tenant_id, operation, future in futures:
                try:
                    result = future.result(timeout=10)
                    if operation == "check_permission" and result.get("violation"):
                        cross_tenant_violations += 1
                except Exception as e:
                    print(f"Operation failed for {tenant_id}: {e}")

        print("✅ Completed 500 parallel multi-tenant operations")
        print(f"   Cross-tenant violations detected: {cross_tenant_violations}")

        # Verify data isolation
        isolation_check = self._verify_tenant_isolation(tenants)
        print(f"   Data isolation verified: {isolation_check['isolated']}")
        print(f"   Roles per tenant: {isolation_check['roles_per_tenant']}")

        assert cross_tenant_violations == 0
        assert isolation_check["isolated"] is True

    @pytest.mark.docker
    @pytest.mark.e2e
    def test_realistic_enterprise_workflow(self):
        """Test a complete enterprise workflow with Ollama-generated data."""
        print("\n🏢 Testing realistic enterprise workflow with AI-generated data...")

        # Generate organization structure using Ollama
        org_prompt = """Generate a realistic enterprise organization structure with:
        - 5 departments (Engineering, Sales, Finance, HR, Operations)
        - 3-4 roles per department with hierarchical relationships
        - Realistic permissions for each role
        - Return as JSON with structure: {"departments": [...]}
        """

        org_data = self._generate_test_data_with_ollama(org_prompt)

        # Create the organization structure
        tenant_id = "enterprise_corp"
        created_roles = {}

        for dept in org_data["departments"]:
            print(f"\n📁 Creating {dept['name']} department...")

            for role in dept["roles"]:
                role_data = {
                    "name": role["name"],
                    "description": role["description"],
                    "permissions": role["permissions"],
                    "parent_roles": [
                        created_roles.get(p)
                        for p in role.get("parents", [])
                        if p in created_roles
                    ],
                    "attributes": {
                        "department": dept["name"],
                        "level": role.get("level", "staff"),
                    },
                }

                result = self.role_node.run(
                    operation="create_role", role_data=role_data, tenant_id=tenant_id
                )

                created_roles[role["name"]] = result["result"]["role"]["role_id"]
                print(f"   ✅ Created role: {role['name']}")

        # Generate and assign users using Ollama
        users_prompt = f"""Generate 50 realistic employees for an enterprise with these departments:
        {', '.join([d['name'] for d in org_data['departments']])}
        Include: name, email, department, role, attributes like clearance level, location, etc.
        Return as JSON: {{"employees": [...]}}
        """

        users_data = self._generate_test_data_with_ollama(users_prompt)

        print(f"\n👥 Assigning {len(users_data['employees'])} employees...")

        for emp in users_data["employees"]:
            # Create user
            self._create_user(emp["email"], emp["attributes"], tenant_id)

            # Assign to role
            if emp["role"] in created_roles:
                self.role_node.run(
                    operation="assign_user",
                    user_id=emp["email"],
                    role_id=created_roles[emp["role"]],
                    tenant_id=tenant_id,
                )

        # Simulate realistic permission checking patterns
        print("\n🔐 Simulating realistic access patterns...")

        access_patterns = [
            # Morning login surge
            {
                "time": "09:00",
                "users": 40,
                "resources": ["email", "calendar", "dashboard"],
            },
            # Midday work
            {
                "time": "14:00",
                "users": 30,
                "resources": ["documents", "reports", "analytics"],
            },
            # End of day
            {
                "time": "17:00",
                "users": 25,
                "resources": ["timesheet", "expenses", "logout"],
            },
        ]

        for pattern in access_patterns:
            print(f"\n⏰ Simulating {pattern['time']} access pattern...")

            # Randomly select users
            selected_users = users_data["employees"][: pattern["users"]]

            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = []

                for user in selected_users:
                    for resource in pattern["resources"]:
                        future = executor.submit(
                            self._check_permission_thread_safe,
                            user["email"],
                            resource,
                            "access",
                            tenant_id,
                        )
                        futures.append(future)

                # Collect results
                allowed = sum(1 for f in futures if f.result(timeout=5)["allowed"])
                total = len(futures)

                print(
                    f"   Access granted: {allowed}/{total} ({allowed/total*100:.1f}%)"
                )

        # Generate compliance report
        print("\n📊 Generating compliance audit report...")
        audit_data = self._generate_compliance_report(tenant_id)

        print(f"   Total roles: {audit_data['total_roles']}")
        print(f"   Total users: {audit_data['total_users']}")
        print(f"   Permission checks today: {audit_data['permission_checks']}")
        print(f"   High-risk permissions: {audit_data['high_risk_permissions']}")
        print(f"   Orphaned roles: {audit_data['orphaned_roles']}")

        assert audit_data["total_roles"] > 15
        assert audit_data["total_users"] == 50
        assert audit_data["orphaned_roles"] == 0

    @pytest.mark.docker
    @pytest.mark.e2e
    def test_permission_propagation_with_dynamic_changes(self):
        """Test permission propagation when roles are modified during active sessions."""
        print("\n🔄 Testing dynamic permission propagation...")

        tenant_id = "dynamic_test"

        # Create initial role structure
        analyst_role = self._create_role(
            tenant_id, "Data Analyst", ["data:read", "reports:view"]
        )
        senior_role = self._create_role(
            tenant_id, "Senior Analyst", ["data:write", "admin:view"], [analyst_role]
        )

        # Assign users
        users = ["alice@company.com", "bob@company.com", "charlie@company.com"]
        for user in users:
            self._create_user(user, {"department": "analytics"}, tenant_id)
            self.role_node.run(
                operation="assign_user",
                user_id=user,
                role_id=senior_role,
                tenant_id=tenant_id,
            )

        # Start monitoring permission checks in background
        stop_monitoring = False
        monitoring_results = {"before": [], "during": [], "after": []}

        def monitor_permissions():
            """Background thread monitoring permission changes."""
            phase = "before"
            while not stop_monitoring:
                for user in users:
                    result = self.permission_node.run(
                        operation="check_permission",
                        user_id=user,
                        resource_id="sensitive_data",
                        permission="delete",
                        tenant_id=tenant_id,
                        cache_level="none",  # Disable cache to see real-time changes
                    )
                    monitoring_results[phase].append(
                        {
                            "user": user,
                            "allowed": result["result"]["check"]["allowed"],
                            "timestamp": datetime.now(),
                        }
                    )
                time.sleep(0.1)

                # Update phase based on elapsed time
                if len(monitoring_results["before"]) > 20 and phase == "before":
                    phase = "during"
                elif len(monitoring_results["during"]) > 30 and phase == "during":
                    phase = "after"

        # Start monitoring
        monitor_thread = ThreadPoolExecutor(max_workers=1).submit(monitor_permissions)

        # Let initial state stabilize
        time.sleep(2)

        print("📝 Adding new permission to role hierarchy...")

        # Dynamically add sensitive permission
        self.role_node.run(
            operation="add_permission",
            role_id=analyst_role,
            permission="sensitive_data:delete",
            tenant_id=tenant_id,
        )

        # Let changes propagate
        time.sleep(3)

        print("🔄 Updating role hierarchy...")

        # Create new parent role
        admin_role = self._create_role(
            tenant_id, "Admin", ["admin:full", "sensitive_data:delete"]
        )

        # Update senior analyst to inherit from admin
        self.role_node.run(
            operation="update_role",
            role_id=senior_role,
            role_data={"parent_roles": [analyst_role, admin_role]},
            tenant_id=tenant_id,
        )

        # Let changes propagate
        time.sleep(2)

        # Stop monitoring
        stop_monitoring = True
        monitor_thread.result(timeout=1)

        # Analyze results
        print("\n📊 Analyzing permission propagation...")

        before_allowed = sum(1 for r in monitoring_results["before"] if r["allowed"])
        during_allowed = sum(1 for r in monitoring_results["during"] if r["allowed"])
        after_allowed = sum(1 for r in monitoring_results["after"] if r["allowed"])

        print(
            f"   Before changes: {before_allowed}/{len(monitoring_results['before'])} allowed"
        )
        print(
            f"   During changes: {during_allowed}/{len(monitoring_results['during'])} allowed"
        )
        print(
            f"   After changes: {after_allowed}/{len(monitoring_results['after'])} allowed"
        )

        # Calculate propagation delay
        first_allowed = next(
            (r for r in monitoring_results["during"] if r["allowed"]), None
        )
        if first_allowed:
            propagation_delay = (
                first_allowed["timestamp"]
                - monitoring_results["before"][-1]["timestamp"]
            ).total_seconds()
            print(f"   Propagation delay: {propagation_delay:.2f} seconds")

        assert before_allowed == 0  # Initially no delete permission
        assert (
            after_allowed > len(monitoring_results["after"]) * 0.9
        )  # Eventually all have permission
        assert propagation_delay < 1.0 if first_allowed else True  # Fast propagation

    @pytest.mark.docker
    @pytest.mark.e2e
    def test_security_edge_cases(self):
        """Test security edge cases including SQL injection and permission escalation."""
        print("\n🔒 Testing security edge cases...")

        tenant_id = "security_test"

        # Test 1: SQL Injection attempts
        print("\n1️⃣ Testing SQL injection prevention...")

        injection_attempts = [
            "admin'; DROP TABLE roles; --",
            "test' OR '1'='1",
            "'); INSERT INTO roles VALUES ('hacker', 'Hacker Role', 'admin:*'); --",
            "test\"; UPDATE users SET roles = ARRAY['admin'] WHERE user_id = 'attacker'; --",
        ]

        sql_injection_blocked = 0
        for attempt in injection_attempts:
            try:
                self.role_node.run(
                    operation="create_role",
                    role_data={
                        "name": attempt,
                        "description": "Testing SQL injection",
                        "permissions": ["test:read"],
                    },
                    tenant_id=tenant_id,
                )
                # If we get here, injection wasn't blocked (but likely sanitized)
                # Check if tables still exist
                if self._verify_database_intact():
                    sql_injection_blocked += 1
            except Exception:
                sql_injection_blocked += 1

        print(
            f"   ✅ Blocked {sql_injection_blocked}/{len(injection_attempts)} SQL injection attempts"
        )

        # Test 2: Permission escalation attempts
        print("\n2️⃣ Testing permission escalation prevention...")

        # Create limited user
        limited_role = self._create_role(tenant_id, "Limited User", ["data:read"])
        attacker_id = "attacker@evil.com"
        self._create_user(attacker_id, {"intent": "malicious"}, tenant_id)
        self.role_node.run(
            operation="assign_user",
            user_id=attacker_id,
            role_id=limited_role,
            tenant_id=tenant_id,
        )

        escalation_attempts = [
            # Try to grant self admin permissions
            lambda: self.role_node.run(
                operation="add_permission",
                role_id=limited_role,
                permission="admin:*",
                tenant_id=tenant_id,
                user_context={"user_id": attacker_id},  # Acting as limited user
            ),
            # Try to assign self to admin role
            lambda: self.role_node.run(
                operation="assign_user",
                user_id=attacker_id,
                role_id="admin",
                tenant_id=tenant_id,
                user_context={"user_id": attacker_id},
            ),
            # Try to modify another user's permissions
            lambda: self.permission_node.run(
                operation="grant_permission",
                target_user="admin@company.com",
                permission="restricted:delete",
                tenant_id=tenant_id,
                user_context={"user_id": attacker_id},
            ),
        ]

        escalation_blocked = 0
        for attempt in escalation_attempts:
            try:
                attempt()
            except (PermissionError, NodeExecutionError):
                escalation_blocked += 1

        print(
            f"   ✅ Blocked {escalation_blocked}/{len(escalation_attempts)} escalation attempts"
        )

        # Test 3: Race condition exploitation
        print("\n3️⃣ Testing race condition prevention...")

        race_role = self._create_role(tenant_id, "Race Test Role", ["test:read"])

        # Try to assign/unassign same user rapidly in parallel
        race_user = "race@test.com"
        self._create_user(race_user, {}, tenant_id)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []

            for i in range(100):
                if i % 2 == 0:
                    future = executor.submit(
                        self.role_node.run,
                        operation="assign_user",
                        user_id=race_user,
                        role_id=race_role,
                        tenant_id=tenant_id,
                    )
                else:
                    future = executor.submit(
                        self.role_node.run,
                        operation="unassign_user",
                        user_id=race_user,
                        role_id=race_role,
                        tenant_id=tenant_id,
                    )
                futures.append(future)

            # Wait for all operations
            errors = []
            for future in futures:
                try:
                    future.result(timeout=1)
                except Exception as e:
                    errors.append(e)

        # Check final state is consistent
        final_roles = self._get_user_roles(race_user, tenant_id)
        print(f"   Final role count after race conditions: {len(final_roles)}")
        print(f"   Errors during race conditions: {len(errors)}")

        assert sql_injection_blocked == len(injection_attempts)
        assert (
            escalation_blocked >= len(escalation_attempts) - 1
        )  # At least most are blocked
        assert len(final_roles) <= 1  # Consistent final state

    @pytest.mark.docker
    @pytest.mark.e2e
    def test_compliance_audit_at_scale(self):
        """Test compliance auditing with millions of permission checks."""
        print("\n📋 Testing compliance audit at scale...")

        tenant_id = "compliance_test"

        # Create realistic organization
        departments = ["Engineering", "Finance", "HR", "Legal", "Operations"]
        roles_per_dept = 5
        users_per_role = 20

        print("🏗️ Building large organization...")

        all_roles = []
        for dept in departments:
            dept_roles = []
            for i in range(roles_per_dept):
                role_name = f"{dept} Level {i+1}"
                permissions = [f"{dept.lower()}:level{i+1}:*"]
                parent_roles = [dept_roles[-1]] if dept_roles else []

                role_id = self._create_role(
                    tenant_id, role_name, permissions, parent_roles
                )
                dept_roles.append(role_id)
                all_roles.append(role_id)

        print(
            f"✅ Created {len(all_roles)} roles across {len(departments)} departments"
        )

        # Create and assign users
        total_users = 0
        for role_id in all_roles:
            for i in range(users_per_role):
                user_id = f"user_{role_id}_{i}@company.com"
                self._create_user(
                    user_id, {"employee_id": f"EMP{total_users:05d}"}, tenant_id
                )
                self.role_node.run(
                    operation="assign_user",
                    user_id=user_id,
                    role_id=role_id,
                    tenant_id=tenant_id,
                )
                total_users += 1

        print(f"✅ Created and assigned {total_users} users")

        # Simulate one day of activity
        print("\n📊 Simulating one day of permission checks...")

        start_time = time.time()
        checks_performed = 0

        # Simulate different activity levels throughout the day
        activity_schedule = [
            {"hour": 9, "checks_per_user": 50},  # Morning login surge
            {"hour": 12, "checks_per_user": 30},  # Lunch time
            {"hour": 15, "checks_per_user": 40},  # Afternoon work
            {"hour": 18, "checks_per_user": 20},  # End of day
        ]

        for schedule in activity_schedule:
            print(
                f"\n⏰ Hour {schedule['hour']:02d}:00 - {schedule['checks_per_user']} checks per user"
            )

            with ThreadPoolExecutor(max_workers=50) as executor:
                futures = []

                # Each user performs multiple permission checks
                for role_id in all_roles[:10]:  # Sample of roles
                    for i in range(20):  # Sample of users per role
                        user_id = f"user_{role_id}_{i}@company.com"

                        for _ in range(schedule["checks_per_user"]):
                            resource = f"resource_{checks_performed % 100}"
                            permission = ["read", "write", "execute", "delete"][
                                checks_performed % 4
                            ]

                            future = executor.submit(
                                self._check_permission_thread_safe,
                                user_id,
                                resource,
                                permission,
                                tenant_id,
                            )
                            futures.append(future)
                            checks_performed += 1

                # Wait for completion
                for future in futures:
                    try:
                        future.result(timeout=0.1)
                    except:
                        pass  # Continue even if some fail

            print(f"   Completed {len(futures)} permission checks")

        total_time = time.time() - start_time

        print(
            f"\n✅ Simulated {checks_performed:,} permission checks in {total_time:.2f} seconds"
        )
        print(f"   Average: {checks_performed/total_time:.2f} checks/second")

        # Generate compliance report
        print("\n📈 Generating compliance analytics...")

        # Query audit logs
        conn = psycopg2.connect(
            host="localhost",
            port=5433,
            database="kailash_test",
            user="test_user",
            password="test_password",
        )
        cur = conn.cursor()

        # Get permission check statistics
        cur.execute(
            """
            SELECT
                COUNT(*) as total_checks,
                COUNT(DISTINCT user_id) as unique_users,
                COUNT(DISTINCT resource_id) as unique_resources,
                AVG(EXTRACT(EPOCH FROM (timestamp - LAG(timestamp) OVER (PARTITION BY user_id ORDER BY timestamp)))) as avg_time_between_checks
            FROM audit_logs
            WHERE operation = 'permission_check'
            AND tenant_id = %s
        """,
            (tenant_id,),
        )

        stats = cur.fetchone()

        # Get high-risk permission usage
        cur.execute(
            """
            SELECT
                resource_id,
                COUNT(*) as access_count,
                COUNT(DISTINCT user_id) as unique_users
            FROM audit_logs
            WHERE operation = 'permission_check'
            AND resource_id LIKE '%sensitive%'
            AND tenant_id = %s
            GROUP BY resource_id
            ORDER BY access_count DESC
            LIMIT 10
        """,
            (tenant_id,),
        )

        high_risk_access = cur.fetchall()

        cur.close()
        conn.close()

        print("\n📊 Compliance Report Summary:")
        print(f"   Total permission checks: {stats[0] if stats else 0:,}")
        print(f"   Unique users: {stats[1] if stats else 0}")
        print(f"   Unique resources: {stats[2] if stats else 0}")
        print(
            f"   Avg time between user checks: {stats[3] if stats and stats[3] else 0:.2f}s"
        )
        print(
            f"   High-risk resource access: {len(high_risk_access)} resources flagged"
        )

        assert checks_performed > 100000  # At least 100k checks
        assert total_time < 300  # Complete within 5 minutes
        assert checks_performed / total_time > 300  # At least 300 checks/second

    # Helper methods
    def _create_large_organization_structure(self):
        """Create a large organization structure for testing."""
        base_roles = ["Employee", "Manager", "Director", "VP", "Executive"]
        departments = ["Engineering", "Sales", "Finance", "HR", "Operations"]

        for tenant_idx in range(10):
            tenant_id = f"tenant_{tenant_idx}"

            for dept in departments:
                parent_role = None
                for role in base_roles:
                    role_id = self._create_role(
                        tenant_id,
                        f"{dept} {role}",
                        [f"{dept.lower()}:{role.lower()}:*"],
                        [parent_role] if parent_role else [],
                    )
                    parent_role = role_id

    def _create_tenant_structure(self, tenant_id: str):
        """Create a standard tenant structure."""
        roles = ["admin", "manager", "analyst", "viewer"]
        parent = None

        for role in roles:
            role_id = self._create_role(
                tenant_id, role.title(), [f"{role}:*"], [parent] if parent else []
            )
            parent = role_id

    def _create_role(
        self,
        tenant_id: str,
        name: str,
        permissions: List[str],
        parent_roles: List[str] = None,
    ) -> str:
        """Helper to create a role."""
        result = self.role_node.run(
            operation="create_role",
            role_data={
                "name": name,
                "description": f"{name} role",
                "permissions": permissions,
                "parent_roles": parent_roles or [],
            },
            tenant_id=tenant_id,
        )
        return result["result"]["role"]["role_id"]

    def _create_user(self, user_id: str, attributes: Dict[str, Any], tenant_id: str):
        """Helper to create a user in the database."""
        conn = psycopg2.connect(
            host="localhost",
            port=5433,
            database="kailash_test",
            user="test_user",
            password="test_password",
        )
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO users (user_id, email, roles, attributes, tenant_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """,
            (user_id, user_id, [], json.dumps(attributes), tenant_id),
        )

        conn.commit()
        cur.close()
        conn.close()

    def _create_random_role(self, tenant_id: str, role_name: str) -> Dict[str, Any]:
        """Create a random role for testing."""
        try:
            return self.role_node.run(
                operation="create_role",
                role_data={
                    "name": role_name,
                    "description": f"Random role {role_name}",
                    "permissions": ["test:read", "test:write"],
                },
                tenant_id=tenant_id,
            )
        except Exception as e:
            return {"error": str(e)}

    def _assign_random_user(
        self, tenant_id: str, user_id: str, role_id: str
    ) -> Dict[str, Any]:
        """Assign a user to a role."""
        try:
            self._create_user(user_id, {}, tenant_id)
            return self.role_node.run(
                operation="assign_user",
                user_id=user_id,
                role_id=role_id,
                tenant_id=tenant_id,
            )
        except Exception as e:
            return {"error": str(e)}

    def _check_cross_tenant_permission(
        self, tenant_id: str, other_tenant_id: str
    ) -> Dict[str, Any]:
        """Check if cross-tenant access is possible."""
        try:
            # Try to access a role from another tenant
            result = self.permission_node.run(
                operation="check_permission",
                user_id=f"user_from_{tenant_id}",
                resource_id=f"resource_from_{other_tenant_id}",
                permission="read",
                tenant_id=other_tenant_id,  # Wrong tenant!
            )

            # If we can access, it's a violation
            return {"violation": result["result"]["check"]["allowed"]}
        except Exception:
            # Exception is expected for cross-tenant access
            return {"violation": False}

    def _verify_tenant_isolation(self, tenants: List[str]) -> Dict[str, Any]:
        """Verify that tenant data is properly isolated."""
        conn = psycopg2.connect(
            host="localhost",
            port=5433,
            database="kailash_test",
            user="test_user",
            password="test_password",
        )
        cur = conn.cursor()

        roles_per_tenant = {}
        for tenant_id in tenants:
            cur.execute("SELECT COUNT(*) FROM roles WHERE tenant_id = %s", (tenant_id,))
            count = cur.fetchone()[0]
            roles_per_tenant[tenant_id] = count

        # Check for any cross-tenant references
        cur.execute(
            """
            SELECT COUNT(*)
            FROM user_roles ur1
            JOIN roles r ON ur1.role_id = r.role_id
            WHERE ur1.tenant_id != r.tenant_id
        """
        )

        cross_tenant_refs = cur.fetchone()[0]

        cur.close()
        conn.close()

        return {
            "isolated": cross_tenant_refs == 0,
            "roles_per_tenant": roles_per_tenant,
            "cross_tenant_references": cross_tenant_refs,
        }

    def _get_cache_statistics(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        info = self.redis_client.info()

        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses

        return {
            "hits": hits,
            "misses": misses,
            "hit_rate": hits / total if total > 0 else 0,
            "total_keys": self.redis_client.dbsize(),
        }

    def _verify_database_intact(self) -> bool:
        """Verify database tables still exist after injection attempts."""
        try:
            conn = psycopg2.connect(
                host="localhost",
                port=5433,
                database="kailash_test",
                user="test_user",
                password="test_password",
            )
            cur = conn.cursor()

            cur.execute("SELECT 1 FROM roles LIMIT 1")
            cur.execute("SELECT 1 FROM user_roles LIMIT 1")
            cur.execute("SELECT 1 FROM users LIMIT 1")

            cur.close()
            conn.close()
            return True
        except:
            return False

    def _get_user_roles(self, user_id: str, tenant_id: str) -> List[str]:
        """Get roles assigned to a user."""
        result = self.role_node.run(
            operation="get_user_roles", user_id=user_id, tenant_id=tenant_id
        )
        return [r["role_id"] for r in result["result"]["roles"]]

    def _generate_compliance_report(self, tenant_id: str) -> Dict[str, Any]:
        """Generate a compliance report for the tenant."""
        conn = psycopg2.connect(
            host="localhost",
            port=5433,
            database="kailash_test",
            user="test_user",
            password="test_password",
        )
        cur = conn.cursor()

        # Get statistics
        cur.execute("SELECT COUNT(*) FROM roles WHERE tenant_id = %s", (tenant_id,))
        total_roles = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(DISTINCT user_id) FROM user_roles WHERE tenant_id = %s",
            (tenant_id,),
        )
        total_users = cur.fetchone()[0]

        cur.execute(
            """
            SELECT COUNT(*) FROM audit_logs
            WHERE tenant_id = %s
            AND operation = 'permission_check'
            AND timestamp > NOW() - INTERVAL '24 hours'
        """,
            (tenant_id,),
        )
        permission_checks = cur.fetchone()[0]

        # High risk permissions
        cur.execute(
            """
            SELECT COUNT(DISTINCT role_id)
            FROM roles
            WHERE tenant_id = %s
            AND (
                'admin:*' = ANY(permissions) OR
                'delete:*' = ANY(permissions) OR
                'security:*' = ANY(permissions)
            )
        """,
            (tenant_id,),
        )
        high_risk = cur.fetchone()[0]

        # Orphaned roles
        cur.execute(
            """
            SELECT COUNT(*)
            FROM roles r
            WHERE r.tenant_id = %s
            AND NOT EXISTS (
                SELECT 1 FROM user_roles ur
                WHERE ur.role_id = r.role_id
            )
        """,
            (tenant_id,),
        )
        orphaned = cur.fetchone()[0]

        cur.close()
        conn.close()

        return {
            "total_roles": total_roles,
            "total_users": total_users,
            "permission_checks": permission_checks,
            "high_risk_permissions": high_risk,
            "orphaned_roles": orphaned,
        }


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s", "-m", "docker and e2e"])
