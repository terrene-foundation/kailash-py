"""Unit tests for Nexus native CORS configuration (TODO-300E).

Tests for CORS constructor parameters, environment-aware defaults,
configure_cors() method, and introspection properties.
Tier 1 tests - mocking allowed for isolated unit testing.
"""

import logging
import os

import pytest
from nexus import Nexus

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean_nexus_env(monkeypatch):
    """Ensure NEXUS_ENV is reset between tests."""
    monkeypatch.delenv("NEXUS_ENV", raising=False)


# =============================================================================
# Tests: Environment-Aware Defaults
# =============================================================================


class TestCorsDefaults:
    """Tests for _get_cors_defaults() environment-aware behavior."""

    def test_development_defaults_allow_all_origins(self, monkeypatch):
        """Development defaults allow all origins with wildcard."""
        monkeypatch.setenv("NEXUS_ENV", "development")
        app = Nexus(enable_durability=False)

        config = app.cors_config
        assert config["allow_origins"] == ["*"]
        assert config["allow_methods"] == ["*"]
        assert config["allow_headers"] == ["*"]

    def test_development_is_default_env(self):
        """Without NEXUS_ENV set, development defaults apply."""
        # NEXUS_ENV is unset via autouse fixture
        app = Nexus(enable_durability=False)

        config = app.cors_config
        assert config["allow_origins"] == ["*"]

    def test_production_defaults_no_origins(self, monkeypatch):
        """Production defaults have empty origins list."""
        monkeypatch.setenv("NEXUS_ENV", "production")
        app = Nexus(enable_auth=False, enable_durability=False)

        config = app.cors_config
        assert config["allow_origins"] == []

    def test_production_defaults_restrictive_methods(self, monkeypatch):
        """Production defaults use specific HTTP methods."""
        monkeypatch.setenv("NEXUS_ENV", "production")
        app = Nexus(enable_auth=False, enable_durability=False)

        config = app.cors_config
        assert "GET" in config["allow_methods"]
        assert "POST" in config["allow_methods"]
        assert "*" not in config["allow_methods"]

    def test_production_defaults_restrictive_headers(self, monkeypatch):
        """Production defaults use specific headers."""
        monkeypatch.setenv("NEXUS_ENV", "production")
        app = Nexus(enable_auth=False, enable_durability=False)

        config = app.cors_config
        assert "Authorization" in config["allow_headers"]
        assert "Content-Type" in config["allow_headers"]
        assert "*" not in config["allow_headers"]

    def test_production_defaults_expose_request_id(self, monkeypatch):
        """Production defaults expose X-Request-ID header."""
        monkeypatch.setenv("NEXUS_ENV", "production")
        app = Nexus(enable_auth=False, enable_durability=False)

        config = app.cors_config
        assert "X-Request-ID" in config["expose_headers"]

    def test_default_max_age(self):
        """Default max_age is 600 seconds."""
        app = Nexus(enable_durability=False)

        assert app.cors_config["max_age"] == 600

    def test_default_credentials_false(self):
        """Default allow_credentials is False (security: avoid wildcard + credentials)."""
        app = Nexus(enable_durability=False)

        assert app.cors_config["allow_credentials"] is False


# =============================================================================
# Tests: Production Validation
# =============================================================================


class TestCorsProductionValidation:
    """Tests for production-mode security validation."""

    def test_production_rejects_wildcard_origins(self, monkeypatch):
        """ValueError when cors_origins=['*'] in production."""
        monkeypatch.setenv("NEXUS_ENV", "production")

        with pytest.raises(ValueError, match="not allowed in production"):
            Nexus(
                cors_origins=["*"],
                enable_auth=False,
                enable_durability=False,
            )

    def test_production_accepts_explicit_origins(self, monkeypatch):
        """No error when explicit origins in production."""
        monkeypatch.setenv("NEXUS_ENV", "production")

        app = Nexus(
            cors_origins=["https://app.example.com"],
            enable_auth=False,
            enable_durability=False,
        )

        assert app.cors_config["allow_origins"] == ["https://app.example.com"]

    def test_development_allows_wildcard(self, monkeypatch):
        """No error when cors_origins=['*'] in development."""
        monkeypatch.setenv("NEXUS_ENV", "development")

        app = Nexus(
            cors_origins=["*"],
            enable_durability=False,
        )

        assert app.cors_config["allow_origins"] == ["*"]


