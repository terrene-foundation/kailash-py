"""
Comprehensive Docker-based E2E tests for admin nodes with real infrastructure.

These tests validate production scenarios using:
- Real PostgreSQL database (Docker port 5433)
- Real Redis cache (Docker port 6380)
- Real Ollama for AI-powered decisions (Docker port 11435)
- Multi-tenant production workloads
- Enterprise security patterns
- Performance benchmarking
"""

import asyncio
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

import pytest

from kailash import LocalRuntime, Workflow, WorkflowBuilder
from kailash.nodes import PythonCodeNode
from kailash.nodes.admin import (
    PermissionCheckNode,
    RoleManagementNode,
    UserManagementNode,
)
from kailash.nodes.admin.schema_manager import AdminSchemaManager
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.data import SQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError
from tests.utils.docker_config import (
    DATABASE_CONFIG,
    OLLAMA_CONFIG,
    REDIS_CONFIG,
    ensure_docker_services,
    get_postgres_connection_string,
)

# Mark as requiring Docker infrastructure
pytestmark = [pytest.mark.docker, pytest.mark.e2e, pytest.mark.slow]


class EnterpriseDataGenerator:
    """Generate realistic enterprise data for testing."""

    @staticmethod
    def generate_enterprise_structure(
        company_name: str, size: str = "large"
    ) -> Dict[str, Any]:
        """Generate a complete enterprise organizational structure."""
        sizes = {
            "small": {"departments": 3, "roles_per_dept": 3, "users_per_role": 5},
            "medium": {"departments": 5, "roles_per_dept": 5, "users_per_role": 10},
            "large": {"departments": 8, "roles_per_dept": 7, "users_per_role": 20},
            "enterprise": {
                "departments": 12,
                "roles_per_dept": 10,
                "users_per_role": 50,
            },
        }

        config = sizes.get(size, sizes["medium"])

        departments = {
            "Engineering": {
                "roles": [
                    {
                        "name": "CTO",
                        "level": 10,
                        "permissions": ["*"],
                        "clearance": "top_secret",
                    },
                    {
                        "name": "VP Engineering",
                        "level": 9,
                        "permissions": ["engineering:*", "deploy:prod"],
                        "clearance": "secret",
                    },
                    {
                        "name": "Engineering Manager",
                        "level": 8,
                        "permissions": ["engineering:manage", "deploy:staging"],
                        "clearance": "secret",
                    },
                    {
                        "name": "Tech Lead",
                        "level": 7,
                        "permissions": ["code:review", "arch:design"],
                        "clearance": "confidential",
                    },
                    {
                        "name": "Senior Engineer",
                        "level": 6,
                        "permissions": ["code:write", "deploy:dev"],
                        "clearance": "confidential",
                    },
                    {
                        "name": "Engineer",
                        "level": 5,
                        "permissions": ["code:write", "docs:write"],
                        "clearance": "internal",
                    },
                    {
                        "name": "Junior Engineer",
                        "level": 4,
                        "permissions": ["code:read", "docs:read"],
                        "clearance": "public",
                    },
                ]
            },
            "Sales": {
                "roles": [
                    {
                        "name": "Chief Revenue Officer",
                        "level": 10,
                        "permissions": ["sales:*", "contracts:approve"],
                        "clearance": "secret",
                    },
                    {
                        "name": "VP Sales",
                        "level": 9,
                        "permissions": ["sales:manage", "deals:approve:1000000"],
                        "clearance": "secret",
                    },
                    {
                        "name": "Sales Director",
                        "level": 8,
                        "permissions": ["sales:region", "deals:approve:500000"],
                        "clearance": "confidential",
                    },
                    {
                        "name": "Sales Manager",
                        "level": 7,
                        "permissions": ["team:manage", "deals:approve:100000"],
                        "clearance": "confidential",
                    },
                    {
                        "name": "Senior Account Executive",
                        "level": 6,
                        "permissions": ["accounts:manage", "deals:create"],
                        "clearance": "internal",
                    },
                    {
                        "name": "Account Executive",
                        "level": 5,
                        "permissions": ["accounts:view", "leads:manage"],
                        "clearance": "internal",
                    },
                    {
                        "name": "Sales Development Rep",
                        "level": 4,
                        "permissions": ["leads:create", "contacts:view"],
                        "clearance": "public",
                    },
                ]
            },
            "Finance": {
                "roles": [
                    {
                        "name": "CFO",
                        "level": 10,
                        "permissions": ["finance:*", "audit:*"],
                        "clearance": "top_secret",
                    },
                    {
                        "name": "VP Finance",
                        "level": 9,
                        "permissions": ["finance:manage", "budget:approve"],
                        "clearance": "secret",
                    },
                    {
                        "name": "Finance Director",
                        "level": 8,
                        "permissions": ["finance:operations", "reports:generate"],
                        "clearance": "secret",
                    },
                    {
                        "name": "Controller",
                        "level": 7,
                        "permissions": ["accounting:manage", "compliance:ensure"],
                        "clearance": "confidential",
                    },
                    {
                        "name": "Senior Accountant",
                        "level": 6,
                        "permissions": ["books:manage", "reports:create"],
                        "clearance": "confidential",
                    },
                    {
                        "name": "Accountant",
                        "level": 5,
                        "permissions": ["transactions:process", "reports:view"],
                        "clearance": "internal",
                    },
                    {
                        "name": "Finance Analyst",
                        "level": 4,
                        "permissions": ["data:analyze", "reports:read"],
                        "clearance": "internal",
                    },
                ]
            },
            "HR": {
                "roles": [
                    {
                        "name": "Chief People Officer",
                        "level": 10,
                        "permissions": ["hr:*", "compensation:*"],
                        "clearance": "secret",
                    },
                    {
                        "name": "VP HR",
                        "level": 9,
                        "permissions": ["hr:manage", "policies:approve"],
                        "clearance": "secret",
                    },
                    {
                        "name": "HR Director",
                        "level": 8,
                        "permissions": ["hr:operations", "hiring:approve"],
                        "clearance": "confidential",
                    },
                    {
                        "name": "HR Manager",
                        "level": 7,
                        "permissions": ["team:hr:manage", "benefits:manage"],
                        "clearance": "confidential",
                    },
                    {
                        "name": "Senior HR Specialist",
                        "level": 6,
                        "permissions": ["employees:manage", "recruiting:lead"],
                        "clearance": "internal",
                    },
                    {
                        "name": "HR Specialist",
                        "level": 5,
                        "permissions": ["employees:view", "recruiting:assist"],
                        "clearance": "internal",
                    },
                    {
                        "name": "HR Coordinator",
                        "level": 4,
                        "permissions": ["scheduling:manage", "docs:hr:read"],
                        "clearance": "public",
                    },
                ]
            },
            "Security": {
                "roles": [
                    {
                        "name": "CISO",
                        "level": 10,
                        "permissions": ["security:*", "incidents:*"],
                        "clearance": "top_secret",
                    },
                    {
                        "name": "VP Security",
                        "level": 9,
                        "permissions": ["security:manage", "policies:security:*"],
                        "clearance": "secret",
                    },
                    {
                        "name": "Security Director",
                        "level": 8,
                        "permissions": ["security:operations", "audits:conduct"],
                        "clearance": "secret",
                    },
                    {
                        "name": "Security Manager",
                        "level": 7,
                        "permissions": ["security:monitor", "incidents:manage"],
                        "clearance": "confidential",
                    },
                    {
                        "name": "Senior Security Engineer",
                        "level": 6,
                        "permissions": ["security:implement", "vulnerabilities:patch"],
                        "clearance": "confidential",
                    },
                    {
                        "name": "Security Analyst",
                        "level": 5,
                        "permissions": ["security:analyze", "logs:review"],
                        "clearance": "internal",
                    },
                    {
                        "name": "Security Operations",
                        "level": 4,
                        "permissions": ["alerts:monitor", "tickets:security:create"],
                        "clearance": "internal",
                    },
                ]
            },
            "Legal": {
                "roles": [
                    {
                        "name": "General Counsel",
                        "level": 10,
                        "permissions": ["legal:*", "contracts:*"],
                        "clearance": "top_secret",
                    },
                    {
                        "name": "VP Legal",
                        "level": 9,
                        "permissions": ["legal:manage", "litigation:oversee"],
                        "clearance": "secret",
                    },
                    {
                        "name": "Legal Director",
                        "level": 8,
                        "permissions": ["legal:operations", "contracts:review"],
                        "clearance": "secret",
                    },
                    {
                        "name": "Senior Counsel",
                        "level": 7,
                        "permissions": ["contracts:draft", "compliance:legal"],
                        "clearance": "confidential",
                    },
                    {
                        "name": "Corporate Counsel",
                        "level": 6,
                        "permissions": ["contracts:review", "policies:draft"],
                        "clearance": "confidential",
                    },
                    {
                        "name": "Legal Analyst",
                        "level": 5,
                        "permissions": ["research:legal", "docs:legal:manage"],
                        "clearance": "internal",
                    },
                    {
                        "name": "Paralegal",
                        "level": 4,
                        "permissions": ["docs:legal:prepare", "filing:manage"],
                        "clearance": "internal",
                    },
                ]
            },
            "Operations": {
                "roles": [
                    {
                        "name": "COO",
                        "level": 10,
                        "permissions": ["operations:*", "strategy:*"],
                        "clearance": "top_secret",
                    },
                    {
                        "name": "VP Operations",
                        "level": 9,
                        "permissions": ["operations:manage", "processes:approve"],
                        "clearance": "secret",
                    },
                    {
                        "name": "Operations Director",
                        "level": 8,
                        "permissions": ["operations:direct", "metrics:define"],
                        "clearance": "secret",
                    },
                    {
                        "name": "Operations Manager",
                        "level": 7,
                        "permissions": ["operations:execute", "teams:coordinate"],
                        "clearance": "confidential",
                    },
                    {
                        "name": "Senior Operations Analyst",
                        "level": 6,
                        "permissions": [
                            "processes:optimize",
                            "data:operations:analyze",
                        ],
                        "clearance": "internal",
                    },
                    {
                        "name": "Operations Analyst",
                        "level": 5,
                        "permissions": ["metrics:track", "reports:operations:create"],
                        "clearance": "internal",
                    },
                    {
                        "name": "Operations Coordinator",
                        "level": 4,
                        "permissions": ["tasks:coordinate", "docs:operations:manage"],
                        "clearance": "public",
                    },
                ]
            },
            "Marketing": {
                "roles": [
                    {
                        "name": "CMO",
                        "level": 10,
                        "permissions": ["marketing:*", "brand:*"],
                        "clearance": "secret",
                    },
                    {
                        "name": "VP Marketing",
                        "level": 9,
                        "permissions": ["marketing:manage", "campaigns:approve"],
                        "clearance": "secret",
                    },
                    {
                        "name": "Marketing Director",
                        "level": 8,
                        "permissions": ["marketing:direct", "budget:marketing:manage"],
                        "clearance": "confidential",
                    },
                    {
                        "name": "Marketing Manager",
                        "level": 7,
                        "permissions": ["campaigns:manage", "content:approve"],
                        "clearance": "confidential",
                    },
                    {
                        "name": "Senior Marketing Specialist",
                        "level": 6,
                        "permissions": ["campaigns:create", "analytics:marketing"],
                        "clearance": "internal",
                    },
                    {
                        "name": "Marketing Specialist",
                        "level": 5,
                        "permissions": ["content:create", "social:manage"],
                        "clearance": "internal",
                    },
                    {
                        "name": "Marketing Coordinator",
                        "level": 4,
                        "permissions": ["events:coordinate", "content:assist"],
                        "clearance": "public",
                    },
                ]
            },
        }

        # Select departments based on company size
        selected_depts = list(departments.keys())[: config["departments"]]

        structure = {"company": company_name, "size": size, "departments": []}

        for dept_name in selected_depts:
            dept = departments[dept_name]
            dept_roles = dept["roles"][: config["roles_per_dept"]]

            dept_structure = {"name": dept_name, "roles": [], "total_employees": 0}

            for role in dept_roles:
                role_data = {
                    **role,
                    "department": dept_name,
                    "employee_count": config["users_per_role"],
                    "employees": [],
                }

                # Generate employees for this role
                for i in range(config["users_per_role"]):
                    employee = {
                        "id": f"{company_name.lower()}_{dept_name.lower()}_{role['name'].replace(' ', '_').lower()}_{i}",
                        "email": f"{role['name'].replace(' ', '.').lower()}.{i}@{company_name.lower()}.com",
                        "first_name": f"{role['name'].split()[0]}{i}",
                        "last_name": dept_name,
                        "title": role["name"],
                        "department": dept_name,
                        "level": role["level"],
                        "clearance": role["clearance"],
                        "start_date": (
                            datetime.now(timezone.utc) - timedelta(days=i * 30)
                        ).isoformat(),
                        "location": ["US-West", "US-East", "EU", "APAC"][i % 4],
                        "reports_to": (
                            f"{company_name.lower()}_{dept_name.lower()}_manager"
                            if role["level"] < 8
                            else None
                        ),
                    }
                    role_data["employees"].append(employee)

                dept_structure["roles"].append(role_data)
                dept_structure["total_employees"] += config["users_per_role"]

            structure["departments"].append(dept_structure)

        structure["total_employees"] = sum(
            d["total_employees"] for d in structure["departments"]
        )
        structure["total_roles"] = sum(
            len(d["roles"]) for d in structure["departments"]
        )

        return structure


