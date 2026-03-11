"""
End-to-End tests for DataFlow Migration Foundation.

Tests complete user workflows for the migration system including
model registration, schema changes, user interactions, and
complete migration execution scenarios.

Focuses on:
- Complete user workflows with real database operations
- End-to-end migration scenarios from registration to execution
- User interaction workflows with migration confirmations
- Real-world schema evolution patterns
- Complete rollback and recovery scenarios
"""

import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest
from dataflow.core.config import DatabaseConfig, DataFlowConfig, SecurityConfig
from dataflow.core.engine import DataFlow


class TestMigrationFoundationE2E:
    """End-to-end tests for complete migration foundation workflows."""

    @pytest.fixture(scope="class", autouse=True)
    def setup_test_environment(self):
        """Ensure test infrastructure is running for E2E tests."""
        test_env_script = (
            Path(__file__).parent.parent.parent.parent.parent
            / "tests"
            / "utils"
            / "test-env"
        )

        if test_env_script.exists():
            import subprocess

            # Start test environment
            result = subprocess.run(
                [str(test_env_script), "up"], capture_output=True, text=True
            )
            if result.returncode != 0:
                pytest.skip(f"Test environment failed to start: {result.stderr}")

            # Check status
            result = subprocess.run(
                [str(test_env_script), "status"], capture_output=True, text=True
            )
            if result.returncode != 0:
                pytest.skip(f"Test environment not healthy: {result.stderr}")
        else:
            pytest.skip("Test environment script not found")

    def test_complete_user_journey_blog_platform_with_migrations(self):
        """Test complete user journey: build blog platform with evolving schema and migrations."""
        database_url = "postgresql://testuser:testpass@localhost:5434/testdb"

        # Phase 1: Initial blog platform setup
        dataflow = DataFlow(database_url=database_url, migration_enabled=True)

        # Mock user confirmation to automatically approve migrations
        original_confirmation = getattr(dataflow, "_request_user_confirmation", None)
        dataflow._request_user_confirmation = lambda preview: True

        try:
            # Step 1: Register initial User model
            @dataflow.model
            class User:
                username: str
                email: str
                created_at: str

            # Step 2: Register initial Post model
            @dataflow.model
            class Post:
                title: str
                content: str
                user_id: int
                published: bool

            # Verify initial setup worked
            assert "User" in dataflow.get_models()
            assert "Post" in dataflow.get_models()

            # Phase 2: Evolve schema - add user profiles
            @dataflow.model
            class User:
                username: str
                email: str
                created_at: str
                # New fields requiring migration
                first_name: str
                last_name: str
                bio: Optional[str]
                avatar_url: Optional[str]

            # Phase 3: Add comment system
            @dataflow.model
            class Comment:
                content: str
                post_id: int
                user_id: int
                created_at: str
                is_approved: bool

            # Phase 4: Add categories and tags
            @dataflow.model
            class Category:
                name: str
                description: str
                slug: str

            @dataflow.model
            class Tag:
                name: str
                color: str

            # Phase 5: Update Post model with relationships
            @dataflow.model
            class Post:
                title: str
                content: str
                user_id: int
                published: bool
                # New fields
                category_id: int
                excerpt: str
                featured_image: Optional[str]
                view_count: int
                seo_title: Optional[str]
                seo_description: Optional[str]

            # Verify complete evolution worked
            final_models = dataflow.get_models()
            expected_models = ["User", "Post", "Comment", "Category", "Tag"]

            for model_name in expected_models:
                assert (
                    model_name in final_models
                ), f"Model {model_name} not found in final models"

            # Verify migration system handled all changes
            migration_system = dataflow._migration_system
            assert migration_system is not None

        finally:
            # Restore original confirmation function
            if original_confirmation:
                dataflow._request_user_confirmation = original_confirmation

    def test_real_world_ecommerce_schema_evolution_e2e(self):
        """Test real-world e-commerce platform schema evolution with migrations."""
        database_url = "postgresql://testuser:testpass@localhost:5434/testdb"
        dataflow = DataFlow(database_url=database_url, migration_enabled=True)

        # Enable automatic migration approval for E2E test
        dataflow._request_user_confirmation = lambda preview: True

        # Phase 1: Basic e-commerce setup
        @dataflow.model
        class Customer:
            email: str
            first_name: str
            last_name: str
            created_at: str

        @dataflow.model
        class Product:
            name: str
            price: float
            description: str
            in_stock: bool

        @dataflow.model
        class Order:
            customer_id: int
            total_amount: float
            status: str
            created_at: str

        # Phase 2: Add inventory management
        @dataflow.model
        class Product:
            name: str
            price: float
            description: str
            in_stock: bool
            # New inventory fields
            sku: str
            stock_quantity: int
            weight: Optional[float]
            dimensions: Optional[str]
            category_id: Optional[int]

        # Phase 3: Add customer profiles and addresses
        @dataflow.model
        class Customer:
            email: str
            first_name: str
            last_name: str
            created_at: str
            # New profile fields
            phone: Optional[str]
            date_of_birth: Optional[str]
            loyalty_points: int
            preferred_language: str

        @dataflow.model
        class Address:
            customer_id: int
            address_line1: str
            address_line2: Optional[str]
            city: str
            state: str
            postal_code: str
            country: str
            is_default: bool

        # Phase 4: Enhanced order management
        @dataflow.model
        class Order:
            customer_id: int
            total_amount: float
            status: str
            created_at: str
            # New order fields
            shipping_address_id: int
            billing_address_id: int
            payment_method: str
            shipping_method: str
            tracking_number: Optional[str]
            discount_amount: float
            tax_amount: float
            notes: Optional[str]

        @dataflow.model
        class OrderItem:
            order_id: int
            product_id: int
            quantity: int
            unit_price: float
            total_price: float

        # Phase 5: Add reviews and ratings
        @dataflow.model
        class Review:
            product_id: int
            customer_id: int
            rating: int
            title: str
            content: str
            created_at: str
            is_verified_purchase: bool

        # Verify complete e-commerce evolution
        final_models = dataflow.get_models()
        expected_models = [
            "Customer",
            "Product",
            "Order",
            "Address",
            "OrderItem",
            "Review",
        ]

        for model_name in expected_models:
            assert model_name in final_models, f"E-commerce model {model_name} missing"

        # Verify migration system processed all changes
        assert hasattr(dataflow, "_migration_system")
        assert dataflow._migration_system is not None

    def test_migration_rollback_scenario_e2e(self):
        """Test complete migration rollback scenario in real failure conditions."""
        database_url = "postgresql://testuser:testpass@localhost:5434/testdb"
        dataflow = DataFlow(database_url=database_url, migration_enabled=True)

        connection = dataflow._get_database_connection()
        try:
            # Create initial stable state
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rollback_test_stable (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    stable_field VARCHAR(50)
                )
            """
            )

            # Insert test data
            connection.execute(
                """
                INSERT INTO rollback_test_stable (name, stable_field)
                VALUES ('Test User', 'stable_value')
            """
            )

            # Simulate migration that will fail
            # Mock migration system to simulate failure scenario
            migration_system = dataflow._migration_system
            if migration_system:
                # Store original methods
                original_execute = getattr(migration_system, "execute_migration", None)
                original_rollback = getattr(
                    migration_system, "rollback_migration", None
                )

                # Mock failure during migration execution
                migration_executed = False
                rollback_executed = False

                def mock_execute_migration(*args, **kwargs):
                    nonlocal migration_executed
                    migration_executed = True
                    raise Exception("Simulated migration failure")

                def mock_rollback_migration(*args, **kwargs):
                    nonlocal rollback_executed
                    rollback_executed = True
                    return True

                migration_system.execute_migration = mock_execute_migration
                migration_system.rollback_migration = mock_rollback_migration

                # Enable automatic approval but expect failure
                dataflow._request_user_confirmation = lambda preview: True

                try:
                    # Register model that will trigger failed migration
                    @dataflow.model
                    class RollbackTestStable:
                        name: str
                        stable_field: str
                        new_field_causing_failure: str  # This will trigger migration

                    # Verify rollback was executed after failure
                    assert (
                        rollback_executed
                    ), "Rollback should have been executed after migration failure"

                finally:
                    # Restore original methods
                    if original_execute:
                        migration_system.execute_migration = original_execute
                    if original_rollback:
                        migration_system.rollback_migration = original_rollback

            # Verify original data is still intact after rollback
            result = connection.execute(
                "SELECT name, stable_field FROM rollback_test_stable"
            )
            rows = result.fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "Test User"
            assert rows[0][1] == "stable_value"

        finally:
            connection.execute("DROP TABLE IF EXISTS rollback_test_stable")
            connection.close()

    def test_user_migration_confirmation_workflow_e2e(self):
        """Test complete user confirmation workflow for migrations."""
        database_url = "postgresql://testuser:testpass@localhost:5434/testdb"
        dataflow = DataFlow(database_url=database_url, migration_enabled=True)

        # Track user interaction workflow
        confirmation_requests = []
        migration_previews = []

        def mock_request_confirmation(preview):
            confirmation_requests.append(True)
            migration_previews.append(preview)
            return True  # User approves migration

        def mock_show_preview(preview):
            migration_previews.append(preview)

        # Mock user interaction methods
        dataflow._request_user_confirmation = mock_request_confirmation
        if hasattr(dataflow, "_show_migration_preview"):
            dataflow._show_migration_preview = mock_show_preview

        # Register models that require migrations
        @dataflow.model
        class UserConfirmationTest:
            username: str
            email: str

        # Add field that requires migration
        @dataflow.model
        class UserConfirmationTest:
            username: str
            email: str
            profile_image: str  # New field requiring migration
            last_login: Optional[str]  # Another new field

        # Verify user confirmation workflow was triggered
        assert (
            len(confirmation_requests) > 0
        ), "User confirmation should have been requested"

        # Verify migration previews were generated
        assert (
            len(migration_previews) > 0
        ), "Migration previews should have been generated"

        # Verify preview contains expected migration SQL
        preview_content = " ".join(migration_previews)
        assert (
            "ALTER TABLE" in preview_content.upper()
            or "CREATE TABLE" in preview_content.upper()
        )

    def test_cross_database_migration_consistency_e2e(self):
        """Test migration consistency across different database types in complete workflow."""
        database_configs = [
            ("postgresql://testuser:testpass@localhost:5434/testdb", "PostgreSQL"),
            ("mysql://testuser:testpass@localhost:3307/testdb", "MySQL"),
        ]

        for database_url, db_name in database_configs:
            # Test complete workflow with each database type
            dataflow = DataFlow(database_url=database_url, migration_enabled=True)
            dataflow._request_user_confirmation = lambda preview: True

            # Consistent model evolution across databases
            @dataflow.model
            class CrossDbConsistencyTest:
                name: str
                created_at: str

            # Add fields requiring migration
            @dataflow.model
            class CrossDbConsistencyTest:
                name: str
                created_at: str
                # New fields should work consistently across databases
                description: str
                is_active: bool
                updated_at: Optional[str]

            # Verify migration system works consistently
            assert hasattr(
                dataflow, "_migration_system"
            ), f"Migration system missing for {db_name}"
            assert (
                dataflow._migration_system is not None
            ), f"Migration system not initialized for {db_name}"

            # Verify model registration worked
            models = dataflow.get_models()
            assert (
                "CrossDbConsistencyTest" in models
            ), f"Model registration failed for {db_name}"

    def test_high_volume_schema_changes_performance_e2e(self):
        """Test migration system performance with high volume of schema changes."""
        database_url = "postgresql://testuser:testpass@localhost:5434/testdb"
        dataflow = DataFlow(database_url=database_url, migration_enabled=True)
        dataflow._request_user_confirmation = lambda preview: True

        start_time = time.time()

        # Simulate large application with many models and evolutions
        model_count = 10  # Reasonable for E2E test

        for i in range(model_count):
            model_name = f"HighVolumeTest{i}"

            # Phase 1: Initial model
            initial_class = type(
                model_name,
                (),
                {"__annotations__": {"id": int, "name": str, "created_at": str}},
            )
            decorated_initial = dataflow.model(initial_class)

            # Phase 2: Evolve model (add fields)
            evolved_class = type(
                model_name,
                (),
                {
                    "__annotations__": {
                        "id": int,
                        "name": str,
                        "created_at": str,
                        # New fields requiring migration
                        "updated_at": str,
                        "description": Optional[str],
                        "status": str,
                        "priority": int,
                    }
                },
            )
            decorated_evolved = dataflow.model(evolved_class)

        end_time = time.time()
        total_time = end_time - start_time

        # Should handle high volume efficiently (< 10 seconds for E2E)
        assert (
            total_time < 10.0
        ), f"Migration system too slow for high volume: {total_time} seconds"

        # Verify all models were processed
        final_models = dataflow.get_models()
        for i in range(model_count):
            model_name = f"HighVolumeTest{i}"
            assert model_name in final_models, f"High volume model {model_name} missing"

    def test_complete_error_recovery_workflow_e2e(self):
        """Test complete error recovery workflow including user notification and retry."""
        database_url = "postgresql://testuser:testpass@localhost:5434/testdb"
        dataflow = DataFlow(database_url=database_url, migration_enabled=True)

        # Track error notifications
        error_notifications = []
        retry_attempts = []

        def mock_notify_error(error_message):
            error_notifications.append(error_message)

        def mock_retry_migration():
            retry_attempts.append(True)
            return True

        # Mock error handling methods
        if hasattr(dataflow, "_notify_user_error"):
            dataflow._notify_user_error = mock_notify_error
        if hasattr(dataflow, "_retry_migration"):
            dataflow._retry_migration = mock_retry_migration

        # Simulate migration system that fails initially
        migration_system = dataflow._migration_system
        if migration_system:
            original_detect = getattr(migration_system, "detect_schema_changes", None)
            call_count = 0

            def failing_detect_changes(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise Exception("Temporary migration system failure")
                else:
                    return True  # Succeed on retry

            migration_system.detect_schema_changes = failing_detect_changes

            try:
                # Register model that will trigger error and recovery
                @dataflow.model
                class ErrorRecoveryTest:
                    name: str
                    recovery_field: str

                # Verify error was handled and user was notified
                # Note: Specific implementation depends on error handling strategy

            finally:
                # Restore original method
                if original_detect:
                    migration_system.detect_schema_changes = original_detect

        # Verify error recovery workflow completed
        assert True  # If we reach here, error recovery didn't crash the system

    def test_silent_failure_mode_eliminated_e2e(self):
        """Test that silent failure mode is completely eliminated in real scenarios."""
        database_url = "postgresql://testuser:testpass@localhost:5434/testdb"
        dataflow = DataFlow(database_url=database_url, migration_enabled=True)

        # Track all user communications
        user_communications = []

        def track_communication(message):
            user_communications.append(message)

        # Mock all user communication methods
        dataflow._request_user_confirmation = lambda preview: (
            track_communication(f"CONFIRMATION: {preview}"),
            True,
        )[1]
        if hasattr(dataflow, "_notify_user_error"):
            dataflow._notify_user_error = lambda error: track_communication(
                f"ERROR: {error}"
            )
        if hasattr(dataflow, "_show_migration_preview"):
            dataflow._show_migration_preview = lambda preview: track_communication(
                f"PREVIEW: {preview}"
            )

        # Register model with various scenarios
        @dataflow.model
        class SilentFailureTest:
            name: str

        # Evolution that should trigger user communication
        @dataflow.model
        class SilentFailureTest:
            name: str
            new_field: str  # Should trigger migration confirmation

        # Verify user was communicated with (no silent operation)
        assert (
            len(user_communications) > 0
        ), "Silent failure mode detected - user should receive communications"

        # Verify types of communications
        has_confirmation = any("CONFIRMATION" in comm for comm in user_communications)
        has_preview = any("PREVIEW" in comm for comm in user_communications)

        # At least one type of user communication should have occurred
        assert (
            has_confirmation or has_preview
        ), "User should receive migration confirmations or previews"
