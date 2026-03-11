"""
Tier 3 E2E Tests for WebMigrationAPI
Complete user workflows, real infrastructure, NO MOCKING, <10s timeout

Tests complete end-to-end scenarios for web-based migration management:
1. Complete user workflow from schema inspection to migration execution
2. Multi-step migration planning and validation
3. Session-based migration development workflow
4. Integration with VisualMigrationBuilder + AutoMigrationSystem + Database
5. Real schema evolution scenarios
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest
from dataflow.migrations.auto_migration_system import AutoMigrationSystem

# DataFlow components - NO MOCKING for E2E
from dataflow.migrations.visual_migration_builder import (
    ColumnType,
    VisualMigrationBuilder,
)

# Test utilities for real PostgreSQL environment
from tests.utils.test_env_setup import (
    cleanup_test_data,
    create_test_table,
    execute_sql,
    get_test_connection,
    verify_column_exists,
    verify_table_exists,
)


@pytest.fixture(scope="function")
async def clean_database():
    """Ensure clean database state for each test."""
    await cleanup_test_data()
    yield
    await cleanup_test_data()


@pytest.fixture(scope="function")
async def test_connection():
    """Get real PostgreSQL test connection."""
    conn = await get_test_connection()
    yield conn
    await conn.close()


@pytest.fixture(scope="function")
async def initial_schema(test_connection):
    """Create initial schema for E2E testing."""
    await execute_sql(
        test_connection,
        """
        CREATE TABLE companies (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL UNIQUE,
            industry VARCHAR(100),
            founded_year INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE employees (
            id SERIAL PRIMARY KEY,
            first_name VARCHAR(100) NOT NULL,
            last_name VARCHAR(100) NOT NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            hire_date DATE DEFAULT CURRENT_DATE,
            salary DECIMAL(10,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX idx_employees_company ON employees(company_id);
        CREATE INDEX idx_employees_email ON employees(email);
    """,
    )
    yield
    # Cleanup handled by clean_database fixture


class TestCompleteUserWorkflow:
    """Test complete user workflow from inspection to execution."""

    @pytest.mark.asyncio
    async def test_developer_adds_new_feature_complete_workflow(self, initial_schema):
        """
        E2E Test: Developer adds new employee benefits feature

        Workflow:
        1. Inspect current schema
        2. Plan new benefits table and employee relationship
        3. Create session and draft migrations
        4. Generate previews and validate
        5. Execute migrations
        6. Verify schema changes
        """
        from dataflow.web.migration_api import WebMigrationAPI

        api = WebMigrationAPI(
            "postgresql://dataflow_test:dataflow_test_password@localhost:5433/dataflow_test"
        )

        # Step 1: Inspect current schema
        schema_before = api.inspect_schema()
        assert "companies" in schema_before["tables"]
        assert "employees" in schema_before["tables"]
        assert "benefits" not in schema_before["tables"]

        # Step 2: Create developer session
        session_id = api.create_session("developer_alice")

        # Step 3: Plan benefits table migration
        benefits_migration = {
            "name": "create_benefits_table",
            "type": "create_table",
            "spec": {
                "table_name": "benefits",
                "columns": [
                    {"name": "id", "type": "SERIAL", "primary_key": True},
                    {
                        "name": "name",
                        "type": "VARCHAR",
                        "length": 100,
                        "nullable": False,
                    },
                    {"name": "description", "type": "TEXT"},
                    {
                        "name": "type",
                        "type": "VARCHAR",
                        "length": 50,
                        "nullable": False,
                    },
                    {"name": "value", "type": "DECIMAL", "precision": 10, "scale": 2},
                    {
                        "name": "created_at",
                        "type": "TIMESTAMP",
                        "default": "CURRENT_TIMESTAMP",
                    },
                ],
            },
        }

        api.add_draft_migration(session_id, benefits_migration)

        # Step 4: Plan employee benefits relationship
        employee_benefits_migration = {
            "name": "create_employee_benefits_table",
            "type": "create_table",
            "spec": {
                "table_name": "employee_benefits",
                "columns": [
                    {"name": "id", "type": "SERIAL", "primary_key": True},
                    {"name": "employee_id", "type": "INTEGER", "nullable": False},
                    {"name": "benefit_id", "type": "INTEGER", "nullable": False},
                    {
                        "name": "enrolled_at",
                        "type": "TIMESTAMP",
                        "default": "CURRENT_TIMESTAMP",
                    },
                    {
                        "name": "status",
                        "type": "VARCHAR",
                        "length": 20,
                        "default": "'active'",
                    },
                ],
            },
        }

        api.add_draft_migration(session_id, employee_benefits_migration)

        # Step 5: Add foreign key constraints
        fk_constraints_migration = {
            "name": "add_employee_benefits_constraints",
            "type": "multi_operation",
            "spec": {
                "operations": [
                    {
                        "type": "add_constraint",
                        "table_name": "employee_benefits",
                        "constraint": {
                            "type": "foreign_key",
                            "name": "fk_employee_benefits_employee",
                            "column": "employee_id",
                            "references": "employees(id)",
                            "on_delete": "CASCADE",
                        },
                    },
                    {
                        "type": "add_constraint",
                        "table_name": "employee_benefits",
                        "constraint": {
                            "type": "foreign_key",
                            "name": "fk_employee_benefits_benefit",
                            "column": "benefit_id",
                            "references": "benefits(id)",
                            "on_delete": "CASCADE",
                        },
                    },
                    {
                        "type": "add_constraint",
                        "table_name": "employee_benefits",
                        "constraint": {
                            "type": "unique",
                            "name": "uq_employee_benefit",
                            "columns": ["employee_id", "benefit_id"],
                        },
                    },
                ]
            },
        }

        api.add_draft_migration(session_id, fk_constraints_migration)

        # Step 6: Generate complete session preview
        session_preview = api.generate_session_preview(session_id)

        assert len(session_preview["migrations"]) == 3
        assert "CREATE TABLE benefits" in session_preview["combined_sql"]
        assert "CREATE TABLE employee_benefits" in session_preview["combined_sql"]
        assert (
            "ALTER TABLE employee_benefits ADD CONSTRAINT"
            in session_preview["combined_sql"]
        )

        # Step 7: Validate all migrations
        validation_result = api.validate_session_migrations(session_id)

        assert validation_result["valid"] is True
        assert len(validation_result["migration_validations"]) == 3
        for validation in validation_result["migration_validations"]:
            assert validation["valid"] is True

        # Step 8: Execute migrations (simulate)
        execution_plan = api.create_execution_plan(session_id)

        assert len(execution_plan["steps"]) == 3
        assert execution_plan["estimated_duration"] > 0
        assert execution_plan["risk_level"] in ["low", "medium", "high"]

        # Step 9: Actually execute migrations
        execution_result = api.execute_session_migrations(session_id, dry_run=False)

        assert execution_result["success"] is True
        assert len(execution_result["executed_migrations"]) == 3
        assert execution_result["total_duration"] > 0

        # Step 10: Verify schema changes
        schema_after = api.inspect_schema()

        assert "benefits" in schema_after["tables"]
        assert "employee_benefits" in schema_after["tables"]

        # Verify benefits table structure
        benefits_table = schema_after["tables"]["benefits"]
        assert "id" in benefits_table["columns"]
        assert "name" in benefits_table["columns"]
        assert "type" in benefits_table["columns"]
        assert benefits_table["columns"]["id"]["primary_key"] is True

        # Verify employee_benefits table and constraints
        emp_benefits_table = schema_after["tables"]["employee_benefits"]
        assert "employee_id" in emp_benefits_table["columns"]
        assert "benefit_id" in emp_benefits_table["columns"]

        # Verify foreign key constraints exist
        constraints = emp_benefits_table.get("constraints", [])
        fk_constraint_names = [
            c["name"] for c in constraints if c["type"] == "foreign_key"
        ]
        assert "fk_employee_benefits_employee" in fk_constraint_names
        assert "fk_employee_benefits_benefit" in fk_constraint_names

        # Step 11: Clean up session
        api.close_session(session_id)

        with pytest.raises(Exception):  # SessionNotFoundError
            api.get_session(session_id)

    @pytest.mark.asyncio
    async def test_database_architect_schema_evolution_workflow(self, initial_schema):
        """
        E2E Test: Database architect evolves schema for performance

        Workflow:
        1. Analyze current schema performance
        2. Plan index optimizations
        3. Plan column type optimizations
        4. Plan table partitioning (PostgreSQL specific)
        5. Validate performance impact
        6. Execute in stages
        """
        from dataflow.web.migration_api import WebMigrationAPI

        api = WebMigrationAPI(
            "postgresql://dataflow_test:dataflow_test_password@localhost:5433/dataflow_test"
        )

        # Step 1: Performance analysis (simulated)
        performance_analysis = api.analyze_schema_performance()

        assert "recommendations" in performance_analysis
        assert "current_indexes" in performance_analysis
        assert "query_patterns" in performance_analysis

        # Step 2: Create architect session
        session_id = api.create_session("db_architect_bob")

        # Step 3: Add optimized indexes
        index_optimization = {
            "name": "optimize_employee_indexes",
            "type": "multi_operation",
            "spec": {
                "operations": [
                    {
                        "type": "create_index",
                        "table_name": "employees",
                        "index_name": "idx_employees_name_company",
                        "columns": ["last_name", "first_name", "company_id"],
                        "index_type": "btree",
                    },
                    {
                        "type": "create_index",
                        "table_name": "employees",
                        "index_name": "idx_employees_salary_range",
                        "columns": ["salary"],
                        "index_type": "btree",
                        "condition": "salary IS NOT NULL",
                    },
                    {
                        "type": "create_index",
                        "table_name": "companies",
                        "index_name": "idx_companies_industry_founded",
                        "columns": ["industry", "founded_year"],
                        "index_type": "btree",
                    },
                ]
            },
        }

        api.add_draft_migration(session_id, index_optimization)

        # Step 4: Optimize column types
        column_optimization = {
            "name": "optimize_column_types",
            "type": "multi_operation",
            "spec": {
                "operations": [
                    {
                        "type": "modify_column",
                        "table_name": "employees",
                        "column": {
                            "name": "first_name",
                            "type": "VARCHAR",
                            "length": 50,  # Reduce from 100 to 50
                        },
                    },
                    {
                        "type": "modify_column",
                        "table_name": "employees",
                        "column": {
                            "name": "last_name",
                            "type": "VARCHAR",
                            "length": 50,  # Reduce from 100 to 50
                        },
                    },
                ]
            },
        }

        api.add_draft_migration(session_id, column_optimization)

        # Step 5: Add performance tracking columns
        performance_tracking = {
            "name": "add_performance_tracking",
            "type": "multi_operation",
            "spec": {
                "operations": [
                    {
                        "type": "add_column",
                        "table_name": "employees",
                        "column": {
                            "name": "last_updated",
                            "type": "TIMESTAMP",
                            "default": "CURRENT_TIMESTAMP",
                        },
                    },
                    {
                        "type": "add_column",
                        "table_name": "companies",
                        "column": {
                            "name": "employee_count",
                            "type": "INTEGER",
                            "default": "0",
                        },
                    },
                ]
            },
        }

        api.add_draft_migration(session_id, performance_tracking)

        # Step 6: Validate performance impact
        performance_validation = api.validate_performance_impact(session_id)

        assert "estimated_improvement" in performance_validation
        assert "risk_assessment" in performance_validation
        assert performance_validation["safe_to_execute"] is True

        # Step 7: Create execution plan with performance considerations
        execution_plan = api.create_execution_plan(
            session_id, optimize_for="performance"
        )

        assert execution_plan["execution_strategy"] == "staged"
        assert len(execution_plan["stages"]) >= 2

        # Execute stage by stage
        for stage_num, stage in enumerate(execution_plan["stages"]):
            stage_result = api.execute_migration_stage(session_id, stage_num)
            assert stage_result["success"] is True

            # Verify each stage
            if stage_num == 0:  # Index creation stage
                schema = api.inspect_schema()
                employees_indexes = schema["tables"]["employees"]["indexes"]
                index_names = [idx["name"] for idx in employees_indexes]
                assert "idx_employees_name_company" in index_names

        # Step 8: Final verification
        final_schema = api.inspect_schema()

        # Verify optimizations applied
        employees_table = final_schema["tables"]["employees"]
        assert "last_updated" in employees_table["columns"]
        assert employees_table["columns"]["first_name"]["type"] == "VARCHAR(50)"

        companies_table = final_schema["tables"]["companies"]
        assert "employee_count" in companies_table["columns"]

        # Verify performance improvement (simulated)
        final_performance = api.analyze_schema_performance()
        assert (
            final_performance["performance_score"]
            > performance_analysis["performance_score"]
        )


class TestMultiStepMigrationPlanning:
    """Test complex multi-step migration planning and validation."""

    @pytest.mark.asyncio
    async def test_complex_schema_refactoring_workflow(self, initial_schema):
        """
        E2E Test: Complex schema refactoring with dependent changes

        Scenario: Refactor employee table to support multiple roles per employee
        """
        from dataflow.web.migration_api import WebMigrationAPI

        api = WebMigrationAPI(
            "postgresql://dataflow_test:dataflow_test_password@localhost:5433/dataflow_test"
        )

        session_id = api.create_session("lead_developer_charlie")

        # Step 1: Create roles table
        roles_migration = {
            "name": "create_roles_table",
            "type": "create_table",
            "spec": {
                "table_name": "roles",
                "columns": [
                    {"name": "id", "type": "SERIAL", "primary_key": True},
                    {
                        "name": "name",
                        "type": "VARCHAR",
                        "length": 50,
                        "nullable": False,
                        "unique": True,
                    },
                    {"name": "description", "type": "TEXT"},
                    {"name": "department", "type": "VARCHAR", "length": 50},
                    {
                        "name": "min_salary",
                        "type": "DECIMAL",
                        "precision": 10,
                        "scale": 2,
                    },
                    {
                        "name": "max_salary",
                        "type": "DECIMAL",
                        "precision": 10,
                        "scale": 2,
                    },
                    {
                        "name": "created_at",
                        "type": "TIMESTAMP",
                        "default": "CURRENT_TIMESTAMP",
                    },
                ],
            },
        }

        api.add_draft_migration(session_id, roles_migration)

        # Step 2: Create employee_roles junction table
        employee_roles_migration = {
            "name": "create_employee_roles_table",
            "type": "create_table",
            "spec": {
                "table_name": "employee_roles",
                "columns": [
                    {"name": "id", "type": "SERIAL", "primary_key": True},
                    {"name": "employee_id", "type": "INTEGER", "nullable": False},
                    {"name": "role_id", "type": "INTEGER", "nullable": False},
                    {
                        "name": "assigned_at",
                        "type": "TIMESTAMP",
                        "default": "CURRENT_TIMESTAMP",
                    },
                    {"name": "is_primary", "type": "BOOLEAN", "default": "false"},
                    {
                        "name": "salary_override",
                        "type": "DECIMAL",
                        "precision": 10,
                        "scale": 2,
                    },
                ],
            },
        }

        api.add_draft_migration(session_id, employee_roles_migration)

        # Step 3: Add constraints and indexes
        constraints_migration = {
            "name": "add_employee_roles_constraints",
            "type": "multi_operation",
            "spec": {
                "operations": [
                    {
                        "type": "add_constraint",
                        "table_name": "employee_roles",
                        "constraint": {
                            "type": "foreign_key",
                            "name": "fk_employee_roles_employee",
                            "column": "employee_id",
                            "references": "employees(id)",
                            "on_delete": "CASCADE",
                        },
                    },
                    {
                        "type": "add_constraint",
                        "table_name": "employee_roles",
                        "constraint": {
                            "type": "foreign_key",
                            "name": "fk_employee_roles_role",
                            "column": "role_id",
                            "references": "roles(id)",
                            "on_delete": "RESTRICT",
                        },
                    },
                    {
                        "type": "create_index",
                        "table_name": "employee_roles",
                        "index_name": "idx_employee_roles_employee",
                        "columns": ["employee_id"],
                    },
                    {
                        "type": "create_index",
                        "table_name": "employee_roles",
                        "index_name": "idx_employee_roles_role",
                        "columns": ["role_id"],
                    },
                    {
                        "type": "create_index",
                        "table_name": "employee_roles",
                        "index_name": "uq_employee_primary_role",
                        "columns": ["employee_id"],
                        "unique": True,
                        "condition": "is_primary = true",
                    },
                ]
            },
        }

        api.add_draft_migration(session_id, constraints_migration)

        # Step 4: Create data migration to populate roles
        data_migration = {
            "name": "migrate_employee_data_to_roles",
            "type": "data_migration",
            "spec": {
                "description": "Migrate existing employee data to new role structure",
                "operations": [
                    {
                        "type": "insert_data",
                        "table_name": "roles",
                        "data": [
                            {
                                "name": "Software Engineer",
                                "department": "Engineering",
                                "min_salary": 70000,
                                "max_salary": 150000,
                            },
                            {
                                "name": "Senior Software Engineer",
                                "department": "Engineering",
                                "min_salary": 100000,
                                "max_salary": 200000,
                            },
                            {
                                "name": "Manager",
                                "department": "Management",
                                "min_salary": 90000,
                                "max_salary": 180000,
                            },
                            {
                                "name": "Director",
                                "department": "Management",
                                "min_salary": 150000,
                                "max_salary": 300000,
                            },
                        ],
                    },
                    {
                        "type": "execute_sql",
                        "sql": """
                        INSERT INTO employee_roles (employee_id, role_id, is_primary, salary_override)
                        SELECT
                            e.id,
                            CASE
                                WHEN e.salary >= 150000 THEN (SELECT id FROM roles WHERE name = 'Director')
                                WHEN e.salary >= 90000 THEN (SELECT id FROM roles WHERE name = 'Manager')
                                WHEN e.salary >= 100000 THEN (SELECT id FROM roles WHERE name = 'Senior Software Engineer')
                                ELSE (SELECT id FROM roles WHERE name = 'Software Engineer')
                            END,
                            true,
                            e.salary
                        FROM employees e;
                        """,
                    },
                ],
            },
        }

        api.add_draft_migration(session_id, data_migration)

        # Step 5: Validate complex migration plan
        validation_result = api.validate_session_migrations(session_id)

        assert validation_result["valid"] is True
        assert len(validation_result["migration_validations"]) == 4

        # Check dependency validation
        dependency_check = api.validate_migration_dependencies(session_id)
        assert dependency_check["valid"] is True
        assert len(dependency_check["dependency_chain"]) == 4

        # Step 6: Generate execution plan with dependency ordering
        execution_plan = api.create_execution_plan(
            session_id, enforce_dependencies=True
        )

        # Verify correct execution order
        step_names = [step["migration_name"] for step in execution_plan["steps"]]
        assert step_names.index("create_roles_table") < step_names.index(
            "create_employee_roles_table"
        )
        assert step_names.index("create_employee_roles_table") < step_names.index(
            "add_employee_roles_constraints"
        )
        assert step_names.index("add_employee_roles_constraints") < step_names.index(
            "migrate_employee_data_to_roles"
        )

        # Step 7: Execute with rollback capability
        execution_result = api.execute_session_migrations(
            session_id, dry_run=False, create_rollback_point=True
        )

        assert execution_result["success"] is True
        assert "rollback_point_id" in execution_result

        # Step 8: Verify complex schema state
        final_schema = api.inspect_schema()

        # Verify all tables exist
        assert "roles" in final_schema["tables"]
        assert "employee_roles" in final_schema["tables"]

        # Verify data exists
        conn = await get_test_connection()
        try:
            # Check roles data
            roles_count = await conn.fetchval("SELECT COUNT(*) FROM roles")
            assert roles_count == 4

            # Check employee_roles data
            emp_roles_count = await conn.fetchval("SELECT COUNT(*) FROM employee_roles")
            employees_count = await conn.fetchval("SELECT COUNT(*) FROM employees")
            assert (
                emp_roles_count == employees_count
            )  # Each employee should have one role

            # Verify primary role constraint
            primary_roles_count = await conn.fetchval(
                "SELECT COUNT(*) FROM employee_roles WHERE is_primary = true"
            )
            assert primary_roles_count == employees_count

        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_rollback_complex_migration_workflow(self, initial_schema):
        """
        E2E Test: Test rollback of complex migration workflow
        """
        from dataflow.web.migration_api import WebMigrationAPI

        api = WebMigrationAPI(
            "postgresql://dataflow_test:dataflow_test_password@localhost:5433/dataflow_test"
        )

        session_id = api.create_session("test_rollback_developer")

        # Create a migration that we'll rollback
        problematic_migration = {
            "name": "problematic_changes",
            "type": "multi_operation",
            "spec": {
                "operations": [
                    {
                        "type": "add_column",
                        "table_name": "employees",
                        "column": {
                            "name": "temp_field",
                            "type": "VARCHAR",
                            "length": 50,
                        },
                    },
                    {
                        "type": "create_table",
                        "table_name": "temp_table",
                        "columns": [
                            {"name": "id", "type": "SERIAL", "primary_key": True},
                            {"name": "data", "type": "TEXT"},
                        ],
                    },
                ]
            },
        }

        api.add_draft_migration(session_id, problematic_migration)

        # Execute migration
        execution_result = api.execute_session_migrations(
            session_id, dry_run=False, create_rollback_point=True
        )

        assert execution_result["success"] is True
        rollback_point_id = execution_result["rollback_point_id"]

        # Verify changes were applied
        schema_after = api.inspect_schema()
        assert "temp_table" in schema_after["tables"]
        assert "temp_field" in schema_after["tables"]["employees"]["columns"]

        # Now rollback the changes
        rollback_result = api.rollback_to_point(rollback_point_id)

        assert rollback_result["success"] is True
        assert len(rollback_result["operations_rolled_back"]) == 2

        # Verify rollback was successful
        schema_rolled_back = api.inspect_schema()
        assert "temp_table" not in schema_rolled_back["tables"]
        assert "temp_field" not in schema_rolled_back["tables"]["employees"]["columns"]

        # Original schema should be intact
        assert "companies" in schema_rolled_back["tables"]
        assert "employees" in schema_rolled_back["tables"]


class TestSessionBasedMigrationDevelopment:
    """Test session-based migration development workflows."""

    @pytest.mark.asyncio
    async def test_collaborative_migration_development(self, initial_schema):
        """
        E2E Test: Multiple developers working on migrations collaboratively
        """
        from dataflow.web.migration_api import WebMigrationAPI

        api = WebMigrationAPI(
            "postgresql://dataflow_test:dataflow_test_password@localhost:5433/dataflow_test"
        )

        # Developer 1: Working on user management features
        dev1_session = api.create_session("developer_alice")

        user_features_migration = {
            "name": "add_user_management_features",
            "type": "multi_operation",
            "spec": {
                "operations": [
                    {
                        "type": "add_column",
                        "table_name": "employees",
                        "column": {
                            "name": "status",
                            "type": "VARCHAR",
                            "length": 20,
                            "default": "'active'",
                        },
                    },
                    {
                        "type": "add_column",
                        "table_name": "employees",
                        "column": {
                            "name": "manager_id",
                            "type": "INTEGER",
                            "nullable": True,
                        },
                    },
                ]
            },
        }

        api.add_draft_migration(dev1_session, user_features_migration)

        # Developer 2: Working on audit features
        dev2_session = api.create_session("developer_bob")

        audit_features_migration = {
            "name": "add_audit_features",
            "type": "create_table",
            "spec": {
                "table_name": "audit_log",
                "columns": [
                    {"name": "id", "type": "SERIAL", "primary_key": True},
                    {
                        "name": "table_name",
                        "type": "VARCHAR",
                        "length": 100,
                        "nullable": False,
                    },
                    {"name": "record_id", "type": "INTEGER", "nullable": False},
                    {
                        "name": "action",
                        "type": "VARCHAR",
                        "length": 20,
                        "nullable": False,
                    },
                    {"name": "old_values", "type": "JSONB"},
                    {"name": "new_values", "type": "JSONB"},
                    {"name": "user_id", "type": "INTEGER"},
                    {
                        "name": "timestamp",
                        "type": "TIMESTAMP",
                        "default": "CURRENT_TIMESTAMP",
                    },
                ],
            },
        }

        api.add_draft_migration(dev2_session, audit_features_migration)

        # Team lead: Review and merge migrations
        lead_session = api.create_session("team_lead_charlie")

        # Import migrations from other sessions
        dev1_migrations = api.get_session_migrations(dev1_session)
        dev2_migrations = api.get_session_migrations(dev2_session)

        for migration in dev1_migrations:
            api.add_draft_migration(lead_session, migration)

        for migration in dev2_migrations:
            api.add_draft_migration(lead_session, migration)

        # Add additional constraint migration
        constraints_migration = {
            "name": "add_manager_constraint",
            "type": "add_constraint",
            "spec": {
                "table_name": "employees",
                "constraint": {
                    "type": "foreign_key",
                    "name": "fk_employees_manager",
                    "column": "manager_id",
                    "references": "employees(id)",
                    "on_delete": "SET NULL",
                },
            },
        }

        api.add_draft_migration(lead_session, constraints_migration)

        # Validate combined migrations
        validation_result = api.validate_session_migrations(lead_session)

        assert validation_result["valid"] is True
        assert len(validation_result["migration_validations"]) == 3

        # Check for conflicts
        conflict_check = api.check_migration_conflicts(lead_session)
        assert conflict_check["has_conflicts"] is False

        # Execute combined migrations
        execution_result = api.execute_session_migrations(lead_session, dry_run=False)

        assert execution_result["success"] is True
        assert len(execution_result["executed_migrations"]) == 3

        # Verify all features are in place
        final_schema = api.inspect_schema()

        # Check user management features
        employees_table = final_schema["tables"]["employees"]
        assert "status" in employees_table["columns"]
        assert "manager_id" in employees_table["columns"]

        # Check audit features
        assert "audit_log" in final_schema["tables"]
        audit_table = final_schema["tables"]["audit_log"]
        assert "old_values" in audit_table["columns"]
        assert "JSONB" in audit_table["columns"]["old_values"]["type"]

        # Verify constraints
        manager_fk_exists = any(
            c["name"] == "fk_employees_manager"
            for c in employees_table.get("constraints", [])
            if c["type"] == "foreign_key"
        )
        assert manager_fk_exists

        # Clean up sessions
        api.close_session(dev1_session)
        api.close_session(dev2_session)
        api.close_session(lead_session)

    @pytest.mark.asyncio
    async def test_migration_conflict_resolution(self, initial_schema):
        """
        E2E Test: Handle migration conflicts and resolution
        """
        from dataflow.web.migration_api import WebMigrationAPI

        api = WebMigrationAPI(
            "postgresql://dataflow_test:dataflow_test_password@localhost:5433/dataflow_test"
        )

        # Session 1: Add email column as VARCHAR
        session1 = api.create_session("developer_session1")

        email_varchar_migration = {
            "name": "add_email_varchar",
            "type": "add_column",
            "spec": {
                "table_name": "companies",
                "column": {"name": "contact_email", "type": "VARCHAR", "length": 255},
            },
        }

        api.add_draft_migration(session1, email_varchar_migration)

        # Session 2: Add email column as TEXT (conflict)
        session2 = api.create_session("developer_session2")

        email_text_migration = {
            "name": "add_email_text",
            "type": "add_column",
            "spec": {
                "table_name": "companies",
                "column": {"name": "contact_email", "type": "TEXT"},
            },
        }

        api.add_draft_migration(session2, email_text_migration)

        # Execute first session
        execution1 = api.execute_session_migrations(session1, dry_run=False)
        assert execution1["success"] is True

        # Try to execute second session - should detect conflict
        with pytest.raises(Exception) as exc_info:  # MigrationConflictError
            api.execute_session_migrations(session2, dry_run=False)

        assert "conflict" in str(exc_info.value).lower()

        # Resolve conflict by updating second session
        updated_migration = {
            "name": "add_website_field",
            "type": "add_column",
            "spec": {
                "table_name": "companies",
                "column": {"name": "website", "type": "VARCHAR", "length": 255},
            },
        }

        api.remove_draft_migration(session2, email_text_migration["name"])
        api.add_draft_migration(session2, updated_migration)

        # Now execution should succeed
        execution2 = api.execute_session_migrations(session2, dry_run=False)
        assert execution2["success"] is True

        # Verify final state
        final_schema = api.inspect_schema()
        companies_table = final_schema["tables"]["companies"]
        assert "contact_email" in companies_table["columns"]
        assert "website" in companies_table["columns"]
        assert companies_table["columns"]["contact_email"]["type"] == "VARCHAR(255)"


class TestPerformanceAndScalability:
    """Test performance and scalability of E2E workflows."""

    @pytest.mark.asyncio
    async def test_large_migration_performance(self, clean_database):
        """
        E2E Test: Performance with large migrations
        """
        import time

        from dataflow.web.migration_api import WebMigrationAPI

        api = WebMigrationAPI(
            "postgresql://dataflow_test:dataflow_test_password@localhost:5433/dataflow_test"
        )

        session_id = api.create_session("performance_tester")

        # Create large table migration
        large_table_migration = {
            "name": "create_large_table",
            "type": "create_table",
            "spec": {
                "table_name": "large_table",
                "columns": [{"name": "id", "type": "SERIAL", "primary_key": True}]
                + [
                    {"name": f"column_{i}", "type": "VARCHAR", "length": 100}
                    for i in range(100)  # 100 columns
                ],
            },
        }

        api.add_draft_migration(session_id, large_table_migration)

        # Multiple index creation
        indexes_migration = {
            "name": "create_multiple_indexes",
            "type": "multi_operation",
            "spec": {
                "operations": [
                    {
                        "type": "create_index",
                        "table_name": "large_table",
                        "index_name": f"idx_large_table_col_{i}",
                        "columns": [f"column_{i}"],
                    }
                    for i in range(0, 20, 2)  # 10 indexes
                ]
            },
        }

        api.add_draft_migration(session_id, indexes_migration)

        # Measure performance
        start_time = time.perf_counter()

        # Generate preview
        preview_start = time.perf_counter()
        session_preview = api.generate_session_preview(session_id)
        preview_time = time.perf_counter() - preview_start

        # Validate
        validation_start = time.perf_counter()
        validation_result = api.validate_session_migrations(session_id)
        validation_time = time.perf_counter() - validation_start

        # Execute
        execution_start = time.perf_counter()
        execution_result = api.execute_session_migrations(session_id, dry_run=False)
        execution_time = time.perf_counter() - execution_start

        total_time = time.perf_counter() - start_time

        # Performance assertions
        assert preview_time < 5.0  # Preview should be fast
        assert validation_time < 3.0  # Validation should be reasonable
        assert execution_time < 10.0  # Execution within E2E timeout
        assert total_time < 15.0  # Total workflow time

        # Verify execution success
        assert execution_result["success"] is True
        assert validation_result["valid"] is True

        # Verify schema
        final_schema = api.inspect_schema()
        assert "large_table" in final_schema["tables"]

        large_table = final_schema["tables"]["large_table"]
        assert len(large_table["columns"]) == 101  # 1 id + 100 columns
        assert len(large_table["indexes"]) >= 10  # At least 10 custom indexes

        # Performance metadata
        performance_data = {
            "preview_time_ms": preview_time * 1000,
            "validation_time_ms": validation_time * 1000,
            "execution_time_ms": execution_time * 1000,
            "total_time_ms": total_time * 1000,
            "columns_created": 101,
            "indexes_created": 10,
        }

        # Log performance for monitoring
        api.log_performance_metrics(session_id, performance_data)

    @pytest.mark.asyncio
    async def test_concurrent_session_handling(self, initial_schema):
        """
        E2E Test: Concurrent session handling and isolation
        """
        import asyncio

        from dataflow.web.migration_api import WebMigrationAPI

        api = WebMigrationAPI(
            "postgresql://dataflow_test:dataflow_test_password@localhost:5433/dataflow_test"
        )

        # Create multiple concurrent sessions
        sessions = []
        for i in range(5):
            session_id = api.create_session(f"concurrent_developer_{i}")
            sessions.append(session_id)

        # Add different migrations to each session
        async def add_migration_to_session(session_id, table_suffix):
            migration = {
                "name": f"create_table_{table_suffix}",
                "type": "create_table",
                "spec": {
                    "table_name": f"test_table_{table_suffix}",
                    "columns": [
                        {"name": "id", "type": "SERIAL", "primary_key": True},
                        {"name": "data", "type": "VARCHAR", "length": 100},
                    ],
                },
            }
            api.add_draft_migration(session_id, migration)
            return session_id

        # Add migrations concurrently
        tasks = [
            add_migration_to_session(session_id, i)
            for i, session_id in enumerate(sessions)
        ]

        await asyncio.gather(*tasks)

        # Validate all sessions concurrently
        async def validate_session(session_id):
            return api.validate_session_migrations(session_id)

        validation_tasks = [validate_session(sid) for sid in sessions]
        validation_results = await asyncio.gather(*validation_tasks)

        # All validations should succeed
        for result in validation_results:
            assert result["valid"] is True

        # Execute migrations concurrently
        async def execute_session(session_id):
            return api.execute_session_migrations(session_id, dry_run=False)

        execution_tasks = [execute_session(sid) for sid in sessions]
        execution_results = await asyncio.gather(*execution_tasks)

        # All executions should succeed
        for result in execution_results:
            assert result["success"] is True

        # Verify all tables were created
        final_schema = api.inspect_schema()
        for i in range(5):
            assert f"test_table_{i}" in final_schema["tables"]

        # Clean up sessions
        for session_id in sessions:
            api.close_session(session_id)
