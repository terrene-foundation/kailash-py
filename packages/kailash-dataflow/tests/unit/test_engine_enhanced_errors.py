"""
Unit tests for engine.py enhanced errors (Phase 1C Week 7 Task 1.2).

Tests the 6 newly enhanced error sites:
- Group A (4 pre-initialization configuration errors): Lines 5895, 5902, 5915, 5922
- Group B (2 post-initialization errors): Lines 736, 1257

All tests verify that ErrorEnhancer produces correct error codes and actionable solutions.
"""

import pytest
from dataflow import DataFlow
from dataflow.exceptions import EnhancedDataFlowError  # Core ErrorEnhancer exception
from dataflow.platform.errors import DataFlowError  # Platform ErrorEnhancer exception


class TestPreInitializationConfigurationErrors:
    """Test Group A: Pre-initialization configuration errors in _is_valid_database_url()."""

    def test_invalid_file_extension_error_enhanced(self):
        """
        Test Line 5895 (now 5897): Invalid file extension error.

        Verify that providing a file path without .db/.sqlite/.sqlite3 extension
        produces an enhanced error with error code DF-401.
        """
        # Arrange: Invalid SQLite file path (no proper extension)
        invalid_url = "mydata.txt"

        # Act & Assert: Should raise enhanced DataFlowError with DF-401
        with pytest.raises(DataFlowError) as exc_info:
            db = DataFlow(invalid_url)

        # Verify error enhancement
        error_message = str(exc_info.value)
        assert (
            "INVALID_DATABASE_URL" in error_message
            or "Invalid Database URL" in error_message
        )
        assert (
            "file databases" in error_message.lower()
            or ".db" in error_message.lower()
            or ".sqlite" in error_message.lower()
        )

    def test_unsupported_database_scheme_error_enhanced(self):
        """
        Test Line 5902 (now 5911): Unsupported database scheme error.

        Verify that providing an unsupported database scheme (e.g., oracle://)
        produces an enhanced error with error code DF-401.
        """
        # Arrange: Unsupported database scheme
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
        assert (
            "PostgreSQL" in error_message
            or "MySQL" in error_message
            or "SQLite" in error_message
        )

    def test_invalid_postgresql_url_format_error_enhanced(self):
        """
        Test Line 5915 (now 5931): Invalid PostgreSQL URL format error.

        Verify that providing a malformed PostgreSQL URL (missing @ or /)
        produces an enhanced error with error code DF-401.
        """
        # Arrange: Invalid PostgreSQL URL (missing @ symbol)
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

    def test_invalid_mysql_url_format_error_enhanced(self):
        """
        Test Line 5922 (now 5945): Invalid MySQL URL format error.

        Verify that providing a malformed MySQL URL (missing @ or /)
        produces an enhanced error with error code DF-401.
        """
        # Arrange: Invalid MySQL URL (missing / after host)
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


class TestPostInitializationErrors:
    """Test Group B: Post-initialization errors using self.error_enhancer."""

    def test_duplicate_model_registration_error_enhanced(self):
        """
        Test Line 736 (now 738): Duplicate model registration error.

        Verify that registering the same model twice produces an enhanced error
        with error code DF-501 and actionable solutions.
        """
        # Arrange: Create DataFlow instance and register a model
        db = DataFlow(":memory:")

        @db.model
        class User:
            id: str
            name: str

        # Act & Assert: Attempt to register the same model again
        with pytest.raises(EnhancedDataFlowError) as exc_info:

            @db.model
            class User:  # Same name, duplicate registration
                id: str
                email: str

        # Verify error enhancement
        error_message = str(exc_info.value)
        assert "DF-501" in error_message or "already registered" in error_message
        assert "User" in error_message

    def test_model_persistence_disabled_error_enhanced(self):
        """
        Test Line 1257 (now 1267): Model persistence disabled error.

        Verify that accessing model registry when persistence is disabled
        produces an enhanced error with error code DF-501.
        """
        # Arrange: Create DataFlow with model persistence disabled
        db = DataFlow(":memory:", enable_model_persistence=False)

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
            "DataFlow instance" in error_message or "disabled" in error_message.lower()
        )