# =============================================================================
# Tests: Constructor Parameters
# =============================================================================


class TestCorsConstructorParams:
    """Tests for CORS constructor parameters."""

    def test_cors_origins_parameter(self):
        """cors_origins parameter is applied."""
        app = Nexus(
            cors_origins=["http://example.com"],
            enable_durability=False,
        )

        assert app.cors_config["allow_origins"] == ["http://example.com"]

    def test_cors_allow_methods_parameter(self):
        """cors_allow_methods parameter is applied."""
        app = Nexus(
            cors_allow_methods=["GET", "POST"],
            enable_durability=False,
        )

        assert app.cors_config["allow_methods"] == ["GET", "POST"]

    def test_cors_allow_headers_parameter(self):
        """cors_allow_headers parameter is applied."""
        app = Nexus(
            cors_allow_headers=["Authorization", "Content-Type"],
            enable_durability=False,
        )

        assert app.cors_config["allow_headers"] == ["Authorization", "Content-Type"]

    def test_cors_allow_credentials_parameter(self):
        """cors_allow_credentials parameter is applied."""
        app = Nexus(
            cors_allow_credentials=False,
            enable_durability=False,
        )

        assert app.cors_config["allow_credentials"] is False

    def test_cors_expose_headers_parameter(self):
        """cors_expose_headers parameter is applied."""
        app = Nexus(
            cors_expose_headers=["X-Custom-Header"],
            enable_durability=False,
        )

        assert app.cors_config["expose_headers"] == ["X-Custom-Header"]

    def test_cors_max_age_parameter(self):
        """cors_max_age parameter is applied."""
        app = Nexus(
            cors_max_age=3600,
            enable_durability=False,
        )

        assert app.cors_config["max_age"] == 3600

    def test_multiple_cors_origins(self):
        """Multiple CORS origins are preserved."""
        origins = [
            "http://localhost:3000",
            "http://localhost:5173",
            "https://app.example.com",
        ]
        app = Nexus(
            cors_origins=origins,
            enable_durability=False,
        )

        assert app.cors_config["allow_origins"] == origins


# =============================================================================
# Tests: configure_cors() Method
# =============================================================================


class TestConfigureCors:
    """Tests for configure_cors() programmatic configuration."""

    def test_updates_origins(self):
        """configure_cors() updates origins."""
        app = Nexus(enable_durability=False)

        app.configure_cors(allow_origins=["http://new.example.com"])

        assert app.cors_config["allow_origins"] == ["http://new.example.com"]

    def test_updates_methods(self):
        """configure_cors() updates methods."""
        app = Nexus(enable_durability=False)

        app.configure_cors(allow_methods=["GET", "POST"])

        assert app.cors_config["allow_methods"] == ["GET", "POST"]

    def test_updates_headers(self):
        """configure_cors() updates headers."""
        app = Nexus(enable_durability=False)

        app.configure_cors(allow_headers=["X-Custom"])

        assert app.cors_config["allow_headers"] == ["X-Custom"]

    def test_updates_credentials(self):
        """configure_cors() updates credentials flag."""
        app = Nexus(enable_durability=False)

        app.configure_cors(allow_credentials=False)

        assert app.cors_config["allow_credentials"] is False

    def test_updates_expose_headers(self):
        """configure_cors() updates expose_headers."""
        app = Nexus(enable_durability=False)

        app.configure_cors(expose_headers=["X-Total-Count"])

        assert app.cors_config["expose_headers"] == ["X-Total-Count"]

    def test_updates_max_age(self):
        """configure_cors() updates max_age."""
        app = Nexus(enable_durability=False)

        app.configure_cors(max_age=1800)

        assert app.cors_config["max_age"] == 1800

    def test_partial_update_preserves_other_settings(self):
        """Updating one setting preserves others."""
        app = Nexus(
            cors_origins=["http://example.com"],
            cors_max_age=300,
            enable_durability=False,
        )

        app.configure_cors(allow_methods=["GET"])

        assert app.cors_config["allow_origins"] == ["http://example.com"]
        assert app.cors_config["allow_methods"] == ["GET"]
        assert app.cors_config["max_age"] == 300

    def test_returns_self_for_chaining(self):
        """configure_cors() returns self for method chaining."""
        app = Nexus(enable_durability=False)

        result = app.configure_cors(allow_origins=["http://example.com"])

        assert result is app

    def test_chained_configuration(self):
        """Multiple configure_cors() calls can be chained."""
        app = Nexus(enable_durability=False)

        result = (
            app.configure_cors(allow_origins=["http://example.com"])
            .configure_cors(allow_methods=["GET"])
            .configure_cors(max_age=1800)
        )

        assert result is app
        assert app.cors_config["allow_origins"] == ["http://example.com"]
        assert app.cors_config["allow_methods"] == ["GET"]
        assert app.cors_config["max_age"] == 1800

    def test_production_rejects_wildcard_via_configure(self, monkeypatch):
        """configure_cors() rejects wildcard in production."""
        monkeypatch.setenv("NEXUS_ENV", "production")
        app = Nexus(enable_auth=False, enable_durability=False)

        with pytest.raises(ValueError, match="not allowed in production"):
            app.configure_cors(allow_origins=["*"])


