# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for TSG-103: Declarative __validation__ dict (DSL)."""

from __future__ import annotations

import pytest

from dataflow.validation.decorators import validate_model
from dataflow.validation.dsl import (
    NAMED_VALIDATORS,
    apply_validation_dict,
    one_of_validator,
)
from dataflow.validation.field_validators import (
    email_validator,
    length_validator,
    one_of_validator as fv_one_of_validator,
    pattern_validator,
    range_validator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_model(validation_dict, **fields):
    """Create a model class with __validation__ and given field defaults."""

    class Model:
        pass

    Model.__validation__ = validation_dict
    for k, v in fields.items():
        setattr(Model, k, v)
    # Simulate model decoration: apply the validation dict
    apply_validation_dict(Model, validation_dict)
    return Model


def _make_instance(model_cls, **data):
    """Create a proxy instance with data as attributes."""
    inst = model_cls()
    for k, v in data.items():
        setattr(inst, k, v)
    return inst


# ---------------------------------------------------------------------------
# one_of_validator
# ---------------------------------------------------------------------------


class TestOneOfValidator:
    def test_accepts_valid(self):
        fn = one_of_validator(["active", "inactive", "pending"])
        assert fn("active") is True
        assert fn("inactive") is True

    def test_rejects_invalid(self):
        fn = one_of_validator(["active", "inactive"])
        assert fn("deleted") is False

    def test_numeric_values(self):
        fn = one_of_validator([1, 2, 3])
        assert fn(2) is True
        assert fn(99) is False

    def test_field_validators_one_of(self):
        """one_of_validator also exists in field_validators module."""
        fn = fv_one_of_validator(["a", "b"])
        assert fn("a") is True
        assert fn("c") is False


# ---------------------------------------------------------------------------
# Validation dict parsing
# ---------------------------------------------------------------------------


class TestValidationDictParsing:
    def test_min_max_length(self):
        Model = _make_model({"name": {"min_length": 2, "max_length": 50}})
        validators = getattr(Model, "__field_validators__", [])
        assert len(validators) == 1
        field, fn, label = validators[0]
        assert field == "name"
        assert fn("ok") is True
        assert fn("x") is False  # too short

    def test_named_email_validator(self):
        Model = _make_model({"email": {"validators": ["email"]}})
        validators = getattr(Model, "__field_validators__", [])
        assert len(validators) == 1
        _, fn, _ = validators[0]
        assert fn("user@example.com") is True
        assert fn("not-email") is False

    def test_range_validator(self):
        Model = _make_model({"score": {"range": {"min": 0, "max": 100}}})
        validators = getattr(Model, "__field_validators__", [])
        _, fn, _ = validators[0]
        assert fn(50) is True
        assert fn(-1) is False
        assert fn(101) is False

    def test_one_of_from_dict(self):
        Model = _make_model({"status": {"one_of": ["active", "inactive"]}})
        validators = getattr(Model, "__field_validators__", [])
        _, fn, _ = validators[0]
        assert fn("active") is True
        assert fn("deleted") is False

    def test_pattern_validator(self):
        Model = _make_model({"code": {"pattern": r"[A-Z]{3}-\d{4}"}})
        validators = getattr(Model, "__field_validators__", [])
        _, fn, _ = validators[0]
        assert fn("ABC-1234") is True
        assert fn("abc-1234") is False

    def test_custom_callable(self):
        Model = _make_model({"value": {"custom": lambda v: v > 0}})
        validators = getattr(Model, "__field_validators__", [])
        _, fn, _ = validators[0]
        assert fn(5) is True
        assert fn(-1) is False

    def test_unknown_named_validator_raises(self):
        with pytest.raises(ValueError, match="Unknown validator"):
            _make_model({"email": {"validators": ["nonexistent"]}})

    def test_config_key_skipped(self):
        Model = _make_model(
            {"_config": {"validate_on_read": True}, "name": {"min_length": 1}}
        )
        validators = getattr(Model, "__field_validators__", [])
        # Only the name validator, not _config
        assert len(validators) == 1

    def test_invalid_rules_type_raises(self):
        with pytest.raises(ValueError, match="must be a dict"):
            _make_model({"name": "invalid"})


# ---------------------------------------------------------------------------
# Integration with validate_model
# ---------------------------------------------------------------------------


class TestValidateModelIntegration:
    def test_dict_and_decorator_equivalent(self):
        """Both approaches produce the same validation outcome."""
        # Dict approach
        DictModel = _make_model({"name": {"min_length": 1, "max_length": 50}})
        inst_dict = _make_instance(DictModel, name="")
        result_dict = validate_model(inst_dict)

        # Decorator approach
        from dataflow.validation.decorators import field_validator

        @field_validator("name", length_validator(min_len=1, max_len=50))
        class DecoratorModel:
            pass

        inst_dec = DecoratorModel()
        inst_dec.name = ""
        result_dec = validate_model(inst_dec)

        # Both should fail with one error on "name"
        assert not result_dict.valid
        assert not result_dec.valid
        assert len(result_dict.errors) == 1
        assert len(result_dec.errors) == 1
        assert result_dict.errors[0].field == "name"
        assert result_dec.errors[0].field == "name"

    def test_valid_data_passes(self):
        Model = _make_model(
            {
                "name": {"min_length": 1, "max_length": 50},
                "email": {"validators": ["email"]},
                "status": {"one_of": ["active", "inactive"]},
            }
        )
        inst = _make_instance(
            Model, name="Alice", email="alice@example.com", status="active"
        )
        result = validate_model(inst)
        assert result.valid

    def test_invalid_data_fails(self):
        Model = _make_model(
            {
                "name": {"min_length": 1, "max_length": 50},
                "email": {"validators": ["email"]},
            }
        )
        inst = _make_instance(Model, name="", email="not-email")
        result = validate_model(inst)
        assert not result.valid
        assert len(result.errors) == 2

    def test_multiple_rules_per_field(self):
        Model = _make_model(
            {
                "name": {"min_length": 2, "max_length": 50, "pattern": r"[A-Za-z ]+"},
            }
        )
        # Passes both
        inst = _make_instance(Model, name="Alice")
        assert validate_model(inst).valid

        # Fails pattern (numeric)
        inst = _make_instance(Model, name="Alice123")
        assert not validate_model(inst).valid

        # Fails length
        inst = _make_instance(Model, name="A")
        assert not validate_model(inst).valid
