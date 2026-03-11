"""Unit tests for Nexus preset system (TODO-300D).

Tests for NexusConfig, PresetConfig, preset registry, factory functions,
and Nexus integration via the preset constructor parameter.
Tier 1 tests - mocking allowed for isolated unit testing.
"""

import logging

import pytest
from nexus import Nexus
from nexus.presets import (
    PRESETS,
    NexusConfig,
    PresetConfig,
    _audit_plugin_factory,
    _cors_middleware_factory,
    _error_handler_middleware_factory,
    _feature_flags_plugin_factory,
    _jwt_auth_plugin_factory,
    _rate_limit_middleware_factory,
    _rbac_plugin_factory,
    _sso_plugin_factory,
    _tenant_isolation_plugin_factory,
    apply_preset,
    get_preset,
)

# =============================================================================
# Tests: NexusConfig Dataclass
# =============================================================================


class TestNexusConfig:
    """Tests for NexusConfig dataclass."""

    def test_default_values(self):
        """NexusConfig has sensible defaults."""
        config = NexusConfig()

        assert config.cors_origins == ["*"]
        assert config.cors_allow_methods == ["*"]
        assert config.cors_allow_credentials is False
        assert config.jwt_secret is None
        assert config.jwt_algorithm == "HS256"
        assert config.rate_limit == 100
        assert config.audit_enabled is True
        assert config.environment == "development"

    def test_custom_values(self):
        """NexusConfig accepts custom values."""
        config = NexusConfig(
            cors_origins=["http://example.com"],
            jwt_secret="my-secret",
            rate_limit=50,
            environment="production",
        )

        assert config.cors_origins == ["http://example.com"]
        assert config.jwt_secret == "my-secret"
        assert config.rate_limit == 50
        assert config.environment == "production"

    def test_repr_redacts_jwt_secret(self):
        """__repr__ redacts jwt_secret."""
        config = NexusConfig(jwt_secret="super-secret-key")

        repr_str = repr(config)
        assert "[REDACTED]" in repr_str
        assert "super-secret-key" not in repr_str

    def test_repr_shows_none_when_no_jwt(self):
        """__repr__ shows None when no jwt_secret."""
        config = NexusConfig()

        repr_str = repr(config)
        assert "jwt_secret=None" in repr_str

    def test_repr_redacts_sso_secrets(self):
        """__repr__ redacts sensitive fields in sso_config."""
        config = NexusConfig(
            sso_provider="okta",
            sso_config={
                "client_id": "my-client",
                "client_secret": "very-secret",
                "api_key": "also-secret",
                "domain": "example.okta.com",
            },
        )

        repr_str = repr(config)
        assert "very-secret" not in repr_str
        assert "also-secret" not in repr_str
        assert "example.okta.com" in repr_str

    def test_repr_no_sso_config(self):
        """__repr__ shows None when no sso_config."""
        config = NexusConfig()

        repr_str = repr(config)
        assert "sso_config=None" in repr_str

    def test_tenant_defaults(self):
        """Tenant configuration has defaults."""
        config = NexusConfig()

        assert config.tenant_header == "X-Tenant-ID"
        assert config.tenant_required is True


# =============================================================================
# Tests: PresetConfig Dataclass
# =============================================================================


class TestPresetConfig:
    """Tests for PresetConfig dataclass."""

    def test_basic_creation(self):
        """PresetConfig can be created with name and description."""
        preset = PresetConfig(name="test", description="Test preset")

        assert preset.name == "test"
        assert preset.description == "Test preset"
        assert preset.middleware_factories == []
        assert preset.plugin_factories == []

    def test_with_factories(self):
        """PresetConfig accepts factory lists."""

        def dummy_factory(config):
            return None

        preset = PresetConfig(
            name="test",
            description="Test",
            middleware_factories=[dummy_factory],
            plugin_factories=[dummy_factory],
        )

        assert len(preset.middleware_factories) == 1
        assert len(preset.plugin_factories) == 1


# =============================================================================
# Tests: Preset Registry
# =============================================================================


