"""
Unit tests for DataFlow validation configuration.

Tests the validation modes available via the standalone @model decorator.
Note: DataFlow class does NOT have strict_mode parameter - validation is
configured per-model using the @model decorator from dataflow.decorators.

Available validation modes:
- ValidationMode.OFF: No validation
- ValidationMode.WARN: Warn about issues but allow registration (default)
- ValidationMode.STRICT: Raise errors on validation failures

Shorthand parameters:
- strict=True is equivalent to validation=ValidationMode.STRICT
- strict=False is equivalent to validation=ValidationMode.WARN
- skip_validation=True is equivalent to validation=ValidationMode.OFF

StrictLevel enum exists in strict_mode_validator.py for workflow validation.
"""

import warnings

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

from dataflow.decorators import ValidationMode, model
from dataflow.exceptions import DataFlowValidationWarning
from dataflow.validators.strict_mode_validator import StrictLevel


@pytest.fixture
def base():
    """Create SQLAlchemy declarative base."""
    return declarative_base()


# ==============================================================================
# Test 1: ValidationMode Enum Exists and Has Expected Values
# ==============================================================================


def test_validation_mode_enum_exists():
    """Test that ValidationMode enum exists with expected values."""
    assert hasattr(ValidationMode, "OFF")
    assert hasattr(ValidationMode, "WARN")
    assert hasattr(ValidationMode, "STRICT")


def test_validation_mode_off_value():
    """Test ValidationMode.OFF value."""
    assert ValidationMode.OFF.value == "off"


def test_validation_mode_warn_value():
    """Test ValidationMode.WARN value."""
    assert ValidationMode.WARN.value == "warn"


def test_validation_mode_strict_value():
    """Test ValidationMode.STRICT value."""
    assert ValidationMode.STRICT.value == "strict"


# ==============================================================================
# Test 2: StrictLevel Enum Exists and Has Expected Values
# ==============================================================================


def test_strict_level_enum_exists():
    """Test that StrictLevel enum exists."""
    assert StrictLevel is not None


def test_strict_level_relaxed():
    """Test StrictLevel.RELAXED exists."""
    assert hasattr(StrictLevel, "RELAXED")
    assert StrictLevel.RELAXED.value == "relaxed"


def test_strict_level_moderate():
    """Test StrictLevel.MODERATE exists."""
    assert hasattr(StrictLevel, "MODERATE")
    assert StrictLevel.MODERATE.value == "moderate"


def test_strict_level_aggressive():
    """Test StrictLevel.AGGRESSIVE exists."""
    assert hasattr(StrictLevel, "AGGRESSIVE")
    assert StrictLevel.AGGRESSIVE.value == "aggressive"


# ==============================================================================
# Test 3: Model Decorator Accepts Validation Parameters
# ==============================================================================


def test_model_decorator_accepts_validation_parameter(base):
    """Test that @model decorator accepts validation parameter."""

    # Should not raise
    @model(validation=ValidationMode.OFF)
    class User(base):
        __tablename__ = "users_val_param_1"
        id = Column(Integer, primary_key=True)
        name = Column(String)

    assert User is not None


def test_model_decorator_accepts_strict_parameter(base):
    """Test that @model decorator accepts strict parameter."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        # strict=True should enable strict validation
        @model(strict=True)
        class User(base):
            __tablename__ = "users_strict_param_1"
            user_id = Column(Integer, primary_key=True)  # Will warn

        assert User is not None
        warning_msgs = [str(warning.message) for warning in w]
        assert any("VAL-003" in msg for msg in warning_msgs)


def test_model_decorator_accepts_skip_validation_parameter(base):
    """Test that @model decorator accepts skip_validation parameter."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(skip_validation=True)
        class User(base):
            __tablename__ = "users_skip_param_1"
            user_id = Column(Integer, primary_key=True)

        assert User is not None
        # Should have no DataFlow validation warnings
        dataflow_warnings = [
            warning
            for warning in w
            if issubclass(warning.category, DataFlowValidationWarning)
        ]
        assert len(dataflow_warnings) == 0


# ==============================================================================
# Test 4: Validation Mode Behavior
# ==============================================================================


def test_validation_mode_off_skips_validation(base):
    """Test that ValidationMode.OFF skips all validation."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(validation=ValidationMode.OFF)
        class User(base):
            __tablename__ = "users_mode_off"
            user_id = Column(Integer, primary_key=True)

        assert User is not None
        # Should have no DataFlow validation warnings
        dataflow_warnings = [
            warning
            for warning in w
            if issubclass(warning.category, DataFlowValidationWarning)
        ]
        assert len(dataflow_warnings) == 0


def test_validation_mode_warn_emits_warnings(base):
    """Test that ValidationMode.WARN emits warnings."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(validation=ValidationMode.WARN)
        class User(base):
            __tablename__ = "users_mode_warn"
            user_id = Column(Integer, primary_key=True)

        assert User is not None
        warning_msgs = [str(warning.message) for warning in w]
        assert any("VAL-003" in msg for msg in warning_msgs)


def test_validation_mode_strict_emits_warnings_for_non_errors(base):
    """Test that ValidationMode.STRICT still emits warnings for non-error issues."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(validation=ValidationMode.STRICT)
        class User(base):
            __tablename__ = "users_mode_strict"
            user_id = Column(Integer, primary_key=True)

        assert User is not None
        warning_msgs = [str(warning.message) for warning in w]
        assert any("VAL-003" in msg for msg in warning_msgs)


# ==============================================================================
# Test 5: Default is WARN (Backward Compatible)
# ==============================================================================


def test_default_validation_mode_is_warn(base):
    """Test that default validation mode is WARN."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model
        class User(base):
            __tablename__ = "users_default_warn"
            user_id = Column(Integer, primary_key=True)

        assert User is not None
        # Default WARN mode should emit warnings
        warning_msgs = [str(warning.message) for warning in w]
        assert any("VAL-003" in msg for msg in warning_msgs)


