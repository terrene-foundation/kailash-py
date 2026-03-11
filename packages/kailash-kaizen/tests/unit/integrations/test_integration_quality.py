"""
Integration quality and edge case tests for Kaizen-Nexus.

This test suite validates:
- Deployment parameter validation
- Session edge cases
- Channel isolation
- Error message clarity
- Graceful degradation without Nexus

Part of TODO-149 Phase 4: Performance & Testing
"""

from dataclasses import dataclass

import pytest

# Import Kaizen components
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature


class TestDeploymentParameterValidation:
    """Test deployment parameter validation."""

    def test_validates_agent_parameter(self):
        """Test that agent parameter is validated."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import deploy_as_api
        from nexus import Nexus

        app = Nexus(auto_discovery=False)

        # Invalid agent (None)
        with pytest.raises((TypeError, AttributeError, ValueError)):
            deploy_as_api(None, app, "test")

        # Invalid agent (not BaseAgent)
        with pytest.raises((AttributeError, TypeError)):
            deploy_as_api("not_an_agent", app, "test")

    def test_validates_nexus_app_parameter(self):
        """Test that nexus_app parameter is validated."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import deploy_as_api

        # Create mock agent
        class TestSignature(Signature):
            input: str = InputField()
            output: str = OutputField()

        @dataclass
        class TestConfig:
            llm_provider: str = "mock"

        class TestAgent(BaseAgent):
            def __init__(self):
                super().__init__(config=TestConfig(), signature=TestSignature())

        agent = TestAgent()

        # Invalid app (None)
        with pytest.raises((TypeError, AttributeError)):
            deploy_as_api(agent, None, "test")

        # Invalid app (not Nexus)
        with pytest.raises((AttributeError, TypeError)):
            deploy_as_api(agent, "not_nexus", "test")


class TestSessionEdgeCases:
    """Test session management edge cases."""

    def test_handles_expired_sessions_gracefully(self):
        """Test handling of expired sessions."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        import time

        from kaizen.integrations.nexus import NexusSessionManager

        manager = NexusSessionManager(cleanup_interval=60)

        # Create session with very short TTL
        session = manager.create_session(user_id="test_user", ttl_hours=0.0001)

        # Wait for expiration
        time.sleep(0.1)

        # Try to access expired session
        state = manager.get_session_state(session.session_id)

        # Should handle gracefully (None or empty dict)
        assert state is None or state == {}

    def test_handles_missing_sessions_gracefully(self):
        """Test handling of missing sessions."""
        from kaizen.integrations.nexus import NEXUS_AVAILABLE

        if not NEXUS_AVAILABLE:
            pytest.skip("Nexus not available")

        from kaizen.integrations.nexus import NexusSessionManager

        manager = NexusSessionManager(cleanup_interval=60)

        # Try to access non-existent session
        state = manager.get_session_state("non_existent_session_id")

        # Should return None or empty dict
        assert state is None or state == {}


class TestGracefulDegradationWithoutNexus:
    """Test that Kaizen works without Nexus."""

    def test_kaizen_works_without_nexus_import(self):
        """Test that Kaizen works when Nexus is not installed."""
        # Import Kaizen components (should work regardless of Nexus)
        from kaizen.core.base_agent import BaseAgent
        from kaizen.signatures import Signature

        # Should import successfully
        assert BaseAgent is not None
        assert Signature is not None

    def test_nexus_integration_module_handles_missing_nexus(self):
        """Test that integration module handles missing Nexus gracefully."""
        # Should be able to import integration module
        from kaizen.integrations import nexus as nexus_integration

        # Should have NEXUS_AVAILABLE flag
        assert hasattr(nexus_integration, "NEXUS_AVAILABLE")

        # If Nexus not available, should export minimal interface
        if not nexus_integration.NEXUS_AVAILABLE:
            assert "NEXUS_AVAILABLE" in nexus_integration.__all__
            # Should not crash on import
            assert nexus_integration.__version__ is not None