class TestPresetRegistry:
    """Tests for preset registry and lookup."""

    def test_all_five_presets_registered(self):
        """All five presets exist in registry."""
        expected = {"none", "lightweight", "standard", "saas", "enterprise"}
        assert set(PRESETS.keys()) == expected

    def test_get_preset_valid(self):
        """get_preset returns correct preset."""
        preset = get_preset("lightweight")

        assert preset.name == "lightweight"
        assert "CORS" in preset.description

    def test_get_preset_invalid(self):
        """get_preset raises ValueError for unknown preset."""
        with pytest.raises(ValueError, match="Unknown preset 'bogus'"):
            get_preset("bogus")

    def test_get_preset_error_lists_available(self):
        """Error message lists all available presets."""
        with pytest.raises(ValueError) as exc_info:
            get_preset("bogus")

        error_msg = str(exc_info.value)
        for name in PRESETS:
            assert name in error_msg

    def test_none_preset_has_no_factories(self):
        """'none' preset has empty factory lists."""
        preset = get_preset("none")

        assert preset.middleware_factories == []
        assert preset.plugin_factories == []

    def test_lightweight_has_cors_only(self):
        """'lightweight' preset has CORS middleware only."""
        preset = get_preset("lightweight")

        assert len(preset.middleware_factories) == 1
        assert preset.middleware_factories[0] is _cors_middleware_factory
        assert preset.plugin_factories == []

    def test_standard_has_three_middleware(self):
        """'standard' preset has CORS + rate limit + error handler."""
        preset = get_preset("standard")

        assert len(preset.middleware_factories) == 3
        assert preset.plugin_factories == []

    def test_saas_has_middleware_and_plugins(self):
        """'saas' preset has middleware and plugin factories."""
        preset = get_preset("saas")

        assert len(preset.middleware_factories) == 3
        assert len(preset.plugin_factories) == 4

    def test_enterprise_has_most_plugins(self):
        """'enterprise' preset has the most plugin factories."""
        preset = get_preset("enterprise")

        assert len(preset.middleware_factories) == 3
        assert len(preset.plugin_factories) == 6


# =============================================================================
# Tests: Factory Functions
# =============================================================================


class TestFactoryFunctions:
    """Tests for middleware and plugin factory functions."""

    def test_cors_factory_returns_tuple(self):
        """CORS factory returns (class, kwargs) tuple."""
        config = NexusConfig(cors_origins=["http://example.com"])

        result = _cors_middleware_factory(config)

        assert result is not None
        middleware_class, kwargs = result
        assert kwargs["allow_origins"] == ["http://example.com"]

    def test_rate_limit_factory_returns_none_when_disabled(self):
        """Rate limit factory returns None when rate_limit is None."""
        config = NexusConfig(rate_limit=None)

        result = _rate_limit_middleware_factory(config)
        assert result is None

    def test_rate_limit_factory_warns_not_implemented(self, caplog):
        """Rate limit factory logs warning (placeholder)."""
        config = NexusConfig(rate_limit=100)

        with caplog.at_level(logging.WARNING):
            result = _rate_limit_middleware_factory(config)

        assert result is None
        assert "not yet implemented" in caplog.text

    def test_error_handler_factory_returns_none(self):
        """Error handler factory returns None (placeholder)."""
        config = NexusConfig()

        result = _error_handler_middleware_factory(config)
        assert result is None

    def test_jwt_factory_returns_none_without_secret(self):
        """JWT factory returns None when no jwt_secret."""
        config = NexusConfig()

        result = _jwt_auth_plugin_factory(config)
        assert result is None

    def test_jwt_factory_warns_with_secret(self, caplog):
        """JWT factory logs warning when secret configured (placeholder)."""
        config = NexusConfig(jwt_secret="my-secret")

        with caplog.at_level(logging.WARNING):
            result = _jwt_auth_plugin_factory(config)

        assert result is None
        assert "not yet implemented" in caplog.text

    def test_rbac_factory_returns_none_without_config(self):
        """RBAC factory returns None when no rbac_config."""
        config = NexusConfig()

        result = _rbac_plugin_factory(config)
        assert result is None

    def test_audit_factory_returns_none_when_disabled(self):
        """Audit factory returns None when audit_enabled=False."""
        config = NexusConfig(audit_enabled=False)

        result = _audit_plugin_factory(config)
        assert result is None

    def test_sso_factory_returns_none_without_provider(self):
        """SSO factory returns None when no sso_provider."""
        config = NexusConfig()

        result = _sso_plugin_factory(config)
        assert result is None

    def test_feature_flags_factory_returns_none_without_provider(self):
        """Feature flags factory returns None when no provider."""
        config = NexusConfig()

        result = _feature_flags_plugin_factory(config)
        assert result is None