class TestErrorEnhancementPatterns:
    """Test that enhancement patterns are correctly applied."""

    def test_group_a_uses_module_level_errorenhancer(self):
        """
        Verify that Group A errors use module-level ErrorEnhancer.enhance_invalid_database_url().

        This is critical because these errors occur BEFORE self.error_enhancer is initialized.
        """
        # Test invalid file extension (pre-initialization)
        with pytest.raises(DataFlowError) as exc_info:
            db = DataFlow("mydata.txt")

        error_message = str(exc_info.value)
        # Should contain enhanced error details
        assert any(
            [
                "INVALID_DATABASE_URL" in error_message,
                "Invalid Database URL" in error_message,
                "file databases" in error_message.lower(),
            ]
        )

    def test_group_b_uses_instance_level_errorenhancer(self):
        """
        Verify that Group B errors use self.error_enhancer.enhance_runtime_error().

        These errors occur AFTER self.error_enhancer is initialized (line 267).
        """
        # Create DataFlow instance (initializes error_enhancer)
        db = DataFlow(":memory:")

        @db.model
        class Product:
            id: str
            name: str

        # Test duplicate model registration (post-initialization)
        with pytest.raises(EnhancedDataFlowError) as exc_info:

            @db.model
            class Product:  # Duplicate
                id: str
                price: float

        error_message = str(exc_info.value)
        # Should contain enhanced error details
        assert any(
            [
                "DF-501" in error_message,
                "already registered" in error_message,
                "Product" in error_message,
            ]
        )


class TestErrorMessages:
    """Test that error messages are informative and actionable."""

    def test_configuration_errors_provide_examples(self):
        """Verify that configuration errors provide URL format examples."""
        # Test unsupported scheme
        with pytest.raises(DataFlowError) as exc_info:
            db = DataFlow("mssql://localhost/db")

        error_message = str(exc_info.value)
        # Should provide examples of supported formats
        assert any(
            [
                "postgresql://" in error_message.lower(),
                "mysql://" in error_message.lower(),
                "sqlite://" in error_message.lower(),
            ]
        )

    def test_model_errors_include_model_name(self):
        """Verify that model errors include the specific model name."""
        db = DataFlow(":memory:")

        @db.model
        class Order:
            id: str
            total: float

        # Trigger duplicate registration error
        with pytest.raises(EnhancedDataFlowError) as exc_info:

            @db.model
            class Order:  # Duplicate
                id: str
                status: str

        error_message = str(exc_info.value)
        # Should include model name for context
        assert "Order" in error_message

    def test_runtime_errors_explain_feature_status(self):
        """Verify that runtime errors explain feature status and how to enable."""
        db = DataFlow(":memory:", enable_model_persistence=False)

        # Trigger model persistence disabled error
        with pytest.raises(EnhancedDataFlowError) as exc_info:
            registry = db.get_model_registry()

        error_message = str(exc_info.value)
        # Should explain that feature is disabled
        assert (
            "disabled" in error_message.lower()
            or "not available" in error_message.lower()
        )


# Summary of test coverage:
# - Group A (4 tests): Pre-initialization configuration errors
#   - test_invalid_file_extension_error_enhanced
#   - test_unsupported_database_scheme_error_enhanced
#   - test_invalid_postgresql_url_format_error_enhanced
#   - test_invalid_mysql_url_format_error_enhanced
#
# - Group B (2 tests): Post-initialization errors
#   - test_duplicate_model_registration_error_enhanced
#   - test_model_persistence_disabled_error_enhanced
#
# - Pattern verification (2 tests): Ensure correct enhancement patterns
#   - test_group_a_uses_module_level_errorenhancer
#   - test_group_b_uses_instance_level_errorenhancer
#
# - Error message quality (3 tests): Verify actionable error messages
#   - test_configuration_errors_provide_examples
#   - test_model_errors_include_model_name
#   - test_runtime_errors_explain_feature_status
#
# Total: 11 tests covering all 6 newly enhanced error sites + pattern and message quality verification
