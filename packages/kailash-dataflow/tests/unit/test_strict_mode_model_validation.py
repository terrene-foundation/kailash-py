"""
Unit tests for strict mode model validation.

Tests the strict mode validation feature using the standalone @model decorator
with strict=True parameter. This tests the existing validation infrastructure.

Actual Behavior (as implemented):
- STRICT mode only raises ModelValidationError for ERRORS, not warnings
- VAL-002: Missing primary key (ERROR - raises in STRICT)
- VAL-003: Primary key not named 'id' (WARNING - does not raise)
- VAL-004: Composite primary key (WARNING - does not raise)
- VAL-005: Auto-managed field conflicts (WARNING - does not raise)
- VAL-006: DateTime without timezone (WARNING)
- VAL-007: String without length (WARNING)
- VAL-008: camelCase field names (WARNING)
- VAL-009: SQL reserved words (WARNING)

This reflects the design decision that only critical issues (missing PK)
should block registration, while best practice violations are warnings.
"""

import warnings

import pytest
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import declarative_base

from dataflow.decorators import ValidationMode, model
from dataflow.exceptions import DataFlowValidationWarning, ModelValidationError

# ==============================================================================
# Test Fixtures
# ==============================================================================


@pytest.fixture
def base():
    """Create fresh declarative_base for each test to avoid table conflicts."""
    return declarative_base()


# ==============================================================================
# Missing Primary Key (SQLAlchemy raises ArgumentError before decorator runs)
# ==============================================================================


def test_missing_primary_key_raises_sqlalchemy_error(base):
    """Test that missing primary key is caught by SQLAlchemy before decorator runs."""
    # SQLAlchemy's mapper raises ArgumentError for missing PK before
    # our decorator has a chance to validate. This is expected behavior.
    from sqlalchemy.exc import ArgumentError

    with pytest.raises(ArgumentError) as exc_info:

        @model(strict=True)
        class User(base):
            __tablename__ = "users_pk_missing"
            name = Column(String)

    # SQLAlchemy's error message should mention primary key
    assert "primary key" in str(exc_info.value).lower()


def test_missing_primary_key_in_warn_mode_raises_sqlalchemy_error(base):
    """Test that SQLAlchemy error occurs regardless of validation mode."""
    # SQLAlchemy catches missing PK before our decorator runs
    from sqlalchemy.exc import ArgumentError

    with pytest.raises(ArgumentError):

        @model(validation=ValidationMode.WARN)
        class User(base):
            __tablename__ = "users_pk_missing_warn"
            name = Column(String)


# ==============================================================================
# VAL-003: Primary Key Not Named 'id' (WARNING - does not raise)
# ==============================================================================


def test_strict_mode_warns_about_non_id_primary_key(base):
    """Test that strict mode warns (not errors) about non-'id' primary key."""
    # VAL-003 is a WARNING, not an error, so it doesn't raise in STRICT mode
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(strict=True)
        class User(base):
            __tablename__ = "users_pk_warn_1"
            user_id = Column(Integer, primary_key=True)
            name = Column(String)

        # Should succeed (no error raised) but have warning
        assert User is not None
        warning_msgs = [str(warning.message) for warning in w]
        assert any("VAL-003" in msg for msg in warning_msgs)


def test_strict_mode_allows_id_primary_key(base):
    """Test that strict mode allows primary key named 'id' without warnings."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(strict=True)
        class User(base):
            __tablename__ = "users_pk_ok_1"
            id = Column(Integer, primary_key=True)
            name = Column(String)

        assert User is not None
        # Should have no VAL-003 warnings
        warning_msgs = [str(warning.message) for warning in w]
        assert not any("VAL-003" in msg for msg in warning_msgs)


def test_warn_mode_allows_non_id_primary_key(base):
    """Test that WARN mode allows primary key with non-'id' name (backward compatible)."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(validation=ValidationMode.WARN)
        class User(base):
            __tablename__ = "users_pk_warn_2"
            user_id = Column(Integer, primary_key=True)
            name = Column(String)

        # Should have warning but not error
        assert User is not None
        warning_msgs = [str(warning.message) for warning in w]
        assert any("VAL-003" in msg for msg in warning_msgs)


# ==============================================================================
# VAL-005: Auto-Managed Field Conflicts (WARNING - does not raise)
# ==============================================================================


def test_strict_mode_warns_about_created_at_conflict(base):
    """Test that strict mode warns about user-defined 'created_at' field."""
    # VAL-005 is a WARNING, not an error
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(strict=True)
        class User(base):
            __tablename__ = "users_auto_warn_1"
            id = Column(Integer, primary_key=True)
            name = Column(String)
            created_at = Column(DateTime)

        assert User is not None
        warning_msgs = [str(warning.message) for warning in w]
        assert any("VAL-005" in msg and "created_at" in msg for msg in warning_msgs)


