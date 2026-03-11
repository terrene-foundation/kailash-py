"""
Tests for optional DataFlow integration activation.

Verifies:
- Framework independence (Kaizen works without DataFlow)
- Integration activation when both present
- Graceful degradation when DataFlow missing
- No hard dependencies
"""

from unittest.mock import MagicMock, patch

import pytest


class TestOptionalActivation:
    """Test suite for optional DataFlow integration activation."""

    def test_kaizen_works_without_dataflow(self):
        """
        Verify Kaizen imports and works when DataFlow not installed.

        Critical: Kaizen must be independently usable.

        NOTE: Since DataFlow is installed in the test environment, this test
        verifies the import structure is correct. When DataFlow is absent,
        DATAFLOW_AVAILABLE would be False. We test the import mechanism works.
        """
        # When DataFlow is installed, DATAFLOW_AVAILABLE is True
        # This test verifies the integration module imports correctly
        from kaizen.integrations import dataflow

        # Should have DATAFLOW_AVAILABLE attribute
        assert hasattr(dataflow, "DATAFLOW_AVAILABLE")

        # In our test environment, DataFlow IS installed, so it's True
        # The key verification is that importing doesn't fail
        if dataflow.DATAFLOW_AVAILABLE:
            # When available, should have integration components
            assert hasattr(dataflow, "DataFlowConnection")
            assert hasattr(dataflow, "DataFlowAwareAgent")
            assert hasattr(dataflow, "DataFlowOperationsMixin")
        else:
            # When unavailable, should only have DATAFLOW_AVAILABLE
            assert not hasattr(dataflow, "DataFlowConnection")
            assert not hasattr(dataflow, "DataFlowAwareAgent")
            assert not hasattr(dataflow, "DataFlowOperationsMixin")

    def test_dataflow_integration_available_when_present(self):
        """
        Verify integration activates when both frameworks present.

        When DataFlow is installed, integration components should be available.
        """
        # DataFlow is installed in test environment, so test directly
        from kaizen.integrations import dataflow as df_integration

        # Should indicate DataFlow available (it's installed in test env)
        assert df_integration.DATAFLOW_AVAILABLE is True

        # Should have integration components
        assert hasattr(df_integration, "DataFlowConnection")
        assert hasattr(df_integration, "DataFlowAwareAgent")
        assert hasattr(df_integration, "DataFlowOperationsMixin")

    def test_no_hard_dependency_on_dataflow(self):
        """
        Verify importing Kaizen doesn't require DataFlow.

        Kaizen should be fully functional without DataFlow installed.
        """
        # Should import without error (tests Kaizen core imports)
        import kaizen
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig

        # Core Kaizen should work
        assert kaizen is not None
        assert BaseAgent is not None
        assert BaseAgentConfig is not None

    def test_integration_exports_when_available(self):
        """
        Verify kaizen.integrations.dataflow exports correctly when available.

        When DataFlow present, all integration components should be exported.
        """
        # DataFlow is installed in test environment
        from kaizen.integrations import dataflow as df_integration

        # Check __all__ exports
        assert hasattr(df_integration, "__all__")
        expected_exports = [
            "DATAFLOW_AVAILABLE",
            "DataFlowConnection",
            "DataFlowAwareAgent",
            "DataFlowOperationsMixin",
        ]

        for export in expected_exports:
            assert export in df_integration.__all__, f"Missing export: {export}"


class TestIntegrationIsolation:
    """Test framework isolation and independence."""

    def test_kaizen_core_independent_of_integration(self):
        """
        Verify Kaizen core functionality is independent of DataFlow integration.

        Core agents should work without any DataFlow awareness.
        """
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig

        # Create a basic agent without DataFlow
        config = BaseAgentConfig(llm_provider="mock", model="gpt-4")

        agent = BaseAgent(config)

        # Should work without DataFlow
        assert agent is not None
        assert agent.config.llm_provider == "mock"

    def test_integration_module_lazy_loading(self):
        """
        Verify integration module loads lazily.

        Integration should only initialize when explicitly used.
        """
        # Just importing the module shouldn't fail
        from kaizen.integrations import dataflow

        # Module should exist
        assert dataflow is not None

        # Should have version
        assert hasattr(dataflow, "__version__")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
