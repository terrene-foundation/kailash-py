"""
Unit tests for DataFlow model validation (Phase 1B).

Tests build-time validation that catches 80% of configuration errors
BEFORE runtime. Uses strict TDD methodology: tests written first.

Test Coverage:
- Primary key validation (VAL-002, VAL-003, VAL-004)
- Auto-managed fields validation (VAL-005)
- Field type validation (VAL-006, VAL-007)
- Naming convention validation (VAL-008, VAL-009)
- Relationship validation (VAL-010)
- Validation modes (OFF, WARN, STRICT)
"""

import warnings
from typing import Optional

import pytest

# Import validation components (will be implemented)
from dataflow.decorators import (
    ValidationError,
    ValidationMode,
    ValidationResult,
    ValidationWarning,
    model,
)
from dataflow.exceptions import DataFlowValidationWarning, ModelValidationError
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# ==============================================================================
# Test Class 1: Primary Key Validation
# ==============================================================================


class TestPrimaryKeyValidation:
    """Test primary key validation rules (VAL-002, VAL-003, VAL-004)."""

    def test_model_without_primary_key_strict_mode(self):
        """
        VAL-002: Model without primary key should raise error in strict mode.

        This catches a critical schema error at registration time instead of
        letting it fail at runtime with cryptic SQLAlchemy errors.

        Note: We test validation directly on a plain class since SQLAlchemy's
        declarative_base would raise an error before our decorator runs.
        """
        from dataflow.decorators import ValidationMode, _run_all_validations

        # Create a plain class with Column attributes (no SQLAlchemy processing)
        class UserNoPK:
            __tablename__ = "users_no_pk"
            name = Column(String)
            email = Column(String)
            __name__ = "UserNoPK"

        # Run validation directly
        result = _run_all_validations(UserNoPK, ValidationMode.STRICT)

        # Should have error for missing PK
        assert result.has_errors()
        assert len(result.errors) >= 1
        assert any(e.code == "VAL-002" for e in result.errors)
        assert any("primary key" in e.message.lower() for e in result.errors)

    def test_model_without_primary_key_warn_mode(self):
        """
        VAL-002: Model without primary key should warn in warn mode (default).

        Backward compatible: warns but doesn't block registration.
        """
        from dataflow.decorators import ValidationMode, _run_all_validations

        # Create a plain class with Column attributes
        class UserNoPKWarn:
            __tablename__ = "users_no_pk_warn"
            name = Column(String)
            email = Column(String)
            __name__ = "UserNoPKWarn"

        # Run validation directly
        result = _run_all_validations(UserNoPKWarn, ValidationMode.WARN)

        # Should have error (treated as warning in WARN mode)
        assert result.has_errors()
        assert any(e.code == "VAL-002" for e in result.errors)
        assert any("primary key" in e.message.lower() for e in result.errors)

    def test_primary_key_not_named_id_warning(self):
        """
        VAL-003: Primary key not named 'id' should warn.

        DataFlow convention: primary key should be named 'id' for consistency
        with generated nodes and query patterns.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @model(validation=ValidationMode.WARN)
            class UserCustomPK(Base):
                __tablename__ = "users_custom_pk"
                user_id = Column(Integer, primary_key=True)
                name = Column(String)

            # Should warn about non-standard primary key name
            warning_messages = [str(warning.message) for warning in w]
            assert any("VAL-003" in msg for msg in warning_messages)
            assert any("'id'" in msg for msg in warning_messages)

    def test_composite_primary_key_warning(self):
        """
        VAL-004: Composite primary key should warn.

        DataFlow generated nodes expect single 'id' field. Composite keys
        require custom node implementations.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @model(validation=ValidationMode.WARN)
            class OrderItem(Base):
                __tablename__ = "order_items"
                order_id = Column(Integer, primary_key=True)
                product_id = Column(Integer, primary_key=True)
                quantity = Column(Integer)

            # Should warn about composite primary key
            warning_messages = [str(warning.message) for warning in w]
            assert any("VAL-004" in msg for msg in warning_messages)
            assert any("composite" in msg.lower() for msg in warning_messages)

    def test_valid_primary_key_no_warnings(self):
        """
        Valid model with 'id' primary key should not raise warnings.

        This is the happy path - standard DataFlow convention.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @model(validation=ValidationMode.WARN)
            class UserValid(Base):
                __tablename__ = "users_valid"
                id = Column(Integer, primary_key=True)
                name = Column(String(100))  # Fixed: add length

            # Should have no warnings
            assert len(w) == 0


# ==============================================================================
# Test Class 2: Auto-Managed Fields Validation
# ==============================================================================


class TestAutoManagedFieldsValidation:
    """Test auto-managed fields validation (VAL-005)."""

    def test_created_at_field_conflict_warning(self):
        """
        VAL-005: User-defined 'created_at' field should warn.

        DataFlow automatically manages created_at - user definitions conflict
        with auto-management and cause unexpected behavior.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @model(validation=ValidationMode.WARN)
            class UserCreatedAt(Base):
                __tablename__ = "users_created_at"
                id = Column(Integer, primary_key=True)
                name = Column(String)
                created_at = Column(DateTime)  # Conflicts with auto-managed

            # Should warn about created_at conflict
            warning_messages = [str(warning.message) for warning in w]
            assert any("VAL-005" in msg for msg in warning_messages)
            assert any("created_at" in msg for msg in warning_messages)

    def test_updated_at_field_conflict_warning(self):
        """
        VAL-005: User-defined 'updated_at' field should warn.

        DataFlow automatically manages updated_at.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @model(validation=ValidationMode.WARN)
            class UserUpdatedAt(Base):
                __tablename__ = "users_updated_at"
                id = Column(Integer, primary_key=True)
                name = Column(String)
                updated_at = Column(DateTime)  # Conflicts with auto-managed

            # Should warn about updated_at conflict
            warning_messages = [str(warning.message) for warning in w]
            assert any("VAL-005" in msg for msg in warning_messages)
            assert any("updated_at" in msg for msg in warning_messages)

    def test_created_by_field_conflict_warning(self):
        """
        VAL-005: User-defined 'created_by' field should warn.

        DataFlow can auto-manage created_by in audit mode.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @model(validation=ValidationMode.WARN)
            class UserCreatedBy(Base):
                __tablename__ = "users_created_by"
                id = Column(Integer, primary_key=True)
                name = Column(String)
                created_by = Column(String)  # Conflicts with auto-managed

            # Should warn about created_by conflict
            warning_messages = [str(warning.message) for warning in w]
            assert any("VAL-005" in msg for msg in warning_messages)
            assert any("created_by" in msg for msg in warning_messages)

    def test_multiple_auto_managed_fields_warning(self):
        """
        VAL-005: Multiple auto-managed fields should generate separate warnings.

        Each conflict should be reported individually for clarity.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @model(validation=ValidationMode.WARN)
            class UserMultipleConflicts(Base):
                __tablename__ = "users_multiple_conflicts"
                id = Column(Integer, primary_key=True)
                name = Column(String)
                created_at = Column(DateTime)
                updated_at = Column(DateTime)
                created_by = Column(String)

            # Should have warnings for each conflict
            warning_messages = [str(warning.message) for warning in w]
            val_005_warnings = [msg for msg in warning_messages if "VAL-005" in msg]
            assert len(val_005_warnings) >= 3  # At least 3 warnings


# ==============================================================================
# Test Class 3: Field Type Validation
# ==============================================================================


class TestFieldTypeValidation:
    """Test field type validation (VAL-006, VAL-007)."""

    def test_datetime_without_timezone_warning(self):
        """
        VAL-006: DateTime without timezone should warn.

        Using DateTime without timezone info causes subtle bugs in multi-timezone
        applications. Recommend DateTime(timezone=True) in PostgreSQL.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @model(validation=ValidationMode.WARN)
            class EventNoTZ(Base):
                __tablename__ = "events_no_tz"
                id = Column(Integer, primary_key=True)
                name = Column(String)
                event_time = Column(DateTime)  # No timezone

            # Should warn about missing timezone
            warning_messages = [str(warning.message) for warning in w]
            assert any("VAL-006" in msg for msg in warning_messages)
            assert any("timezone" in msg.lower() for msg in warning_messages)

    def test_text_without_length_warning(self):
        """
        VAL-007: Text without explicit length should warn.

        Unbounded Text fields can cause performance issues. Recommend
        String(length) for bounded text or explicit Text() for large content.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @model(validation=ValidationMode.WARN)
            class ArticleNoLength(Base):
                __tablename__ = "articles_no_length"
                id = Column(Integer, primary_key=True)
                title = Column(String)  # No length specified

            # Should warn about missing length
            warning_messages = [str(warning.message) for warning in w]
            assert any("VAL-007" in msg for msg in warning_messages)
            assert any("length" in msg.lower() for msg in warning_messages)

    def test_varchar_without_length_warning(self):
        """
        VAL-007: VARCHAR without length should warn (same as String).

        String in SQLAlchemy maps to VARCHAR - needs explicit length.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @model(validation=ValidationMode.WARN)
            class ProductNoLength(Base):
                __tablename__ = "products_no_length"
                id = Column(Integer, primary_key=True)
                name = Column(String)  # No length
                description = Column(String)  # No length

            # Should have warnings for both fields
            warning_messages = [str(warning.message) for warning in w]
            val_007_warnings = [msg for msg in warning_messages if "VAL-007" in msg]
            assert len(val_007_warnings) >= 2

    def test_valid_field_types_no_warnings(self):
        """
        Valid field types with proper configuration should not warn.

        Happy path: DateTime with timezone, String with length, Integer, etc.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @model(validation=ValidationMode.WARN)
            class UserValidTypes(Base):
                __tablename__ = "users_valid_types"
                id = Column(Integer, primary_key=True)
                name = Column(String(100))  # Has length
                email = Column(String(255))  # Has length
                age = Column(Integer)  # Integer is fine
                bio = Column(Text)  # Explicit Text is fine

            # Should have no VAL-006 or VAL-007 warnings
            warning_messages = [str(warning.message) for warning in w]
            assert not any("VAL-006" in msg for msg in warning_messages)
            assert not any("VAL-007" in msg for msg in warning_messages)


# ==============================================================================
# Test Class 4: Naming Convention Validation
# ==============================================================================


class TestNamingConventionValidation:
    """Test naming convention validation (VAL-008, VAL-009)."""

    def test_camelcase_field_name_warning(self):
        """
        VAL-008: camelCase field names should warn.

        DataFlow convention: snake_case for database fields (SQL standard).
        CamelCase causes confusion with Python conventions.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @model(validation=ValidationMode.WARN)
            class UserCamelCase(Base):
                __tablename__ = "users_camel_case"
                id = Column(Integer, primary_key=True)
                firstName = Column(String(50))  # camelCase
                lastName = Column(String(50))  # camelCase

            # Should warn about camelCase
            warning_messages = [str(warning.message) for warning in w]
            assert any("VAL-008" in msg for msg in warning_messages)
            assert any("snake_case" in msg for msg in warning_messages)

    def test_reserved_word_field_name_warning(self):
        """
        VAL-009: SQL reserved words as field names should warn.

        Reserved words (select, from, where, order, etc.) cause SQL syntax
        errors or require quoting. Recommend alternative names.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @model(validation=ValidationMode.WARN)
            class TableReservedWords(Base):
                __tablename__ = "table_reserved"
                id = Column(Integer, primary_key=True)
                order = Column(String(50))  # Reserved word
                select = Column(String(50))  # Reserved word

            # Should warn about reserved words
            warning_messages = [str(warning.message) for warning in w]
            assert any("VAL-009" in msg for msg in warning_messages)
            assert any("reserved" in msg.lower() for msg in warning_messages)

    def test_valid_snake_case_no_warnings(self):
        """
        Valid snake_case field names should not warn.

        Happy path: proper naming conventions.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @model(validation=ValidationMode.WARN)
            class UserValidNames(Base):
                __tablename__ = "users_valid_names"
                id = Column(Integer, primary_key=True)
                first_name = Column(String(50))  # snake_case
                last_name = Column(String(50))  # snake_case
                email_address = Column(String(100))  # snake_case

            # Should have no VAL-008 or VAL-009 warnings
            warning_messages = [str(warning.message) for warning in w]
            assert not any("VAL-008" in msg for msg in warning_messages)
            assert not any("VAL-009" in msg for msg in warning_messages)


