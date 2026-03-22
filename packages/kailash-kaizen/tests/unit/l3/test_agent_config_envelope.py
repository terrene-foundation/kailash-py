# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for M0-01: AgentConfig envelope field (B1)."""

import pytest

from kaizen.agent_config import AgentConfig


class TestAgentConfigEnvelope:
    """Verify B1 acceptance criteria."""

    def test_config_without_envelope_works(self):
        """AC-1/2: Existing code without envelope continues to work."""
        config = AgentConfig(model="gpt-4")
        assert config.envelope is None
        assert config.model == "gpt-4"

    def test_config_with_envelope(self):
        """AC-3: Agent with envelope can be queried."""
        mock_envelope = {"financial": {"limit": 1000.0}, "operational": {}}
        config = AgentConfig(model="gpt-4", envelope=mock_envelope)
        assert config.envelope is not None
        assert config.envelope["financial"]["limit"] == 1000.0

    def test_to_dict_without_envelope(self):
        """AC-4: Serialization round-trip without envelope."""
        config = AgentConfig(model="gpt-4")
        d = config.to_dict()
        assert "envelope" in d
        assert d["envelope"] is None

    def test_to_dict_with_envelope_dict(self):
        """AC-4: Serialization round-trip with dict envelope."""
        envelope = {"financial": {"limit": 500.0}}
        config = AgentConfig(model="gpt-4", envelope=envelope)
        d = config.to_dict()
        assert d["envelope"] == envelope

    def test_to_dict_with_envelope_object(self):
        """AC-4: Serialization with object that has to_dict()."""

        class MockEnvelope:
            def to_dict(self):
                return {"financial": {"limit": 200.0}}

        config = AgentConfig(model="gpt-4", envelope=MockEnvelope())
        d = config.to_dict()
        assert d["envelope"] == {"financial": {"limit": 200.0}}

    def test_envelope_default_is_none(self):
        """Envelope defaults to None — backward compatible."""
        config = AgentConfig(model="claude-3")
        assert config.envelope is None

    def test_enabled_features_unchanged(self):
        """Envelope field does not affect existing feature detection."""
        config = AgentConfig(model="gpt-4", budget_limit_usd=5.0)
        features = config.get_enabled_features()
        assert "cost_tracking" in features
