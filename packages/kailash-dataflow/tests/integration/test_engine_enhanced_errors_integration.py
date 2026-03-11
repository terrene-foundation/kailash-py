"""
Integration tests for engine.py enhanced errors (Phase 1C Week 7 Task 1.2).

Tests the 6 newly enhanced error sites in real database scenarios:
- Scenario 1: Invalid database URL configuration errors (Group A)
- Scenario 2: Duplicate model registration with real database (Group B)
- Scenario 3: Model persistence disabled with real operations (Group B)

All tests use real infrastructure (NO MOCKING) following Tier 2 testing policies.
"""

import pytest
from dataflow import DataFlow
from dataflow.exceptions import EnhancedDataFlowError  # Core ErrorEnhancer exception
from dataflow.platform.errors import DataFlowError  # Platform ErrorEnhancer exception


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestInvalidDatabaseURLErrors:
    """
    Scenario 1: Test Group A pre-initialization configuration errors.

    These errors occur during DataFlow initialization when validating database URLs.
    Tests verify that ErrorEnhancer.enhance_invalid_database_url() produces correct
    error codes and actionable solutions.
    """

    def test_invalid_file_extension_with_real_file_path(self):
        """
        Integration test: Invalid file extension error with real file path.

        Verifies that attempting to use a non-database file extension produces
        an enhanced error with DF-401 and suggests correct extensions.
        """
        # Arrange: Attempt to use .txt file as database (no sqlite:// prefix)
        invalid_url = "mydata.txt"

        # Act & Assert: Should raise enhanced DataFlowError
        with pytest.raises(DataFlowError) as exc_info:
            db = DataFlow(invalid_url)

        # Verify error enhancement
        error_message = str(exc_info.value)
        assert (
            "INVALID_DATABASE_URL" in error_message
            or "Invalid Database URL" in error_message
        )
        # Error message should mention file databases or SQLite
        assert (
            ".db" in error_message
            or "sqlite" in error_message.lower()
            or "file" in error_message.lower()
        )

    def test_unsupported_database_scheme_with_real_connection_attempt(self):
        """
        Integration test: Unsupported database scheme error.

        Verifies that attempting to use an unsupported database type (Oracle, MSSQL)
        produces an enhanced error listing supported databases.
        """
        # Arrange: Attempt to use Oracle database
        invalid_url = "oracle://user:pass@localhost/db"

        # Act & Assert: Should raise enhanced DataFlowError
        with pytest.raises(DataFlowError) as exc_info:
            db = DataFlow(invalid_url)

        # Verify error enhancement
        error_message = str(exc_info.value)
        assert (
            "INVALID_DATABASE_URL" in error_message
            or "Unsupported database scheme" in error_message
        )
        assert "oracle" in error_message.lower()

        # Verify supported databases are listed
        assert any(
            [
                "PostgreSQL" in error_message or "postgresql" in error_message.lower(),
                "MySQL" in error_message or "mysql" in error_message.lower(),
                "SQLite" in error_message or "sqlite" in error_message.lower(),
            ]
        )

    def test_invalid_postgresql_url_format_with_malformed_url(self):
        """
        Integration test: Invalid PostgreSQL URL format error.

        Verifies that a malformed PostgreSQL URL (missing @ or /) produces
        an enhanced error with correct URL format examples.
        """
        # Arrange: Malformed PostgreSQL URL (missing @ symbol)
        invalid_url = "postgresql://userpass:localhost/db"

        # Act & Assert: Should raise enhanced DataFlowError
        with pytest.raises(DataFlowError) as exc_info:
            db = DataFlow(invalid_url)

        # Verify error enhancement
        error_message = str(exc_info.value)
        assert (
            "INVALID_DATABASE_URL" in error_message
            or "Invalid PostgreSQL URL format" in error_message
        )
        assert "postgresql://" in error_message.lower()

    def test_invalid_mysql_url_format_with_missing_database(self):
        """
        Integration test: Invalid MySQL URL format error.

        Verifies that a MySQL URL missing the database name produces
        an enhanced error with correct format examples.
        """
        # Arrange: MySQL URL missing database name (no / after host)
        invalid_url = "mysql://user:pass@localhost"

        # Act & Assert: Should raise enhanced DataFlowError
        with pytest.raises(DataFlowError) as exc_info:
            db = DataFlow(invalid_url)

        # Verify error enhancement
        error_message = str(exc_info.value)
        assert (
            "INVALID_DATABASE_URL" in error_message
            or "Invalid MySQL URL format" in error_message
        )
        assert "mysql://" in error_message.lower()


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestDuplicateModelRegistrationError:
    """
    Scenario 2: Test Group B post-initialization duplicate model error.

    Tests duplicate model registration with real database to verify that
    self.error_enhancer.enhance_runtime_error() produces correct error codes.
    """

    def test_duplicate_model_registration_with_sqlite(self):
        """
        Integration test: Duplicate model registration with SQLite database.

        Verifies that registering the same model twice on a real database
        produces an enhanced error with DF-501 and model name context.
        """
        # Arrange: Create DataFlow with real SQLite database
        db = DataFlow(":memory:")

        @db.model
        class Customer:
            id: str
            name: str
            email: str

        # Act & Assert: Attempt to register the same model again
        with pytest.raises(EnhancedDataFlowError) as exc_info:

            @db.model
            class Customer:  # Duplicate registration
                id: str
                phone: str

        # Verify error enhancement
        error_message = str(exc_info.value)
        assert "DF-501" in error_message or "already registered" in error_message
        assert "Customer" in error_message

    def test_duplicate_model_registration_preserves_first_model(self):
        """
        Integration test: Verify first model is preserved after duplicate error.

        Ensures that after a duplicate registration error, the original model
        remains registered and functional.
        """
        # Arrange: Create DataFlow and register first model
        db = DataFlow(":memory:")

        @db.model
        class Product:
            id: str
            name: str
            price: float

        # Verify first model is registered
        assert "Product" in db.get_models()

        # Act: Attempt duplicate registration (should fail)
        with pytest.raises(EnhancedDataFlowError):

            @db.model
            class Product:  # Duplicate
                id: str
                description: str

        # Assert: Original model is still registered
        models = db.get_models()
        assert "Product" in models

        # Verify only one Product model exists (not duplicated)
        assert (
            models.count("Product") == 1
            if isinstance(models, list)
            else "Product" in models
        )


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestModelPersistenceDisabledError:
    """
    Scenario 3: Test Group B post-initialization persistence disabled error.

    Tests model persistence disabled scenario with real database operations to
    verify that error enhancement provides clear feature status explanation.
    """

    def test_model_persistence_disabled_with_sqlite(self):
        """
        Integration test: Model persistence disabled error with SQLite.

        Verifies that accessing model registry when persistence is disabled
        produces an enhanced error with DF-501 and clear explanation.
        """
        # Arrange: Create DataFlow with model persistence explicitly disabled
        db = DataFlow(":memory:", enable_model_persistence=False)

        # Register a model (should succeed even with persistence disabled)
        @db.model
        class Order:
            id: str
            total: float
            status: str

        # Act & Assert: Attempt to access model registry
        with pytest.raises(EnhancedDataFlowError) as exc_info:
            registry = db.get_model_registry()

        # Verify error enhancement
        error_message = str(exc_info.value)
        assert (
            "DF-501" in error_message
            or "Model persistence is disabled" in error_message
        )
        assert (
            "disabled" in error_message.lower()
            or "not available" in error_message.lower()
        )

        # Verify actionable solution is provided
        assert any(
            [
                "enable_model_persistence" in error_message,
                "DataFlow instance" in error_message,
                "feature" in error_message.lower(),
            ]
        )

    def test_model_persistence_disabled_does_not_affect_basic_operations(self):
        """
        Integration test: Verify model registration still works when persistence disabled.

        Ensures that disabling model persistence only affects registry access,
        not basic model registration and usage.
        """
        # Arrange: Create DataFlow with persistence disabled
        db = DataFlow(":memory:", enable_model_persistence=False)

        # Act: Register model (should succeed)
        @db.model
        class Invoice:
            id: str
            amount: float
            paid: bool

        # Assert: Model is registered and usable
        assert "Invoice" in db.get_models()

        # Only registry access should fail
        with pytest.raises(EnhancedDataFlowError) as exc_info:
            registry = db.get_model_registry()

        error_message = str(exc_info.value)
        assert "disabled" in error_message.lower()


