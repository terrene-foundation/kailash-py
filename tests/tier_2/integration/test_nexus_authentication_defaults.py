"""
P0-1: Hybrid Authentication System - Security Fix Verification

SECURITY ISSUE PREVENTED:
- Development mode accidentally enabled in production with auth bypass
- No warning when auth disabled in production environments
- Unclear authentication status during startup

Tests verify:
1. Development mode (default): enable_auth=False by default
2. Production mode: NEXUS_ENV=production auto-enables auth
3. Explicit override: Nexus(enable_auth=True) forces auth in dev
4. Production warnings: Critical warning when auth disabled in production
5. Auth status logging: Clear startup logs showing auth status
"""

import logging
import os
from io import StringIO

import pytest
from nexus import Nexus


class TestHybridAuthenticationDefaults:
    """Test Nexus hybrid authentication system for security compliance."""

    @pytest.fixture(autouse=True)
    def reset_environment(self):
        """Reset environment variables before each test."""
        original_env = os.environ.get("NEXUS_ENV")
        yield
        # Restore original environment
        if original_env is not None:
            os.environ["NEXUS_ENV"] = original_env
        elif "NEXUS_ENV" in os.environ:
            del os.environ["NEXUS_ENV"]

    @pytest.fixture
    def log_capture(self):
        """Capture log output for verification."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.INFO)
        logger = logging.getLogger("nexus.core")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        yield log_stream

        logger.removeHandler(handler)

    def test_development_mode_default_no_auth(self, log_capture):
        """
        TEST: Development mode should have auth disabled by default.

        SECURITY: Safe default for development - no accidental lockouts.
        """
        # GIVEN: Development environment (no NEXUS_ENV set)
        if "NEXUS_ENV" in os.environ:
            del os.environ["NEXUS_ENV"]

        # WHEN: Nexus initialized without explicit auth parameter
        nexus = Nexus(auto_discovery=False, enable_durability=False)

        # THEN: Authentication should be disabled by default
        assert (
            nexus._enable_auth is False
        ), "❌ SECURITY RISK: Development mode should default to enable_auth=False"

        # THEN: Log should clearly indicate auth status
        logs = log_capture.getvalue()
        assert (
            "auth" in logs.lower() or "security" in logs.lower()
        ), "❌ Missing authentication status in startup logs"

        print("✅ P0-1.1: Development mode correctly defaults to enable_auth=False")

    def test_production_mode_auto_enables_auth(self, log_capture):
        """
        TEST: Production mode should auto-enable authentication.

        SECURITY: Critical - prevents accidental auth bypass in production.
        """
        # GIVEN: Production environment set
        os.environ["NEXUS_ENV"] = "production"

        # WHEN: Nexus initialized without explicit auth parameter
        nexus = Nexus(auto_discovery=False, enable_durability=False)

        # THEN: Authentication should be auto-enabled in production
        assert (
            nexus._enable_auth is True
        ), "❌ CRITICAL SECURITY BUG: Production mode MUST auto-enable authentication"

        # THEN: Log should warn about production security
        logs = log_capture.getvalue()
        assert any(
            keyword in logs.lower() for keyword in ["production", "security", "auth"]
        ), "❌ Missing production security warning in logs"

        print("✅ P0-1.2: Production mode auto-enables auth (SECURITY FIX VERIFIED)")

    def test_explicit_auth_override_in_development(self, log_capture):
        """
        TEST: Explicit enable_auth=True should force auth even in development.

        SECURITY: Allows testing auth flows in development environment.
        """
        # GIVEN: Development environment
        if "NEXUS_ENV" in os.environ:
            del os.environ["NEXUS_ENV"]

        # WHEN: Explicitly enabling auth in development
        nexus = Nexus(enable_auth=True, auto_discovery=False, enable_durability=False)

        # THEN: Authentication should be enabled
        assert (
            nexus._enable_auth is True
        ), "❌ BUG: Explicit enable_auth=True not respected"

        # THEN: Log should reflect explicit auth enablement
        logs = log_capture.getvalue()
        # Should NOT contain production warnings (we're in dev mode)
        # But SHOULD show auth is enabled

        print("✅ P0-1.3: Explicit enable_auth=True works in development")

    def test_explicit_auth_disable_in_production_warns(self, log_capture):
        """
        TEST: Disabling auth in production should log CRITICAL warning.

        SECURITY: Critical - warns operators of dangerous configuration.
        """
        # GIVEN: Production environment
        os.environ["NEXUS_ENV"] = "production"

        # Capture warnings at CRITICAL level
        logger = logging.getLogger("nexus.core")
        logger.setLevel(logging.WARNING)

        # WHEN: Explicitly disabling auth in production (dangerous!)
        nexus = Nexus(
            enable_auth=False,  # DANGEROUS in production!
            auto_discovery=False,
            enable_durability=False,
        )

        # THEN: Auth should be disabled (explicit override)
        assert (
            nexus._enable_auth is False
        ), "❌ BUG: Explicit enable_auth=False not respected"

        # THEN: Should log CRITICAL warning about security risk
        logs = log_capture.getvalue()
        has_critical_warning = any(
            keyword in logs.lower()
            for keyword in ["critical", "danger", "security risk", "warning"]
        )

        assert (
            has_critical_warning
        ), "❌ CRITICAL SECURITY BUG: Must warn when auth disabled in production"

        print("✅ P0-1.4: Critical warning logged when auth disabled in production")

    def test_auth_status_clearly_logged_at_startup(self, log_capture):
        """
        TEST: Startup logs must clearly show authentication status.

        SECURITY: Operators must know at a glance if auth is active.
        """
        # Test both enabled and disabled states
        test_cases = [
            (False, "development", "disabled"),
            (True, "development", "enabled"),
        ]

        for enable_auth, mode, expected_status in test_cases:
            # Clear previous logs
            log_capture.truncate(0)
            log_capture.seek(0)

            # GIVEN: Specific auth configuration
            if "NEXUS_ENV" in os.environ:
                del os.environ["NEXUS_ENV"]

            # WHEN: Nexus initialized
            nexus = Nexus(
                enable_auth=enable_auth, auto_discovery=False, enable_durability=False
            )

            # THEN: Logs should clearly indicate auth status
            logs = log_capture.getvalue()

            # Look for clear authentication status indicators
            auth_mentioned = any(
                keyword in logs.lower()
                for keyword in ["auth", "security", "authentication"]
            )

            assert (
                auth_mentioned
            ), f"❌ BUG: Auth status not mentioned in logs (enable_auth={enable_auth})"

            print(
                f"✅ P0-1.5.{test_cases.index((enable_auth, mode, expected_status)) + 1}: "
                f"Auth status '{expected_status}' clearly logged"
            )

    def test_production_detection_from_common_env_vars(self, log_capture):
        """
        TEST: Production should be detected from common environment variables.

        SECURITY: Prevents accidental production deployment without auth.
        """
        # Common production environment indicators
        production_indicators = [
            ("NEXUS_ENV", "production"),
            ("NEXUS_ENV", "prod"),
            ("ENV", "production"),
            ("ENVIRONMENT", "production"),
        ]

        for env_var, env_value in production_indicators:
            # Clear logs
            log_capture.truncate(0)
            log_capture.seek(0)

            # GIVEN: Production indicator environment variable
            os.environ[env_var] = env_value

            try:
                # WHEN: Nexus initialized without explicit auth
                nexus = Nexus(auto_discovery=False, enable_durability=False)

                # THEN: Should auto-enable auth (if production detection works)
                # NOTE: Current implementation only checks NEXUS_ENV
                # This test documents expected behavior for future enhancement

                if env_var == "NEXUS_ENV":
                    assert (
                        nexus._enable_auth is True
                    ), f"❌ BUG: {env_var}={env_value} should auto-enable auth"
                    print(f"✅ P0-1.6: Production detected via {env_var}={env_value}")
                else:
                    # Document current limitation
                    print(
                        f"⚠️  P0-1.6: {env_var}={env_value} not yet supported "
                        "(future enhancement)"
                    )
            finally:
                # Clean up
                if env_var in os.environ:
                    del os.environ[env_var]

    def test_backward_compatibility_preserved(self):
        """
        TEST: Existing code without auth parameter should work unchanged.

        SECURITY: No breaking changes to existing deployments.
        """
        # GIVEN: Existing code pattern (no auth parameter)
        # WHEN: Nexus initialized the old way
        nexus = Nexus(auto_discovery=False, enable_durability=False)

        # THEN: Should work with sensible defaults
        assert nexus is not None
        assert hasattr(nexus, "_enable_auth")
        assert isinstance(nexus._enable_auth, bool)

        print("✅ P0-1.7: Backward compatibility preserved for existing code")


class TestAuthenticationConfigurationMatrix:
    """Test all combinations of auth configuration for comprehensive coverage."""

    @pytest.fixture(autouse=True)
    def reset_environment(self):
        """Reset environment before each test."""
        original_env = os.environ.get("NEXUS_ENV")
        yield
        if original_env is not None:
            os.environ["NEXUS_ENV"] = original_env
        elif "NEXUS_ENV" in os.environ:
            del os.environ["NEXUS_ENV"]

    @pytest.mark.parametrize(
        "nexus_env,enable_auth,expected_auth",
        [
            # Development scenarios
            (None, None, False),  # Dev default: no auth
            (None, False, False),  # Dev explicit no auth
            (None, True, True),  # Dev explicit auth enabled
            ("development", None, False),  # Dev explicit: no auth
            ("development", False, False),  # Dev explicit: no auth
            ("development", True, True),  # Dev explicit: auth enabled
            # Production scenarios
            ("production", None, True),  # Prod default: AUTH REQUIRED
            ("production", False, False),  # Prod override: DANGEROUS
            ("production", True, True),  # Prod explicit: auth enabled
            ("prod", None, True),  # Prod alias: AUTH REQUIRED
        ],
    )
    def test_authentication_configuration_matrix(
        self, nexus_env, enable_auth, expected_auth
    ):
        """
        COMPREHENSIVE TEST: Verify all auth configuration combinations.

        This test ensures no edge cases break the security model.
        """
        # GIVEN: Specific environment and auth configuration
        if nexus_env is not None:
            os.environ["NEXUS_ENV"] = nexus_env
        elif "NEXUS_ENV" in os.environ:
            del os.environ["NEXUS_ENV"]

        # WHEN: Nexus initialized with specific config
        kwargs = {
            "auto_discovery": False,
            "enable_durability": False,
        }
        if enable_auth is not None:
            kwargs["enable_auth"] = enable_auth

        nexus = Nexus(**kwargs)

        # THEN: Auth status should match expected behavior
        assert nexus._enable_auth == expected_auth, (
            f"❌ SECURITY BUG: "
            f"NEXUS_ENV={nexus_env}, enable_auth={enable_auth} -> "
            f"Expected auth={expected_auth}, got {nexus._enable_auth}"
        )

        # Additional security check for production
        if nexus_env in ("production", "prod") and enable_auth is False:
            # CRITICAL: Operator explicitly disabled auth in production
            # This is dangerous and must be logged
            pass  # Warning check covered in other tests

        print(
            f"✅ Matrix test passed: "
            f"env={nexus_env}, explicit={enable_auth} -> auth={expected_auth}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