def test_default_allows_models_with_issues(base):
    """Test that default mode allows models with issues (backward compatible)."""

    # Should not raise
    @model
    class User(base):
        __tablename__ = "users_default_allows"
        user_id = Column(Integer, primary_key=True)
        created_at = Column(String)

    assert User is not None


# ==============================================================================
# Test 6: strict=True/False Shorthand Works
# ==============================================================================


def test_strict_true_is_equivalent_to_strict_mode(base):
    """Test that strict=True is equivalent to validation=ValidationMode.STRICT."""
    with warnings.catch_warnings(record=True) as w1:
        warnings.simplefilter("always")

        @model(strict=True)
        class User1(base):
            __tablename__ = "users_strict_true_1"
            user_id = Column(Integer, primary_key=True)

    with warnings.catch_warnings(record=True) as w2:
        warnings.simplefilter("always")

        @model(validation=ValidationMode.STRICT)
        class User2(base):
            __tablename__ = "users_strict_true_2"
            user_id = Column(Integer, primary_key=True)

    # Both should produce the same warning
    w1_msgs = [str(warning.message) for warning in w1]
    w2_msgs = [str(warning.message) for warning in w2]
    assert any("VAL-003" in msg for msg in w1_msgs)
    assert any("VAL-003" in msg for msg in w2_msgs)


def test_strict_false_is_equivalent_to_warn_mode(base):
    """Test that strict=False is equivalent to validation=ValidationMode.WARN."""
    with warnings.catch_warnings(record=True) as w1:
        warnings.simplefilter("always")

        @model(strict=False)
        class User1(base):
            __tablename__ = "users_strict_false_1"
            user_id = Column(Integer, primary_key=True)

    with warnings.catch_warnings(record=True) as w2:
        warnings.simplefilter("always")

        @model(validation=ValidationMode.WARN)
        class User2(base):
            __tablename__ = "users_strict_false_2"
            user_id = Column(Integer, primary_key=True)

    # Both should produce the same warning
    w1_msgs = [str(warning.message) for warning in w1]
    w2_msgs = [str(warning.message) for warning in w2]
    assert any("VAL-003" in msg for msg in w1_msgs)
    assert any("VAL-003" in msg for msg in w2_msgs)


# ==============================================================================
# Test 7: Multiple Models with Different Validation Settings
# ==============================================================================


def test_multiple_models_different_validation(base):
    """Test that multiple models can have different validation settings."""

    # Model 1: Skip validation
    @model(skip_validation=True)
    class LegacyModel(base):
        __tablename__ = "legacy_model_multi"
        custom_id = Column(Integer, primary_key=True)

    # Model 2: Strict validation (with warnings only)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(strict=True)
        class StrictModel(base):
            __tablename__ = "strict_model_multi"
            user_id = Column(Integer, primary_key=True)

        warning_msgs = [str(warning.message) for warning in w]
        assert any("VAL-003" in msg for msg in warning_msgs)

    assert LegacyModel is not None
    assert StrictModel is not None


# ==============================================================================
# Test 8: Valid Models Pass All Validation Modes
# ==============================================================================


def test_valid_model_passes_strict_mode(base):
    """Test that valid models pass strict mode without warnings."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(strict=True)
        class User(base):
            __tablename__ = "users_valid_model"
            id = Column(Integer, primary_key=True)
            name = Column(String(100))
            email = Column(String(255))

        assert User is not None
        # Valid model should have no validation warnings
        dataflow_warnings = [
            warning
            for warning in w
            if issubclass(warning.category, DataFlowValidationWarning)
        ]
        assert len(dataflow_warnings) == 0


def test_valid_model_passes_warn_mode(base):
    """Test that valid models pass warn mode without warnings."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(validation=ValidationMode.WARN)
        class User(base):
            __tablename__ = "users_valid_warn"
            id = Column(Integer, primary_key=True)
            name = Column(String(100))

        assert User is not None
        # Valid model should have no validation warnings
        dataflow_warnings = [
            warning
            for warning in w
            if issubclass(warning.category, DataFlowValidationWarning)
        ]
        assert len(dataflow_warnings) == 0


# ==============================================================================
# Test 9: Validation Decorators Work Without DataFlow Instance
# ==============================================================================


def test_model_decorator_works_standalone(base):
    """Test that @model decorator works without DataFlow instance."""
    # The standalone @model decorator should work independently
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(strict=True)
        class User(base):
            __tablename__ = "users_standalone"
            id = Column(Integer, primary_key=True)
            name = Column(String)

        assert User is not None


def test_model_decorator_validation_is_per_model(base):
    """Test that validation is applied per-model, not globally."""

    # First model: skip validation
    @model(skip_validation=True)
    class Model1(base):
        __tablename__ = "model1_per_model"
        custom_id = Column(Integer, primary_key=True)

    # Second model: strict validation (should warn)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @model(strict=True)
        class Model2(base):
            __tablename__ = "model2_per_model"
            user_id = Column(Integer, primary_key=True)

        # Only Model2 should trigger warning
        warning_msgs = [str(warning.message) for warning in w]
        assert any("VAL-003" in msg and "Model2" in msg for msg in warning_msgs)

    assert Model1 is not None
    assert Model2 is not None