# =============================================================================
# Tests: Origin Validation Warnings
# =============================================================================


class TestCorsOriginValidation:
    """Tests for origin format validation warnings."""

    def test_warns_on_invalid_origin_format(self, caplog):
        """Warning logged for origins missing protocol."""
        with caplog.at_level(logging.WARNING):
            app = Nexus(enable_durability=False)
            app.configure_cors(allow_origins=["example.com"])

        assert "may be invalid" in caplog.text

    def test_no_warning_for_valid_http_origin(self, caplog):
        """No warning for valid http:// origin."""
        app = Nexus(enable_durability=False)

        with caplog.at_level(logging.WARNING):
            caplog.clear()
            app.configure_cors(allow_origins=["http://example.com"])

        assert "may be invalid" not in caplog.text

    def test_no_warning_for_valid_https_origin(self, caplog):
        """No warning for valid https:// origin."""
        app = Nexus(enable_durability=False)

        with caplog.at_level(logging.WARNING):
            caplog.clear()
            app.configure_cors(allow_origins=["https://example.com"])

        assert "may be invalid" not in caplog.text

    def test_no_warning_for_wildcard(self, caplog):
        """No warning for wildcard origin."""
        app = Nexus(enable_durability=False)

        with caplog.at_level(logging.WARNING):
            caplog.clear()
            app.configure_cors(allow_origins=["*"])

        assert "may be invalid" not in caplog.text


# =============================================================================
# Tests: cors_config Property
# =============================================================================


class TestCorsConfigProperty:
    """Tests for cors_config introspection property."""

    def test_returns_dict(self):
        """cors_config returns a dictionary."""
        app = Nexus(enable_durability=False)

        config = app.cors_config
        assert isinstance(config, dict)

    def test_contains_all_keys(self):
        """cors_config has all expected keys."""
        app = Nexus(enable_durability=False)

        config = app.cors_config
        expected_keys = {
            "allow_origins",
            "allow_methods",
            "allow_headers",
            "allow_credentials",
            "expose_headers",
            "max_age",
        }
        assert set(config.keys()) == expected_keys

    def test_reflects_constructor_params(self):
        """cors_config reflects values passed to constructor."""
        app = Nexus(
            cors_origins=["http://test.com"],
            cors_allow_methods=["GET"],
            cors_allow_headers=["X-Test"],
            cors_allow_credentials=False,
            cors_expose_headers=["X-Expose"],
            cors_max_age=999,
            enable_durability=False,
        )

        config = app.cors_config
        assert config["allow_origins"] == ["http://test.com"]
        assert config["allow_methods"] == ["GET"]
        assert config["allow_headers"] == ["X-Test"]
        assert config["allow_credentials"] is False
        assert config["expose_headers"] == ["X-Expose"]
        assert config["max_age"] == 999


# =============================================================================
# Tests: is_origin_allowed()
# =============================================================================


