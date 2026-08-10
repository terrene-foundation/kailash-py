#!/usr/bin/env python3
"""
End-to-End Tests for Core Dependency Analysis Engine - TODO-137 Phase 1

Tests complete dependency analysis workflows from user perspective,
including integration with DataFlow migration system and real-world scenarios.

Following Tier 3 testing guidelines:
- Complete user workflows from start to finish
- Real infrastructure and data (NO MOCKING)
- Timeout: <10 seconds per test
- Tests actual user scenarios and business requirements
- Validates complete dependency analysis to removal planning workflow

E2E Test Setup:
1. Run: ./tests/utils/test-env up && ./tests/utils/test-env status
2. Tests use complete DataFlow + Migration system integration
3. Validates real user scenarios with complex schema dependencies
"""

import asyncio
import logging
import time
from typing import Any, Dict, List

import asyncpg
import pytest

from dataflow import DataFlow
from dataflow.migrations.dependency_analyzer import (
    DependencyAnalyzer,
    DependencyReport,
    DependencyType,
    ImpactLevel,
)
from dataflow.migrations.migration_connection_manager import MigrationConnectionManager

# Import test infrastructure
from tests.infrastructure.test_harness import DatabaseConfig, DatabaseInfrastructure

# Configure logging for E2E test debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# E2E test fixtures
@pytest.fixture(scope="session")
async def e2e_database():
    """Set up E2E test database infrastructure."""
    config = DatabaseConfig.from_environment()
    infrastructure = DatabaseInfrastructure(config)
    await infrastructure.initialize()

    yield infrastructure

    # Cleanup
    if infrastructure._pool:
        await infrastructure._pool.close()


@pytest.fixture(scope="session")
async def e2e_dataflow(e2e_database):
    """Create DataFlow instance for E2E tests."""
    config = e2e_database.config

    # Create DataFlow with real database
    dataflow = DataFlow(config.url, existing_schema_mode=True)

    yield dataflow

    # Cleanup
    if hasattr(dataflow, "close"):
        await dataflow.close()


@pytest.fixture
async def e2e_connection(e2e_database):
    """Direct connection for E2E test setup."""
    pool = e2e_database._pool
    async with pool.acquire() as conn:
        yield conn


@pytest.fixture(autouse=True)
async def clean_e2e_schema(e2e_connection):
    """Clean E2E test schema before each test."""
    # Drop all E2E test objects
    await e2e_connection.execute(
        """
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            -- Drop views
            FOR r IN (SELECT schemaname, viewname FROM pg_views
                     WHERE schemaname = 'public' AND viewname LIKE 'e2e_%')
            LOOP
                EXECUTE 'DROP VIEW IF EXISTS ' || quote_ident(r.schemaname) || '.' || quote_ident(r.viewname) || ' CASCADE';
            END LOOP;

            -- Drop functions
            FOR r IN (SELECT routine_schema, routine_name FROM information_schema.routines
                     WHERE routine_schema = 'public' AND routine_name LIKE 'e2e_%')
            LOOP
                EXECUTE 'DROP FUNCTION IF EXISTS ' || quote_ident(r.routine_schema) || '.' || quote_ident(r.routine_name) || ' CASCADE';
            END LOOP;

            -- Drop tables
            FOR r IN (SELECT schemaname, tablename FROM pg_tables
                     WHERE schemaname = 'public' AND tablename LIKE 'e2e_%')
            LOOP
                EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.schemaname) || '.' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$;
    """
    )


