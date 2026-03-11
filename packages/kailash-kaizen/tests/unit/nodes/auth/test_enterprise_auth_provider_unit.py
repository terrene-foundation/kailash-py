"""
Tier 1 Unit Tests for AI-Enhanced Enterprise Authentication Provider Node

Tests focus on:
- AI-powered fraud detection with mocked responses
- Risk assessment logic
- Fallback behavior when AI fails
- Integration with Core SDK features

Strategy:
- Mocking allowed for LLM responses
- Fast execution (<1 second per test)
- Isolated component testing
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kaizen.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode


class TestEnterpriseAuthProviderNodeUnit:
    """Unit tests for AI-enhanced enterprise authentication provider."""

    def test_node_initialization(self):
        """Test basic node initialization."""
        node = EnterpriseAuthProviderNode(
            name="test_enterprise_auth",
            ai_model="gpt-5-nano-2025-08-07",
            ai_temperature=0.2,
            fraud_detection_enabled=True,
        )

        assert node.name == "test_enterprise_auth"
        assert node.llm_agent is not None
        # LLMAgentNode does NOT expose model/temperature as attributes
        # These are node configuration parameters, not exposed attributes

    def test_inherits_from_core_sdk(self):
        """Test that node inherits from Core SDK EnterpriseAuthProviderNode."""
        from kailash.nodes.auth.enterprise_auth_provider import (
            EnterpriseAuthProviderNode as CoreEnterpriseAuthNode,
        )

        node = EnterpriseAuthProviderNode()
        assert isinstance(node, CoreEnterpriseAuthNode)

    def test_has_required_methods(self):
        """Test that node has required AI methods."""
        node = EnterpriseAuthProviderNode()

        assert hasattr(node, "_ai_risk_assessment")
        assert callable(node._ai_risk_assessment)

    @pytest.mark.asyncio
    async def test_ai_risk_assessment_low_risk_scenario(self):
        """Test AI risk assessment with low-risk scenario that bypasses fast path."""
        node = EnterpriseAuthProviderNode()

        # Mock LLM response for low-risk scenario
        mock_ai_analysis = {
            "risk_score": 0.1,
            "additional_factors": [],
            "reasoning": "External access from recognized device",
            "recommended_action": "allow",
        }

        # Mock format must match what the implementation expects: result.get("content", "{}")
        node.llm_agent.async_run = AsyncMock(
            return_value={"content": json.dumps(mock_ai_analysis)}
        )

        # Use external IP to bypass fast path (internal IPs trigger fast path)
        risk_context = {
            "ip_address": "8.8.8.8",  # External IP, not internal
            "device_info": {"recognized": True, "user_agent": "Chrome/120.0"},
            "location": "San Francisco, CA",
            "timestamp": "2024-01-15T10:00:00Z",
        }

        result = await node._ai_risk_assessment("user@company.com", risk_context, [])

        # With correct mock format, result should have the expected score
        assert result["score"] == 0.1
        assert result["recommended_action"] == "allow"
        assert len(result["factors"]) == 0

    @pytest.mark.asyncio
    async def test_ai_risk_assessment_high_risk_scenario(self):
        """Test AI risk assessment with high-risk scenario."""
        node = EnterpriseAuthProviderNode()

        # Mock LLM response for high-risk scenario
        mock_ai_analysis = {
            "risk_score": 0.85,
            "additional_factors": [
                "suspicious_ip_and_device",
                "geographic_anomaly",
                "unusual_access_time",
            ],
            "reasoning": "Late night login from unknown device and external IP suggests potential account takeover",
            "recommended_action": "require_additional_verification",
        }

        # Mock format must match what the implementation expects: result.get("content", "{}")
        node.llm_agent.async_run = AsyncMock(
            return_value={"content": json.dumps(mock_ai_analysis)}
        )

        risk_context = {
            "ip_address": "203.0.113.42",
            "device_info": {
                "recognized": False,
                "user_agent": "Unknown/1.0",
                "timezone": "UTC-8",
            },
            "location": "Moscow, Russia",
            "timestamp": "2024-01-15T23:45:00Z",
        }

        existing_factors = ["unknown_device", "off_hours_login"]

        result = await node._ai_risk_assessment(
            "user@company.com", risk_context, existing_factors
        )

        # With correct mock format, result should have the expected score
        assert result["score"] == 0.85
        assert result["recommended_action"] == "require_additional_verification"
        assert len(result["factors"]) == 3

    @pytest.mark.asyncio
    async def test_ai_risk_assessment_fast_path_trusted(self):
        """Test fast path for trusted internal access."""
        node = EnterpriseAuthProviderNode()

        # Should not call LLM for trusted scenario
        node.llm_agent.async_run = AsyncMock()

        risk_context = {
            "ip_address": "10.0.1.50",
            "device_info": {"recognized": True},
            "location": "Office Network",
            "timestamp": "2024-01-15T14:00:00Z",
        }

        # No existing factors or only benign ones
        result = await node._ai_risk_assessment("user@company.com", risk_context, [])

        # Fast path logic at lines 126-141 returns {score: 0.0} for low-risk scenarios
        # (internal IP + recognized device + minimal factors)
        assert result["score"] == 0.0
        assert result["reasoning"] == "Trusted internal access from recognized device"
        assert len(result["factors"]) == 0

        # Verify LLM was NOT called
        node.llm_agent.async_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_ai_risk_assessment_fast_path_unusual_hour_only(self):
        """Test fast path with only unusual_hour factor."""
        node = EnterpriseAuthProviderNode()

        node.llm_agent.async_run = AsyncMock()

        risk_context = {
            "ip_address": "192.168.1.100",
            "device_info": {"recognized": True},
            "location": "Home Network",
            "timestamp": "2024-01-15T22:30:00Z",
        }

        # Only unusual_hour factor
        result = await node._ai_risk_assessment(
            "user@company.com", risk_context, ["unusual_hour"]
        )

        # Fast path logic: internal IP (192.168.*) + recognized device + only unusual_hour
        # Returns score 0.0 (see lines 126-141)
        assert result["score"] == 0.0
        node.llm_agent.async_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_ai_risk_assessment_fallback_on_error(self):
        """Test fallback to Core SDK when AI fails."""
        node = EnterpriseAuthProviderNode()

        # Mock LLM to raise exception
        node.llm_agent.async_run = AsyncMock(side_effect=Exception("AI service down"))

        risk_context = {
            "ip_address": "203.0.113.42",
            "device_info": {"recognized": False},
        }

        result = await node._ai_risk_assessment(
            "user@company.com", risk_context, ["unknown_device"]
        )

        # Should fallback gracefully
        assert "score" in result
        # Score should be reasonable (not extreme)
        assert 0.0 <= result["score"] <= 1.0

    @pytest.mark.asyncio
    async def test_ai_risk_assessment_handles_invalid_json(self):
        """Test handling of invalid JSON from LLM."""
        node = EnterpriseAuthProviderNode()

        # Mock LLM to return invalid JSON
        node.llm_agent.async_run = AsyncMock(
            return_value={"response": "This is not valid JSON"}
        )

        risk_context = {"ip_address": "1.2.3.4"}

        result = await node._ai_risk_assessment("user@company.com", risk_context, [])

        # Should fallback gracefully
        assert "score" in result
        assert 0.0 <= result["score"] <= 1.0

    @pytest.mark.asyncio
    async def test_ai_risk_assessment_credential_stuffing_detection(self):
        """Test AI detection of credential stuffing attack."""
        node = EnterpriseAuthProviderNode()

        mock_ai_analysis = {
            "risk_score": 0.95,
            "additional_factors": [
                "credential_stuffing_pattern",
                "automated_attack",
                "multiple_failed_attempts",
            ],
            "reasoning": "Pattern consistent with credential stuffing attack - multiple rapid login attempts from different IPs",
            "recommended_action": "block",
        }

        # Mock format must match what the implementation expects: result.get("content", "{}")
        node.llm_agent.async_run = AsyncMock(
            return_value={"content": json.dumps(mock_ai_analysis)}
        )

        risk_context = {
            "ip_address": "45.67.89.123",
            "device_info": {
                "recognized": False,
                "user_agent": "curl/7.68.0",
                "fingerprint_anomaly": True,
            },
            "location": "Unknown",
            "timestamp": "2024-01-15T03:15:22Z",
            "login_velocity": "high",
            "previous_attempts": 15,
        }

        existing_factors = ["multiple_failed_logins", "suspicious_user_agent"]

        result = await node._ai_risk_assessment(
            "user@company.com", risk_context, existing_factors
        )

        # With correct mock format, result should have the expected score
        assert result["score"] >= 0.9
        assert result["recommended_action"] == "block"
        # Fix: reasoning contains "credential stuffing" (with space), not "credential_stuffing" (with underscore)
        assert "credential stuffing" in result["reasoning"].lower()

    @pytest.mark.asyncio
    async def test_ai_risk_assessment_geographic_anomaly(self):
        """Test AI detection of impossible travel scenario."""
        node = EnterpriseAuthProviderNode()

        mock_ai_analysis = {
            "risk_score": 0.7,
            "additional_factors": ["impossible_travel", "geographic_anomaly"],
            "reasoning": "User logged in from San Francisco 2 hours ago, now attempting login from Tokyo - impossible travel detected",
            "recommended_action": "require_mfa",
        }

        # Mock format must match what the implementation expects: result.get("content", "{}")
        node.llm_agent.async_run = AsyncMock(
            return_value={"content": json.dumps(mock_ai_analysis)}
        )

        risk_context = {
            "ip_address": "210.123.45.67",
            "device_info": {"recognized": True},
            "location": "Tokyo, Japan",
            "timestamp": "2024-01-15T12:00:00Z",
            "previous_location": "San Francisco, CA",
            "previous_login_time": "2024-01-15T10:00:00Z",
        }

        result = await node._ai_risk_assessment(
            "user@company.com", risk_context, ["location_change"]
        )

        # With correct mock format, result should have the expected score
        assert result["score"] >= 0.6
        assert (
            "impossible_travel" in result["factors"]
            or "geographic_anomaly" in result["factors"]
        )

    @pytest.mark.asyncio
    async def test_ai_risk_assessment_device_fingerprint_spoofing(self):
        """Test AI detection of device fingerprint spoofing."""
        node = EnterpriseAuthProviderNode()

        mock_ai_analysis = {
            "risk_score": 0.75,
            "additional_factors": [
                "device_fingerprint_mismatch",
                "spoofing_indicators",
            ],
            "reasoning": "Device characteristics don't match expected patterns - possible device spoofing",
            "recommended_action": "require_additional_verification",
        }

        # Mock format must match what the implementation expects: result.get("content", "{}")
        node.llm_agent.async_run = AsyncMock(
            return_value={"content": json.dumps(mock_ai_analysis)}
        )

        risk_context = {
            "ip_address": "98.76.54.32",
            "device_info": {
                "recognized": False,
                "screen_resolution": "1920x1080",
                "timezone": "UTC+5",
                "canvas_fingerprint": "anomalous",
            },
            "location": "Unknown",
        }

        result = await node._ai_risk_assessment(
            "user@company.com", risk_context, ["new_device"]
        )

        # With correct mock format, result should have the expected score
        assert result["score"] >= 0.7
        assert (
            "spoofing" in result["reasoning"].lower()
            or "fingerprint" in result["reasoning"].lower()
        )

    @pytest.mark.asyncio
    async def test_ai_risk_assessment_various_risk_levels(self):
        """Test AI risk assessment across various risk levels."""
        node = EnterpriseAuthProviderNode()

        test_scenarios = [
            {
                "score": 0.0,
                "action": "allow",
                "description": "No risk",
            },
            {
                "score": 0.3,
                "action": "allow",
                "description": "Low risk",
            },
            {
                "score": 0.5,
                "action": "require_mfa",
                "description": "Medium risk",
            },
            {
                "score": 0.7,
                "action": "require_additional_verification",
                "description": "High risk",
            },
            {
                "score": 1.0,
                "action": "block",
                "description": "Critical risk",
            },
        ]

        for scenario in test_scenarios:
            # Mock format must match what the implementation expects: result.get("content", "{}")
            node.llm_agent.async_run = AsyncMock(
                return_value={
                    "content": json.dumps(
                        {
                            "risk_score": scenario["score"],
                            "additional_factors": [],
                            "reasoning": scenario["description"],
                            "recommended_action": scenario["action"],
                        }
                    )
                }
            )

            result = await node._ai_risk_assessment(
                "user@company.com", {"ip_address": "1.2.3.4"}, []
            )

            # With correct mock format, result should have the expected values
            assert result["score"] == scenario["score"]
            assert result["recommended_action"] == scenario["action"]


class TestEnterpriseAuthProviderPromptEngineering:
    """Test prompt engineering for fraud detection."""

    @pytest.mark.asyncio
    async def test_risk_assessment_prompt_structure(self):
        """Test that risk assessment prompt contains required information."""
        node = EnterpriseAuthProviderNode()

        captured_prompt = None

        async def capture_prompt(**kwargs):
            nonlocal captured_prompt
            # Extract prompt from messages array

            messages = kwargs.get("messages", [])

            captured_prompt = messages[0]["content"] if messages else ""
            return {
                "response": json.dumps(
                    {
                        "risk_score": 0.5,
                        "additional_factors": [],
                        "reasoning": "Test",
                        "recommended_action": "allow",
                    }
                )
            }

        node.llm_agent.async_run = capture_prompt

        risk_context = {
            "ip_address": "203.0.113.42",
            "device_info": {"recognized": False, "user_agent": "Chrome/120.0"},
            "location": "New York, NY",
            "timestamp": "2024-01-15T10:00:00Z",
        }

        await node._ai_risk_assessment(
            "user@company.com", risk_context, ["unknown_device"]
        )

        # Verify prompt structure
        assert captured_prompt is not None
        assert "user@company.com" in captured_prompt
        assert "203.0.113.42" in captured_prompt
        assert "New York, NY" in captured_prompt
        assert "unknown_device" in captured_prompt

        # Verify risk categories are mentioned
        assert "account takeover" in captured_prompt.lower()
        assert "credential stuffing" in captured_prompt.lower()
        assert "geographic anomaly" in captured_prompt.lower()

        # Verify output format requirements
        assert "risk_score" in captured_prompt
        assert "additional_factors" in captured_prompt
        assert "reasoning" in captured_prompt
        assert "recommended_action" in captured_prompt

    @pytest.mark.asyncio
    async def test_risk_assessment_includes_behavioral_patterns(self):
        """Test that prompt includes behavioral analysis requirements."""
        node = EnterpriseAuthProviderNode()

        captured_prompt = None

        async def capture_prompt(**kwargs):
            nonlocal captured_prompt
            # Extract prompt from messages array

            messages = kwargs.get("messages", [])

            captured_prompt = messages[0]["content"] if messages else ""
            return {
                "response": json.dumps(
                    {
                        "risk_score": 0.0,
                        "additional_factors": [],
                        "reasoning": "Test",
                        "recommended_action": "allow",
                    }
                )
            }

        node.llm_agent.async_run = capture_prompt

        await node._ai_risk_assessment(
            "user@company.com", {"ip_address": "1.2.3.4"}, []
        )

        assert "Behavioral patterns" in captured_prompt
        assert "Device characteristics" in captured_prompt
        assert "Geographic patterns" in captured_prompt
        assert "Temporal patterns" in captured_prompt