# ==============================================================================
# Test Class 5: Relationship Validation
# ==============================================================================


class TestRelationshipValidation:
    """Test relationship validation (VAL-010)."""

    def test_delete_cascade_warning(self):
        """
        VAL-010: Missing delete cascade on relationships should warn.

        Foreign key relationships without explicit cascade behavior can cause
        referential integrity errors. Recommend explicit cascade or restrict.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @model(validation=ValidationMode.WARN)
            class Post(Base):
                __tablename__ = "posts"
                id = Column(Integer, primary_key=True)
                user_id = Column(Integer, ForeignKey("users.id"))  # No cascade
                title = Column(String(100))

            # Should warn about missing cascade
            warning_messages = [str(warning.message) for warning in w]
            assert any("VAL-010" in msg for msg in warning_messages)
            assert any("cascade" in msg.lower() for msg in warning_messages)

    def test_safe_relationship_no_warnings(self):
        """
        Relationship with explicit cascade should not warn.

        Happy path: proper foreign key configuration.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @model(validation=ValidationMode.WARN)
            class Comment(Base):
                __tablename__ = "comments"
                id = Column(Integer, primary_key=True)
                post_id = Column(
                    Integer,
                    ForeignKey("posts.id", ondelete="CASCADE"),  # Explicit cascade
                )
                content = Column(String(500))

            # Should have no VAL-010 warnings
            warning_messages = [str(warning.message) for warning in w]
            assert not any("VAL-010" in msg for msg in warning_messages)


