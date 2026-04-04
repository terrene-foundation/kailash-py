"""Tests for BaseAgentConfig response_format migration and structured_output_mode.

Covers the deprecation shim that migrates provider_config with 'type' key
to response_format, and the structured_output_mode validation.
"""

import warnings

import pytest

from kaizen.core.config import BaseAgentConfig


class TestProviderConfigMigration:
    """Test the _migrate_provider_config() deprecation shim."""

    def test_pure_structured_output_migrated(self):
        """provider_config with only structured output keys migrates fully."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = BaseAgentConfig(
                provider_config={"type": "json_object"},
            )

        assert config.response_format == {"type": "json_object"}
        assert config.provider_config is None
        assert any("deprecated" in str(warning.message).lower() for warning in w)

    def test_mixed_dict_splits_correctly(self):
        """provider_config with both structured output and provider keys splits."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = BaseAgentConfig(
                provider_config={
                    "type": "json_object",
                    "api_version": "2024-10-21",
                },
            )

        assert config.response_format == {"type": "json_object"}
        assert config.provider_config == {"api_version": "2024-10-21"}
        assert any("deprecated" in str(warning.message).lower() for warning in w)

    def test_json_schema_with_extras_splits(self):
        """json_schema config with deployment key splits correctly."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            config = BaseAgentConfig(
                provider_config={
                    "type": "json_schema",
                    "json_schema": {"name": "Test", "strict": True},
                    "deployment": "my-gpt4",
                },
            )

        assert config.response_format == {
            "type": "json_schema",
            "json_schema": {"name": "Test", "strict": True},
        }
        assert config.provider_config == {"deployment": "my-gpt4"}

    def test_provider_config_without_type_not_migrated(self):
        """provider_config without 'type' key stays as provider_config."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = BaseAgentConfig(
                provider_config={"api_version": "2024-10-21"},
            )

        assert config.provider_config == {"api_version": "2024-10-21"}
        assert config.response_format is None
        deprecation_warnings = [
            x for x in w if issubclass(x.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) == 0

    def test_explicit_response_format_no_migration(self):
        """When response_format is set, no migration happens."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = BaseAgentConfig(
                response_format={"type": "json_object"},
            )

        assert config.response_format == {"type": "json_object"}
        assert config.provider_config is None
        deprecation_warnings = [
            x for x in w if issubclass(x.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) == 0

    def test_both_set_response_format_wins(self):
        """When both are set with type keys, response_format wins."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = BaseAgentConfig(
                response_format={"type": "json_schema"},
                provider_config={"type": "json_object", "api_version": "2024-10-21"},
            )

        assert config.response_format == {"type": "json_schema"}
        assert config.provider_config == {"api_version": "2024-10-21"}
        assert any(
            "both response_format" in str(warning.message).lower() for warning in w
        )


class TestStructuredOutputMode:
    """Test structured_output_mode field validation."""

    def test_default_is_explicit(self):
        config = BaseAgentConfig()
        assert config.structured_output_mode == "explicit"

    def test_auto_mode_still_accepted(self):
        config = BaseAgentConfig(structured_output_mode="auto")
        assert config.structured_output_mode == "auto"

    def test_explicit_mode_accepted(self):
        config = BaseAgentConfig(structured_output_mode="explicit")
        assert config.structured_output_mode == "explicit"

    def test_off_mode_accepted(self):
        config = BaseAgentConfig(structured_output_mode="off")
        assert config.structured_output_mode == "off"

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="structured_output_mode"):
            BaseAgentConfig(structured_output_mode="invalid")


class TestNumericValidation:
    """Test NaN/Inf guards on numeric fields."""

    def test_nan_temperature_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            BaseAgentConfig(temperature=float("nan"))

    def test_inf_temperature_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            BaseAgentConfig(temperature=float("inf"))

    def test_nan_budget_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            BaseAgentConfig(budget_limit_usd=float("nan"))

    def test_negative_budget_rejected(self):
        with pytest.raises(ValueError, match=">= 0"):
            BaseAgentConfig(budget_limit_usd=-1.0)
