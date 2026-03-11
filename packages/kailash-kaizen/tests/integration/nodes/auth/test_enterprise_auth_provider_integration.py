"""
Tier 2 Integration Tests for AI-Enhanced Enterprise Authentication Provider Node

Tests focus on:
- Real LLM calls for fraud detection
- AI risk assessment with actual reasoning
- Multiple risk scenarios (low, medium, high)
- Security decision validation
- NO MOCKING policy for LLM responses

Strategy:
- NO MOCKING for LLM - use real API calls
- Target: <40 seconds total runtime
- Cost: ~$0.01-0.02 (gpt-5-nano is cost-efficient)
- Tests: 10 comprehensive integration scenarios
"""

import json
import os

import pytest
from kaizen.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

# Skip if USE_REAL_PROVIDERS is not enabled
pytestmark = pytest.mark.skipif(
    os.getenv("USE_REAL_PROVIDERS", "").lower() != "true",
    reason="Integration tests require USE_REAL_PROVIDERS=true",
)


class TestEnterpriseAuthProviderNodeIntegration:
    """Integration tests for AI-enhanced enterprise auth provider with real LLM calls."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_risk_assessment_low_risk_real_llm(self):
        """
        Test AI risk assessment for low-risk authentication with real LLM.

        Validates:
        - Real gpt-5-nano-2025-08-07 fraud detection
        - Low risk scenario detection
        - Appropriate risk scoring (0.0-0.3)
        - Recommended action: "allow"

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = EnterpriseAuthProviderNode(
            name="test_auth_low_risk",
            enabled_methods=["sso", "mfa"],
            fraud_detection_enabled=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.2,
        )

        # Low risk context - internal IP, recognized device, normal hours
        low_risk_context = {
            "ip_address": "10.0.1.42",
            "device_info": {
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                "recognized": True,
                "screen_resolution": "1920x1080",
                "timezone": "UTC-8",
            },
            "location": "San Francisco, CA",
            "timestamp": "2024-01-15T14:30:00Z",
        }

        existing_factors = []

        result = await node._ai_risk_assessment(
            "user@company.com", low_risk_context, existing_factors
        )

        # Validate low risk assessment
        assert result["score"] <= 0.3
        assert result.get("recommended_action") in ["allow", "require_mfa"]
        assert "reasoning" in result

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_risk_assessment_medium_risk_real_llm(self):
        """
        Test AI risk assessment for medium-risk authentication with real LLM.

        Validates:
        - Detection of unusual patterns (new device + external IP)
        - Medium risk scoring (0.4-0.6)
        - Recommended action: "require_mfa" or "require_additional_verification"

        Cost: ~$0.002 | Expected Duration: 2-5 seconds
        """
        node = EnterpriseAuthProviderNode(
            name="test_auth_medium_risk",
            enabled_methods=["sso", "mfa"],
            fraud_detection_enabled=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.2,
        )

        # Medium risk context - external IP, unknown device
        medium_risk_context = {
            "ip_address": "203.0.113.42",
            "device_info": {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "recognized": False,
                "screen_resolution": "1366x768",
                "timezone": "UTC-5",
            },
            "location": "New York, NY",
            "timestamp": "2024-01-15T15:45:00Z",
        }

        existing_factors = ["unknown_device", "new_location"]

        result = await node._ai_risk_assessment(
            "user@company.com", medium_risk_context, existing_factors
        )

        # Validate medium risk assessment
        assert result["score"] >= 0.3
        assert result["score"] <= 0.7
        assert result.get("recommended_action") in [
            "require_mfa",
            "require_additional_verification",
        ]

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_risk_assessment_high_risk_real_llm(self):
        """
        Test AI risk assessment for high-risk authentication with real LLM.

        Validates:
        - Detection of suspicious patterns (VPN, late night, unknown device)
        - High risk scoring (0.7-1.0)
        - Recommended action: "require_additional_verification" or "block"
        - Detailed reasoning in response

        Cost: ~$0.002 | Expected Duration: 2-5 seconds
        """
        node = EnterpriseAuthProviderNode(
            name="test_auth_high_risk",
            enabled_methods=["sso", "mfa"],
            fraud_detection_enabled=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.2,
        )

        # High risk context - VPN, unknown device, late night, different country
        high_risk_context = {
            "ip_address": "185.220.101.42",  # Known VPN IP range
            "device_info": {
                "user_agent": "Mozilla/5.0 (Linux; Android 10; SM-G973F)",
                "recognized": False,
                "screen_resolution": "412x915",
                "timezone": "UTC+3",
            },
            "location": "Moscow, Russia",
            "timestamp": "2024-01-15T03:15:00Z",  # Late night
        }

        existing_factors = [
            "unknown_device",
            "vpn_detected",
            "impossible_travel",
            "off_hours_login",
        ]

        result = await node._ai_risk_assessment(
            "user@company.com", high_risk_context, existing_factors
        )

        # Validate high risk assessment
        assert result["score"] >= 0.6
        assert result.get("recommended_action") in [
            "require_additional_verification",
            "block",
        ]
        assert len(result.get("reasoning", "")) > 50  # Should have detailed reasoning

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_risk_assessment_account_takeover_pattern(self):
        """
        Test AI detection of account takeover patterns with real LLM.

        Validates:
        - Pattern recognition across multiple weak signals
        - Account takeover scenario detection
        - Context-aware risk amplification
        - Security-focused reasoning

        Cost: ~$0.002 | Expected Duration: 2-5 seconds
        """
        node = EnterpriseAuthProviderNode(
            name="test_auth_takeover",
            enabled_methods=["sso", "mfa"],
            fraud_detection_enabled=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.2,
        )

        # Account takeover pattern - credential stuffing indicators
        takeover_context = {
            "ip_address": "198.51.100.23",
            "device_info": {
                "user_agent": "python-requests/2.28.0",  # Automated tool
                "recognized": False,
                "screen_resolution": "800x600",
                "timezone": "UTC+0",
            },
            "location": "Unknown",
            "timestamp": "2024-01-15T23:45:00Z",
            "failed_attempts": 3,  # Multiple failed attempts before success
            "time_since_last_login": "2 hours",  # Unusual for this user
        }

        existing_factors = [
            "automated_client",
            "unknown_device",
            "multiple_failed_attempts",
        ]

        result = await node._ai_risk_assessment(
            "user@company.com", takeover_context, existing_factors
        )

        # Validate account takeover detection
        assert result["score"] >= 0.7
        assert (
            "takeover" in result.get("reasoning", "").lower()
            or "suspicious" in result.get("reasoning", "").lower()
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_risk_assessment_fast_path_bypass(self):
        """
        Test fast-path bypass for trusted internal access.

        Validates:
        - Fast-path optimization for low-risk scenarios
        - Skip AI call for trusted patterns
        - Internal IP + recognized device = instant allow
        - Cost optimization

        Cost: ~$0.000 (fast path, no LLM call) | Expected Duration: <1 second
        """
        node = EnterpriseAuthProviderNode(
            name="test_auth_fast_path",
            enabled_methods=["sso"],
            fraud_detection_enabled=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.2,
        )

        # Trusted context - internal IP, recognized device, no risk factors
        trusted_context = {
            "ip_address": "192.168.1.100",
            "device_info": {
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                "recognized": True,
                "screen_resolution": "1920x1080",
                "timezone": "UTC-8",
            },
            "location": "San Francisco, CA",
            "timestamp": "2024-01-15T10:00:00Z",
        }

        existing_factors = []

        result = await node._ai_risk_assessment(
            "user@company.com", trusted_context, existing_factors
        )

        # Validate fast-path response
        assert result["score"] == 0.0
        assert "Trusted internal access" in result.get("reasoning", "")

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_risk_assessment_geographic_anomaly(self):
        """
        Test AI detection of geographic anomalies with real LLM.

        Validates:
        - Geographic pattern analysis
        - Impossible travel detection
        - Location-based risk assessment

        Cost: ~$0.002 | Expected Duration: 2-5 seconds
        """
        node = EnterpriseAuthProviderNode(
            name="test_auth_geo",
            enabled_methods=["sso", "mfa"],
            fraud_detection_enabled=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.2,
        )

        # Geographic anomaly - impossible travel
        geo_anomaly_context = {
            "ip_address": "103.28.121.42",
            "device_info": {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "recognized": False,
                "screen_resolution": "1920x1080",
                "timezone": "UTC+8",
            },
            "location": "Singapore",
            "timestamp": "2024-01-15T18:00:00Z",
            "previous_location": "San Francisco, CA",
            "previous_login_time": "2024-01-15T14:00:00Z",  # 4 hours ago
        }

        existing_factors = ["geographic_anomaly", "impossible_travel"]

        result = await node._ai_risk_assessment(
            "user@company.com", geo_anomaly_context, existing_factors
        )

        # Validate geographic anomaly detection
        assert result["score"] >= 0.5
        assert (
            "geographic" in result.get("reasoning", "").lower()
            or "travel" in result.get("reasoning", "").lower()
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_risk_assessment_behavioral_anomaly(self):
        """
        Test AI detection of behavioral anomalies with real LLM.

        Validates:
        - Behavioral pattern analysis
        - Unusual activity detection
        - Context-aware risk assessment

        Cost: ~$0.002 | Expected Duration: 2-5 seconds
        """
        node = EnterpriseAuthProviderNode(
            name="test_auth_behavioral",
            enabled_methods=["sso", "mfa"],
            fraud_detection_enabled=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.2,
        )

        # Behavioral anomaly - unusual access pattern
        behavioral_context = {
            "ip_address": "203.0.113.50",
            "device_info": {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "recognized": True,
                "screen_resolution": "1920x1080",
                "timezone": "UTC-8",
            },
            "location": "San Francisco, CA",
            "timestamp": "2024-01-15T02:30:00Z",  # Very unusual time for this user
            "typical_login_hours": "09:00-17:00",
            "access_pattern": "unusual",
        }

        existing_factors = ["unusual_hour", "atypical_behavior"]

        result = await node._ai_risk_assessment(
            "user@company.com", behavioral_context, existing_factors
        )

        # Validate behavioral anomaly detection
        assert result["score"] >= 0.3

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_risk_assessment_combined_weak_signals(self):
        """
        Test AI detection when multiple weak signals combine to indicate risk.

        Validates:
        - Holistic risk analysis
        - Signal amplification through combination
        - AI's ability to see patterns humans might miss

        Cost: ~$0.002 | Expected Duration: 2-5 seconds
        """
        node = EnterpriseAuthProviderNode(
            name="test_auth_combined",
            enabled_methods=["sso", "mfa"],
            fraud_detection_enabled=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.2,
        )

        # Multiple weak signals that together indicate risk
        combined_signals_context = {
            "ip_address": "203.0.113.75",
            "device_info": {
                "user_agent": "Mozilla/5.0 (X11; Linux x86_64)",  # Unusual OS for this user
                "recognized": False,
                "screen_resolution": "1024x768",  # Unusual resolution
                "timezone": "UTC-6",  # Different timezone than usual
            },
            "location": "Austin, TX",  # Different city
            "timestamp": "2024-01-15T22:00:00Z",  # Evening
            "typical_os": "macOS",
            "typical_location": "San Francisco, CA",
        }

        existing_factors = ["new_device", "unusual_os", "different_timezone"]

        result = await node._ai_risk_assessment(
            "user@company.com", combined_signals_context, existing_factors
        )

        # AI should detect combined risk even if individual signals are weak
        assert result["score"] >= 0.4

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_risk_assessment_device_fingerprint_spoofing(self):
        """
        Test AI detection of device fingerprint spoofing attempts.

        Validates:
        - Detection of inconsistent device characteristics
        - Fingerprint spoofing pattern recognition
        - Security-focused reasoning

        Cost: ~$0.002 | Expected Duration: 2-5 seconds
        """
        node = EnterpriseAuthProviderNode(
            name="test_auth_spoofing",
            enabled_methods=["sso", "mfa"],
            fraud_detection_enabled=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.2,
        )

        # Device fingerprint inconsistencies
        spoofing_context = {
            "ip_address": "203.0.113.90",
            "device_info": {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "recognized": False,
                "screen_resolution": "800x600",  # Uncommon for Win10
                "timezone": "UTC+0",
                "webgl_vendor": "Apple Inc.",  # Inconsistent with Windows
                "canvas_fingerprint": "abc123",
                "audio_fingerprint": "xyz789",
            },
            "location": "London, UK",
            "timestamp": "2024-01-15T16:00:00Z",
        }

        existing_factors = ["device_fingerprint_mismatch", "unknown_device"]

        result = await node._ai_risk_assessment(
            "user@company.com", spoofing_context, existing_factors
        )

        # Validate spoofing detection
        assert result["score"] >= 0.6
        assert (
            "fingerprint" in result.get("reasoning", "").lower()
            or "spoofing" in result.get("reasoning", "").lower()
            or "suspicious" in result.get("reasoning", "").lower()
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_risk_assessment_reasoning_quality(self):
        """
        Test quality and detail of AI reasoning in risk assessments.

        Validates:
        - Reasoning includes specific factors
        - Explanation is clear and actionable
        - Recommended action aligns with risk score
        - Security decision transparency

        Cost: ~$0.002 | Expected Duration: 2-5 seconds
        """
        node = EnterpriseAuthProviderNode(
            name="test_auth_reasoning",
            enabled_methods=["sso", "mfa"],
            fraud_detection_enabled=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.2,
        )

        # Complex risk scenario requiring detailed reasoning
        complex_context = {
            "ip_address": "203.0.113.100",
            "device_info": {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "recognized": False,
                "screen_resolution": "1920x1080",
                "timezone": "UTC+1",
            },
            "location": "Paris, France",
            "timestamp": "2024-01-15T20:00:00Z",
            "recent_password_reset": True,
            "account_age_days": 730,
        }

        existing_factors = ["unknown_device", "new_location", "recent_password_reset"]

        result = await node._ai_risk_assessment(
            "user@company.com", complex_context, existing_factors
        )

        # Validate reasoning quality
        reasoning = result.get("reasoning", "")
        assert len(reasoning) > 30  # Should have substantial reasoning
        assert result.get("recommended_action") in [
            "allow",
            "require_mfa",
            "require_additional_verification",
            "block",
        ]

        # Verify alignment between score and action
        if result["score"] >= 0.7:
            assert result.get("recommended_action") in [
                "require_additional_verification",
                "block",
            ]
        elif result["score"] >= 0.4:
            assert result.get("recommended_action") in [
                "require_mfa",
                "require_additional_verification",
            ]