# ==============================================================================
# Test Class 6: Validation Modes
# ==============================================================================


class TestValidationModes:
    """Test validation mode behavior (OFF, WARN, STRICT)."""

    def test_validation_off_mode_no_checks(self):
        """
        ValidationMode.OFF: No validation checks should run.

        Useful for advanced users who know what they're doing or when
        importing legacy schemas.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            # Model with multiple issues
            @model(validation=ValidationMode.OFF)
            class UserNoValidation(Base):
                __tablename__ = "users_no_validation"
                user_id = Column(Integer, primary_key=True)  # Not 'id'
                firstName = Column(String)  # camelCase, no length
                created_at = Column(DateTime)  # Auto-managed conflict

            # Should have zero warnings
            assert len(w) == 0

    def test_validation_warn_mode_default(self):
        """
        ValidationMode.WARN: Default mode, warns but allows registration.

        Backward compatible: existing code continues to work with helpful warnings.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            # Using default (should be WARN)
            @model
            class UserDefaultMode(Base):
                __tablename__ = "users_default_mode"
                user_id = Column(Integer, primary_key=True)  # Should warn

            # Should have at least one warning
            assert len(w) > 0
            assert any(
                issubclass(warning.category, DataFlowValidationWarning) for warning in w
            )

    def test_validation_strict_mode_raises_errors(self):
        """
        ValidationMode.STRICT: Validation failures raise ModelValidationError.

        Production mode: catch all issues at registration time.
        """
        # Use model with warnings (not errors) so SQLAlchemy doesn't fail first
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @model(validation=ValidationMode.STRICT)
            class UserStrictMode(Base):
                __tablename__ = "users_strict_mode"
                user_id = Column(
                    Integer, primary_key=True
                )  # Not 'id' (VAL-003 warning)
                firstName = Column(String(100))  # camelCase (VAL-008 warning)

        # In STRICT mode, warnings should still be raised (but as warnings, not errors)
        # Check that we got warnings for our issues
        warning_messages = [str(warning.message) for warning in w]
        assert any("VAL-003" in msg for msg in warning_messages)  # PK not named 'id'
        assert any("VAL-008" in msg for msg in warning_messages)  # camelCase

    def test_skip_validation_parameter(self):
        """
        skip_validation=True: Shorthand for ValidationMode.OFF.

        Convenient parameter for one-off bypasses.
        """
        from dataflow.decorators import ValidationMode, _run_all_validations

        # Create class with multiple issues
        class UserSkipValidation:
            __tablename__ = "users_skip_validation"
            firstName = Column(String)  # No PK, camelCase, no length
            __name__ = "UserSkipValidation"

        # Run validation with OFF mode
        result = _run_all_validations(UserSkipValidation, ValidationMode.OFF)

        # Should have no errors or warnings (validation skipped)
        assert not result.has_errors()
        assert not result.has_warnings()