# =============================================================================
# Tests: apply_preset()
# =============================================================================


class TestApplyPreset:
    """Tests for apply_preset() function."""

    def test_apply_none_preset(self):
        """Applying 'none' preset adds no middleware or plugins."""
        app = Nexus(enable_durability=False)
        initial_middleware = len(app._middleware_stack)
        config = NexusConfig()

        apply_preset(app, "none", config)

        assert len(app._middleware_stack) == initial_middleware

    def test_apply_lightweight_adds_cors(self):
        """Applying 'lightweight' adds CORS middleware."""
        app = Nexus(enable_durability=False)
        initial_middleware = len(app._middleware_stack)
        config = NexusConfig(cors_origins=["http://test.com"])

        apply_preset(app, "lightweight", config)

        assert len(app._middleware_stack) == initial_middleware + 1
        assert app._middleware_stack[-1].name == "CORSMiddleware"

    def test_apply_preset_logs_info(self, caplog):
        """apply_preset() logs info messages."""
        app = Nexus(enable_durability=False)
        config = NexusConfig()

        with caplog.at_level(logging.INFO):
            caplog.clear()
            apply_preset(app, "lightweight", config)

        assert "Applying preset 'lightweight'" in caplog.text
        assert "applied successfully" in caplog.text

    def test_apply_invalid_preset_raises(self):
        """apply_preset() raises for unknown preset name."""
        app = Nexus(enable_durability=False)
        config = NexusConfig()

        with pytest.raises(ValueError, match="Unknown preset"):
            apply_preset(app, "bogus", config)


# =============================================================================
# Tests: Nexus Constructor Integration
# =============================================================================


class TestNexusPresetIntegration:
    """Tests for preset parameter in Nexus constructor."""

    def test_preset_none(self):
        """Nexus(preset='none') works without error."""
        app = Nexus(preset="none", enable_durability=False)

        assert app.active_preset == "none"

    def test_preset_lightweight(self):
        """Nexus(preset='lightweight') adds CORS middleware."""
        app = Nexus(preset="lightweight", enable_durability=False)

        assert app.active_preset == "lightweight"
        assert any(m.name == "CORSMiddleware" for m in app._middleware_stack)

    def test_no_preset_by_default(self):
        """Without preset parameter, active_preset is None."""
        app = Nexus(enable_durability=False)

        assert app.active_preset is None

    def test_invalid_preset_raises(self):
        """Invalid preset name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown preset"):
            Nexus(preset="nonexistent", enable_durability=False)

    def test_preset_config_stored(self):
        """NexusConfig is stored and accessible."""
        app = Nexus(preset="lightweight", enable_durability=False)

        assert app.preset_config is not None
        assert isinstance(app.preset_config, NexusConfig)

    def test_preset_config_none_without_preset(self):
        """preset_config is None without preset."""
        app = Nexus(enable_durability=False)

        assert app.preset_config is None


# =============================================================================
# Tests: Introspection
# =============================================================================


class TestPresetIntrospection:
    """Tests for preset introspection methods."""

    def test_describe_preset_no_preset(self):
        """describe_preset() returns empty when no preset."""
        app = Nexus(enable_durability=False)

        result = app.describe_preset()

        assert result["preset"] is None
        assert result["middleware"] == []
        assert result["plugins"] == []

    def test_describe_preset_lightweight(self):
        """describe_preset() returns details for lightweight preset."""
        app = Nexus(preset="lightweight", enable_durability=False)

        result = app.describe_preset()

        assert result["preset"] == "lightweight"
        assert "CORS" in result["description"]
        assert len(result["middleware"]) > 0

    def test_describe_preset_includes_config(self):
        """describe_preset() includes config details."""
        app = Nexus(
            preset="lightweight",
            cors_origins=["http://example.com"],
            enable_durability=False,
        )

        result = app.describe_preset()

        assert "config" in result
        assert result["config"]["cors_origins"] == ["http://example.com"]