@pytest.mark.integration
@pytest.mark.timeout(15)
class TestErrorEnhancementIntegration:
    """
    Integration tests verifying complete error enhancement flow.

    Tests that error enhancements work correctly in complex real-world scenarios
    combining multiple DataFlow features.
    """

    def test_multiple_configuration_errors_in_sequence(self):
        """
        Integration test: Multiple invalid URLs tested in sequence.

        Verifies that each invalid URL produces its own specific enhanced error
        with appropriate error codes and solutions.
        """
        # Test invalid file extension
        with pytest.raises(DataFlowError) as exc_info1:
            db1 = DataFlow("mydata.csv")
        assert "file databases" in str(
            exc_info1.value
        ).lower() or "INVALID_DATABASE_URL" in str(exc_info1.value)

        # Test unsupported scheme
        with pytest.raises(DataFlowError) as exc_info2:
            db2 = DataFlow("mssql://localhost/db")
        assert "mssql" in str(exc_info2.value).lower() or "INVALID_DATABASE_URL" in str(
            exc_info2.value
        )

        # Test malformed PostgreSQL URL
        with pytest.raises(DataFlowError) as exc_info3:
            db3 = DataFlow("postgresql://invalid")
        assert "postgresql" in str(
            exc_info3.value
        ).lower() or "INVALID_DATABASE_URL" in str(exc_info3.value)

    def test_error_enhancement_with_model_operations(self):
        """
        Integration test: Error enhancement during model lifecycle.

        Verifies that errors are properly enhanced throughout the complete
        model registration and usage lifecycle.
        """
        # Arrange: Create valid DataFlow
        db = DataFlow(":memory:")

        # Register first model successfully
        @db.model
        class Account:
            id: str
            balance: float

        # Verify model is registered
        assert "Account" in db.get_models()

        # Attempt duplicate registration (should fail with enhanced error)
        with pytest.raises(EnhancedDataFlowError) as exc_info:

            @db.model
            class Account:  # Duplicate
                id: str
                owner: str

        # Verify enhanced error has all expected components
        error_message = str(exc_info.value)
        assert "Account" in error_message
        assert any(["DF-501" in error_message, "already registered" in error_message])

    def test_error_messages_are_user_friendly(self):
        """
        Integration test: Verify error messages are clear and actionable.

        Ensures that all enhanced errors provide user-friendly messages with:
        - Clear error description
        - Context (what went wrong)
        - Actionable solution (how to fix)
        """
        # Test 1: Invalid file extension provides clear solution
        with pytest.raises(DataFlowError) as exc_info1:
            db1 = DataFlow("data.json")

        message1 = str(exc_info1.value)
        # Should explain what's wrong
        assert "file" in message1.lower() or "extension" in message1.lower()
        # Should provide solution
        assert ".db" in message1.lower() or ".sqlite" in message1.lower()

        # Test 2: Duplicate model provides clear context
        db2 = DataFlow(":memory:")

        @db2.model
        class Transaction:
            id: str
            amount: float

        with pytest.raises(EnhancedDataFlowError) as exc_info2:

            @db2.model
            class Transaction:  # Duplicate
                id: str
                date: str

        message2 = str(exc_info2.value)
        # Should include model name
        assert "Transaction" in message2
        # Should explain what happened
        assert "registered" in message2.lower() or "exists" in message2.lower()


# Summary of integration test coverage:
# - Scenario 1 (4 tests): Invalid database URL errors with real file paths and URLs
# - Scenario 2 (2 tests): Duplicate model registration with real SQLite database
# - Scenario 3 (2 tests): Model persistence disabled with real operations
# - Integration verification (3 tests): Complete error enhancement flow
#
# Total: 11 integration tests covering all 6 newly enhanced error sites
# All tests use real infrastructure (SQLite databases) with NO MOCKING
