# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for middleware presets (S4-005).

Covers:
- Preset registry completeness
- Each preset's middleware composition
- Security headers and CSRF integration in presets
- get_preset() validation
- Middleware factory return types
"""

from __future__ import annotations

import pytest

from nexus.presets import (
    PRESETS,
    NexusConfig,
    PresetConfig,
    _cors_middleware_factory,
    _csrf_middleware_factory,
    _security_headers_middleware_factory,
    apply_preset,
    get_preset,
)


class TestPresetRegistry:
    """Test the preset registry structure."""

    def test_all_presets_present(self):
        expected = {"none", "lightweight", "standard", "saas", "enterprise"}
        assert set(PRESETS.keys()) == expected

    def test_presets_are_preset_configs(self):
        for name, preset in PRESETS.items():
            assert isinstance(preset, PresetConfig), f"Preset '{name}' is not PresetConfig"

    def test_preset_names_match_keys(self):
        for key, preset in PRESETS.items():
            assert preset.name == key

    def test_presets_have_descriptions(self):
        for name, preset in PRESETS.items():
            assert preset.description, f"Preset '{name}' has no description"


class TestGetPreset:
    """Test get_preset() function."""

    def test_get_valid_preset(self):
        preset = get_preset("standard")
        assert preset.name == "standard"

    def test_get_invalid_preset_raises(self):
        with pytest.raises(ValueError, match="Unknown preset"):
            get_preset("nonexistent")

    def test_get_all_presets(self):
        for name in PRESETS:
            preset = get_preset(name)
            assert preset.name == name


class TestNonePreset:
    """Test the 'none' preset has no middleware."""

    def test_no_middleware(self):
        preset = get_preset("none")
        assert len(preset.middleware_factories) == 0

    def test_no_plugins(self):
        preset = get_preset("none")
        assert len(preset.plugin_factories) == 0


class TestLightweightPreset:
    """Test the 'lightweight' preset has CORS + security headers."""

    def test_has_cors(self):
        preset = get_preset("lightweight")
        factory_names = [f.__name__ for f in preset.middleware_factories]
        assert "_cors_middleware_factory" in factory_names

    def test_has_security_headers(self):
        preset = get_preset("lightweight")
        factory_names = [f.__name__ for f in preset.middleware_factories]
        assert "_security_headers_middleware_factory" in factory_names

    def test_no_csrf(self):
        preset = get_preset("lightweight")
        factory_names = [f.__name__ for f in preset.middleware_factories]
        assert "_csrf_middleware_factory" not in factory_names

    def test_no_plugins(self):
        preset = get_preset("lightweight")
        assert len(preset.plugin_factories) == 0


class TestStandardPreset:
    """Test the 'standard' preset adds CSRF."""

    def test_has_cors(self):
        preset = get_preset("standard")
        factory_names = [f.__name__ for f in preset.middleware_factories]
        assert "_cors_middleware_factory" in factory_names

    def test_has_security_headers(self):
        preset = get_preset("standard")
        factory_names = [f.__name__ for f in preset.middleware_factories]
        assert "_security_headers_middleware_factory" in factory_names

    def test_has_csrf(self):
        preset = get_preset("standard")
        factory_names = [f.__name__ for f in preset.middleware_factories]
        assert "_csrf_middleware_factory" in factory_names

    def test_has_rate_limit(self):
        preset = get_preset("standard")
        factory_names = [f.__name__ for f in preset.middleware_factories]
        assert "_rate_limit_middleware_factory" in factory_names


class TestSaaSPreset:
    """Test the 'saas' preset includes security middleware + auth plugins."""

    def test_has_security_headers(self):
        preset = get_preset("saas")
        factory_names = [f.__name__ for f in preset.middleware_factories]
        assert "_security_headers_middleware_factory" in factory_names

    def test_has_csrf(self):
        preset = get_preset("saas")
        factory_names = [f.__name__ for f in preset.middleware_factories]
        assert "_csrf_middleware_factory" in factory_names

    def test_has_auth_plugins(self):
        preset = get_preset("saas")
        plugin_names = [f.__name__ for f in preset.plugin_factories]
        assert "_jwt_auth_plugin_factory" in plugin_names
        assert "_rbac_plugin_factory" in plugin_names
        assert "_tenant_isolation_plugin_factory" in plugin_names
        assert "_audit_plugin_factory" in plugin_names


class TestEnterprisePreset:
    """Test the 'enterprise' preset includes everything."""

    def test_has_security_headers(self):
        preset = get_preset("enterprise")
        factory_names = [f.__name__ for f in preset.middleware_factories]
        assert "_security_headers_middleware_factory" in factory_names

    def test_has_csrf(self):
        preset = get_preset("enterprise")
        factory_names = [f.__name__ for f in preset.middleware_factories]
        assert "_csrf_middleware_factory" in factory_names

    def test_has_sso_plugin(self):
        preset = get_preset("enterprise")
        plugin_names = [f.__name__ for f in preset.plugin_factories]
        assert "_sso_plugin_factory" in plugin_names

    def test_has_feature_flags_plugin(self):
        preset = get_preset("enterprise")
        plugin_names = [f.__name__ for f in preset.plugin_factories]
        assert "_feature_flags_plugin_factory" in plugin_names

    def test_superset_of_saas(self):
        saas = get_preset("saas")
        enterprise = get_preset("enterprise")

        saas_mw = {f.__name__ for f in saas.middleware_factories}
        enterprise_mw = {f.__name__ for f in enterprise.middleware_factories}
        assert saas_mw.issubset(enterprise_mw)

        saas_plugins = {f.__name__ for f in saas.plugin_factories}
        enterprise_plugins = {f.__name__ for f in enterprise.plugin_factories}
        assert saas_plugins.issubset(enterprise_plugins)


class TestMiddlewareFactories:
    """Test individual middleware factories produce correct output."""

    def test_cors_factory_returns_tuple(self):
        config = NexusConfig()
        result = _cors_middleware_factory(config)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_security_headers_factory_returns_tuple(self):
        config = NexusConfig()
        result = _security_headers_middleware_factory(config)
        assert isinstance(result, tuple)
        assert len(result) == 2
        middleware_class, kwargs = result
        assert "config" in kwargs

    def test_csrf_factory_returns_tuple(self):
        config = NexusConfig(cors_origins=["https://app.example.com"])
        result = _csrf_middleware_factory(config)
        assert isinstance(result, tuple)
        assert len(result) == 2
        middleware_class, kwargs = result
        assert "allowed_origins" in kwargs
        assert "https://app.example.com" in kwargs["allowed_origins"]

    def test_csrf_factory_wildcard_allows_missing(self):
        config = NexusConfig(cors_origins=["*"])
        _, kwargs = _csrf_middleware_factory(config)
        assert kwargs["allow_missing_origin"] is True
        # Wildcard should NOT be in allowed_origins list
        assert "*" not in kwargs["allowed_origins"]

    def test_csrf_factory_specific_origins_strict(self):
        config = NexusConfig(cors_origins=["https://specific.com"])
        _, kwargs = _csrf_middleware_factory(config)
        assert kwargs["allow_missing_origin"] is False


class TestNexusConfigRepr:
    """Test NexusConfig secret redaction."""

    def test_repr_redacts_jwt_secret(self):
        config = NexusConfig(jwt_secret="super-secret-key-that-is-very-long")
        r = repr(config)
        assert "super-secret" not in r
        assert "[REDACTED]" in r

    def test_repr_no_jwt_secret(self):
        config = NexusConfig()
        r = repr(config)
        assert "jwt_secret=None" in r