class TestIsOriginAllowed:
    """Tests for is_origin_allowed() helper method."""

    def test_allowed_origin(self):
        """Returns True for explicitly allowed origin."""
        app = Nexus(
            cors_origins=["http://allowed.com"],
            enable_durability=False,
        )

        assert app.is_origin_allowed("http://allowed.com") is True

    def test_denied_origin(self):
        """Returns False for non-allowed origin."""
        app = Nexus(
            cors_origins=["http://allowed.com"],
            enable_durability=False,
        )

        assert app.is_origin_allowed("http://denied.com") is False

    def test_wildcard_allows_all(self):
        """Wildcard origin allows all."""
        app = Nexus(
            cors_origins=["*"],
            enable_durability=False,
        )

        assert app.is_origin_allowed("http://any.com") is True

    def test_multiple_origins(self):
        """Multiple origins checked correctly."""
        app = Nexus(
            cors_origins=["http://a.com", "http://b.com"],
            enable_durability=False,
        )

        assert app.is_origin_allowed("http://a.com") is True
        assert app.is_origin_allowed("http://b.com") is True
        assert app.is_origin_allowed("http://c.com") is False

    def test_uses_defaults_when_no_explicit_origins(self):
        """Falls back to defaults when no explicit origins set."""
        # Development defaults have ["*"]
        app = Nexus(enable_durability=False)

        assert app.is_origin_allowed("http://any.com") is True


# =============================================================================
# Tests: Gateway Integration
# =============================================================================


class TestCorsGatewayIntegration:
    """Tests for CORS middleware application to gateway."""

    def test_gateway_receives_null_cors(self):
        """Gateway is created with cors_origins=None (prevents double CORS)."""
        app = Nexus(
            cors_origins=["http://example.com"],
            enable_durability=False,
        )

        # Gateway should exist and have CORS middleware applied
        assert app._gateway is not None
        assert app._cors_middleware_applied is True

    def test_cors_middleware_not_applied_when_no_origins(self, monkeypatch):
        """CORS middleware not applied when origins list is empty."""
        monkeypatch.setenv("NEXUS_ENV", "production")
        app = Nexus(enable_auth=False, enable_durability=False)

        # No origins configured in production defaults
        assert app._cors_middleware_applied is False

    def test_configure_cors_warns_on_reconfigure(self, caplog):
        """Warning when reconfiguring CORS after gateway init."""
        app = Nexus(
            cors_origins=["http://example.com"],
            enable_durability=False,
        )

        with caplog.at_level(logging.WARNING):
            caplog.clear()
            app.configure_cors(allow_origins=["http://new.example.com"])

        assert "Reconfiguring CORS" in caplog.text


# =============================================================================
# Tests: Logging
# =============================================================================


class TestCorsLogging:
    """Tests for CORS-related logging."""

    def test_logs_cors_configuration(self, caplog):
        """Info log when CORS is configured via configure_cors()."""
        with caplog.at_level(logging.INFO):
            app = Nexus(enable_durability=False)

            caplog.clear()
            app.configure_cors(allow_origins=["http://example.com"])

        assert "CORS configured" in caplog.text


# =============================================================================
# Tests: CORS Security Validation (WS01 red team fix)
# =============================================================================


class TestCORSSecurityValidation:
    """Tests for _validate_cors_security() credentials+wildcard warning."""

    def test_warns_credentials_with_wildcard(self, caplog):
        """Should warn when credentials=True with origins=['*']."""
        app = Nexus(enable_durability=False)

        with caplog.at_level(logging.WARNING):
            app.configure_cors(
                allow_origins=["*"],
                allow_credentials=True,
            )

        assert any("CORS security warning" in msg for msg in caplog.messages)
        assert any("credentials" in msg.lower() for msg in caplog.messages)

    def test_no_warning_with_specific_origins(self, caplog):
        """Should not warn with specific origins and credentials."""
        app = Nexus(enable_durability=False)

        with caplog.at_level(logging.WARNING):
            caplog.clear()
            app.configure_cors(
                allow_origins=["https://example.com"],
                allow_credentials=True,
            )

        security_warnings = [
            msg for msg in caplog.messages if "CORS security warning" in msg
        ]
        assert len(security_warnings) == 0

    def test_no_warning_credentials_false_with_wildcard(self, caplog):
        """Should not warn with wildcard when credentials=False."""
        app = Nexus(enable_durability=False)

        with caplog.at_level(logging.WARNING):
            caplog.clear()
            app.configure_cors(
                allow_origins=["*"],
                allow_credentials=False,
            )

        security_warnings = [
            msg for msg in caplog.messages if "CORS security warning" in msg
        ]
        assert len(security_warnings) == 0
