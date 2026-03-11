"""
AI-Enhanced Enterprise Authentication Provider Node

Extends Core SDK's enterprise authentication with AI-powered intelligent features:
- Intelligent fraud detection with pattern recognition
- Behavioral anomaly detection
- Context-aware risk assessment
- Adaptive security responses

For rule-based authentication only, use the Core SDK version:
    from kailash.nodes.auth import EnterpriseAuthProviderNode
"""

import json
import logging
from typing import Any, Dict, List

from kaizen.nodes.ai import LLMAgentNode

from kailash.nodes.auth.enterprise_auth_provider import (
    EnterpriseAuthProviderNode as CoreEnterpriseAuthNode,
)

logger = logging.getLogger(__name__)


class EnterpriseAuthProviderNode(CoreEnterpriseAuthNode):
    """
    AI-enhanced enterprise authentication provider with intelligent fraud detection.

    Extends the Core SDK enterprise auth provider with:
    - AI-powered fraud detection analyzing behavioral patterns
    - Intelligent anomaly detection for login attempts
    - Context-aware risk assessment considering multiple signals
    - Adaptive security responses based on threat intelligence

    Example:
        ```python
        from kaizen.nodes.auth import EnterpriseAuthProviderNode

        # Initialize with AI-powered fraud detection
        auth_provider = EnterpriseAuthProviderNode(
            name="ai_enterprise_auth",
            enabled_methods=["sso", "mfa", "directory"],
            fraud_detection_enabled=True,  # Enable AI-powered fraud detection
            ai_model="gpt-4o-mini",  # AI model for fraud detection
            ai_temperature=0.2,  # Lower temperature for consistent security decisions
        )
        ```

    Note:
        This node inherits all Core SDK enterprise auth capabilities and adds AI enhancements.
        The AI features activate when fraud_detection_enabled=True.
    """

    def __init__(
        self,
        name: str = "ai_enterprise_auth",
        ai_model: str = "gpt-4o-mini",
        ai_temperature: float = 0.2,
        provider: str = None,
        **kwargs,
    ):
        """
        Initialize AI-enhanced enterprise authentication provider.

        Args:
            name: Node name
            ai_model: AI model for fraud detection and risk assessment
            ai_temperature: Temperature for AI model (0.0-1.0, lower = more deterministic)
            provider: LLM provider (openai, anthropic, etc.). If None, auto-detected from model name
            **kwargs: Additional parameters passed to Core SDK EnterpriseAuthProviderNode
        """
        super().__init__(name=name, **kwargs)

        # Auto-detect provider from model name if not specified
        if provider is None:
            if "gpt" in ai_model.lower() or "o1" in ai_model.lower():
                provider = "openai"
            elif "claude" in ai_model.lower():
                provider = "anthropic"
            else:
                provider = "mock"  # Default for testing

        # Store provider and model for later use in LLM calls
        self.ai_provider = provider
        self.ai_model = ai_model

        # Initialize AI agent for fraud detection and risk assessment
        self.llm_agent = LLMAgentNode(
            name=f"{name}_llm",
            model=ai_model,
            temperature=ai_temperature,
            provider=provider,
        )

    async def _ai_risk_assessment(
        self, user_id: str, risk_context: Dict[str, Any], existing_factors: List[str]
    ) -> Dict[str, Any]:
        """
        AI-powered fraud detection with intelligent pattern recognition.

        This method extends the Core SDK version with AI capabilities to:
        1. Analyze behavioral patterns across multiple dimensions
        2. Detect subtle anomalies that rule-based systems miss
        3. Assess risk context holistically using intelligence
        4. Provide detailed reasoning for security decisions

        Args:
            user_id: User identifier
            risk_context: Risk assessment context (IP, device, location, time, etc.)
            existing_factors: Risk factors already identified by rule-based checks

        Returns:
            Risk assessment with AI-enhanced scoring and reasoning

        Example:
            ```python
            # Complex fraud scenario with multiple weak signals
            risk_context = {
                "ip_address": "203.0.113.42",
                "device_info": {
                    "user_agent": "Mozilla/5.0...",
                    "recognized": False,
                    "screen_resolution": "1920x1080",
                    "timezone": "UTC-8"
                },
                "location": "San Francisco, CA",
                "timestamp": "2024-01-15T23:45:00Z"
            }
            existing_factors = ["unknown_device", "off_hours_login"]

            # AI analyzes pattern: late night + unknown device + external IP
            # = potential account takeover attempt
            risk_assessment = await node._ai_risk_assessment(
                "user@company.com", risk_context, existing_factors
            )
            # Returns: {"score": 0.75, "factors": [...], "reasoning": "..."}
            ```
        """
        # For low-risk scenarios with minimal factors, use fast path
        if not existing_factors or (
            len(existing_factors) == 1 and existing_factors[0] in ["unusual_hour"]
        ):
            # Check if it's a trusted scenario
            ip = risk_context.get("ip_address", "")
            device = risk_context.get("device_info", {})

            if (ip.startswith("10.") or ip.startswith("192.168.")) and device.get(
                "recognized"
            ):
                # Internal IP with recognized device - very low risk
                return {
                    "score": 0.0,
                    "factors": [],
                    "reasoning": "Trusted internal access from recognized device",
                }

        # Prepare context for AI analysis
        prompt = f"""Analyze this authentication attempt for fraud and security risks.

User ID: {user_id}

Context Information:
- IP Address: {risk_context.get('ip_address', 'unknown')}
- Device Recognized: {risk_context.get('device_info', {}).get('recognized', False)}
- Device Info: {json.dumps(risk_context.get('device_info', {}), indent=2)}
- Location: {risk_context.get('location', 'unknown')}
- Timestamp: {risk_context.get('timestamp', 'unknown')}

Risk Factors Already Identified:
{', '.join(existing_factors) if existing_factors else 'None'}

Analyze this authentication attempt considering:
1. Behavioral patterns: Is this consistent with normal user behavior?
2. Device characteristics: Any suspicious device indicators?
3. Geographic patterns: Any impossible travel or location anomalies?
4. Temporal patterns: Is this login time typical for this user?
5. Combined signals: Do multiple weak signals together indicate fraud?

Risk Categories to Consider:
- Account takeover attempt (compromised credentials)
- Credential stuffing (automated attack)
- Geographic anomaly (VPN, proxy, or travel)
- Device fingerprint spoofing
- Behavioral anomaly (unusual patterns)
- Brute force attack patterns
- Social engineering indicators

Provide:
1. risk_score: Float between 0.0 (no risk) and 1.0 (critical risk)
2. additional_factors: List of new risk factors identified by AI analysis
3. reasoning: Clear explanation of the risk assessment
4. recommended_action: One of: "allow", "require_mfa", "require_additional_verification", "block"

Return ONLY a JSON object with these fields. No explanation outside the JSON.

Example output:
{{
  "risk_score": 0.65,
  "additional_factors": ["suspicious_ip_and_device", "geographic_anomaly"],
  "reasoning": "Late night login from unknown device and external IP suggests potential account takeover. Geographic location doesn't match user's typical pattern.",
  "recommended_action": "require_additional_verification"
}}
"""

        try:
            # Use AI for fraud detection
            result = await self.llm_agent.async_run(
                provider=self.ai_provider,
                model=self.ai_model,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=2000,  # OpenAI API compatibility: use max_completion_tokens for gpt-5-nano models
            )

            # Parse AI response - extract content from LLM response
            # Format: {"content": "json_string", "role": "assistant", ...}
            response_content = result.get("content", "{}")
            ai_analysis = json.loads(response_content)

            risk_score = ai_analysis.get("risk_score", 0.0)
            additional_factors = ai_analysis.get("additional_factors", [])
            reasoning = ai_analysis.get("reasoning", "AI risk assessment completed")

            # Log AI risk assessment
            logger.info(
                f"AI fraud detection for {user_id}: risk_score={risk_score:.2f}, "
                f"factors={len(existing_factors) + len(additional_factors)}, "
                f"action={ai_analysis.get('recommended_action', 'allow')}"
            )

            # Log detailed analysis if high risk
            if risk_score > 0.6:
                logger.warning(
                    f"High-risk authentication attempt detected for {user_id}: {reasoning}"
                )

            return {
                "score": risk_score,
                "factors": additional_factors,
                "reasoning": reasoning,
                "recommended_action": ai_analysis.get("recommended_action", "allow"),
            }

        except Exception as e:
            logger.warning(
                f"AI fraud detection failed for {user_id}, falling back to rule-based: {e}"
            )
            # Fallback to Core SDK rule-based assessment
            return await super()._ai_risk_assessment(
                user_id, risk_context, existing_factors
            )
