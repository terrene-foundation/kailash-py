# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for TrustPlane configuration loading."""

from __future__ import annotations

import warnings

import pytest

from kailash.trust.plane.config import CONFIG_FILENAME, TrustPlaneConfig


class TestDefaults:
    """Verify defaults when no config file exists."""

    def test_all_defaults(self, tmp_path):
        config = TrustPlaneConfig.load(tmp_path)
        assert config.store_backend == "sqlite"
        assert config.sqlite_path == ".trust-plane/trust.db"
        assert config.enforcement_mode == "strict"
        assert config.shadow_report_schedule == "weekly"
        assert config.shadow_report_output == "stdout"
        assert config.shadow_report_file == ".trust-plane/shadow-report.md"
        assert config.log_level == "WARNING"

    def test_default_instance(self):
        config = TrustPlaneConfig()
        assert config.store_backend == "sqlite"
        assert config.enforcement_mode == "strict"


class TestLoadFromFile:
    """Test loading from .trustplane.toml."""

    def test_all_fields(self, tmp_path):
        toml = """\
[store]
backend = "filesystem"
sqlite_path = "custom/path.db"

[enforcement]
mode = "shadow"

[shadow]
report_schedule = "daily"
report_output = "file"
report_file = "custom-report.md"

[logging]
level = "DEBUG"
"""
        (tmp_path / CONFIG_FILENAME).write_text(toml)
        config = TrustPlaneConfig.load(tmp_path)
        assert config.store_backend == "filesystem"
        assert config.sqlite_path == "custom/path.db"
        assert config.enforcement_mode == "shadow"
        assert config.shadow_report_schedule == "daily"
        assert config.shadow_report_output == "file"
        assert config.shadow_report_file == "custom-report.md"
        assert config.log_level == "DEBUG"

    def test_partial_config(self, tmp_path):
        """Missing keys use defaults."""
        toml = """\
[store]
backend = "filesystem"
"""
        (tmp_path / CONFIG_FILENAME).write_text(toml)
        config = TrustPlaneConfig.load(tmp_path)
        assert config.store_backend == "filesystem"
        assert config.enforcement_mode == "strict"  # default
        assert config.log_level == "WARNING"  # default

    def test_empty_file(self, tmp_path):
        """Empty TOML file uses all defaults."""
        (tmp_path / CONFIG_FILENAME).write_text("")
        config = TrustPlaneConfig.load(tmp_path)
        assert config.store_backend == "sqlite"
        assert config.enforcement_mode == "strict"


class TestValidation:
    """Test input validation."""

    def test_invalid_backend(self):
        with pytest.raises(ValueError, match="Invalid store_backend"):
            TrustPlaneConfig(store_backend="postgres")

    def test_invalid_mode(self):
        with pytest.raises(ValueError, match="Invalid enforcement_mode"):
            TrustPlaneConfig(enforcement_mode="permissive")

    def test_invalid_schedule(self):
        with pytest.raises(ValueError, match="Invalid shadow_report_schedule"):
            TrustPlaneConfig(shadow_report_schedule="monthly")

    def test_invalid_output(self):
        with pytest.raises(ValueError, match="Invalid shadow_report_output"):
            TrustPlaneConfig(shadow_report_output="email")

    def test_invalid_log_level(self):
        with pytest.raises(ValueError, match="Invalid log_level"):
            TrustPlaneConfig(log_level="TRACE")

    def test_invalid_backend_in_file(self, tmp_path):
        toml = """\
[store]
backend = "mongodb"
"""
        (tmp_path / CONFIG_FILENAME).write_text(toml)
        with pytest.raises(ValueError, match="Invalid store_backend"):
            TrustPlaneConfig.load(tmp_path)


class TestUnknownKeys:
    """Unknown keys produce warnings, not errors."""

    def test_unknown_section(self, tmp_path):
        toml = """\
[store]
backend = "sqlite"

[unknown_section]
foo = "bar"
"""
        (tmp_path / CONFIG_FILENAME).write_text(toml)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = TrustPlaneConfig.load(tmp_path)
            assert len(w) == 1
            assert "Unknown section [unknown_section]" in str(w[0].message)
        assert config.store_backend == "sqlite"

    def test_unknown_key_in_section(self, tmp_path):
        toml = """\
[store]
backend = "sqlite"
unknown_key = "value"
"""
        (tmp_path / CONFIG_FILENAME).write_text(toml)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = TrustPlaneConfig.load(tmp_path)
            assert any("Unknown key 'unknown_key'" in str(x.message) for x in w)
        assert config.store_backend == "sqlite"


class TestEnvironmentOverrides:
    """Environment variables override config file values."""

    def test_env_overrides_file(self, tmp_path, monkeypatch):
        toml = """\
[store]
backend = "filesystem"
"""
        (tmp_path / CONFIG_FILENAME).write_text(toml)
        monkeypatch.setenv("TRUSTPLANE_STORE", "sqlite")
        config = TrustPlaneConfig.load(tmp_path)
        assert config.store_backend == "sqlite"

    def test_env_overrides_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRUSTPLANE_MODE", "shadow")
        config = TrustPlaneConfig.load(tmp_path)
        assert config.enforcement_mode == "shadow"

    def test_env_log_level(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRUSTPLANE_LOG_LEVEL", "DEBUG")
        config = TrustPlaneConfig.load(tmp_path)
        assert config.log_level == "DEBUG"

    def test_env_invalid_value(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRUSTPLANE_STORE", "redis")
        with pytest.raises(ValueError, match="Invalid store_backend"):
            TrustPlaneConfig.load(tmp_path)


class TestTomlRoundTrip:
    """Test serialization and re-loading."""

    def test_roundtrip(self, tmp_path):
        original = TrustPlaneConfig(
            store_backend="filesystem",
            enforcement_mode="shadow",
            log_level="DEBUG",
        )
        original.write(tmp_path)
        loaded = TrustPlaneConfig.load(tmp_path)
        assert loaded.store_backend == original.store_backend
        assert loaded.enforcement_mode == original.enforcement_mode
        assert loaded.log_level == original.log_level
        assert loaded.sqlite_path == original.sqlite_path

    def test_to_toml_is_valid_toml(self, tmp_path):
        """Generated TOML string must parse without errors."""
        config = TrustPlaneConfig()
        toml_str = config.to_toml()
        # Write and re-read to verify TOML validity
        config_path = tmp_path / CONFIG_FILENAME
        config_path.write_text(toml_str)
        loaded = TrustPlaneConfig.load(tmp_path)
        assert loaded.store_backend == "sqlite"

    def test_write_creates_file(self, tmp_path):
        config = TrustPlaneConfig()
        path = config.write(tmp_path)
        assert path.exists()
        assert path.name == CONFIG_FILENAME

    def test_generated_toml_has_comments(self):
        """Generated TOML should include documentation comments."""
        config = TrustPlaneConfig()
        toml_str = config.to_toml()
        assert "# Storage backend" in toml_str
        assert "# Enforcement mode" in toml_str
        assert "# Logging level" in toml_str