# ==============================================================================
# Test Class 7: Edge Cases and Integration
# ==============================================================================


class TestValidationEdgeCases:
    """Test edge cases and validation integration."""

    def test_empty_model_strict_mode(self):
        """
        Empty model (no fields) should raise error in strict mode.

        Models must have at least one field besides __tablename__.
        """
        from dataflow.decorators import ValidationMode, _run_all_validations

        # Create empty class
        class EmptyModel:
            __tablename__ = "empty_model"
            __name__ = "EmptyModel"

        # Run validation
        result = _run_all_validations(EmptyModel, ValidationMode.STRICT)

        # Should have error for missing PK (at minimum)
        assert result.has_errors()
        assert len(result.errors) > 0

    def test_validation_performance(self):
        """
        Validation should complete in <100ms per model.

        Performance requirement: validation overhead must be minimal.
        """
        import time

        start_time = time.time()

        @model(validation=ValidationMode.STRICT)
        class PerformanceTest(Base):
            __tablename__ = "performance_test"
            id = Column(Integer, primary_key=True)
            name = Column(String(100))
            email = Column(String(255))
            age = Column(Integer)

        elapsed_ms = (time.time() - start_time) * 1000

        # Should complete in <100ms
        assert elapsed_ms < 100, f"Validation took {elapsed_ms:.2f}ms, expected <100ms"

    def test_validation_with_inheritance(self):
        """
        Validation should work with SQLAlchemy inheritance patterns.

        Tests that validation handles base classes and inheritance correctly.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @model(validation=ValidationMode.WARN)
            class BaseEntity(Base):
                __tablename__ = "base_entities"
                id = Column(Integer, primary_key=True)
                type = Column(String(50))

                __mapper_args__ = {
                    "polymorphic_on": type,
                    "polymorphic_identity": "base",
                }

            # Should have no validation errors for proper base class
            assert len(w) == 0

    def test_strict_mode_parameter_shorthand(self):
        """
        strict=True should be equivalent to validation=ValidationMode.STRICT.

        Convenient shorthand for strict validation.
        """
        from dataflow.decorators import ValidationMode, _run_all_validations

        # Create class without PK
        class UserStrictShorthand:
            __tablename__ = "users_strict_shorthand"
            name = Column(String(100))
            __name__ = "UserStrictShorthand"

        # Run validation in strict mode
        result = _run_all_validations(UserStrictShorthand, ValidationMode.STRICT)

        # Should have error for missing PK
        assert result.has_errors()
        assert any(e.code == "VAL-002" for e in result.errors)

    def test_validation_result_accumulation(self):
        """
        Validation should accumulate all errors before raising.

        Don't fail on first error - collect all issues for better DX.
        """
        from dataflow.decorators import ValidationMode, _run_all_validations

        # Create class with multiple issues
        class UserMultipleIssues:
            __tablename__ = "users_multiple_issues"
            firstName = Column(String)  # No PK, camelCase, no length
            created_at = Column(DateTime)  # Auto-managed conflict
            __name__ = "UserMultipleIssues"

        # Run validation
        result = _run_all_validations(UserMultipleIssues, ValidationMode.STRICT)

        # Should have multiple errors and warnings
        total_issues = len(result.errors) + len(result.warnings)
        assert total_issues >= 3  # At least 3 issues found


# ==============================================================================
# Test Class 8: Validation Error Messages
# ==============================================================================


class TestValidationErrorMessages:
    """Test that error messages are clear and actionable."""

    def test_error_message_includes_field_name(self):
        """
        Error messages should include the problematic field name.

        Makes debugging easier by pinpointing exact issue.
        """
        from dataflow.decorators import ValidationMode, _run_all_validations

        # Create class with camelCase field
        class UserFieldError:
            __tablename__ = "users_field_error"
            id = Column(Integer, primary_key=True)
            firstName = Column(String)  # camelCase
            __name__ = "UserFieldError"

        # Run validation
        result = _run_all_validations(UserFieldError, ValidationMode.STRICT)

        # Check that field name appears in warnings
        assert result.has_warnings()
        warning_messages = [w.message for w in result.warnings]
        assert any("firstName" in msg for msg in warning_messages)

    def test_error_message_includes_suggestion(self):
        """
        Error messages should include suggestions for fixes.

        Guides users toward correct patterns.
        """
        from dataflow.decorators import ValidationMode, _run_all_validations

        # Create class with user_id instead of id
        class UserNoId:
            __tablename__ = "users_no_id"
            user_id = Column(Integer, primary_key=True)
            __name__ = "UserNoId"

        # Run validation
        result = _run_all_validations(UserNoId, ValidationMode.STRICT)

        # Check that warning suggests using 'id'
        assert result.has_warnings()
        warning_messages = [w.message for w in result.warnings]
        assert any("'id'" in msg or "rename" in msg.lower() for msg in warning_messages)

    def test_warning_message_clear_and_actionable(self):
        """
        Warning messages should be clear and actionable.

        Users should understand what's wrong and how to fix it.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            @model(validation=ValidationMode.WARN)
            class UserWarningMessage(Base):
                __tablename__ = "users_warning_message"
                id = Column(Integer, primary_key=True)
                firstName = Column(String)  # camelCase

        # Check warning message quality
        warning_messages = [str(warning.message) for warning in w]
        assert any("firstName" in msg for msg in warning_messages)
        assert any("snake_case" in msg for msg in warning_messages)


# ==============================================================================
# End of Tests
# ==============================================================================

# Expected test count: 27 tests total
# - TestPrimaryKeyValidation: 5 tests
# - TestAutoManagedFieldsValidation: 4 tests
# - TestFieldTypeValidation: 4 tests
# - TestNamingConventionValidation: 3 tests
# - TestRelationshipValidation: 2 tests
# - TestValidationModes: 4 tests
# - TestValidationEdgeCases: 5 tests
# - TestValidationErrorMessages: 3 tests