@pytest.mark.e2e
@pytest.mark.timeout(60)
class TestDependencyAnalysisE2E:
    """End-to-end tests for complete dependency analysis workflows."""

    @pytest.mark.asyncio
    async def test_e2e_blog_platform_dependency_analysis(
        self, e2e_dataflow, e2e_connection
    ):
        """
        E2E Test: Blog Platform Column Removal Analysis

        Scenario: Database administrator wants to remove a column from users table
        in a blog platform with complex dependencies. System should detect all
        dependencies and provide safety analysis.
        """
        logger.info("Setting up blog platform schema for E2E dependency analysis")

        # Create realistic blog platform schema
        await e2e_connection.execute(
            """
            -- Users table (target for column removal)
            CREATE TABLE e2e_users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                full_name VARCHAR(255),
                bio TEXT,
                avatar_url VARCHAR(500),
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT NOW(),
                last_login_at TIMESTAMP,
                CONSTRAINT check_email_format CHECK (email LIKE '%@%'),
                CONSTRAINT check_username_length CHECK (LENGTH(username) >= 3),
                CONSTRAINT check_status_valid CHECK (status IN ('active', 'suspended', 'deleted'))
            );

            -- Posts table with FK to users
            CREATE TABLE e2e_posts (
                id SERIAL PRIMARY KEY,
                author_id INTEGER NOT NULL,
                title VARCHAR(255) NOT NULL,
                slug VARCHAR(255) UNIQUE NOT NULL,
                content TEXT,
                status VARCHAR(20) DEFAULT 'draft',
                published_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT fk_posts_author_id FOREIGN KEY (author_id) REFERENCES e2e_users(id) ON DELETE CASCADE
            );

            -- Comments table with FK to both users and posts
            CREATE TABLE e2e_comments (
                id SERIAL PRIMARY KEY,
                post_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT fk_comments_post_id FOREIGN KEY (post_id) REFERENCES e2e_posts(id) ON DELETE CASCADE,
                CONSTRAINT fk_comments_author_id FOREIGN KEY (author_id) REFERENCES e2e_users(id) ON DELETE CASCADE
            );

            -- User sessions table
            CREATE TABLE e2e_user_sessions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id INTEGER NOT NULL,
                session_token VARCHAR(255) UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT fk_sessions_user_id FOREIGN KEY (user_id) REFERENCES e2e_users(id) ON DELETE CASCADE
            );

            -- Views using user data
            CREATE VIEW e2e_active_authors AS
            SELECT u.id, u.username, u.full_name, u.bio, COUNT(p.id) as post_count
            FROM e2e_users u
            LEFT JOIN e2e_posts p ON u.id = p.author_id AND p.status = 'published'
            WHERE u.status = 'active'
            GROUP BY u.id, u.username, u.full_name, u.bio;

            CREATE VIEW e2e_user_activity_summary AS
            SELECT u.id, u.username, u.email, u.last_login_at,
                   COUNT(DISTINCT p.id) as total_posts,
                   COUNT(DISTINCT c.id) as total_comments,
                   MAX(p.published_at) as last_post_date
            FROM e2e_users u
            LEFT JOIN e2e_posts p ON u.id = p.author_id
            LEFT JOIN e2e_comments c ON u.id = c.author_id
            GROUP BY u.id, u.username, u.email, u.last_login_at;

            -- Indexes
            CREATE INDEX e2e_users_username_idx ON e2e_users(username);
            CREATE INDEX e2e_users_email_idx ON e2e_users(email);
            CREATE INDEX e2e_users_status_last_login_idx ON e2e_users(status, last_login_at);
            CREATE INDEX e2e_posts_author_status_idx ON e2e_posts(author_id, status);

            -- Audit trigger
            CREATE TABLE e2e_user_audit (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                old_email VARCHAR(255),
                new_email VARCHAR(255),
                changed_by INTEGER,
                changed_at TIMESTAMP DEFAULT NOW()
            );

            CREATE OR REPLACE FUNCTION e2e_audit_user_email_changes()
            RETURNS TRIGGER AS $$
            BEGIN
                IF OLD.email IS DISTINCT FROM NEW.email THEN
                    INSERT INTO e2e_user_audit (user_id, old_email, new_email)
                    VALUES (NEW.id, OLD.email, NEW.email);
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER e2e_user_email_audit_trigger
                AFTER UPDATE ON e2e_users
                FOR EACH ROW EXECUTE FUNCTION e2e_audit_user_email_changes();
        """
        )

        # Create dependency analyzer
        connection_manager = MigrationConnectionManager(e2e_dataflow)
        analyzer = DependencyAnalyzer(connection_manager)

        try:
            logger.info("Analyzing dependencies for e2e_users.email column removal")

            # **MAIN E2E WORKFLOW**: Analyze dependencies for email column removal
            dependency_report = await analyzer.analyze_column_dependencies(
                "e2e_users", "email"
            )

            # **VALIDATION**: Comprehensive dependency detection
            assert (
                dependency_report.has_dependencies() is True
            ), "Should detect multiple dependencies"

            # Verify foreign key dependencies (CRITICAL)
            # Note: email is not directly referenced by FK, but users table is
            if DependencyType.FOREIGN_KEY in dependency_report.dependencies:
                fk_deps = dependency_report.dependencies[DependencyType.FOREIGN_KEY]
                logger.info(f"Found {len(fk_deps)} foreign key dependencies")

            # Verify view dependencies (HIGH impact)
            assert DependencyType.VIEW in dependency_report.dependencies
            view_deps = dependency_report.dependencies[DependencyType.VIEW]
            view_names = {dep.view_name for dep in view_deps}

            # Should detect views using email column
            assert (
                "e2e_user_activity_summary" in view_names
            ), "Should detect view using email column"
            logger.info(f"Detected view dependencies: {view_names}")

            # Verify index dependencies (MEDIUM impact)
            assert DependencyType.INDEX in dependency_report.dependencies
            index_deps = dependency_report.dependencies[DependencyType.INDEX]
            index_names = {dep.index_name for dep in index_deps}

            # Should detect email index
            assert "e2e_users_email_idx" in index_names, "Should detect email index"
            logger.info(f"Detected index dependencies: {index_names}")

            # Verify constraint dependencies (MEDIUM impact)
            assert DependencyType.CONSTRAINT in dependency_report.dependencies
            constraint_deps = dependency_report.dependencies[DependencyType.CONSTRAINT]
            constraint_names = {dep.constraint_name for dep in constraint_deps}

            # Should detect email format check constraint
            assert (
                "check_email_format" in constraint_names
            ), "Should detect email format constraint"
            logger.info(f"Detected constraint dependencies: {constraint_names}")

            # Verify trigger dependencies (HIGH impact)
            assert DependencyType.TRIGGER in dependency_report.dependencies
            trigger_deps = dependency_report.dependencies[DependencyType.TRIGGER]
            trigger_names = {dep.trigger_name for dep in trigger_deps}

            # Should detect email audit trigger
            assert (
                "e2e_user_email_audit_trigger" in trigger_names
            ), "Should detect email audit trigger"
            logger.info(f"Detected trigger dependencies: {trigger_names}")

            # **E2E WORKFLOW VALIDATION**: Impact assessment
            impact_summary = dependency_report.generate_impact_summary()

            # Should have high-impact dependencies due to views and triggers
            assert (
                impact_summary[ImpactLevel.HIGH] > 0
            ), "Should detect high-impact dependencies"
            assert (
                impact_summary[ImpactLevel.MEDIUM] > 0
            ), "Should detect medium-impact dependencies"

            # **E2E WORKFLOW VALIDATION**: Removal recommendation
            recommendation = dependency_report.get_removal_recommendation()

            # Email column has multiple dependencies, should be flagged as risky
            assert recommendation in [
                "CAUTION",
                "DANGEROUS",
            ], f"Should recommend caution for email removal, got: {recommendation}"

            # **E2E WORKFLOW VALIDATION**: Total dependency count
            total_deps = dependency_report.get_total_dependency_count()
            assert (
                total_deps >= 5
            ), f"Should detect at least 5 dependencies, found: {total_deps}"

            logger.info("E2E Blog Platform Analysis Complete:")
            logger.info(f"  - Total dependencies: {total_deps}")
            logger.info(f"  - Impact summary: {dict(impact_summary)}")
            logger.info(f"  - Removal recommendation: {recommendation}")
            logger.info(
                f"  - Critical dependencies: {len(dependency_report.get_critical_dependencies())}"
            )

        finally:
            connection_manager.close_all_connections()

    @pytest.mark.asyncio
    async def test_e2e_ecommerce_foreign_key_dependency_analysis(
        self, e2e_dataflow, e2e_connection
    ):
        """
        E2E Test: E-commerce Platform Foreign Key Dependency Analysis

        Scenario: E-commerce platform wants to remove user_id column that's heavily
        referenced by foreign keys. System should detect CRITICAL dependencies
        and recommend against removal.
        """
        logger.info("Setting up e-commerce platform schema for FK dependency analysis")

        # Create realistic e-commerce schema with heavy FK usage
        await e2e_connection.execute(
            """
            -- Core users table
            CREATE TABLE e2e_customers (
                id SERIAL PRIMARY KEY,
                customer_code VARCHAR(20) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                first_name VARCHAR(100) NOT NULL,
                last_name VARCHAR(100) NOT NULL,
                phone VARCHAR(20),
                created_at TIMESTAMP DEFAULT NOW()
            );

            -- Multiple tables with FK references to customers.id
            CREATE TABLE e2e_orders (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                order_number VARCHAR(50) UNIQUE NOT NULL,
                total_amount DECIMAL(12,2) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT fk_orders_customer_id FOREIGN KEY (customer_id) REFERENCES e2e_customers(id) ON DELETE RESTRICT
            );

            CREATE TABLE e2e_customer_addresses (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                address_type VARCHAR(20) NOT NULL,
                street_address VARCHAR(255) NOT NULL,
                city VARCHAR(100) NOT NULL,
                postal_code VARCHAR(20),
                is_default BOOLEAN DEFAULT FALSE,
                CONSTRAINT fk_addresses_customer_id FOREIGN KEY (customer_id) REFERENCES e2e_customers(id) ON DELETE CASCADE
            );

            CREATE TABLE e2e_payment_methods (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                payment_type VARCHAR(50) NOT NULL,
                masked_number VARCHAR(20),
                expires_at DATE,
                is_default BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT fk_payment_methods_customer_id FOREIGN KEY (customer_id) REFERENCES e2e_customers(id) ON DELETE CASCADE
            );

            CREATE TABLE e2e_shopping_carts (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                session_id VARCHAR(255),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT fk_shopping_carts_customer_id FOREIGN KEY (customer_id) REFERENCES e2e_customers(id) ON DELETE CASCADE
            );

            CREATE TABLE e2e_customer_reviews (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
                review_text TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT fk_reviews_customer_id FOREIGN KEY (customer_id) REFERENCES e2e_customers(id) ON DELETE CASCADE
            );

            CREATE TABLE e2e_support_tickets (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                ticket_number VARCHAR(50) UNIQUE NOT NULL,
                subject VARCHAR(255) NOT NULL,
                status VARCHAR(20) DEFAULT 'open',
                priority VARCHAR(20) DEFAULT 'medium',
                created_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT fk_support_tickets_customer_id FOREIGN KEY (customer_id) REFERENCES e2e_customers(id) ON DELETE RESTRICT
            );

            CREATE TABLE e2e_loyalty_points (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER UNIQUE NOT NULL,
                total_points INTEGER DEFAULT 0,
                lifetime_points INTEGER DEFAULT 0,
                tier_level VARCHAR(20) DEFAULT 'bronze',
                updated_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT fk_loyalty_points_customer_id FOREIGN KEY (customer_id) REFERENCES e2e_customers(id) ON DELETE CASCADE
            );

            -- Composite foreign key example
            CREATE TABLE e2e_order_items (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price DECIMAL(10,2) NOT NULL,
                CONSTRAINT fk_order_items_customer_id FOREIGN KEY (customer_id) REFERENCES e2e_customers(id),
                CONSTRAINT fk_order_items_order_id FOREIGN KEY (order_id) REFERENCES e2e_orders(id)
            );
        """
        )

        # Create dependency analyzer
        connection_manager = MigrationConnectionManager(e2e_dataflow)
        analyzer = DependencyAnalyzer(connection_manager)

        try:
            logger.info(
                "Analyzing dependencies for e2e_customers.id column removal (CRITICAL FK target)"
            )

            # **MAIN E2E WORKFLOW**: Analyze FK dependencies for customers.id
            start_time = time.time()
            dependency_report = await analyzer.analyze_column_dependencies(
                "e2e_customers", "id"
            )
            analysis_time = time.time() - start_time

            # **PERFORMANCE VALIDATION**: Should complete quickly even with many FKs
            assert (
                analysis_time < 10.0
            ), f"Analysis took too long: {analysis_time:.2f} seconds"

            # **CRITICAL VALIDATION**: Must detect all foreign key dependencies
            assert dependency_report.has_dependencies() is True
            assert DependencyType.FOREIGN_KEY in dependency_report.dependencies

            fk_deps = dependency_report.dependencies[DependencyType.FOREIGN_KEY]
            fk_constraints = {dep.constraint_name for dep in fk_deps}

            # Should detect all FK constraints referencing customers.id
            expected_fk_constraints = {
                "fk_orders_customer_id",
                "fk_addresses_customer_id",
                "fk_payment_methods_customer_id",
                "fk_shopping_carts_customer_id",
                "fk_reviews_customer_id",
                "fk_support_tickets_customer_id",
                "fk_loyalty_points_customer_id",
                "fk_order_items_customer_id",
            }

            found_constraints = expected_fk_constraints.intersection(fk_constraints)
            assert (
                len(found_constraints) >= 7
            ), f"Should find at least 7 FK constraints, found: {len(found_constraints)}"

            logger.info(f"Detected FK constraints: {fk_constraints}")

            # **CRITICAL VALIDATION**: All FK dependencies should be CRITICAL impact
            for fk_dep in fk_deps:
                assert (
                    fk_dep.impact_level == ImpactLevel.CRITICAL
                ), f"FK dependency {fk_dep.constraint_name} should be CRITICAL"
                assert fk_dep.target_table == "e2e_customers"
                assert fk_dep.target_column == "id"

            # **E2E WORKFLOW VALIDATION**: Critical dependencies detection
            critical_deps = dependency_report.get_critical_dependencies()
            assert (
                len(critical_deps) >= 7
            ), f"Should find at least 7 critical dependencies, found: {len(critical_deps)}"

            # **E2E WORKFLOW VALIDATION**: Removal recommendation should be DANGEROUS
            recommendation = dependency_report.get_removal_recommendation()
            assert (
                recommendation == "DANGEROUS"
            ), f"Should recommend DANGEROUS for FK target column, got: {recommendation}"

            # **E2E WORKFLOW VALIDATION**: Impact summary
            impact_summary = dependency_report.generate_impact_summary()
            assert (
                impact_summary[ImpactLevel.CRITICAL] >= 7
            ), "Should have multiple critical dependencies"

            # **DATA LOSS PREVENTION VALIDATION**: Verify cascade analysis
            cascade_fks = [dep for dep in fk_deps if dep.on_delete == "CASCADE"]
            restrict_fks = [dep for dep in fk_deps if dep.on_delete == "RESTRICT"]

            assert len(cascade_fks) > 0, "Should detect CASCADE foreign keys"
            assert len(restrict_fks) > 0, "Should detect RESTRICT foreign keys"

            logger.info("E2E E-commerce FK Analysis Complete:")
            logger.info(f"  - Analysis time: {analysis_time:.2f} seconds")
            logger.info(f"  - Total FK dependencies: {len(fk_deps)}")
            logger.info(f"  - CASCADE FKs: {len(cascade_fks)}")
            logger.info(f"  - RESTRICT FKs: {len(restrict_fks)}")
            logger.info(f"  - Removal recommendation: {recommendation}")
            logger.info(f"  - Critical dependencies: {len(critical_deps)}")

        finally:
            connection_manager.close_all_connections()

    @pytest.mark.asyncio
    async def test_e2e_safe_column_removal_workflow(self, e2e_dataflow, e2e_connection):
        """
        E2E Test: Safe Column Removal Workflow

        Scenario: Database administrator wants to remove a truly unused column
        that has no dependencies. System should detect no dependencies and
        recommend safe removal.
        """
        logger.info("Setting up schema with unused column for safe removal test")

        # Create table with unused column
        await e2e_connection.execute(
            """
            CREATE TABLE e2e_products (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                price DECIMAL(10,2) NOT NULL,
                category VARCHAR(100) NOT NULL,
                unused_legacy_field VARCHAR(255),  -- This column should be safe to remove
                created_at TIMESTAMP DEFAULT NOW()
            );

            -- Create some dependencies on OTHER columns (not unused_legacy_field)
            CREATE INDEX e2e_products_name_idx ON e2e_products(name);
            CREATE INDEX e2e_products_category_price_idx ON e2e_products(category, price);

            CREATE VIEW e2e_product_catalog AS
            SELECT id, name, description, price, category, created_at
            FROM e2e_products
            WHERE price > 0;

            -- Constraint on different column
            ALTER TABLE e2e_products ADD CONSTRAINT check_price_positive CHECK (price > 0);
        """
        )

        # Create dependency analyzer
        connection_manager = MigrationConnectionManager(e2e_dataflow)
        analyzer = DependencyAnalyzer(connection_manager)

        try:
            logger.info("Analyzing dependencies for unused_legacy_field column removal")

            # **MAIN E2E WORKFLOW**: Analyze truly unused column
            dependency_report = await analyzer.analyze_column_dependencies(
                "e2e_products", "unused_legacy_field"
            )

            # **SAFE REMOVAL VALIDATION**: Should detect no dependencies
            assert (
                dependency_report.has_dependencies() is False
            ), "Unused column should have no dependencies"

            # **SAFE REMOVAL VALIDATION**: No critical dependencies
            critical_deps = dependency_report.get_critical_dependencies()
            assert len(critical_deps) == 0, "Should have no critical dependencies"

            # **SAFE REMOVAL VALIDATION**: Removal recommendation should be SAFE
            recommendation = dependency_report.get_removal_recommendation()
            assert (
                recommendation == "SAFE"
            ), f"Should recommend SAFE removal, got: {recommendation}"

            # **SAFE REMOVAL VALIDATION**: Impact summary should be empty
            impact_summary = dependency_report.generate_impact_summary()
            total_impact = sum(impact_summary.values())
            assert total_impact == 0, "Should have no impact dependencies"

            # **SAFE REMOVAL VALIDATION**: Total dependency count should be zero
            total_deps = dependency_report.get_total_dependency_count()
            assert (
                total_deps == 0
            ), f"Should have zero dependencies, found: {total_deps}"

            # **WORKFLOW VALIDATION**: Verify other columns still have dependencies
            # (This ensures our analyzer isn't broken)
            name_report = await analyzer.analyze_column_dependencies(
                "e2e_products", "name"
            )
            assert (
                name_report.has_dependencies() is True
            ), "Name column should have dependencies (index, view)"

            price_report = await analyzer.analyze_column_dependencies(
                "e2e_products", "price"
            )
            assert (
                price_report.has_dependencies() is True
            ), "Price column should have dependencies (constraint, view, index)"

            logger.info("E2E Safe Removal Analysis Complete:")
            logger.info(f"  - Unused column dependencies: {total_deps}")
            logger.info(f"  - Removal recommendation: {recommendation}")
            logger.info(
                f"  - Name column dependencies: {name_report.get_total_dependency_count()}"
            )
            logger.info(
                f"  - Price column dependencies: {price_report.get_total_dependency_count()}"
            )

        finally:
            connection_manager.close_all_connections()

    @pytest.mark.asyncio
    async def test_e2e_performance_large_schema_workflow(
        self, e2e_dataflow, e2e_connection
    ):
        """
        E2E Test: Performance with Large Schema Workflow

        Scenario: Large enterprise database with hundreds of objects.
        Dependency analysis should complete within reasonable time (<30 seconds)
        as specified in requirements.
        """
        logger.info("Setting up large schema for performance testing")

        # Create large schema with many objects
        num_dependent_tables = 50
        num_views = 10

        # Create base table
        await e2e_connection.execute(
            """
            CREATE TABLE e2e_large_base (
                id SERIAL PRIMARY KEY,
                code VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT NOW()
            );
        """
        )

        # Create many dependent tables
        logger.info(f"Creating {num_dependent_tables} dependent tables...")
        for i in range(num_dependent_tables):
            await e2e_connection.execute(
                f"""
                CREATE TABLE e2e_large_dep_{i} (
                    id SERIAL PRIMARY KEY,
                    base_id INTEGER NOT NULL,
                    dep_code VARCHAR(50) NOT NULL,
                    data_{i} VARCHAR(255),
                    value_{i} INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT fk_large_dep_{i}_base_id FOREIGN KEY (base_id) REFERENCES e2e_large_base(id) ON DELETE CASCADE
                );

                CREATE INDEX e2e_large_dep_{i}_base_id_idx ON e2e_large_dep_{i}(base_id);
                CREATE INDEX e2e_large_dep_{i}_code_idx ON e2e_large_dep_{i}(dep_code);
            """
            )

        # Create many views
        logger.info(f"Creating {num_views} views...")
        for i in range(num_views):
            await e2e_connection.execute(
                f"""
                CREATE VIEW e2e_large_view_{i} AS
                SELECT
                    b.id, b.code, b.name, b.status,
                    COUNT(d.id) as dep_{i}_count,
                    SUM(d.value_{i % 10}) as total_value_{i}
                FROM e2e_large_base b
                LEFT JOIN e2e_large_dep_{i % num_dependent_tables} d ON b.id = d.base_id
                WHERE b.status = 'active'
                GROUP BY b.id, b.code, b.name, b.status;
            """
            )

        # Add some constraints
        await e2e_connection.execute(
            """
            ALTER TABLE e2e_large_base ADD CONSTRAINT check_code_format CHECK (code ~ '^[A-Z0-9_]+$');
            ALTER TABLE e2e_large_base ADD CONSTRAINT check_name_length CHECK (LENGTH(name) >= 3);
        """
        )

        # Create dependency analyzer
        connection_manager = MigrationConnectionManager(e2e_dataflow)
        analyzer = DependencyAnalyzer(connection_manager)

        try:
            logger.info(
                f"Starting performance analysis of e2e_large_base.id with {num_dependent_tables} FKs and {num_views} views"
            )

            # **PERFORMANCE TEST**: Large schema analysis
            start_time = time.time()

            dependency_report = await analyzer.analyze_column_dependencies(
                "e2e_large_base", "id"
            )

            analysis_time = time.time() - start_time

            # **PERFORMANCE REQUIREMENT**: Must complete within 30 seconds per requirements
            assert (
                analysis_time < 30.0
            ), f"Analysis took too long: {analysis_time:.2f} seconds (requirement: <30s)"

            # **ACCURACY VALIDATION**: Should detect all dependencies
            assert dependency_report.has_dependencies() is True

            # Should detect all FK dependencies
            fk_deps = dependency_report.dependencies.get(DependencyType.FOREIGN_KEY, [])
            assert (
                len(fk_deps) == num_dependent_tables
            ), f"Should find {num_dependent_tables} FK deps, found {len(fk_deps)}"

            # Should detect view dependencies
            view_deps = dependency_report.dependencies.get(DependencyType.VIEW, [])
            assert (
                len(view_deps) >= num_views
            ), f"Should find at least {num_views} view deps, found {len(view_deps)}"

            # Should detect index dependencies
            index_deps = dependency_report.dependencies.get(DependencyType.INDEX, [])
            assert (
                len(index_deps) >= num_dependent_tables
            ), f"Should find many index deps, found {len(index_deps)}"

            # **PERFORMANCE METRICS**: Log detailed performance info
            total_deps = dependency_report.get_total_dependency_count()
            deps_per_second = total_deps / analysis_time if analysis_time > 0 else 0

            logger.info("E2E Large Schema Performance Analysis Complete:")
            logger.info(
                f"  - Schema size: {num_dependent_tables} tables, {num_views} views"
            )
            logger.info(f"  - Analysis time: {analysis_time:.2f} seconds")
            logger.info(f"  - Total dependencies found: {total_deps}")
            logger.info(f"  - Analysis rate: {deps_per_second:.1f} dependencies/second")
            logger.info(f"  - FK dependencies: {len(fk_deps)}")
            logger.info(f"  - View dependencies: {len(view_deps)}")
            logger.info(f"  - Index dependencies: {len(index_deps)}")

            # **SUCCESS METRICS VALIDATION**
            # - Performance: <30 seconds (checked above)
            # - Accuracy: 100% FK detection
            fk_accuracy = (len(fk_deps) / num_dependent_tables) * 100
            assert (
                fk_accuracy == 100.0
            ), f"FK detection accuracy: {fk_accuracy}% (requirement: 100%)"

            logger.info(f"  - FK Detection Accuracy: {fk_accuracy}%")

        finally:
            connection_manager.close_all_connections()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