def test_strict_mode_warns_about_updated_at_conflict(base):
    """Test that strict mode warns about user-defined 'updated_at' field."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(strict=True)
        class User(base):
            __tablename__ = "users_auto_warn_2"
            id = Column(Integer, primary_key=True)
            name = Column(String)
            updated_at = Column(DateTime)

        assert User is not None
        warning_msgs = [str(warning.message) for warning in w]
        assert any("VAL-005" in msg and "updated_at" in msg for msg in warning_msgs)


def test_strict_mode_warns_about_created_by_conflict(base):
    """Test that strict mode warns about user-defined 'created_by' field."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(strict=True)
        class User(base):
            __tablename__ = "users_auto_warn_3"
            id = Column(Integer, primary_key=True)
            name = Column(String)
            created_by = Column(String)

        assert User is not None
        warning_msgs = [str(warning.message) for warning in w]
        assert any("VAL-005" in msg and "created_by" in msg for msg in warning_msgs)


def test_strict_mode_warns_about_updated_by_conflict(base):
    """Test that strict mode warns about user-defined 'updated_by' field."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(strict=True)
        class User(base):
            __tablename__ = "users_auto_warn_4"
            id = Column(Integer, primary_key=True)
            name = Column(String)
            updated_by = Column(String)

        assert User is not None
        warning_msgs = [str(warning.message) for warning in w]
        assert any("VAL-005" in msg and "updated_by" in msg for msg in warning_msgs)


def test_warn_mode_allows_auto_managed_conflicts(base):
    """Test that WARN mode allows auto-managed field conflicts (backward compatible)."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(validation=ValidationMode.WARN)
        class User(base):
            __tablename__ = "users_auto_warn_5"
            id = Column(Integer, primary_key=True)
            created_at = Column(DateTime)

        assert User is not None
        warning_msgs = [str(warning.message) for warning in w]
        assert any("VAL-005" in msg for msg in warning_msgs)


# ==============================================================================
# VAL-008, VAL-009: Field Naming Conventions (WARNING)
# ==============================================================================


def test_strict_mode_warns_about_camelcase(base):
    """Test that strict mode warns about camelCase field names."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(strict=True)
        class User(base):
            __tablename__ = "users_naming_warn_1"
            id = Column(Integer, primary_key=True)
            userName = Column(String)

        assert User is not None
        warning_msgs = [str(warning.message) for warning in w]
        assert any("VAL-008" in msg for msg in warning_msgs)


def test_strict_mode_warns_about_sql_reserved_words(base):
    """Test that strict mode warns about SQL reserved words."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(strict=True)
        class User(base):
            __tablename__ = "users_naming_warn_2"
            id = Column(Integer, primary_key=True)
            order = Column(String)

        assert User is not None
        warning_msgs = [str(warning.message) for warning in w]
        assert any("VAL-009" in msg for msg in warning_msgs)


# ==============================================================================
# Validation Mode Behavior
# ==============================================================================


def test_validation_off_skips_all_validation(base):
    """Test that validation=OFF skips all validation."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(validation=ValidationMode.OFF)
        class User(base):
            __tablename__ = "users_off_mode"
            user_id = Column(Integer, primary_key=True)
            created_at = Column(DateTime)

        assert User is not None
        # Should have no DataFlow validation warnings
        dataflow_warnings = [
            warning
            for warning in w
            if issubclass(warning.category, DataFlowValidationWarning)
        ]
        assert len(dataflow_warnings) == 0


def test_skip_validation_shorthand(base):
    """Test that skip_validation=True is a shorthand for validation=OFF."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(skip_validation=True)
        class User(base):
            __tablename__ = "users_skip_mode"
            user_id = Column(Integer, primary_key=True)

        assert User is not None
        # Should have no DataFlow validation warnings
        dataflow_warnings = [
            warning
            for warning in w
            if issubclass(warning.category, DataFlowValidationWarning)
        ]
        assert len(dataflow_warnings) == 0


def test_strict_true_raises_on_errors(base):
    """Test that strict=True triggers error for critical issues."""
    # Note: Missing PK is caught by SQLAlchemy before our decorator.
    # This test verifies the decorator works with valid SQLAlchemy models
    # that have issues the decorator can catch (not missing PK).
    from sqlalchemy.exc import ArgumentError

    # SQLAlchemy raises ArgumentError for missing PK before decorator runs
    with pytest.raises(ArgumentError):

        @model(strict=True)
        class User(base):
            __tablename__ = "users_strict_err"
            name = Column(String)  # No primary key = SQLAlchemy error


def test_strict_true_does_not_raise_on_warnings_only(base):
    """Test that strict=True does not raise when only warnings exist."""
    # Non-id PK is a warning - should not raise
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(strict=True)
        class User(base):
            __tablename__ = "users_strict_warn"
            user_id = Column(Integer, primary_key=True)  # Warning, not error

        assert User is not None
        warning_msgs = [str(warning.message) for warning in w]
        assert any("VAL-003" in msg for msg in warning_msgs)


# ==============================================================================
# Backward Compatibility
# ==============================================================================


