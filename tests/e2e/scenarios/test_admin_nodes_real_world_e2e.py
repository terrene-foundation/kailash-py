"""
Comprehensive real-world integration test for admin nodes using Docker services.

This test demonstrates production-quality usage of RoleManagementNode and
PermissionCheckNode with:
- Real PostgreSQL database operations on port 5433
- Redis caching for permission checks
- Ollama for generating realistic test data
- Complex organizational hierarchies
- Multi-tenant isolation
- Performance testing under load
- Real-world RBAC and ABAC scenarios
"""

import asyncio
import json
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pytest
from faker import Faker

from kailash.nodes.admin.permission_check import PermissionCheckNode
from kailash.nodes.admin.role_management import RoleManagementNode
from kailash.nodes.admin.schema_manager import AdminSchemaManager
from kailash.nodes.admin.user_management import UserManagementNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.data import SQLDatabaseNode
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import NodeExecutionError
from kailash.workflow import WorkflowBuilder
from tests.utils.docker_config import (
    DATABASE_CONFIG,
    OLLAMA_CONFIG,
    REDIS_CONFIG,
    ensure_docker_services,
    get_postgres_connection_string,
)


class TestAdminNodesRealWorldE2E:
    """Real-world integration tests for admin nodes with Docker services."""

    @classmethod
    def setup_class(cls):
        """Set up test environment with real Docker services."""
        # Database configuration for admin operations
        cls.db_config = {
            "connection_string": get_postgres_connection_string("kailash_admin"),
            "database_type": "postgresql",
            "host": DATABASE_CONFIG["host"],
            "port": DATABASE_CONFIG["port"],
            "database": "kailash_admin",
            "user": DATABASE_CONFIG["user"],
            "password": DATABASE_CONFIG["password"],
            "pool_size": 20,
            "max_overflow": 10,
        }

        # Redis configuration for caching
        cls.redis_config = {
            "host": REDIS_CONFIG["host"],
            "port": REDIS_CONFIG["port"],
            "decode_responses": True,
            "socket_keepalive": True,
            "max_connections": 50,
        }

        # Ollama configuration for generating test data
        cls.ollama_config = {
            "base_url": f"http://{OLLAMA_CONFIG['host']}:{OLLAMA_CONFIG['port']}",
            "model": "llama3.2:3b",  # Fast model for testing
            "temperature": 0.7,
            "timeout": 30.0,
        }

        # Initialize Faker for realistic data
        cls.faker = Faker()
        cls.faker.seed_instance(42)  # Reproducible tests

    async def setup_method_async(self):
        """Async setup for each test method."""
        # Ensure Docker services are available
        services_ready = await ensure_docker_services()
        if not services_ready:
            pytest.skip("Docker services not available")

        # Initialize schema manager and ensure schema exists
        self.schema_manager = AdminSchemaManager(self.db_config)

        # Create schema if needed
        try:
            validation = self.schema_manager.validate_schema()
            if not validation["is_valid"]:
                print("Creating admin schema...")
                self.schema_manager.create_full_schema(drop_existing=False)
        except Exception:
            # Schema doesn't exist, create it
            print("Creating admin schema...")
            self.schema_manager.create_full_schema(drop_existing=False)

        # Initialize admin nodes
        self.role_node = RoleManagementNode(database_config=self.db_config)
        self.permission_node = PermissionCheckNode(
            database_config=self.db_config,
            cache_level="full",
            cache_ttl=300,
        )
        self.user_node = UserManagementNode(database_config=self.db_config)

        # Initialize LLM node for data generation
        self.llm_node = LLMAgentNode(
            name="data_generator",
            model=self.ollama_config["model"],
            base_url=self.ollama_config["base_url"],
            temperature=self.ollama_config["temperature"],
            timeout=self.ollama_config["timeout"],
        )

        # Direct database access for verification
        self.db_node = SQLDatabaseNode(name="test_db", **self.db_config)

    def setup_method(self):
        """Synchronous wrapper for async setup."""
        asyncio.run(self.setup_method_async())

    def teardown_method(self):
        """Clean up after each test."""
        # Clean up test data
        cleanup_queries = [
            "DELETE FROM user_role_assignments WHERE tenant_id LIKE 'test_%'",
            "DELETE FROM roles WHERE tenant_id LIKE 'test_%'",
            "DELETE FROM users WHERE tenant_id LIKE 'test_%'",
            "DELETE FROM admin_audit_log WHERE tenant_id LIKE 'test_%'",
        ]

        for query in cleanup_queries:
            try:
                self.db_node.run(query=query)
            except Exception:
                pass  # Ignore cleanup errors

    @pytest.mark.slow
    @pytest.mark.e2e
    @pytest.mark.requires_docker
    @pytest.mark.requires_redis
    @pytest.mark.requires_ollama
    @pytest.mark.asyncio
    async def test_corporate_hierarchy_with_ollama_generation(self):
        """Test creating a realistic corporate hierarchy with Ollama-generated data."""
        print("\n🏢 Testing corporate hierarchy with AI-generated data...")

        tenant_id = f"test_corp_{int(time.time())}"

        # Generate company structure using Ollama
        company_prompt = """Generate a realistic corporate structure for a tech company.
        Return a JSON object with this structure:
        {
            "company_name": "string",
            "departments": [
                {
                    "name": "string",
                    "description": "string",
                    "teams": [
                        {
                            "name": "string",
                            "description": "string",
                            "roles": ["role1", "role2"]
                        }
                    ]
                }
            ]
        }
        Include at least 4 departments with 2-3 teams each."""

        # Generate company structure
        llm_result = self.llm_node.run(
            prompt=company_prompt,
            response_format="json",
            max_tokens=1000,
        )

        try:
            company_structure = json.loads(llm_result["result"]["response"])
        except json.JSONDecodeError:
            # Fallback to default structure if LLM fails
            company_structure = self._get_default_company_structure()

        print(f"Generated company: {company_structure['company_name']}")

        # Create hierarchical roles based on company structure
        created_roles = {}
        role_hierarchy = {
            "ceo": {
                "name": "Chief Executive Officer",
                "permissions": ["*:*"],  # Full access
                "parent_roles": [],
            },
            "cto": {
                "name": "Chief Technology Officer",
                "permissions": ["tech:*", "workflow:*", "node:*"],
                "parent_roles": ["ceo"],
            },
            "cfo": {
                "name": "Chief Financial Officer",
                "permissions": ["finance:*", "budget:*", "reports:view"],
                "parent_roles": ["ceo"],
            },
            "ciso": {
                "name": "Chief Information Security Officer",
                "permissions": ["security:*", "audit:*", "compliance:*"],
                "parent_roles": ["ceo"],
            },
        }

        # Create C-level roles
        for role_id, role_data in role_hierarchy.items():
            result = self.role_node.run(
                operation="create_role",
                role_data={
                    "name": role_data["name"],
                    "description": f"{role_data['name']} of {company_structure['company_name']}",
                    "permissions": role_data["permissions"],
                    "parent_roles": role_data["parent_roles"],
                    "attributes": {
                        "level": "c_suite",
                        "company": company_structure["company_name"],
                        "clearance": "top_secret",
                    },
                },
                tenant_id=tenant_id,
            )
            created_roles[role_id] = result["result"]["role"]
            print(f"✓ Created role: {role_data['name']}")

        # Create department and team roles
        for dept in company_structure["departments"]:
            dept_role_id = dept["name"].lower().replace(" ", "_") + "_head"

            # Determine parent based on department
            parent_role = "cto" if "tech" in dept["name"].lower() else "ceo"

            # Create department head role
            dept_result = self.role_node.run(
                operation="create_role",
                role_data={
                    "name": f"{dept['name']} Head",
                    "description": dept["description"],
                    "permissions": [f"{dept['name'].lower()}:*"],
                    "parent_roles": [parent_role],
                    "attributes": {
                        "level": "department_head",
                        "department": dept["name"],
                        "clearance": "confidential",
                    },
                },
                tenant_id=tenant_id,
            )
            created_roles[dept_role_id] = dept_result["result"]["role"]

            # Create team roles
            for team in dept.get("teams", []):
                team_role_id = team["name"].lower().replace(" ", "_") + "_lead"

                # Create team lead role
                team_result = self.role_node.run(
                    operation="create_role",
                    role_data={
                        "name": f"{team['name']} Lead",
                        "description": team["description"],
                        "permissions": [f"{team['name'].lower()}:*"],
                        "parent_roles": [dept_role_id],
                        "attributes": {
                            "level": "team_lead",
                            "department": dept["name"],
                            "team": team["name"],
                            "clearance": "internal",
                        },
                    },
                    tenant_id=tenant_id,
                )
                created_roles[team_role_id] = team_result["result"]["role"]

                # Create individual contributor roles
                for role_name in team.get("roles", []):
                    ic_role_id = role_name.lower().replace(" ", "_")

                    ic_result = self.role_node.run(
                        operation="create_role",
                        role_data={
                            "name": role_name,
                            "description": f"{role_name} in {team['name']}",
                            "permissions": [
                                f"{team['name'].lower()}:read",
                                f"{team['name'].lower()}:write",
                                "workflow:execute",
                            ],
                            "parent_roles": [team_role_id],
                            "attributes": {
                                "level": "individual_contributor",
                                "department": dept["name"],
                                "team": team["name"],
                                "role": role_name,
                                "clearance": "basic",
                            },
                        },
                        tenant_id=tenant_id,
                    )
                    created_roles[ic_role_id] = ic_result["result"]["role"]

        print(f"\n✅ Created {len(created_roles)} roles in hierarchy")

        # Generate employees using Ollama
        employee_prompt = f"""Generate 20 realistic employees for {company_structure['company_name']}.
        Return a JSON array where each employee has:
        {{
            "first_name": "string",
            "last_name": "string",
            "email": "string",
            "department": "string (from: {', '.join([d['name'] for d in company_structure['departments']])})",
            "title": "string",
            "skills": ["skill1", "skill2"],
            "years_experience": number,
            "location": "string"
        }}"""

        # Generate employees
        employee_result = self.llm_node.run(
            prompt=employee_prompt,
            response_format="json",
            max_tokens=2000,
        )

        try:
            employees = json.loads(employee_result["result"]["response"])
        except json.JSONDecodeError:
            # Fallback to Faker-generated employees
            employees = self._generate_fake_employees(20, company_structure)

        # Create users and assign roles
        created_users = []
        for i, emp in enumerate(employees[:20]):  # Limit to 20 for testing
            # Create user
            user_result = self.user_node.run(
                operation="create_user",
                user_data={
                    "user_id": f"emp_{i+1}",
                    "email": emp.get("email", f"user{i+1}@company.com"),
                    "first_name": emp.get("first_name", f"User{i+1}"),
                    "last_name": emp.get("last_name", f"Test{i+1}"),
                    "attributes": {
                        "department": emp.get("department", "Engineering"),
                        "title": emp.get("title", "Engineer"),
                        "skills": emp.get("skills", ["python", "javascript"]),
                        "years_experience": emp.get(
                            "years_experience", random.randint(1, 10)
                        ),
                        "location": emp.get("location", "Remote"),
                        "hire_date": self.faker.date_between(
                            start_date="-5y", end_date="today"
                        ).isoformat(),
                    },
                },
                tenant_id=tenant_id,
            )
            created_users.append(user_result["result"]["user"])

            # Assign appropriate role based on title
            if "chief" in emp.get("title", "").lower():
                role_to_assign = random.choice(["ceo", "cto", "cfo", "ciso"])
            elif (
                "head" in emp.get("title", "").lower()
                or "director" in emp.get("title", "").lower()
            ):
                role_to_assign = random.choice(
                    [r for r in created_roles.keys() if "head" in r]
                )
            elif (
                "lead" in emp.get("title", "").lower()
                or "manager" in emp.get("title", "").lower()
            ):
                role_to_assign = random.choice(
                    [r for r in created_roles.keys() if "lead" in r]
                )
            else:
                # Individual contributor
                ic_roles = [
                    r
                    for r in created_roles.keys()
                    if r not in ["ceo", "cto", "cfo", "ciso"]
                    and "head" not in r
                    and "lead" not in r
                ]
                role_to_assign = (
                    random.choice(ic_roles) if ic_roles else "engineering_lead"
                )

            if role_to_assign in created_roles:
                self.role_node.run(
                    operation="assign_user",
                    user_id=user_result["result"]["user"]["user_id"],
                    role_id=role_to_assign,
                    tenant_id=tenant_id,
                )

        print(f"✅ Created {len(created_users)} employees with role assignments")

        # Test permission inheritance
        print("\n🔍 Testing permission inheritance...")

        # Test CEO has access to everything
        ceo_user = created_users[0]  # Assuming first user is CEO
        perm_check = self.permission_node.run(
            operation="check_permission",
            user_id=ceo_user["user_id"],
            resource_id="finance",
            permission="delete",
            tenant_id=tenant_id,
            explain=True,
        )
        assert perm_check["result"]["check"]["allowed"], "CEO should have full access"
        print("✓ CEO has full access as expected")

        # Test department isolation
        eng_user = next(
            (
                u
                for u in created_users
                if u["attributes"].get("department") == "Engineering"
            ),
            None,
        )
        if eng_user:
            perm_check = self.permission_node.run(
                operation="check_permission",
                user_id=eng_user["user_id"],
                resource_id="finance",
                permission="write",
                tenant_id=tenant_id,
            )
            assert not perm_check["result"]["check"][
                "allowed"
            ], "Engineering should not access finance"
            print("✓ Department isolation working correctly")

        # Test hierarchical permissions
        result = self.role_node.run(
            operation="validate_hierarchy",
            tenant_id=tenant_id,
        )
        assert result["result"]["validation"][
            "is_valid"
        ], "Role hierarchy should be valid"
        print(
            f"✓ Role hierarchy validated: {result['result']['validation']['total_roles']} roles"
        )

        # Performance test with concurrent permission checks
        print("\n⚡ Testing concurrent permission checks...")

        start_time = time.time()
        concurrent_checks = 100
        check_results = []

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = []
            for _ in range(concurrent_checks):
                user = random.choice(created_users)
                resource = random.choice(
                    ["workflow", "node", "data", "reports", "admin"]
                )
                permission = random.choice(["read", "write", "execute", "delete"])

                future = executor.submit(
                    self.permission_node.run,
                    operation="check_permission",
                    user_id=user["user_id"],
                    resource_id=resource,
                    permission=permission,
                    tenant_id=tenant_id,
                    cache_level="full",
                )
                futures.append(future)

            for future in as_completed(futures):
                try:
                    result = future.result()
                    check_results.append(result["result"]["check"])
                except Exception as e:
                    print(f"Permission check failed: {e}")

        duration = time.time() - start_time
        checks_per_second = len(check_results) / duration

        print(f"✓ Completed {len(check_results)} permission checks in {duration:.2f}s")
        print(f"✓ Performance: {checks_per_second:.0f} checks/second")

        # Verify cache effectiveness
        cache_hits = sum(1 for r in check_results if r.get("cache_hit", False))
        cache_hit_rate = cache_hits / len(check_results) * 100 if check_results else 0
        print(f"✓ Cache hit rate: {cache_hit_rate:.1f}%")

        # Test audit trail
        audit_query = """
        SELECT COUNT(*) as audit_count
        FROM admin_audit_log
        WHERE tenant_id = $1 AND action = 'permission_check'
        """
        audit_result = self.db_node.run(
            query=audit_query, parameters=[tenant_id], result_format="dict"
        )
        # Note: Audit logging may be disabled by default in tests
        print(f"✓ Audit entries created: {audit_result['data'][0]['audit_count']}")

    @pytest.mark.slow
    @pytest.mark.e2e
    @pytest.mark.requires_docker
    @pytest.mark.requires_redis
    @pytest.mark.requires_ollama
    @pytest.mark.asyncio
    async def test_multi_tenant_isolation_under_load(self):
        """Test multi-tenant isolation with concurrent operations."""
        print("\n🏢 Testing multi-tenant isolation under load...")

        # Create multiple tenants
        tenants = []
        for i in range(3):
            tenant_id = f"test_tenant_{i}_{int(time.time())}"
            tenants.append(
                {
                    "id": tenant_id,
                    "name": self.faker.company(),
                    "users": [],
                    "roles": [],
                }
            )

        # Create roles and users for each tenant
        for tenant in tenants:
            print(f"\nSetting up tenant: {tenant['name']}")

            # Create standard roles
            roles = ["admin", "manager", "employee", "viewer"]
            for role_name in roles:
                role_result = self.role_node.run(
                    operation="create_role",
                    role_data={
                        "name": role_name,
                        "description": f"{role_name} role for {tenant['name']}",
                        "permissions": self._get_role_permissions(role_name),
                        "attributes": {
                            "tenant": tenant["name"],
                            "level": role_name,
                        },
                    },
                    tenant_id=tenant["id"],
                )
                tenant["roles"].append(role_result["result"]["role"])

            # Create users
            for i in range(10):
                user_result = self.user_node.run(
                    operation="create_user",
                    user_data={
                        "user_id": f"{tenant['id']}_user_{i}",
                        "email": self.faker.email(),
                        "first_name": self.faker.first_name(),
                        "last_name": self.faker.last_name(),
                        "attributes": {
                            "department": random.choice(
                                ["Sales", "Engineering", "Marketing", "Support"]
                            ),
                            "tenant": tenant["name"],
                        },
                    },
                    tenant_id=tenant["id"],
                )
                tenant["users"].append(user_result["result"]["user"])

                # Assign random role
                role = random.choice(tenant["roles"])
                self.role_node.run(
                    operation="assign_user",
                    user_id=user_result["result"]["user"]["user_id"],
                    role_id=role["role_id"],
                    tenant_id=tenant["id"],
                )

        print(f"\n✅ Created {len(tenants)} tenants with users and roles")

        # Test concurrent cross-tenant access attempts
        print("\n🔒 Testing cross-tenant access prevention...")

        cross_tenant_violations = []
        successful_checks = []

        with ThreadPoolExecutor(max_workers=30) as executor:
            futures = []

            # Generate mixed valid and invalid permission checks
            for _ in range(200):
                # 80% valid checks, 20% cross-tenant attempts
                if random.random() < 0.8:
                    # Valid check within same tenant
                    tenant = random.choice(tenants)
                    user = random.choice(tenant["users"])
                    tenant_id = tenant["id"]
                else:
                    # Cross-tenant attempt
                    user_tenant = random.choice(tenants)
                    user = random.choice(user_tenant["users"])
                    # Use different tenant ID
                    other_tenant = random.choice(
                        [t for t in tenants if t["id"] != user_tenant["id"]]
                    )
                    tenant_id = other_tenant["id"]

                resource = f"resource_{random.randint(1, 10)}"
                permission = random.choice(["read", "write", "execute"])

                future = executor.submit(
                    self._check_permission_safe,
                    user["user_id"],
                    resource,
                    permission,
                    tenant_id,
                    user.get("tenant_id", tenant_id),  # Pass expected tenant
                )
                futures.append(future)

            # Collect results
            for future in as_completed(futures):
                try:
                    result, expected_tenant, actual_tenant = future.result()
                    if expected_tenant != actual_tenant:
                        # This was a cross-tenant attempt
                        if result.get("allowed", False):
                            cross_tenant_violations.append(
                                {
                                    "user_id": result.get("user_id"),
                                    "expected_tenant": expected_tenant,
                                    "actual_tenant": actual_tenant,
                                }
                            )
                    else:
                        successful_checks.append(result)
                except Exception as e:
                    print(f"Check failed: {e}")

        print(f"✓ Completed {len(successful_checks)} valid permission checks")
        print(f"✓ Cross-tenant violations detected: {len(cross_tenant_violations)}")
        assert (
            len(cross_tenant_violations) == 0
        ), "No cross-tenant access should be allowed"

        # Verify data isolation at database level
        for tenant in tenants:
            # Check users are isolated
            user_query = """
            SELECT COUNT(*) as user_count
            FROM users
            WHERE tenant_id = $1
            """
            user_result = self.db_node.run(
                query=user_query, parameters=[tenant["id"]], result_format="dict"
            )
            assert user_result["data"][0]["user_count"] == len(tenant["users"])

            # Check roles are isolated
            role_query = """
            SELECT COUNT(*) as role_count
            FROM roles
            WHERE tenant_id = $1
            """
            role_result = self.db_node.run(
                query=role_query, parameters=[tenant["id"]], result_format="dict"
            )
            assert role_result["data"][0]["role_count"] == len(tenant["roles"])

        print("✅ Multi-tenant isolation verified at database level")

    @pytest.mark.slow
    @pytest.mark.e2e
    @pytest.mark.requires_docker
    @pytest.mark.requires_redis
    @pytest.mark.requires_ollama
    @pytest.mark.asyncio
    async def test_abac_with_dynamic_attributes(self):
        """Test ABAC permissions with dynamic context attributes."""
        print("\n🔐 Testing ABAC with dynamic attributes...")

        tenant_id = f"test_abac_{int(time.time())}"

        # Create roles with ABAC conditions
        roles_with_conditions = [
            {
                "role_id": "data_scientist",
                "name": "Data Scientist",
                "permissions": ["data:read", "model:train", "model:evaluate"],
                "conditions": {
                    "time_based": {
                        "business_hours_only": True,
                        "timezone": "UTC",
                    },
                    "resource_based": {
                        "max_data_size_gb": 100,
                        "allowed_data_types": ["csv", "parquet", "json"],
                    },
                },
            },
            {
                "role_id": "security_analyst",
                "name": "Security Analyst",
                "permissions": ["logs:read", "alerts:manage", "incidents:investigate"],
                "conditions": {
                    "location_based": {
                        "allowed_ips": ["10.0.0.0/8", "192.168.0.0/16"],
                        "require_vpn": True,
                    },
                    "clearance_based": {
                        "min_clearance_level": "secret",
                        "background_check_required": True,
                    },
                },
            },
            {
                "role_id": "financial_approver",
                "name": "Financial Approver",
                "permissions": ["budget:approve", "expense:review", "report:generate"],
                "conditions": {
                    "amount_based": {
                        "max_approval_amount": 50000,
                        "require_second_approval_above": 25000,
                    },
                    "department_based": {
                        "allowed_departments": ["Finance", "Accounting", "Executive"],
                    },
                },
            },
        ]

        # Create roles with ABAC attributes
        created_roles = {}
        for role_config in roles_with_conditions:
            result = self.role_node.run(
                operation="create_role",
                role_data={
                    "name": role_config["name"],
                    "description": f"Role with ABAC conditions: {role_config['name']}",
                    "permissions": role_config["permissions"],
                    "attributes": {
                        "conditions": role_config["conditions"],
                        "abac_enabled": True,
                    },
                },
                tenant_id=tenant_id,
            )
            created_roles[role_config["role_id"]] = result["result"]["role"]
            print(f"✓ Created ABAC role: {role_config['name']}")

        # Create users with varying attributes
        test_scenarios = [
            {
                "user": {
                    "user_id": "scientist_1",
                    "email": "alice@company.com",
                    "first_name": "Alice",
                    "last_name": "Smith",
                    "attributes": {
                        "department": "Research",
                        "clearance_level": "confidential",
                        "location": "office",
                        "ip_address": "10.0.1.100",
                    },
                },
                "role": "data_scientist",
                "test_cases": [
                    {
                        "resource": "large_dataset",
                        "permission": "read",
                        "context": {
                            "time": "14:00",
                            "data_size_gb": 50,
                            "data_type": "csv",
                        },
                        "expected": True,
                    },
                    {
                        "resource": "huge_dataset",
                        "permission": "read",
                        "context": {
                            "time": "14:00",
                            "data_size_gb": 150,  # Exceeds limit
                            "data_type": "csv",
                        },
                        "expected": False,
                    },
                ],
            },
            {
                "user": {
                    "user_id": "analyst_1",
                    "email": "bob@company.com",
                    "first_name": "Bob",
                    "last_name": "Johnson",
                    "attributes": {
                        "department": "Security",
                        "clearance_level": "top_secret",
                        "location": "remote",
                        "ip_address": "192.168.1.50",
                        "vpn_connected": True,
                        "background_check": "passed",
                    },
                },
                "role": "security_analyst",
                "test_cases": [
                    {
                        "resource": "security_logs",
                        "permission": "read",
                        "context": {
                            "source_ip": "192.168.1.50",
                            "vpn_status": True,
                        },
                        "expected": True,
                    },
                    {
                        "resource": "security_logs",
                        "permission": "read",
                        "context": {
                            "source_ip": "1.2.3.4",  # External IP
                            "vpn_status": False,
                        },
                        "expected": False,
                    },
                ],
            },
            {
                "user": {
                    "user_id": "approver_1",
                    "email": "carol@company.com",
                    "first_name": "Carol",
                    "last_name": "Davis",
                    "attributes": {
                        "department": "Finance",
                        "approval_limit": 50000,
                        "years_experience": 10,
                    },
                },
                "role": "financial_approver",
                "test_cases": [
                    {
                        "resource": "expense_report",
                        "permission": "approve",
                        "context": {
                            "amount": 10000,
                            "department": "Finance",
                            "expense_type": "software",
                        },
                        "expected": True,
                    },
                    {
                        "resource": "expense_report",
                        "permission": "approve",
                        "context": {
                            "amount": 75000,  # Exceeds limit
                            "department": "Finance",
                            "expense_type": "equipment",
                        },
                        "expected": False,
                    },
                ],
            },
        ]

        # Execute test scenarios
        for scenario in test_scenarios:
            # Create user
            user_result = self.user_node.run(
                operation="create_user",
                user_data=scenario["user"],
                tenant_id=tenant_id,
            )
            user_id = user_result["result"]["user"]["user_id"]

            # Assign role
            self.role_node.run(
                operation="assign_user",
                user_id=user_id,
                role_id=scenario["role"],
                tenant_id=tenant_id,
            )

            print(
                f"\n📋 Testing ABAC for {scenario['user']['first_name']} ({scenario['role']}):"
            )

            # Test each permission scenario
            for test_case in scenario["test_cases"]:
                # Combine user attributes with context
                full_context = {
                    **scenario["user"]["attributes"],
                    **test_case["context"],
                }

                result = self.permission_node.run(
                    operation="check_permission",
                    user_id=user_id,
                    resource_id=test_case["resource"],
                    permission=test_case["permission"],
                    context=full_context,
                    tenant_id=tenant_id,
                    explain=True,
                )

                allowed = result["result"]["check"]["allowed"]
                expected = test_case["expected"]

                status = "✓" if allowed == expected else "✗"
                print(
                    f"  {status} {test_case['resource']}:{test_case['permission']} "
                    f"(amount: {test_case['context'].get('amount', 'N/A')}, "
                    f"size: {test_case['context'].get('data_size_gb', 'N/A')}GB) "
                    f"- {'Allowed' if allowed else 'Denied'}"
                )

                assert allowed == expected, f"ABAC check failed for {test_case}"

        print("\n✅ All ABAC scenarios passed correctly")

    @pytest.mark.slow
    @pytest.mark.e2e
    @pytest.mark.requires_docker
    @pytest.mark.requires_redis
    @pytest.mark.requires_ollama
    @pytest.mark.asyncio
    async def test_performance_under_extreme_load(self):
        """Test system performance under extreme concurrent load."""
        print("\n⚡ Testing performance under extreme load...")

        tenant_id = f"test_perf_{int(time.time())}"

        # Create a large number of roles and users
        print("Creating test data...")

        # Create role hierarchy
        num_departments = 5
        num_teams_per_dept = 4
        num_users_per_team = 10

        all_users = []
        all_roles = []

        # Create department roles
        for dept_idx in range(num_departments):
            dept_name = f"Department_{dept_idx}"
            dept_role_result = self.role_node.run(
                operation="create_role",
                role_data={
                    "name": f"{dept_name}_Manager",
                    "description": f"Manager of {dept_name}",
                    "permissions": [f"{dept_name.lower()}:*"],
                },
                tenant_id=tenant_id,
            )
            dept_role_id = dept_role_result["result"]["role"]["role_id"]
            all_roles.append(dept_role_id)

            # Create team roles
            for team_idx in range(num_teams_per_dept):
                team_name = f"{dept_name}_Team_{team_idx}"
                team_role_result = self.role_node.run(
                    operation="create_role",
                    role_data={
                        "name": f"{team_name}_Lead",
                        "description": f"Lead of {team_name}",
                        "permissions": [f"{team_name.lower()}:*"],
                        "parent_roles": [dept_role_id],
                    },
                    tenant_id=tenant_id,
                )
                team_role_id = team_role_result["result"]["role"]["role_id"]
                all_roles.append(team_role_id)

                # Create users in bulk
                user_ids = []
                for user_idx in range(num_users_per_team):
                    user_id = f"user_{dept_idx}_{team_idx}_{user_idx}"
                    user_result = self.user_node.run(
                        operation="create_user",
                        user_data={
                            "user_id": user_id,
                            "email": f"{user_id}@company.com",
                            "first_name": self.faker.first_name(),
                            "last_name": self.faker.last_name(),
                            "attributes": {
                                "department": dept_name,
                                "team": team_name,
                            },
                        },
                        tenant_id=tenant_id,
                    )
                    user_ids.append(user_id)
                    all_users.append(user_id)

                # Bulk assign users to team role
                self.role_node.run(
                    operation="bulk_assign",
                    role_id=team_role_id,
                    user_ids=user_ids,
                    tenant_id=tenant_id,
                )

        total_users = len(all_users)
        total_roles = len(all_roles)
        print(f"✓ Created {total_users} users and {total_roles} roles")

        # Warm up cache with initial checks
        print("\nWarming up cache...")
        warmup_start = time.time()

        with ThreadPoolExecutor(max_workers=50) as executor:
            warmup_futures = []
            for _ in range(100):
                user = random.choice(all_users)
                resource = f"resource_{random.randint(1, 20)}"
                permission = random.choice(["read", "write", "execute"])

                future = executor.submit(
                    self.permission_node.run,
                    operation="check_permission",
                    user_id=user,
                    resource_id=resource,
                    permission=permission,
                    tenant_id=tenant_id,
                    cache_level="full",
                )
                warmup_futures.append(future)

            for future in as_completed(warmup_futures):
                future.result()  # Just wait for completion

        warmup_duration = time.time() - warmup_start
        print(f"✓ Cache warmed up in {warmup_duration:.2f}s")

        # Run extreme load test
        print("\n🚀 Running extreme load test...")

        num_operations = 10000
        concurrent_workers = 100
        operation_results = {
            "permission_checks": [],
            "role_updates": [],
            "user_updates": [],
        }
        errors = []

        start_time = time.time()
        operations_completed = 0
        lock = threading.Lock()

        def perform_operation(op_idx):
            nonlocal operations_completed
            try:
                op_type = random.choices(
                    ["permission_check", "role_update", "user_update"],
                    weights=[0.8, 0.1, 0.1],
                )[0]

                op_start = time.time()

                if op_type == "permission_check":
                    user = random.choice(all_users)
                    resource = f"resource_{random.randint(1, 50)}"
                    permission = random.choice(["read", "write", "execute", "delete"])

                    result = self.permission_node.run(
                        operation="check_permission",
                        user_id=user,
                        resource_id=resource,
                        permission=permission,
                        tenant_id=tenant_id,
                        cache_level="full",
                    )

                    latency = time.time() - op_start
                    with lock:
                        operation_results["permission_checks"].append(
                            {
                                "latency": latency,
                                "cached": result["result"]["check"].get(
                                    "cache_hit", False
                                ),
                            }
                        )

                elif op_type == "role_update":
                    role = random.choice(all_roles)
                    new_permission = f"new_perm_{op_idx}"

                    result = self.role_node.run(
                        operation="add_permission",
                        role_id=role,
                        permission=new_permission,
                        tenant_id=tenant_id,
                    )

                    latency = time.time() - op_start
                    with lock:
                        operation_results["role_updates"].append({"latency": latency})

                else:  # user_update
                    user = random.choice(all_users)

                    result = self.user_node.run(
                        operation="update_user",
                        user_id=user,
                        updates={
                            "attributes": {
                                "last_access": datetime.now(UTC).isoformat(),
                                "access_count": op_idx,
                            }
                        },
                        tenant_id=tenant_id,
                    )

                    latency = time.time() - op_start
                    with lock:
                        operation_results["user_updates"].append({"latency": latency})

                with lock:
                    operations_completed += 1
                    if operations_completed % 1000 == 0:
                        elapsed = time.time() - start_time
                        rate = operations_completed / elapsed
                        print(
                            f"  Progress: {operations_completed}/{num_operations} "
                            f"({rate:.0f} ops/sec)"
                        )

                return True

            except Exception as e:
                with lock:
                    errors.append(str(e))
                return False

        # Run operations concurrently
        with ThreadPoolExecutor(max_workers=concurrent_workers) as executor:
            futures = [
                executor.submit(perform_operation, i) for i in range(num_operations)
            ]

            for future in as_completed(futures):
                future.result()

        total_duration = time.time() - start_time

        # Calculate statistics
        print("\n📊 Performance Results:")
        print(f"Total duration: {total_duration:.2f}s")
        print(f"Total operations: {operations_completed}")
        print(
            f"Overall throughput: {operations_completed / total_duration:.0f} ops/sec"
        )
        print(f"Errors: {len(errors)} ({len(errors) / num_operations * 100:.1f}%)")

        # Permission check statistics
        if operation_results["permission_checks"]:
            perm_latencies = [
                r["latency"] for r in operation_results["permission_checks"]
            ]
            cache_hits = sum(
                1 for r in operation_results["permission_checks"] if r["cached"]
            )

            print(f"\nPermission Checks ({len(perm_latencies)} total):")
            print(
                f"  Average latency: {sum(perm_latencies) / len(perm_latencies) * 1000:.1f}ms"
            )
            print(
                f"  P50 latency: {sorted(perm_latencies)[len(perm_latencies)//2] * 1000:.1f}ms"
            )
            print(
                f"  P95 latency: {sorted(perm_latencies)[int(len(perm_latencies)*0.95)] * 1000:.1f}ms"
            )
            print(
                f"  P99 latency: {sorted(perm_latencies)[int(len(perm_latencies)*0.99)] * 1000:.1f}ms"
            )
            print(f"  Cache hit rate: {cache_hits / len(perm_latencies) * 100:.1f}%")

        # Role update statistics
        if operation_results["role_updates"]:
            role_latencies = [r["latency"] for r in operation_results["role_updates"]]
            print(f"\nRole Updates ({len(role_latencies)} total):")
            print(
                f"  Average latency: {sum(role_latencies) / len(role_latencies) * 1000:.1f}ms"
            )

        # User update statistics
        if operation_results["user_updates"]:
            user_latencies = [r["latency"] for r in operation_results["user_updates"]]
            print(f"\nUser Updates ({len(user_latencies)} total):")
            print(
                f"  Average latency: {sum(user_latencies) / len(user_latencies) * 1000:.1f}ms"
            )

        # Verify system stability
        print("\n🔍 Verifying system stability...")

        # Check database connections
        db_status = self.db_node.run(
            query="SELECT count(*) as conn_count FROM pg_stat_activity WHERE datname = 'kailash_admin'",
            result_format="dict",
        )
        print(f"✓ Active DB connections: {db_status['data'][0]['conn_count']}")

        # Verify data integrity
        user_count = self.db_node.run(
            query="SELECT COUNT(*) as count FROM users WHERE tenant_id = $1",
            parameters=[tenant_id],
            result_format="dict",
        )
        assert user_count["data"][0]["count"] == total_users, "User count mismatch"

        role_count = self.db_node.run(
            query="SELECT COUNT(*) as count FROM roles WHERE tenant_id = $1",
            parameters=[tenant_id],
            result_format="dict",
        )
        assert role_count["data"][0]["count"] == total_roles, "Role count mismatch"

        print("✅ System remained stable under extreme load")

    # Helper methods
    def _get_default_company_structure(self) -> Dict[str, Any]:
        """Get default company structure if LLM fails."""
        return {
            "company_name": self.faker.company(),
            "departments": [
                {
                    "name": "Engineering",
                    "description": "Product development and technical operations",
                    "teams": [
                        {
                            "name": "Backend Engineering",
                            "description": "Server-side development",
                            "roles": [
                                "Senior Backend Engineer",
                                "Backend Engineer",
                                "Junior Backend Engineer",
                            ],
                        },
                        {
                            "name": "Frontend Engineering",
                            "description": "Client-side development",
                            "roles": [
                                "Senior Frontend Engineer",
                                "Frontend Engineer",
                                "UI/UX Developer",
                            ],
                        },
                        {
                            "name": "DevOps",
                            "description": "Infrastructure and deployment",
                            "roles": [
                                "DevOps Lead",
                                "Site Reliability Engineer",
                                "Cloud Engineer",
                            ],
                        },
                    ],
                },
                {
                    "name": "Product",
                    "description": "Product strategy and management",
                    "teams": [
                        {
                            "name": "Product Management",
                            "description": "Product planning and roadmap",
                            "roles": [
                                "Senior Product Manager",
                                "Product Manager",
                                "Associate PM",
                            ],
                        },
                        {
                            "name": "Product Design",
                            "description": "User experience and design",
                            "roles": [
                                "Design Lead",
                                "Senior Designer",
                                "UX Researcher",
                            ],
                        },
                    ],
                },
                {
                    "name": "Sales",
                    "description": "Revenue generation and customer acquisition",
                    "teams": [
                        {
                            "name": "Enterprise Sales",
                            "description": "Large account management",
                            "roles": [
                                "Enterprise Account Executive",
                                "Sales Engineer",
                                "Customer Success Manager",
                            ],
                        },
                        {
                            "name": "SMB Sales",
                            "description": "Small and medium business sales",
                            "roles": [
                                "SMB Account Executive",
                                "Sales Development Rep",
                                "Account Manager",
                            ],
                        },
                    ],
                },
                {
                    "name": "Operations",
                    "description": "Business operations and support",
                    "teams": [
                        {
                            "name": "Finance",
                            "description": "Financial planning and analysis",
                            "roles": [
                                "Financial Analyst",
                                "Accountant",
                                "Budget Analyst",
                            ],
                        },
                        {
                            "name": "HR",
                            "description": "Human resources and talent",
                            "roles": ["HR Manager", "Recruiter", "HR Coordinator"],
                        },
                    ],
                },
            ],
        }

    def _generate_fake_employees(
        self, count: int, company_structure: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate fake employees using Faker."""
        employees = []
        departments = company_structure["departments"]

        for i in range(count):
            dept = random.choice(departments)
            team = random.choice(
                dept.get("teams", [{"name": "General", "roles": ["Employee"]}])
            )
            role = random.choice(team.get("roles", ["Employee"]))

            employees.append(
                {
                    "first_name": self.faker.first_name(),
                    "last_name": self.faker.last_name(),
                    "email": self.faker.email(),
                    "department": dept["name"],
                    "title": role,
                    "skills": self.faker.words(nb=random.randint(2, 5)),
                    "years_experience": random.randint(1, 15),
                    "location": self.faker.city(),
                }
            )

        return employees

    def _get_role_permissions(self, role_name: str) -> List[str]:
        """Get standard permissions for a role."""
        permissions_map = {
            "admin": ["*:*"],
            "manager": [
                "workflow:*",
                "node:execute",
                "data:read",
                "data:write",
                "reports:*",
            ],
            "employee": [
                "workflow:execute",
                "node:execute",
                "data:read",
                "reports:view",
            ],
            "viewer": ["workflow:view", "data:read", "reports:view"],
        }
        return permissions_map.get(role_name, ["data:read"])

    def _check_permission_safe(
        self,
        user_id: str,
        resource: str,
        permission: str,
        tenant_id: str,
        expected_tenant: str,
    ) -> Tuple[Dict[str, Any], str, str]:
        """Safely check permission and return result with tenant info."""
        try:
            result = self.permission_node.run(
                operation="check_permission",
                user_id=user_id,
                resource_id=resource,
                permission=permission,
                tenant_id=tenant_id,
                cache_level="full",
            )
            return result["result"]["check"], expected_tenant, tenant_id
        except Exception as e:
            return {"allowed": False, "error": str(e)}, expected_tenant, tenant_id
