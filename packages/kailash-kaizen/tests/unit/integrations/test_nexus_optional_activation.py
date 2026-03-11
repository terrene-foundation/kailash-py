"""
Test Nexus Optional Activation - Framework Independence.

Tests verify that:
1. Kaizen works independently without Nexus
2. Integration activates only when Nexus is present
3. No hard dependencies between frameworks
4. Graceful degradation when Nexus unavailable
"""

import sys
from unittest.mock import patch


class TestNexusAvailabilityFlag:
    """Test NEXUS_AVAILABLE flag existence and behavior."""

    def test_nexus_available_flag_exists(self):
        """NEXUS_AVAILABLE flag should exist in kaizen.integrations.nexus."""
        # Import should work regardless of Nexus availability
        from kaizen.integrations import nexus as nexus_integration

        assert hasattr(nexus_integration, "NEXUS_AVAILABLE")
        assert isinstance(nexus_integration.NEXUS_AVAILABLE, bool)

    def test_flag_reflects_nexus_installation(self):
        """Flag should reflect whether Nexus is actually installed."""
        from kaizen.integrations import nexus as nexus_integration

        # Flag should be True if Nexus can be imported, False otherwise
        try:
            import nexus

            assert nexus_integration.NEXUS_AVAILABLE is True
        except ImportError:
            assert nexus_integration.NEXUS_AVAILABLE is False


class TestKaizenWithoutNexus:
    """Test Kaizen works independently without Nexus."""

    def test_kaizen_imports_without_nexus(self):
        """Kaizen should import successfully even when Nexus not installed."""
        # Mock Nexus as unavailable
        with patch.dict(sys.modules, {"nexus": None}):
            # Force reimport to trigger ImportError

            if "kaizen.integrations.nexus" in sys.modules:
                del sys.modules["kaizen.integrations.nexus"]

            # This should NOT raise ImportError
            import kaizen.integrations.nexus as nexus_integration

            # Flag should indicate unavailability
            assert hasattr(nexus_integration, "NEXUS_AVAILABLE")

    def test_kaizen_base_agent_works_without_nexus(self):
        """BaseAgent should work without Nexus installed."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig

        # Should work fine
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        # Agent creation should succeed
        agent = BaseAgent(config=config)
        assert agent is not None


class TestNexusIntegrationAvailability:
    """Test integration availability based on Nexus presence."""

    def test_nexus_integration_available_when_present(self):
        """Integration components should be available when Nexus present."""
        from kaizen.integrations import nexus as nexus_integration

        if nexus_integration.NEXUS_AVAILABLE:
            # Integration components should be importable
            assert hasattr(nexus_integration, "NexusConnection")
            assert hasattr(nexus_integration, "NexusDeploymentMixin")
            assert "NexusConnection" in nexus_integration.__all__
            assert "NexusDeploymentMixin" in nexus_integration.__all__

    def test_nexus_integration_unavailable_when_missing(self):
        """Integration should gracefully degrade when Nexus missing."""
        # Mock Nexus as unavailable
        with patch.dict(sys.modules, {"nexus": None}):
            import importlib

            if "kaizen.integrations.nexus" in sys.modules:
                del sys.modules["kaizen.integrations.nexus"]

            # Reimport with Nexus unavailable
            import kaizen.integrations.nexus as nexus_integration

            importlib.reload(nexus_integration)

            # Should only export NEXUS_AVAILABLE
            assert nexus_integration.NEXUS_AVAILABLE is False
            assert nexus_integration.__all__ == ["NEXUS_AVAILABLE"]


class TestNoDependencyOnNexus:
    """Test no hard dependencies on Nexus."""

    def test_no_hard_dependency_on_nexus(self):
        """Importing Kaizen should not require Nexus."""
        # This test verifies the import chain doesn't force Nexus
        import kaizen
        import kaizen.core
        import kaizen.core.base_agent

        # All imports should succeed regardless of Nexus
        assert kaizen is not None
        assert kaizen.core is not None
        assert kaizen.core.base_agent is not None

    def test_nexus_integration_lazy_loading(self):
        """Nexus integration should use lazy loading pattern."""
        from kaizen.integrations import nexus as nexus_integration

        # Integration should exist but not force Nexus import
        assert nexus_integration is not None
        assert hasattr(nexus_integration, "NEXUS_AVAILABLE")


class TestIntegrationExports:
    """Test integration module exports."""

    def test_integration_exports_when_available(self):
        """Integration should export correct components when Nexus available."""
        from kaizen.integrations import nexus as nexus_integration

        if nexus_integration.NEXUS_AVAILABLE:
            # Check __all__ contains expected exports
            expected_exports = [
                "NEXUS_AVAILABLE",
                "NexusConnection",
                "NexusDeploymentMixin",
            ]

            for export in expected_exports:
                assert export in nexus_integration.__all__

    def test_integration_empty_when_unavailable(self):
        """Integration should only export NEXUS_AVAILABLE when Nexus missing."""
        # Mock Nexus unavailable
        with patch.dict(sys.modules, {"nexus": None}):
            import importlib

            if "kaizen.integrations.nexus" in sys.modules:
                del sys.modules["kaizen.integrations.nexus"]

            import kaizen.integrations.nexus as nexus_integration

            importlib.reload(nexus_integration)

            # Only NEXUS_AVAILABLE should be exported
            assert nexus_integration.__all__ == ["NEXUS_AVAILABLE"]
            assert nexus_integration.NEXUS_AVAILABLE is False

    def test_version_attribute_exists(self):
        """Integration module should have version attribute."""
        from kaizen.integrations import nexus as nexus_integration

        assert hasattr(nexus_integration, "__version__")
        assert isinstance(nexus_integration.__version__, str)


class TestGracefulDegradation:
    """Test graceful degradation scenarios."""

    def test_import_integration_without_nexus(self):
        """Integration module should import without errors even without Nexus."""
        # This should always work
        from kaizen.integrations import nexus

        # Should have at minimum the availability flag
        assert hasattr(nexus, "NEXUS_AVAILABLE")

    def test_conditional_feature_availability(self):
        """Features should be conditionally available based on Nexus."""
        from kaizen.integrations import nexus as nexus_integration

        if nexus_integration.NEXUS_AVAILABLE:
            # Full features available
            assert len(nexus_integration.__all__) > 1
        else:
            # Only flag available
            assert len(nexus_integration.__all__) == 1
            assert nexus_integration.__all__[0] == "NEXUS_AVAILABLE"