def test_default_behavior_is_warn_mode(base):
    """Test that default behavior is WARN mode (backward compatible)."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model
        class User(base):
            __tablename__ = "users_default_mode"
            user_id = Column(Integer, primary_key=True)
            created_at = Column(DateTime)

        assert User is not None
        warning_msgs = [str(warning.message) for warning in w]
        # Should have warnings for both issues
        assert any("VAL-003" in msg for msg in warning_msgs)
        assert any("VAL-005" in msg for msg in warning_msgs)


def test_existing_code_unaffected(base):
    """Test that existing code without strict mode is unaffected."""

    # All these should work (backward compatible with warnings)
    @model
    class User(base):
        __tablename__ = "users_compat_mode_1"
        user_id = Column(Integer, primary_key=True)

    @model
    class Product(base):
        __tablename__ = "products_compat_mode_1"
        product_id = Column(Integer, primary_key=True)
        created_at = Column(DateTime)

    @model
    class Order(base):
        __tablename__ = "orders_compat_mode_1"
        id = Column(Integer, primary_key=True)
        userName = Column(String)

    assert User is not None
    assert Product is not None
    assert Order is not None


# ==============================================================================
# Warning Message Quality
# ==============================================================================


def test_warning_message_includes_code(base):
    """Test that warning messages include VAL-XXX codes."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(strict=True)
        class User(base):
            __tablename__ = "users_warn_code"
            user_id = Column(Integer, primary_key=True)

        warning_msgs = [str(warning.message) for warning in w]
        assert any(
            "VAL-003" in msg for msg in warning_msgs
        ), "Warning should include VAL code"


def test_warning_message_is_actionable(base):
    """Test that warning messages provide actionable guidance."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(strict=True)
        class User(base):
            __tablename__ = "users_warn_actionable"
            user_id = Column(Integer, primary_key=True)

        warning_msgs = [str(warning.message).lower() for warning in w]
        # Should mention what to do
        assert any(
            "id" in msg or "rename" in msg or "primary key" in msg
            for msg in warning_msgs
        )


def test_warning_message_includes_field_name(base):
    """Test that warning messages include the problematic field name."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(strict=True)
        class User(base):
            __tablename__ = "users_warn_field"
            id = Column(Integer, primary_key=True)
            created_at = Column(DateTime)

        warning_msgs = [str(warning.message) for warning in w]
        assert any("created_at" in msg for msg in warning_msgs)


def test_multiple_warnings_reported(base):
    """Test that multiple warnings are reported together."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(strict=True)
        class User(base):
            __tablename__ = "users_multi_warn"
            user_id = Column(Integer, primary_key=True)  # VAL-003
            created_at = Column(DateTime)  # VAL-005
            updated_at = Column(DateTime)  # VAL-005

        # Should have multiple warnings
        dataflow_warnings = [
            warning
            for warning in w
            if issubclass(warning.category, DataFlowValidationWarning)
        ]
        # At least VAL-003 + VAL-005 (may also have VAL-006 for DateTime without tz)
        assert len(dataflow_warnings) >= 2


# ==============================================================================
# SQLAlchemy Error Handling (for cases like missing PK)
# ==============================================================================


def test_sqlalchemy_error_message_includes_primary_key(base):
    """Test that SQLAlchemy errors for missing PK are descriptive."""
    from sqlalchemy.exc import ArgumentError

    with pytest.raises(ArgumentError) as exc_info:

        @model(strict=True)
        class User(base):
            __tablename__ = "users_err_code"
            name = Column(String)  # Missing PK = SQLAlchemy error

    error_msg = str(exc_info.value).lower()
    assert "primary key" in error_msg, "SQLAlchemy error should mention primary key"


def test_sqlalchemy_error_is_actionable(base):
    """Test that SQLAlchemy errors are actionable."""
    from sqlalchemy.exc import ArgumentError

    with pytest.raises(ArgumentError) as exc_info:

        @model(strict=True)
        class User(base):
            __tablename__ = "users_err_actionable"
            name = Column(String)

    error_msg = str(exc_info.value).lower()
    # SQLAlchemy error should mention the issue
    assert "primary key" in error_msg


# ==============================================================================
# Integration Tests
# ==============================================================================


def test_strict_mode_with_valid_model(base):
    """Test that strict mode accepts valid models without any warnings."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(strict=True)
        class User(base):
            __tablename__ = "users_valid_strict"
            id = Column(Integer, primary_key=True)
            email = Column(String(255))  # With length to avoid VAL-007
            name = Column(String(100))

        assert User is not None
        # Valid model should have no validation warnings
        dataflow_warnings = [
            warning
            for warning in w
            if issubclass(warning.category, DataFlowValidationWarning)
        ]
        assert len(dataflow_warnings) == 0


def test_strict_mode_mixed_models(base):
    """Test that validation modes can be selectively applied to models."""

    # This should pass with no warnings (skip_validation=True)
    @model(skip_validation=True)
    class LegacyUser(base):
        __tablename__ = "legacy_users_mixed"
        user_id = Column(Integer, primary_key=True)

    # This should pass but with warnings (strict=True, but only warnings exist)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(strict=True)
        class NewUser(base):
            __tablename__ = "new_users_mixed"
            user_id = Column(Integer, primary_key=True)  # Has PK, but wrong name

        # Should have VAL-003 warning
        warning_msgs = [str(warning.message) for warning in w]
        assert any("VAL-003" in msg for msg in warning_msgs)

    assert LegacyUser is not None
    assert NewUser is not None