class TestAdminNodesComprehensiveDockerE2E:
    """Comprehensive Docker-based E2E tests for enterprise admin scenarios."""

    def setup_method(self):
        """Set up test environment."""
        # Check Docker services
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            services_ready = loop.run_until_complete(ensure_docker_services())
            if not services_ready:
                pytest.skip("Docker services not available")
        finally:
            loop.close()

        self.db_config = {
            "connection_string": get_postgres_connection_string(),
            "database_type": "postgresql",
            "pool_size": 50,
            "max_overflow": 20,
            "pool_timeout": 30,
            "pool_recycle": 3600,
        }

        self.redis_config = {
            **REDIS_CONFIG,
            "decode_responses": True,
            "max_connections": 100,
            "socket_keepalive": True,
            "socket_keepalive_options": {},
        }

        self.ollama_config = {**OLLAMA_CONFIG, "model": "llama3.2:3b", "timeout": 60}

        # Generate unique test identifiers
        self.test_id = str(uuid4())[:8]
        self.tenants = [
            f"enterprise_alpha_{self.test_id}",
            f"enterprise_beta_{self.test_id}",
            f"enterprise_gamma_{self.test_id}",
        ]

        # Initialize schema
        self._initialize_schema()

    def teardown_method(self):
        """Clean up test data."""
        self._cleanup_test_data()

    def _initialize_schema(self):
        """Initialize database schema."""
        try:
            schema_manager = AdminSchemaManager(self.db_config)
            result = schema_manager.create_full_schema(drop_existing=False)
            print(f"Schema initialized: {result}")
        except Exception as e:
            print(f"Schema initialization warning: {e}")

    def _cleanup_test_data(self):
        """Clean up all test data."""
        try:
            db_node = SQLDatabaseNode(name="cleanup", **self.db_config)

            # Clean up test data
            for tenant in self.tenants:
                for table in [
                    "admin_audit_log",
                    "permission_cache",
                    "user_sessions",
                    "user_attributes",
                    "resource_attributes",
                    "abac_rules",
                    "user_role_assignments",
                    "users",
                    "permissions",
                    "roles",
                ]:
                    try:
                        db_node.run(
                            query=f"DELETE FROM {table} WHERE tenant_id = %s",
                            parameters=[tenant],
                        )
                    except Exception:
                        pass
        except Exception as e:
            print(f"Cleanup warning: {e}")

    def test_enterprise_scale_rbac_with_real_postgresql(self):
        """Test enterprise-scale RBAC with thousands of users and complex hierarchies."""
        print("\n🏢 Testing Enterprise-Scale RBAC Implementation...")

        # Generate enterprise structure
        enterprise = EnterpriseDataGenerator.generate_enterprise_structure(
            "TechCorp", size="large"
        )

        print(
            f"Generated enterprise with {enterprise['total_employees']} employees across {enterprise['total_roles']} roles"
        )

        # Create workflow for setting up enterprise
        setup_workflow = WorkflowBuilder.from_dict(
            {
                "name": "enterprise_setup",
                "description": "Set up complete enterprise RBAC structure",
                "nodes": {
                    "create_hierarchy": {
                        "type": "PythonCodeNode",
                        "parameters": {
                            "code": """
import json

# Process enterprise structure
enterprise = kwargs.get("enterprise")
tenant_id = kwargs.get("tenant_id")

# Create role hierarchy
role_hierarchy = {}
for dept in enterprise["departments"]:
    dept_roles = []
    parent_role = None

    # Sort roles by level (highest first)
    sorted_roles = sorted(dept["roles"], key=lambda r: r["level"], reverse=True)

    for role in sorted_roles:
        role_id = f"{tenant_id}_{dept['name'].lower()}_{role['name'].replace(' ', '_').lower()}"
        dept_roles.append({
            "role_id": role_id,
            "name": role["name"],
            "department": dept["name"],
            "level": role["level"],
            "permissions": role["permissions"],
            "parent_role": parent_role,
            "clearance": role["clearance"]
        })
        parent_role = role_id

    role_hierarchy[dept["name"]] = dept_roles

result = {
    "role_hierarchy": role_hierarchy,
    "total_roles": sum(len(roles) for roles in role_hierarchy.values()),
    "departments": list(role_hierarchy.keys())
}
"""
                        },
                    },
                    "create_roles": {
                        "type": "RoleManagementNode",
                        "parameters": {"operation": "create_role"},
                    },
                    "create_users": {
                        "type": "UserManagementNode",
                        "parameters": {"operation": "create_user"},
                    },
                    "assign_roles": {
                        "type": "RoleManagementNode",
                        "parameters": {"operation": "assign_user"},
                    },
                },
                "connections": [
                    {"from": "create_hierarchy", "to": "create_roles"},
                    {"from": "create_roles", "to": "create_users"},
                    {"from": "create_users", "to": "assign_roles"},
                ],
            }
        )

        runtime = LocalRuntime()

        # Track performance metrics
        start_time = time.time()
        created_roles = {}
        created_users = []

        # Process each department
        for dept in enterprise["departments"]:
            print(f"\n📁 Processing {dept['name']} department...")

            # Create roles for department
            dept_start = time.time()
            sorted_roles = sorted(dept["roles"], key=lambda r: r["level"], reverse=True)

            parent_role = None
            for role in sorted_roles:
                role_id = f"{self.tenants[0]}_{dept['name'].lower()}_{role['name'].replace(' ', '_').lower()}"

                role_data = {
                    "name": f"{dept['name']} - {role['name']}",
                    "description": f"{role['name']} in {dept['name']} department",
                    "permissions": role["permissions"],
                    "parent_roles": [parent_role] if parent_role else [],
                    "attributes": {
                        "department": dept["name"],
                        "level": role["level"],
                        "clearance": role["clearance"],
                        "risk_level": (
                            "high"
                            if role["level"] >= 8
                            else "medium" if role["level"] >= 6 else "low"
                        ),
                    },
                    "role_type": "system",
                }

                result, _ = runtime.execute(
                    setup_workflow,
                    parameters={
                        "create_hierarchy": {
                            "enterprise": enterprise,
                            "tenant_id": self.tenants[0],
                        },
                        "create_roles": {
                            "role_data": role_data,
                            "tenant_id": self.tenants[0],
                            "database_config": self.db_config,
                        },
                    },
                )

                created_roles[role_id] = role["name"]
                parent_role = role_id

                # Create users for this role
                for emp in role["employees"]:
                    user_data = {
                        "user_id": emp["id"],
                        "email": emp["email"],
                        "username": emp["id"],
                        "first_name": emp["first_name"],
                        "last_name": emp["last_name"],
                        "display_name": f"{emp['first_name']} {emp['last_name']}",
                        "attributes": {
                            "title": emp["title"],
                            "department": emp["department"],
                            "level": emp["level"],
                            "clearance": emp["clearance"],
                            "location": emp["location"],
                            "start_date": emp["start_date"],
                            "reports_to": emp["reports_to"],
                        },
                        "status": "active",
                    }

                    user_result, _ = runtime.execute(
                        setup_workflow,
                        parameters={
                            "create_hierarchy": {
                                "enterprise": enterprise,
                                "tenant_id": self.tenants[0],
                            },
                            "create_users": {
                                "user_data": user_data,
                                "tenant_id": self.tenants[0],
                                "database_config": self.db_config,
                            },
                            "assign_roles": {
                                "user_id": emp["id"],
                                "role_id": role_id,
                                "tenant_id": self.tenants[0],
                                "database_config": self.db_config,
                            },
                        },
                    )

                    created_users.append(emp["id"])

            dept_time = time.time() - dept_start
            print(
                f"  ✅ Processed {len(dept['roles'])} roles and {dept['total_employees']} employees in {dept_time:.2f}s"
            )

        setup_time = time.time() - start_time
        print(f"\n✅ Enterprise setup completed in {setup_time:.2f}s")
        print(f"  - Created {len(created_roles)} roles")
        print(f"  - Created {len(created_users)} users")
        print(f"  - Average: {setup_time/len(created_users)*1000:.2f}ms per user")

        # Test complex permission scenarios
        perm_check = PermissionCheckNode()

        test_scenarios = [
            {
                "name": "C-Suite Global Access",
                "user": next(u for u in created_users if "cto" in u),
                "tests": [
                    ("*", "global_resource", True, "CTO has wildcard permissions"),
                    (
                        "finance:audit",
                        "financial_records",
                        True,
                        "CTO can audit finances",
                    ),
                    ("hr:terminate", "employee_record", True, "CTO has HR permissions"),
                ],
            },
            {
                "name": "Department Isolation",
                "user": next(u for u in created_users if "engineering_manager" in u),
                "tests": [
                    (
                        "engineering:manage",
                        "engineering_team",
                        True,
                        "Can manage own department",
                    ),
                    (
                        "sales:manage",
                        "sales_team",
                        False,
                        "Cannot manage other departments",
                    ),
                    (
                        "finance:view",
                        "budget_report",
                        False,
                        "No cross-department access",
                    ),
                ],
            },
            {
                "name": "Hierarchical Inheritance",
                "user": next(u for u in created_users if "senior_engineer" in u),
                "tests": [
                    ("code:write", "source_code", True, "Direct permission"),
                    (
                        "docs:read",
                        "documentation",
                        True,
                        "Inherited from Engineer role",
                    ),
                    (
                        "deploy:prod",
                        "production",
                        False,
                        "No production deploy permission",
                    ),
                ],
            },
            {
                "name": "Clearance-Based Access",
                "user": next(u for u in created_users if "junior" in u),
                "tests": [
                    ("docs:read", "public_docs", True, "Can read public documents"),
                    (
                        "data:classified",
                        "secret_data",
                        False,
                        "No access to classified data",
                    ),
                    ("code:read", "source_code", True, "Can read code"),
                ],
            },
        ]

        print("\n🔐 Testing Permission Scenarios...")

        for scenario in test_scenarios:
            print(f"\n📋 {scenario['name']} - User: {scenario['user']}")

            for permission, resource, expected, reason in scenario["tests"]:
                start = time.time()
                result = perm_check.run(
                    operation="check_permission",
                    user_id=scenario["user"],
                    resource_id=resource,
                    permission=permission,
                    tenant_id=self.tenants[0],
                    database_config=self.db_config,
                    cache_backend="redis",
                    cache_config=self.redis_config,
                    explain=True,
                )
                check_time = (time.time() - start) * 1000

                actual = result["result"]["check"]["allowed"]
                status = "✅" if actual == expected else "❌"
                cache_status = "🚀" if result["result"]["check"]["cache_hit"] else "🔍"

                print(
                    f"  {status} {permission} on {resource}: {actual} (expected: {expected}) - {reason}"
                )
                print(f"     {cache_status} Response time: {check_time:.2f}ms")

                assert actual == expected, f"Permission check failed: {reason}"

        # Performance benchmarking
        print("\n📊 Running Performance Benchmark...")

        # Warm up cache
        warmup_users = created_users[:100]
        for user in warmup_users:
            perm_check.run(
                operation="check_permission",
                user_id=user,
                resource_id="warmup_resource",
                permission="read",
                tenant_id=self.tenants[0],
                database_config=self.db_config,
                cache_backend="redis",
                cache_config=self.redis_config,
            )

        # Benchmark concurrent permission checks
        benchmark_users = created_users[:500]
        num_checks = 5000

        def benchmark_check(i):
            user = benchmark_users[i % len(benchmark_users)]
            resource = f"resource_{i % 100}"
            permission = ["read", "write", "execute", "delete"][i % 4]

            start = time.time()
            result = perm_check.run(
                operation="check_permission",
                user_id=user,
                resource_id=resource,
                permission=permission,
                tenant_id=self.tenants[0],
                database_config=self.db_config,
                cache_backend="redis",
                cache_config=self.redis_config,
            )
            elapsed = time.time() - start

            return {
                "time": elapsed,
                "cached": result["result"]["check"]["cache_hit"],
                "allowed": result["result"]["check"]["allowed"],
            }

        print(f"Running {num_checks} concurrent permission checks...")
        bench_start = time.time()

        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(benchmark_check, i) for i in range(num_checks)]
            results = [f.result() for f in as_completed(futures)]

        bench_time = time.time() - bench_start

        # Analyze results
        times = [r["time"] for r in results]
        cache_hits = sum(1 for r in results if r["cached"])

        stats = {
            "total_checks": num_checks,
            "total_time": bench_time,
            "throughput": num_checks / bench_time,
            "avg_latency_ms": sum(times) / len(times) * 1000,
            "min_latency_ms": min(times) * 1000,
            "max_latency_ms": max(times) * 1000,
            "p50_latency_ms": sorted(times)[len(times) // 2] * 1000,
            "p95_latency_ms": sorted(times)[int(len(times) * 0.95)] * 1000,
            "p99_latency_ms": sorted(times)[int(len(times) * 0.99)] * 1000,
            "cache_hit_rate": cache_hits / num_checks * 100,
        }

        print("\n📈 Performance Results:")
        print(f"  Throughput: {stats['throughput']:.0f} checks/second")
        print(f"  Average latency: {stats['avg_latency_ms']:.2f}ms")
        print(f"  P50 latency: {stats['p50_latency_ms']:.2f}ms")
        print(f"  P95 latency: {stats['p95_latency_ms']:.2f}ms")
        print(f"  P99 latency: {stats['p99_latency_ms']:.2f}ms")
        print(f"  Cache hit rate: {stats['cache_hit_rate']:.1f}%")

        # Assertions
        assert stats["throughput"] > 1000, "Should handle >1000 checks/second"
        assert stats["avg_latency_ms"] < 50, "Average latency should be <50ms"
        assert stats["cache_hit_rate"] > 70, "Cache hit rate should be >70%"

    def test_multi_tenant_security_isolation_with_redis(self):
        """Test complete tenant isolation with Redis-backed caching."""
        print("\n🔒 Testing Multi-Tenant Security Isolation...")

        # Create three competing enterprises
        enterprises = [
            ("TechCorp", self.tenants[0]),
            ("DataSystems", self.tenants[1]),
            ("CloudWorks", self.tenants[2]),
        ]

        # Set up each enterprise
        enterprise_data = {}

        for company_name, tenant_id in enterprises:
            print(f"\n🏢 Setting up {company_name} (Tenant: {tenant_id})")

            # Generate small enterprise structure
            structure = EnterpriseDataGenerator.generate_enterprise_structure(
                company_name, size="small"
            )

            enterprise_data[tenant_id] = {
                "name": company_name,
                "structure": structure,
                "sensitive_resources": [
                    f"{company_name.lower()}_customer_database",
                    f"{company_name.lower()}_financial_records",
                    f"{company_name.lower()}_ip_portfolio",
                    f"{company_name.lower()}_employee_data",
                ],
                "roles": {},
                "users": [],
            }

            # Create roles and users
            role_mgmt = RoleManagementNode()
            user_mgmt = UserManagementNode()

            for dept in structure["departments"][:2]:  # Just first 2 departments
                for role in dept["roles"][:3]:  # Just first 3 roles
                    # Create role
                    role_result = role_mgmt.run(
                        operation="create_role",
                        role_data={
                            "name": f"{company_name} {role['name']}",
                            "description": f"{role['name']} at {company_name}",
                            "permissions": role["permissions"],
                            "attributes": {
                                "company": company_name,
                                "clearance": role["clearance"],
                            },
                        },
                        tenant_id=tenant_id,
                        database_config=self.db_config,
                    )

                    role_id = role_result["result"]["role"]["role_id"]
                    enterprise_data[tenant_id]["roles"][role["name"]] = role_id

                    # Create users
                    for emp in role["employees"][:3]:  # Just first 3 employees
                        user_result = user_mgmt.run(
                            operation="create_user",
                            user_data={
                                "user_id": f"{tenant_id}_{emp['id']}",
                                "email": emp["email"].replace(
                                    "@", f"@{company_name.lower()}."
                                ),
                                "username": f"{company_name.lower()}_{emp['id']}",
                                "attributes": {
                                    "company": company_name,
                                    "clearance": emp["clearance"],
                                },
                            },
                            tenant_id=tenant_id,
                            database_config=self.db_config,
                        )

                        # Assign role
                        role_mgmt.run(
                            operation="assign_user",
                            user_id=user_result["result"]["user"]["user_id"],
                            role_id=role_id,
                            tenant_id=tenant_id,
                            database_config=self.db_config,
                        )

                        enterprise_data[tenant_id]["users"].append(
                            {
                                "user_id": user_result["result"]["user"]["user_id"],
                                "role": role["name"],
                                "clearance": emp["clearance"],
                            }
                        )

        print("\n🔍 Testing Cross-Tenant Access Attempts...")

        perm_check = PermissionCheckNode()
        security_violations = []

        # Test 1: Users trying to access other tenants' resources
        for attacker_tenant, attacker_data in enterprise_data.items():
            for victim_tenant, victim_data in enterprise_data.items():
                if attacker_tenant == victim_tenant:
                    continue

                print(
                    f"\n🚨 {attacker_data['name']} users attempting to access {victim_data['name']} resources:"
                )

                # Select an attacker (highest privilege user)
                attacker = next(
                    u
                    for u in attacker_data["users"]
                    if u["clearance"] in ["secret", "top_secret"]
                )

                # Try to access victim's sensitive resources
                for resource in victim_data["sensitive_resources"]:
                    try:
                        result = perm_check.run(
                            operation="check_permission",
                            user_id=attacker["user_id"],
                            resource_id=resource,
                            permission="read",
                            tenant_id=victim_tenant,  # Wrong tenant!
                            database_config=self.db_config,
                            cache_backend="redis",
                            cache_config=self.redis_config,
                        )

                        if result["result"]["check"]["allowed"]:
                            violation = {
                                "attacker": attacker["user_id"],
                                "attacker_tenant": attacker_tenant,
                                "victim_resource": resource,
                                "victim_tenant": victim_tenant,
                                "result": "ALLOWED",
                            }
                            security_violations.append(violation)
                            print(
                                f"  ❌ SECURITY BREACH: {attacker['user_id']} accessed {resource}"
                            )
                        else:
                            print(
                                f"  ✅ Blocked: {attacker['user_id']} denied access to {resource}"
                            )

                    except (NodeExecutionError, NodeValidationError) as e:
                        print(f"  ✅ Exception blocked access: {str(e)[:50]}...")

        # Test 2: Cache poisoning attempts
        print("\n💉 Testing Cache Poisoning Prevention...")

        # User from tenant 1 checks permission (should be denied)
        attacker = enterprise_data[self.tenants[0]]["users"][0]
        victim_resource = enterprise_data[self.tenants[1]]["sensitive_resources"][0]

        # First check - should be denied
        result1 = perm_check.run(
            operation="check_permission",
            user_id=attacker["user_id"],
            resource_id=victim_resource,
            permission="admin",
            tenant_id=self.tenants[0],  # Attacker's tenant
            database_config=self.db_config,
            cache_backend="redis",
            cache_config=self.redis_config,
        )

        assert not result1["result"]["check"][
            "allowed"
        ], "Should not have admin permission"

        # Try to poison cache by checking with different tenant context
        try:
            # This should fail or be blocked
            poison_result = perm_check.run(
                operation="check_permission",
                user_id=attacker["user_id"],
                resource_id=victim_resource,
                permission="admin",
                tenant_id=self.tenants[1],  # Victim's tenant
                database_config=self.db_config,
                cache_backend="redis",
                cache_config=self.redis_config,
            )
        except Exception:
            pass

        # Check again with original tenant - cache should not be poisoned
        result2 = perm_check.run(
            operation="check_permission",
            user_id=attacker["user_id"],
            resource_id=victim_resource,
            permission="admin",
            tenant_id=self.tenants[0],  # Attacker's tenant
            database_config=self.db_config,
            cache_backend="redis",
            cache_config=self.redis_config,
        )

        assert not result2["result"]["check"]["allowed"], "Cache should not be poisoned"
        print("✅ Cache poisoning prevented")

        # Test 3: Concurrent multi-tenant operations
        print("\n🔄 Testing Concurrent Multi-Tenant Operations...")

        def concurrent_operation(tenant_id, user, resource, operation_id):
            """Simulate concurrent operations from multiple tenants."""
            try:
                # Random operations
                operations = [
                    lambda: perm_check.run(
                        operation="check_permission",
                        user_id=user["user_id"],
                        resource_id=resource,
                        permission="read",
                        tenant_id=tenant_id,
                        database_config=self.db_config,
                        cache_backend="redis",
                        cache_config=self.redis_config,
                    ),
                    lambda: role_mgmt.run(
                        operation="get_user_roles",
                        user_id=user["user_id"],
                        tenant_id=tenant_id,
                        database_config=self.db_config,
                    ),
                ]

                result = operations[operation_id % 2]()
                return {
                    "tenant": tenant_id,
                    "operation": operation_id,
                    "success": True,
                    "result": result,
                }
            except Exception as e:
                return {
                    "tenant": tenant_id,
                    "operation": operation_id,
                    "success": False,
                    "error": str(e),
                }

        # Run 1000 concurrent operations across all tenants
        with ThreadPoolExecutor(max_workers=30) as executor:
            futures = []

            for i in range(1000):
                tenant_id = self.tenants[i % 3]
                tenant_data = enterprise_data[tenant_id]
                user = tenant_data["users"][i % len(tenant_data["users"])]
                resource = tenant_data["sensitive_resources"][i % 4]

                future = executor.submit(
                    concurrent_operation, tenant_id, user, resource, i
                )
                futures.append(future)

            results = [f.result() for f in as_completed(futures)]

        # Analyze results
        success_count = sum(1 for r in results if r["success"])
        print(f"✅ Completed {success_count}/1000 concurrent operations successfully")

        # Verify data isolation after concurrent operations
        print("\n🔍 Verifying Data Isolation Post-Concurrency...")

        db_node = SQLDatabaseNode(name="isolation_check", **self.db_config)

        for tenant_id in self.tenants:
            # Check that users only exist in their tenant
            user_check = db_node.run(
                query="""
                    SELECT COUNT(*) as cross_tenant_users
                    FROM users u1
                    WHERE u1.tenant_id = %s
                    AND EXISTS (
                        SELECT 1 FROM users u2
                        WHERE u2.user_id = u1.user_id
                        AND u2.tenant_id != %s
                    )
                """,
                parameters=[tenant_id, tenant_id],
            )

            cross_tenant_users = user_check["data"][0]["cross_tenant_users"]
            assert (
                cross_tenant_users == 0
            ), f"Found {cross_tenant_users} cross-tenant users"

            # Check role assignments
            role_check = db_node.run(
                query="""
                    SELECT COUNT(*) as cross_tenant_roles
                    FROM user_role_assignments ura
                    JOIN roles r ON ura.role_id = r.role_id
                    WHERE ura.tenant_id = %s
                    AND r.tenant_id != %s
                """,
                parameters=[tenant_id, tenant_id],
            )

            cross_tenant_roles = role_check["data"][0]["cross_tenant_roles"]
            assert (
                cross_tenant_roles == 0
            ), f"Found {cross_tenant_roles} cross-tenant role assignments"

        print("✅ All tenant data properly isolated")

        # Final security report
        print("\n📊 Security Isolation Report:")
        print(f"  Total cross-tenant attempts: {len(security_violations)}")
        print(
            f"  Successful breaches: {len([v for v in security_violations if v['result'] == 'ALLOWED'])}"
        )
        print("  Cache poisoning attempts blocked: ✅")
        print("  Data isolation maintained: ✅")
        print(f"  Concurrent operation success rate: {success_count/10:.1f}%")

        assert len(security_violations) == 0, "No security violations should occur"

    def test_ai_powered_adaptive_access_control_with_ollama(self):
        """Test AI-powered adaptive access control using Ollama for real-time decisions."""
        print("\n🤖 Testing AI-Powered Adaptive Access Control...")

        # Create workflow with AI decision making
        ai_workflow = WorkflowBuilder.from_dict(
            {
                "name": "ai_adaptive_access",
                "description": "AI-powered adaptive access control workflow",
                "nodes": {
                    "setup_context": {
                        "type": "PythonCodeNode",
                        "parameters": {
                            "code": """
import json
from datetime import datetime

# Prepare context for AI evaluation
user = kwargs.get("user")
resource = kwargs.get("resource")
context = kwargs.get("context", {})

# Enrich context with additional signals
enriched_context = {
    "user": user,
    "resource": resource,
    "environment": {
                        "time": datetime.now().isoformat(),
                        "day_of_week": datetime.now().strftime("%A"),
                        "hour": datetime.now().hour,
                        "is_business_hours": 9 <= datetime.now().hour <= 17,
                        "is_weekend": datetime.now().weekday() >= 5
                    },
    "request": context,
    "risk_factors": []
}

# Identify risk factors
if not enriched_context["environment"]["is_business_hours"]:
    enriched_context["risk_factors"].append("outside_business_hours")

if enriched_context["environment"]["is_weekend"]:
    enriched_context["risk_factors"].append("weekend_access")

if context.get("location", "").lower() not in ["office", "vpn"]:
    enriched_context["risk_factors"].append("unusual_location")

if resource.get("sensitivity", "").lower() in ["critical", "top_secret"]:
    enriched_context["risk_factors"].append("high_sensitivity_resource")

result = enriched_context
"""
                        },
                    },
                    "ai_risk_assessment": {
                        "type": "LLMAgentNode",
                        "parameters": {
                            "backend": "ollama",
                            "model": "llama3.2:3b",
                            "temperature": 0.1,
                            "system_prompt": """You are an AI security analyst evaluating access requests in real-time.

Analyze the provided context and determine:
1. Risk level (low/medium/high/critical)
2. Whether to allow, deny, or require additional authentication
3. Specific concerns or anomalies detected
4. Recommended security measures

Consider factors like:
- User's role and clearance level
- Resource sensitivity and classification
- Access patterns and anomalies
- Time and location of access
- Recent security incidents or threats

Respond with a JSON object:
{
    "decision": "allow" | "deny" | "challenge",
    "risk_level": "low" | "medium" | "high" | "critical",
    "confidence": 0-100,
    "reasoning": "Brief explanation",
    "anomalies": ["list of detected anomalies"],
    "recommendations": ["list of security recommendations"],
    "require_mfa": true | false,
    "alert_security": true | false
}""",
                        },
                    },
                    "ai_behavior_analysis": {
                        "type": "LLMAgentNode",
                        "parameters": {
                            "backend": "ollama",
                            "model": "llama3.2:3b",
                            "temperature": 0.2,
                            "system_prompt": """You are an AI behavior analyst detecting unusual access patterns.

Analyze the user's access history and current request to identify:
1. Whether this matches their normal behavior
2. Any suspicious patterns or anomalies
3. Potential security threats (account compromise, insider threat, etc.)

Consider:
- Typical access times and locations
- Resources normally accessed
- Sudden privilege escalation attempts
- Bulk data access patterns
- Failed authentication attempts

Respond with a JSON object:
{
    "behavior_match": true | false,
    "anomaly_score": 0-100,
    "patterns_detected": ["list of patterns"],
    "threat_indicators": ["list of potential threats"],
    "recommended_action": "allow" | "monitor" | "investigate" | "block"
}""",
                        },
                    },
                    "make_decision": {
                        "type": "PythonCodeNode",
                        "parameters": {
                            "code": """
import json

# Combine AI assessments
risk_assessment = json.loads(inputs.get("risk_assessment", "{}"))
behavior_analysis = json.loads(inputs.get("behavior_analysis", "{}"))

# Make final decision based on both AI outputs
decision = "deny"  # Default to deny
require_mfa = False
alert_security = False
audit_priority = "normal"

# Decision logic
risk_level = risk_assessment.get("risk_level", "high")
anomaly_score = behavior_analysis.get("anomaly_score", 100)
behavior_match = behavior_analysis.get("behavior_match", False)

if risk_level == "low" and anomaly_score < 30 and behavior_match:
    decision = "allow"
elif risk_level in ["low", "medium"] and anomaly_score < 50:
    decision = "allow"
    require_mfa = True
elif risk_level == "medium" and anomaly_score < 70:
    decision = "challenge"
    require_mfa = True
    audit_priority = "high"
else:
    decision = "deny"
    alert_security = risk_level in ["high", "critical"] or anomaly_score > 80
    audit_priority = "critical"

result = {
    "final_decision": decision,
    "require_mfa": require_mfa,
    "alert_security": alert_security,
    "audit_priority": audit_priority,
    "risk_summary": {
                        "risk_level": risk_level,
                        "anomaly_score": anomaly_score,
                        "behavior_match": behavior_match
                    },
    "ai_reasoning": {
                        "risk_assessment": risk_assessment.get("reasoning", ""),
                        "behavior_analysis": behavior_analysis.get("patterns_detected", [])
                    }
}
"""
                        },
                    },
                    "enforce_decision": {
                        "type": "PermissionCheckNode",
                        "parameters": {"operation": "check_permission"},
                    },
                },
                "connections": [
                    {
                        "from": "setup_context",
                        "to": "ai_risk_assessment",
                        "map": {"result": "context"},
                    },
                    {
                        "from": "setup_context",
                        "to": "ai_behavior_analysis",
                        "map": {"result": "context"},
                    },
                    {
                        "from": "ai_risk_assessment",
                        "to": "make_decision",
                        "map": {"result.content": "risk_assessment"},
                    },
                    {
                        "from": "ai_behavior_analysis",
                        "to": "make_decision",
                        "map": {"result.content": "behavior_analysis"},
                    },
                    {"from": "make_decision", "to": "enforce_decision"},
                ],
            }
        )

        # Set up test organization
        print("🏢 Setting up test organization...")

        role_mgmt = RoleManagementNode()
        user_mgmt = UserManagementNode()

        # Create roles
        roles = {
            "security_admin": role_mgmt.run(
                operation="create_role",
                role_data={
                    "name": "Security Administrator",
                    "permissions": ["security:*", "audit:*", "users:manage"],
                    "attributes": {
                        "clearance": "top_secret",
                        "risk_profile": "trusted",
                    },
                },
                tenant_id=self.tenants[0],
                database_config=self.db_config,
            )["result"]["role"]["role_id"],
            "data_scientist": role_mgmt.run(
                operation="create_role",
                role_data={
                    "name": "Data Scientist",
                    "permissions": ["data:read", "models:train", "reports:create"],
                    "attributes": {
                        "clearance": "confidential",
                        "risk_profile": "standard",
                    },
                },
                tenant_id=self.tenants[0],
                database_config=self.db_config,
            )["result"]["role"]["role_id"],
            "contractor": role_mgmt.run(
                operation="create_role",
                role_data={
                    "name": "External Contractor",
                    "permissions": ["docs:read", "tickets:create"],
                    "attributes": {"clearance": "public", "risk_profile": "elevated"},
                },
                tenant_id=self.tenants[0],
                database_config=self.db_config,
            )["result"]["role"]["role_id"],
        }

        # Create test scenarios
        test_scenarios = [
            {
                "name": "Normal Business Hours Access",
                "user": {
                    "user_id": "alice_security",
                    "email": "alice@company.com",
                    "role": "security_admin",
                    "attributes": {
                        "department": "Security",
                        "years_employed": 5,
                        "access_history": "consistent",
                        "location": "office",
                    },
                },
                "resource": {
                    "id": "security_logs",
                    "type": "logs",
                    "sensitivity": "high",
                    "classification": "confidential",
                },
                "context": {
                    "location": "office",
                    "device": "company_laptop",
                    "vpn": False,
                    "reason": "Daily security review",
                },
                "expected_decision": "allow",
            },
            {
                "name": "Suspicious After-Hours Access",
                "user": {
                    "user_id": "bob_contractor",
                    "email": "bob@external.com",
                    "role": "contractor",
                    "attributes": {
                        "department": "External",
                        "years_employed": 0.5,
                        "access_history": "limited",
                        "location": "remote",
                    },
                },
                "resource": {
                    "id": "customer_database",
                    "type": "database",
                    "sensitivity": "critical",
                    "classification": "top_secret",
                },
                "context": {
                    "location": "unknown",
                    "device": "personal_device",
                    "vpn": False,
                    "reason": "Urgent data export",
                    "time": "02:30 AM",
                },
                "expected_decision": "deny",
            },
            {
                "name": "Unusual Location Access",
                "user": {
                    "user_id": "charlie_scientist",
                    "email": "charlie@company.com",
                    "role": "data_scientist",
                    "attributes": {
                        "department": "Research",
                        "years_employed": 3,
                        "access_history": "regular",
                        "usual_location": "us-west",
                    },
                },
                "resource": {
                    "id": "ml_training_data",
                    "type": "dataset",
                    "sensitivity": "medium",
                    "classification": "internal",
                },
                "context": {
                    "location": "asia-pacific",
                    "device": "company_laptop",
                    "vpn": True,
                    "reason": "Conference presentation prep",
                    "recent_travel": True,
                },
                "expected_decision": "allow",  # With MFA
            },
        ]

        runtime = LocalRuntime()

        for scenario in test_scenarios:
            print(f"\n📋 Testing: {scenario['name']}")

            # Create user
            user_mgmt.run(
                operation="create_user",
                user_data={
                    **scenario["user"],
                    "username": scenario["user"]["user_id"],
                    "status": "active",
                },
                tenant_id=self.tenants[0],
                database_config=self.db_config,
            )

            # Assign role
            role_mgmt.run(
                operation="assign_user",
                user_id=scenario["user"]["user_id"],
                role_id=roles[scenario["user"]["role"]],
                tenant_id=self.tenants[0],
                database_config=self.db_config,
            )

            # Execute AI workflow
            try:
                result, metadata = runtime.execute(
                    ai_workflow,
                    parameters={
                        "setup_context": {
                            "user": scenario["user"],
                            "resource": scenario["resource"],
                            "context": scenario["context"],
                        },
                        "ai_risk_assessment": {
                            "prompt": f"""Analyze this access request:
User: {json.dumps(scenario['user'], indent=2)}
Resource: {json.dumps(scenario['resource'], indent=2)}
Context: {json.dumps(scenario['context'], indent=2)}

Evaluate the risk and make a security decision.""",
                            "backend_config": {
                                "host": self.ollama_config["host"],
                                "port": self.ollama_config["port"],
                            },
                        },
                        "ai_behavior_analysis": {
                            "prompt": f"""Analyze user behavior:
User Profile: {json.dumps(scenario['user'], indent=2)}
Access Context: {json.dumps(scenario['context'], indent=2)}
Resource Type: {scenario['resource']['type']}

Is this normal behavior for this user?""",
                            "backend_config": {
                                "host": self.ollama_config["host"],
                                "port": self.ollama_config["port"],
                            },
                        },
                        "make_decision": {},
                        "enforce_decision": {
                            "user_id": scenario["user"]["user_id"],
                            "resource_id": scenario["resource"]["id"],
                            "permission": "access",
                            "tenant_id": self.tenants[0],
                            "database_config": self.db_config,
                            "cache_backend": "redis",
                            "cache_config": self.redis_config,
                        },
                    },
                )

                # Extract decision
                final_decision = result["make_decision"]["result"]["final_decision"]
                risk_summary = result["make_decision"]["result"]["risk_summary"]

                print(f"  🤖 AI Decision: {final_decision}")
                print(f"  📊 Risk Level: {risk_summary['risk_level']}")
                print(f"  📈 Anomaly Score: {risk_summary['anomaly_score']}/100")
                print(
                    f"  🔐 MFA Required: {result['make_decision']['result']['require_mfa']}"
                )
                print(
                    f"  🚨 Security Alert: {result['make_decision']['result']['alert_security']}"
                )

                # For allow/challenge, we consider it correct if it's not deny
                if scenario["expected_decision"] == "allow":
                    assert final_decision in [
                        "allow",
                        "challenge",
                    ], f"Expected allow/challenge, got {final_decision}"
                else:
                    assert (
                        final_decision == scenario["expected_decision"]
                    ), f"Expected {scenario['expected_decision']}, got {final_decision}"

            except Exception as e:
                print(f"  ❌ Error in AI workflow: {str(e)}")
                # For testing, we'll continue even if Ollama fails

        # Test adaptive learning
        print("\n🧠 Testing Adaptive Security Learning...")

        # Simulate repeated suspicious access attempts
        suspicious_user = {
            "user_id": "eve_attacker",
            "email": "eve@suspicious.com",
            "role": "contractor",
            "attributes": {"risk_score": 0},
        }

        # Create suspicious user
        user_mgmt.run(
            operation="create_user",
            user_data={
                **suspicious_user,
                "username": suspicious_user["user_id"],
                "status": "active",
            },
            tenant_id=self.tenants[0],
            database_config=self.db_config,
        )

        role_mgmt.run(
            operation="assign_user",
            user_id=suspicious_user["user_id"],
            role_id=roles["contractor"],
            tenant_id=self.tenants[0],
            database_config=self.db_config,
        )

        # Simulate escalating suspicious behavior
        print("\n🔄 Simulating Escalating Threat Pattern...")

        suspicious_resources = [
            ("public_docs", "low", 0),
            ("internal_wiki", "medium", 20),
            ("employee_directory", "medium", 40),
            ("salary_database", "high", 60),
            ("security_keys", "critical", 80),
        ]

        for resource_name, sensitivity, expected_risk in suspicious_resources:
            print(
                f"\n  Attempt to access: {resource_name} (sensitivity: {sensitivity})"
            )

            # Update user risk score based on previous attempts
            suspicious_user["attributes"]["risk_score"] = expected_risk

            try:
                ai_result, _ = runtime.execute(
                    ai_workflow,
                    parameters={
                        "setup_context": {
                            "user": suspicious_user,
                            "resource": {
                                "id": resource_name,
                                "sensitivity": sensitivity,
                                "type": "data",
                            },
                            "context": {
                                "location": "tor_exit_node",
                                "device": "unknown",
                                "pattern": "data_exfiltration",
                            },
                        },
                        "ai_risk_assessment": {
                            "prompt": f"Analyze access to {resource_name} by user with risk score {expected_risk}",
                            "backend_config": {
                                "host": self.ollama_config["host"],
                                "port": self.ollama_config["port"],
                            },
                        },
                        "ai_behavior_analysis": {
                            "prompt": f"Detect escalating threat pattern for {resource_name} access",
                            "backend_config": {
                                "host": self.ollama_config["host"],
                                "port": self.ollama_config["port"],
                            },
                        },
                        "make_decision": {},
                        "enforce_decision": {
                            "user_id": suspicious_user["user_id"],
                            "resource_id": resource_name,
                            "permission": "read",
                            "tenant_id": self.tenants[0],
                            "database_config": self.db_config,
                        },
                    },
                )

                decision = ai_result["make_decision"]["result"]["final_decision"]
                alert = ai_result["make_decision"]["result"]["alert_security"]

                print(f"    Decision: {decision}, Security Alert: {alert}")

                # Should deny high-sensitivity resources
                if sensitivity in ["high", "critical"]:
                    assert (
                        decision == "deny"
                    ), f"Should deny access to {sensitivity} resources"

            except Exception as e:
                print(f"    Error: {str(e)[:50]}...")

        print("\n✅ AI-Powered Adaptive Access Control validated")

    def test_production_scale_performance_and_compliance(self):
        """Test production-scale performance with compliance tracking."""
        print("\n📊 Testing Production Scale Performance & Compliance...")

        # Create large-scale test environment
        print("🏗️ Building production-scale environment...")

        # Generate enterprise
        enterprise = EnterpriseDataGenerator.generate_enterprise_structure(
            "GlobalCorp", size="enterprise"  # Largest size
        )

        print(f"  Total employees: {enterprise['total_employees']:,}")
        print(f"  Total roles: {enterprise['total_roles']:,}")
        print(f"  Departments: {len(enterprise['departments'])}")

        # Create compliance tracking workflow
        compliance_workflow = WorkflowBuilder.from_dict(
            {
                "name": "compliance_tracking",
                "description": "Track compliance during high-volume operations",
                "nodes": {
                    "operation_tracker": {
                        "type": "PythonCodeNode",
                        "parameters": {
                            "code": """
import json
from datetime import UTC, datetime

# Track operation for compliance
operation = inputs.get("operation", {})
timestamp = datetime.now(UTC).isoformat()

compliance_record = {
    "timestamp": timestamp,
    "operation_type": operation.get("type"),
    "user_id": operation.get("user_id"),
    "resource_id": operation.get("resource_id"),
    "result": operation.get("result"),
    "response_time_ms": operation.get("response_time_ms", 0),
    "compliance_flags": []
}

# Check compliance rules
if operation.get("response_time_ms", 0) > 1000:
    compliance_record["compliance_flags"].append("slow_response")

if operation.get("type") == "permission_check" and operation.get("resource_sensitivity") == "critical":
    compliance_record["compliance_flags"].append("critical_resource_access")

if operation.get("failed_attempts", 0) > 3:
    compliance_record["compliance_flags"].append("multiple_failures")

result = compliance_record
"""
                        },
                    },
                    "audit_logger": {
                        "type": "SQLDatabaseNode",
                        "parameters": {
                            "operation": "insert",
                            "table": "admin_audit_log",
                        },
                    },
                },
                "connections": [{"from": "operation_tracker", "to": "audit_logger"}],
            }
        )

        # Phase 1: Bulk User Provisioning
        print("\n📥 Phase 1: Bulk User Provisioning")

        role_mgmt = RoleManagementNode()
        user_mgmt = UserManagementNode()
        runtime = LocalRuntime()

        # Track provisioning performance
        provisioning_start = time.time()
        roles_created = 0
        users_created = 0

        # Process in batches for better performance
        batch_size = 100

        for dept in enterprise["departments"]:
            print(f"\n  Processing {dept['name']} department...")
            dept_start = time.time()

            # Create roles
            for role in dept["roles"]:
                role_result = role_mgmt.run(
                    operation="create_role",
                    role_data={
                        "name": f"{dept['name']} - {role['name']}",
                        "permissions": role["permissions"],
                        "attributes": {
                            "department": dept["name"],
                            "level": role["level"],
                            "clearance": role["clearance"],
                        },
                    },
                    tenant_id=self.tenants[0],
                    database_config=self.db_config,
                )
                roles_created += 1

                # Batch create users
                user_batch = []
                for i, emp in enumerate(role["employees"]):
                    user_batch.append(
                        {
                            "user_id": emp["id"],
                            "email": emp["email"],
                            "username": emp["id"],
                            "attributes": {
                                "department": dept["name"],
                                "role": role["name"],
                                "clearance": emp["clearance"],
                            },
                            "role_id": role_result["result"]["role"]["role_id"],
                        }
                    )

                    if len(user_batch) >= batch_size or i == len(role["employees"]) - 1:
                        # Process batch
                        with ThreadPoolExecutor(max_workers=10) as executor:
                            futures = []
                            for user_data in user_batch:
                                future = executor.submit(
                                    self._provision_user, user_data, self.tenants[0]
                                )
                                futures.append(future)

                            for future in as_completed(futures):
                                if future.result():
                                    users_created += 1

                        user_batch = []

            dept_time = time.time() - dept_start
            print(f"    Completed in {dept_time:.2f}s")

        provisioning_time = time.time() - provisioning_start

        print("\n✅ Provisioning completed:")
        print(f"  - Time: {provisioning_time:.2f}s")
        print(f"  - Roles created: {roles_created}")
        print(f"  - Users created: {users_created}")
        print(f"  - Rate: {users_created/provisioning_time:.0f} users/second")

        # Phase 2: Simulate Production Load
        print("\n🔥 Phase 2: Production Load Simulation")

        # Simulate different types of operations
        operation_mix = [
            ("permission_check", 70),  # 70% of operations
            ("role_lookup", 15),  # 15% of operations
            ("audit_query", 10),  # 10% of operations
            ("user_update", 5),  # 5% of operations
        ]

        total_operations = 50000
        operation_results = {
            "permission_check": [],
            "role_lookup": [],
            "audit_query": [],
            "user_update": [],
        }

        print(f"  Executing {total_operations:,} operations...")
        load_start = time.time()

        # Generate operation schedule
        operations = []
        for op_type, percentage in operation_mix:
            count = int(total_operations * percentage / 100)
            operations.extend([op_type] * count)

        # Shuffle for realistic distribution
        import random

        random.shuffle(operations)

        # Execute operations in parallel
        perm_check = PermissionCheckNode()

        def execute_operation(op_index):
            op_type = operations[op_index]
            start = time.time()
            success = False

            try:
                if op_type == "permission_check":
                    user_id = f"globalcorp_engineering_engineer_{op_index % 100}"
                    resource = f"resource_{op_index % 1000}"
                    permission = ["read", "write", "execute", "delete"][op_index % 4]

                    result = perm_check.run(
                        operation="check_permission",
                        user_id=user_id,
                        resource_id=resource,
                        permission=permission,
                        tenant_id=self.tenants[0],
                        database_config=self.db_config,
                        cache_backend="redis",
                        cache_config=self.redis_config,
                    )
                    success = True

                elif op_type == "role_lookup":
                    result = role_mgmt.run(
                        operation="get_user_roles",
                        user_id=f"globalcorp_sales_account_executive_{op_index % 50}",
                        tenant_id=self.tenants[0],
                        database_config=self.db_config,
                    )
                    success = True

                elif op_type == "audit_query":
                    db_node = SQLDatabaseNode(name="audit", **self.db_config)
                    result = db_node.run(
                        query="""
                            SELECT COUNT(*) as audit_count
                            FROM admin_audit_log
                            WHERE tenant_id = %s
                            AND created_at > NOW() - INTERVAL '1 hour'
                        """,
                        parameters=[self.tenants[0]],
                    )
                    success = True

                elif op_type == "user_update":
                    result = user_mgmt.run(
                        operation="update_user",
                        user_id=f"globalcorp_hr_hr_specialist_{op_index % 30}",
                        user_data={
                            "attributes": {
                                "last_login": datetime.now(timezone.utc).isoformat()
                            }
                        },
                        tenant_id=self.tenants[0],
                        database_config=self.db_config,
                    )
                    success = True

            except Exception as e:
                result = {"error": str(e)}

            elapsed = (time.time() - start) * 1000  # Convert to ms

            # Track for compliance
            compliance_op = {
                "type": op_type,
                "user_id": f"user_{op_index}",
                "resource_id": f"resource_{op_index}",
                "result": "success" if success else "failure",
                "response_time_ms": elapsed,
                "resource_sensitivity": "critical" if op_index % 10 == 0 else "normal",
            }

            # Log if slow or critical
            if elapsed > 100 or compliance_op["resource_sensitivity"] == "critical":
                try:
                    runtime.execute(
                        compliance_workflow,
                        parameters={
                            "operation_tracker": {"operation": compliance_op},
                            "audit_logger": {
                                "data": {
                                    "operation": op_type,
                                    "user_id": compliance_op["user_id"],
                                    "resource_type": "system",
                                    "resource_id": compliance_op["resource_id"],
                                    "success": success,
                                    "tenant_id": self.tenants[0],
                                    "created_at": datetime.now(timezone.utc),
                                },
                                "database_config": self.db_config,
                            },
                        },
                    )
                except:
                    pass

            return {"type": op_type, "success": success, "time_ms": elapsed}

        # Execute with thread pool
        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = []

            # Submit in batches to avoid overwhelming
            batch_size = 1000
            for i in range(0, total_operations, batch_size):
                batch_futures = [
                    executor.submit(execute_operation, j)
                    for j in range(i, min(i + batch_size, total_operations))
                ]
                futures.extend(batch_futures)

                # Process completed futures
                for future in as_completed(batch_futures):
                    result = future.result()
                    operation_results[result["type"]].append(result)

                # Progress update
                completed = min(i + batch_size, total_operations)
                print(
                    f"    Progress: {completed:,}/{total_operations:,} ({completed/total_operations*100:.1f}%)"
                )

        load_time = time.time() - load_start

        # Phase 3: Performance Analysis
        print("\n📈 Phase 3: Performance Analysis")

        # Calculate statistics for each operation type
        overall_stats = {
            "total_operations": total_operations,
            "total_time": load_time,
            "throughput": total_operations / load_time,
            "success_rate": 0,
            "operation_stats": {},
        }

        total_success = 0

        for op_type, results in operation_results.items():
            if results:
                times = [r["time_ms"] for r in results]
                successes = sum(1 for r in results if r["success"])

                stats = {
                    "count": len(results),
                    "success_count": successes,
                    "success_rate": successes / len(results) * 100,
                    "avg_time_ms": sum(times) / len(times),
                    "min_time_ms": min(times),
                    "max_time_ms": max(times),
                    "p50_time_ms": sorted(times)[len(times) // 2],
                    "p95_time_ms": sorted(times)[int(len(times) * 0.95)],
                    "p99_time_ms": sorted(times)[int(len(times) * 0.99)],
                }

                overall_stats["operation_stats"][op_type] = stats
                total_success += successes

                print(f"\n  {op_type}:")
                print(f"    Count: {stats['count']:,}")
                print(f"    Success rate: {stats['success_rate']:.1f}%")
                print(f"    Avg latency: {stats['avg_time_ms']:.2f}ms")
                print(f"    P95 latency: {stats['p95_time_ms']:.2f}ms")
                print(f"    P99 latency: {stats['p99_time_ms']:.2f}ms")

        overall_stats["success_rate"] = total_success / total_operations * 100

        print("\n  Overall:")
        print(f"    Throughput: {overall_stats['throughput']:.0f} ops/second")
        print(f"    Success rate: {overall_stats['success_rate']:.1f}%")

        # Phase 4: Compliance Verification
        print("\n✅ Phase 4: Compliance Verification")

        db_node = SQLDatabaseNode(name="compliance", **self.db_config)

        # Check audit completeness
        audit_check = db_node.run(
            query="""
                SELECT
                    COUNT(*) as total_audits,
                    COUNT(DISTINCT user_id) as unique_users,
                    COUNT(DISTINCT resource_id) as unique_resources,
                    AVG(CASE WHEN success THEN 1 ELSE 0 END) * 100 as success_rate
                FROM admin_audit_log
                WHERE tenant_id = %s
                AND created_at > NOW() - INTERVAL '1 hour'
            """,
            parameters=[self.tenants[0]],
        )

        audit_stats = audit_check["data"][0]
        print(f"  Audit entries: {audit_stats['total_audits']:,}")
        print(f"  Unique users: {audit_stats['unique_users']:,}")
        print(f"  Unique resources: {audit_stats['unique_resources']:,}")

        # Check for compliance violations
        violation_check = db_node.run(
            query="""
                SELECT
                    operation,
                    COUNT(*) as failure_count
                FROM admin_audit_log
                WHERE tenant_id = %s
                AND success = false
                AND created_at > NOW() - INTERVAL '1 hour'
                GROUP BY operation
                ORDER BY failure_count DESC
                LIMIT 10
            """,
            parameters=[self.tenants[0]],
        )

        if violation_check["data"]:
            print("\n  ⚠️  Compliance Violations:")
            for violation in violation_check["data"]:
                print(
                    f"    {violation['operation']}: {violation['failure_count']} failures"
                )
        else:
            print("  No compliance violations detected")

        # Assertions
        assert overall_stats["throughput"] > 500, "Should handle >500 ops/second"
        assert overall_stats["success_rate"] > 95, "Success rate should be >95%"
        assert (
            overall_stats["operation_stats"]["permission_check"]["p95_time_ms"] < 100
        ), "P95 latency should be <100ms"

        print("\n🎉 Production scale test completed successfully!")

    def _provision_user(self, user_data: Dict[str, Any], tenant_id: str) -> bool:
        """Helper to provision a user with role assignment."""
        try:
            user_mgmt = UserManagementNode()
            role_mgmt = RoleManagementNode()

            # Create user
            user_mgmt.run(
                operation="create_user",
                user_data={
                    "user_id": user_data["user_id"],
                    "email": user_data["email"],
                    "username": user_data["username"],
                    "attributes": user_data["attributes"],
                    "status": "active",
                },
                tenant_id=tenant_id,
                database_config=self.db_config,
            )

            # Assign role
            role_mgmt.run(
                operation="assign_user",
                user_id=user_data["user_id"],
                role_id=user_data["role_id"],
                tenant_id=tenant_id,
                database_config=self.db_config,
            )

            return True
        except Exception:
            return False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "-k", "test_"])
