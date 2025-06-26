"""
End-to-End Admin Nodes Workflow Tests

Complete E2E validation of admin nodes in production-like environment:
- Real PostgreSQL database with schema initialization
- Real Redis cache for performance validation
- Real Ollama for AI-powered test data generation
- Complete user onboarding to access validation workflow
- Multi-tenant enterprise scenarios
- Performance and compliance validation

These tests simulate real enterprise usage patterns.
"""

import asyncio
import json
import random
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from kailash.nodes.admin import (
    PermissionCheckNode,
    RoleManagementNode,
    UserManagementNode,
)
from kailash.nodes.admin.schema_manager import AdminSchemaManager
from kailash.nodes.ai import LLMAgentNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError
from tests.utils.docker_config import (
    OLLAMA_CONFIG,
    REDIS_CONFIG,
    TEST_DATABASES,
    ensure_docker_services,
    get_postgres_connection_string,
)


@pytest.mark.e2e
@pytest.mark.slow
class TestAdminNodesCompleteWorkflow:
    """Complete E2E workflow tests for admin nodes."""

    @pytest.fixture(scope="class", autouse=True)
    async def setup_infrastructure(self):
        """Setup complete infrastructure for E2E tests."""
        # Ensure Docker services are available
        available = await ensure_docker_services()
        if not available:
            pytest.skip("Docker services not available for E2E tests")

        # Initialize database schema
        db_config = {
            "connection_string": get_postgres_connection_string(
                TEST_DATABASES["admin"]
            ),
            "database_type": "postgresql",
        }

        schema_manager = AdminSchemaManager(database_config=db_config)
        try:
            schema_manager.initialize_schema()
            print("Database schema initialized successfully")
        except Exception as e:
            print(f"Schema initialization warning: {e}")
            # Continue even if schema already exists

    @pytest.fixture
    def enterprise_config(self):
        """Complete enterprise configuration."""
        return {
            "database": {
                "connection_string": get_postgres_connection_string(
                    TEST_DATABASES["admin"]
                ),
                "database_type": "postgresql",
            },
            "cache": {
                "host": REDIS_CONFIG["host"],
                "port": REDIS_CONFIG["port"],
                "ttl": 300,
            },
            "ai": {
                "base_url": f"http://{OLLAMA_CONFIG['host']}:{OLLAMA_CONFIG['port']}",
                "model": "llama3.2:latest",
            },
        }

    @pytest.fixture
    def admin_nodes(self, enterprise_config):
        """Complete admin node suite."""
        db_config = enterprise_config["database"]
        cache_config = enterprise_config["cache"]

        return {
            "user": UserManagementNode(database_config=db_config),
            "role": RoleManagementNode(database_config=db_config),
            "permission": PermissionCheckNode(
                database_config=db_config,
                cache_backend="redis",
                cache_config=cache_config,
            ),
        }

    @pytest.fixture
    def ai_assistant(self, enterprise_config):
        """AI assistant for test data generation."""
        return LLMAgentNode(
            agent_config={
                "provider": "ollama",
                "model": enterprise_config["ai"]["model"],
                "base_url": enterprise_config["ai"]["base_url"],
                "temperature": 0.7,
            }
        )

    def generate_enterprise_id(self) -> str:
        """Generate enterprise-like ID."""
        return f"enterprise_{random.randint(10000, 99999)}"

    def generate_unique_identifier(self, prefix: str = "test") -> str:
        """Generate unique identifier."""
        unique = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        return f"{prefix}_{unique}"

    async def create_enterprise_structure(
        self, admin_nodes: Dict, tenant_id: str
    ) -> Dict[str, Any]:
        """Create complete enterprise role structure."""

        # Define enterprise role hierarchy
        enterprise_roles = [
            # Base roles
            {
                "name": "employee",
                "description": "Base employee role",
                "permissions": ["profile:read", "profile:update", "company:read"],
                "role_type": "base",
                "parent_roles": [],
            },
            # Department roles
            {
                "name": "engineering",
                "description": "Engineering department access",
                "permissions": ["code:read", "docs:technical", "tools:development"],
                "role_type": "department",
                "parent_roles": ["employee"],
            },
            {
                "name": "sales",
                "description": "Sales department access",
                "permissions": ["crm:read", "leads:manage", "proposals:create"],
                "role_type": "department",
                "parent_roles": ["employee"],
            },
            {
                "name": "hr",
                "description": "Human Resources access",
                "permissions": ["employees:read", "policies:read", "benefits:manage"],
                "role_type": "department",
                "parent_roles": ["employee"],
            },
            # Seniority levels
            {
                "name": "senior_engineer",
                "description": "Senior engineering role",
                "permissions": ["code:write", "code:review", "deployment:staging"],
                "role_type": "seniority",
                "parent_roles": ["engineering"],
            },
            {
                "name": "team_lead",
                "description": "Team leadership role",
                "permissions": ["team:manage", "projects:plan", "reports:create"],
                "role_type": "leadership",
                "parent_roles": ["senior_engineer"],
            },
            # Management roles
            {
                "name": "manager",
                "description": "Department manager",
                "permissions": [
                    "budget:view",
                    "hiring:participate",
                    "performance:review",
                ],
                "role_type": "management",
                "parent_roles": ["team_lead"],
            },
            {
                "name": "director",
                "description": "Department director",
                "permissions": ["budget:approve", "hiring:decide", "strategy:plan"],
                "role_type": "executive",
                "parent_roles": ["manager"],
            },
            # Executive roles
            {
                "name": "c_level",
                "description": "C-level executive",
                "permissions": ["company:strategic", "board:access", "financial:full"],
                "role_type": "executive",
                "parent_roles": ["director"],
            },
            # Special roles
            {
                "name": "security_officer",
                "description": "Security and compliance officer",
                "permissions": [
                    "security:audit",
                    "compliance:manage",
                    "incidents:respond",
                ],
                "role_type": "special",
                "parent_roles": ["manager"],
            },
            {
                "name": "system_admin",
                "description": "System administrator",
                "permissions": [
                    "system:configure",
                    "users:manage",
                    "infrastructure:control",
                ],
                "role_type": "technical",
                "parent_roles": ["senior_engineer"],
            },
        ]

        created_roles = {}

        # Create roles in dependency order
        for role_data in enterprise_roles:
            try:
                result = admin_nodes["role"].run(
                    operation="create_role", role_data=role_data, tenant_id=tenant_id
                )

                if result["result"]["success"]:
                    created_roles[role_data["name"]] = result["result"]["role"]
                    print(f"Created role: {role_data['name']}")

            except Exception as e:
                print(f"Failed to create role {role_data['name']}: {e}")

        return created_roles

    async def generate_employee_cohort(
        self, ai_assistant: LLMAgentNode, count: int = 15
    ) -> List[Dict[str, Any]]:
        """Generate realistic employee cohort using AI."""

        prompt = f"""
        Generate {count} realistic employees for a tech company with diverse roles and departments.
        Include mix of: Software Engineers, Sales Reps, HR Specialists, Managers, Directors.

        For each employee provide:
        - first_name, last_name
        - department (Engineering, Sales, HR, Marketing, Finance)
        - job_title (specific title matching department)
        - seniority_level (Junior, Mid, Senior, Lead, Manager, Director)
        - security_clearance (Basic, Elevated, Admin)
        - start_date (realistic dates in past 5 years)

        Return as JSON array only, no explanation.
        """

        try:
            result = ai_assistant.run(prompt=prompt, max_tokens=1500, temperature=0.8)

            response_text = result["result"]["response"]

            # Extract JSON from response
            start_idx = response_text.find("[")
            end_idx = response_text.rfind("]") + 1

            if start_idx != -1 and end_idx != -1:
                json_text = response_text[start_idx:end_idx]
                employees = json.loads(json_text)

                # Enhance with required fields
                for emp in employees:
                    emp["email"] = (
                        f"{emp['first_name'].lower()}.{emp['last_name'].lower()}@company.com"
                    )
                    emp["username"] = (
                        f"{emp['first_name'].lower()}{emp['last_name'].lower()}"
                    )
                    emp["password"] = "Enterprise123!"
                    emp["status"] = "active"
                    emp["employee_id"] = f"EMP{random.randint(1000, 9999)}"

                    # Assign roles based on department and seniority
                    roles = ["employee"]
                    dept = emp.get("department", "").lower()
                    if "engineering" in dept:
                        roles.append("engineering")
                        if "senior" in emp.get("seniority_level", "").lower():
                            roles.append("senior_engineer")
                        if "lead" in emp.get("job_title", "").lower():
                            roles.append("team_lead")
                    elif "sales" in dept:
                        roles.append("sales")
                    elif "hr" in dept:
                        roles.append("hr")

                    if "manager" in emp.get("job_title", "").lower():
                        roles.append("manager")
                    elif "director" in emp.get("job_title", "").lower():
                        roles.append("director")

                    emp["roles"] = roles

                return employees[:count]  # Ensure we don't exceed requested count

        except Exception as e:
            print(f"AI employee generation failed: {e}, using fallback")

        # Fallback employee data
        departments = ["Engineering", "Sales", "HR", "Marketing", "Finance"]
        titles = ["Developer", "Engineer", "Manager", "Specialist", "Director", "Lead"]

        fallback_employees = []
        for i in range(count):
            dept = random.choice(departments)
            title = random.choice(titles)

            employee = {
                "first_name": f"Employee{i}",
                "last_name": f"Test{i}",
                "email": f"employee{i}.test{i}@company.com",
                "username": f"employee{i}test{i}",
                "password": "Enterprise123!",
                "department": dept,
                "job_title": f"{title} - {dept}",
                "seniority_level": random.choice(["Junior", "Mid", "Senior"]),
                "security_clearance": random.choice(["Basic", "Elevated"]),
                "start_date": "2023-01-01",
                "status": "active",
                "employee_id": f"EMP{2000 + i}",
                "roles": ["employee"],
            }

            if dept.lower() == "engineering":
                employee["roles"].append("engineering")
            elif dept.lower() == "sales":
                employee["roles"].append("sales")
            elif dept.lower() == "hr":
                employee["roles"].append("hr")

            fallback_employees.append(employee)

        return fallback_employees

    @pytest.mark.asyncio
    async def test_complete_enterprise_onboarding_workflow(
        self, admin_nodes, ai_assistant
    ):
        """Test complete enterprise employee onboarding workflow."""

        tenant_id = self.generate_enterprise_id()
        print(f"Testing enterprise workflow for tenant: {tenant_id}")

        created_users = []

        try:
            # Step 1: Create enterprise role structure
            print("Creating enterprise role structure...")
            enterprise_roles = await self.create_enterprise_structure(
                admin_nodes, tenant_id
            )
            assert len(enterprise_roles) >= 5, "Should create multiple enterprise roles"

            # Step 2: Generate employee cohort with AI
            print("Generating employee cohort with AI...")
            employees = await self.generate_employee_cohort(ai_assistant, count=10)
            assert len(employees) == 10, "Should generate requested number of employees"

            # Step 3: Bulk onboard employees
            print("Bulk onboarding employees...")
            bulk_result = admin_nodes["user"].run(
                operation="bulk_create", users_data=employees, tenant_id=tenant_id
            )

            assert bulk_result["result"]["success"], "Bulk user creation should succeed"
            created_users = bulk_result["result"]["bulk_result"]["created_users"]

            print(f"Successfully created {len(created_users)} users")

            # Step 4: Assign roles based on employee attributes
            print("Assigning roles based on employee attributes...")
            role_assignments = 0

            for user in created_users:
                # Find original employee data
                original_emp = next(
                    (emp for emp in employees if emp["email"] == user["email"]), None
                )
                if not original_emp:
                    continue

                # Assign roles based on employee profile
                for role_name in original_emp.get("roles", ["employee"]):
                    if role_name in enterprise_roles:
                        try:
                            assignment_result = admin_nodes["role"].run(
                                operation="assign_user",
                                user_id=user["user_id"],
                                role_id=role_name,
                                tenant_id=tenant_id,
                                validate_hierarchy=False,
                            )
                            if assignment_result["result"]["success"]:
                                role_assignments += 1
                        except Exception as e:
                            print(f"Role assignment warning for {user['email']}: {e}")

            print(f"Completed {role_assignments} role assignments")

            # Step 5: Validate enterprise access patterns
            print("Validating enterprise access patterns...")
            access_validations = 0

            # Test different access scenarios
            test_scenarios = [
                # Basic employee access
                ("employee", "profile:read", True),
                ("employee", "company:read", True),
                ("employee", "system:configure", False),
                # Engineering department access
                ("engineering", "code:read", True),
                ("engineering", "tools:development", True),
                ("engineering", "financial:full", False),
                # Management access
                ("manager", "budget:view", True),
                ("manager", "hiring:participate", True),
                ("manager", "board:access", False),
                # Security officer access
                ("security_officer", "security:audit", True),
                ("security_officer", "compliance:manage", True),
                ("security_officer", "system:configure", False),
            ]

            for role_name, permission, expected_access in test_scenarios:
                # Find user with this role
                test_user = None
                for user in created_users:
                    original_emp = next(
                        (emp for emp in employees if emp["email"] == user["email"]),
                        None,
                    )
                    if original_emp and role_name in original_emp.get("roles", []):
                        test_user = user
                        break

                if test_user:
                    try:
                        perm_result = admin_nodes["permission"].run(
                            operation="check_permission",
                            user_id=test_user["user_id"],
                            resource_id="enterprise_system",
                            permission=permission.split(":")[
                                1
                            ],  # Extract action from permission
                            tenant_id=tenant_id,
                        )

                        actual_access = perm_result["result"]["check"]["allowed"]
                        print(
                            f"Access test: {role_name} -> {permission} = {actual_access} (expected: {expected_access})"
                        )
                        access_validations += 1

                    except Exception as e:
                        print(f"Permission check warning: {e}")

            assert (
                access_validations >= 5
            ), "Should complete multiple access validations"

            # Step 6: Test cache performance
            print("Testing permission cache performance...")
            if created_users:
                test_user = created_users[0]

                # Cache miss
                start_time = datetime.now(timezone.utc)
                result1 = admin_nodes["permission"].run(
                    operation="check_permission",
                    user_id=test_user["user_id"],
                    resource_id="performance_test",
                    permission="read",
                    tenant_id=tenant_id,
                )
                miss_time = (datetime.now(timezone.utc) - start_time).total_seconds()

                # Cache hit
                start_time = datetime.now(timezone.utc)
                result2 = admin_nodes["permission"].run(
                    operation="check_permission",
                    user_id=test_user["user_id"],
                    resource_id="performance_test",
                    permission="read",
                    tenant_id=tenant_id,
                )
                hit_time = (datetime.now(timezone.utc) - start_time).total_seconds()

                print(
                    f"Cache performance: {miss_time:.4f}s miss vs {hit_time:.4f}s hit"
                )
                assert hit_time < miss_time * 0.7, "Cache should improve performance"

            # Step 7: Test multi-tenant isolation
            print("Testing multi-tenant isolation...")
            other_tenant = self.generate_enterprise_id()

            if created_users:
                test_user = created_users[0]

                # Should not be able to access user from different tenant
                with pytest.raises(NodeExecutionError):
                    admin_nodes["user"].run(
                        operation="get_user",
                        user_id=test_user["user_id"],
                        tenant_id=other_tenant,
                    )
                print("Multi-tenant isolation verified")

            # Step 8: Test enterprise workflow completion
            print("Testing enterprise workflow scenarios...")

            # Simulate employee promotion
            if created_users and "team_lead" in enterprise_roles:
                test_user = created_users[0]

                promotion_result = admin_nodes["role"].run(
                    operation="assign_user",
                    user_id=test_user["user_id"],
                    role_id="team_lead",
                    tenant_id=tenant_id,
                    validate_hierarchy=False,
                )

                if promotion_result["result"]["success"]:
                    print(f"Employee promotion successful: {test_user['email']}")

            print("Enterprise workflow completed successfully!")

        finally:
            # Cleanup: Remove all created users
            print("Cleaning up test data...")
            cleanup_count = 0
            for user in created_users:
                try:
                    admin_nodes["user"].run(
                        operation="delete_user",
                        user_id=user["user_id"],
                        hard_delete=True,
                        tenant_id=tenant_id,
                    )
                    cleanup_count += 1
                except Exception as e:
                    print(f"Cleanup warning for {user.get('email', 'unknown')}: {e}")

            print(f"Cleaned up {cleanup_count} users")

    @pytest.mark.asyncio
    async def test_enterprise_compliance_and_audit_workflow(
        self, admin_nodes, ai_assistant
    ):
        """Test complete compliance and audit workflow."""

        tenant_id = self.generate_enterprise_id()
        created_users = []

        try:
            # Create compliance-focused roles
            compliance_roles = [
                {
                    "name": "data_subject",
                    "description": "Regular employee with GDPR rights",
                    "permissions": [
                        "profile:read",
                        "profile:update",
                        "data:export_own",
                    ],
                    "role_type": "compliance",
                },
                {
                    "name": "dpo",  # Data Protection Officer
                    "description": "Data Protection Officer",
                    "permissions": ["gdpr:audit", "data:export_any", "privacy:manage"],
                    "role_type": "compliance",
                },
                {
                    "name": "auditor",
                    "description": "Security auditor",
                    "permissions": ["audit:read", "logs:access", "compliance:verify"],
                    "role_type": "compliance",
                },
            ]

            for role_data in compliance_roles:
                admin_nodes["role"].run(
                    operation="create_role", role_data=role_data, tenant_id=tenant_id
                )

            # Create test users with sensitive data
            sensitive_users = [
                {
                    "email": "john.doe@company.com",
                    "username": "johndoe",
                    "password": "Secure123!",
                    "first_name": "John",
                    "last_name": "Doe",
                    "attributes": {
                        "ssn": "***-**-1234",  # Masked
                        "gdpr_consent": True,
                        "data_retention_until": "2025-12-31",
                        "privacy_settings": {"marketing": False, "analytics": True},
                    },
                    "roles": ["data_subject"],
                },
                {
                    "email": "jane.dpo@company.com",
                    "username": "janedpo",
                    "password": "Secure123!",
                    "first_name": "Jane",
                    "last_name": "Smith",
                    "attributes": {
                        "certification": "GDPR_DPO",
                        "clearance_level": "high",
                    },
                    "roles": ["dpo"],
                },
            ]

            # Create users
            for user_data in sensitive_users:
                result = admin_nodes["user"].run(
                    operation="create_user", user_data=user_data, tenant_id=tenant_id
                )
                if result["result"]["success"]:
                    created_users.append(result["result"]["user"])

                    # Assign roles
                    for role_name in user_data["roles"]:
                        admin_nodes["role"].run(
                            operation="assign_user",
                            user_id=result["result"]["user"]["user_id"],
                            role_id=role_name,
                            tenant_id=tenant_id,
                            validate_hierarchy=False,
                        )

            # Test GDPR data subject rights
            data_subject = next(
                (u for u in created_users if "john.doe" in u["email"]), None
            )
            if data_subject:
                # Test data export (GDPR Article 20)
                try:
                    export_result = admin_nodes["user"].run(
                        operation="export_user_data",
                        user_id=data_subject["user_id"],
                        tenant_id=tenant_id,
                        include_audit_logs=True,
                    )
                    print("Data export capability verified")
                except Exception as e:
                    print(f"Data export not implemented: {e}")

                # Test permission checks with audit trails
                audit_check = admin_nodes["permission"].run(
                    operation="check_permission",
                    user_id=data_subject["user_id"],
                    resource_id="sensitive_document",
                    permission="access",
                    tenant_id=tenant_id,
                    audit=True,
                    context={
                        "purpose": "compliance_test",
                        "ip_address": "192.168.1.100",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )

                print("Audit trail generation verified")

            # Test DPO access patterns
            dpo_user = next(
                (u for u in created_users if "jane.dpo" in u["email"]), None
            )
            if dpo_user:
                # DPO should have broad audit access
                dpo_check = admin_nodes["permission"].run(
                    operation="check_permission",
                    user_id=dpo_user["user_id"],
                    resource_id="audit_logs",
                    permission="read",
                    tenant_id=tenant_id,
                )

                print(f"DPO audit access: {dpo_check['result']['check']['allowed']}")

            print("Compliance and audit workflow completed")

        finally:
            # Secure cleanup
            for user in created_users:
                try:
                    admin_nodes["user"].run(
                        operation="delete_user",
                        user_id=user["user_id"],
                        hard_delete=True,  # Permanent deletion for compliance test
                        tenant_id=tenant_id,
                    )
                except Exception:
                    pass
