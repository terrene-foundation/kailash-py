"""Regression: F31-FU4 — wrong-shape-adapter false-greens masked real
production parse defects.

Production LLMAgentNode publishes its result envelope with "response" as a
NESTED dict: ``{"success": True, "response": {"content": ..., "role": ...},
...}`` (src/kaizen/nodes/ai/llm_agent.py:995; docstring :586). The FU4 audit
(2026-06-10, 55 doubles across 26 non-RAG test files) confirmed three test
doubles publishing shapes production never emits, two of which masked real
production defects:

1. ``Agent.communicate_with`` (src/kaizen/core/agents.py) str()'d the nested
   response dict — agent-to-agent messages and conversation history carried
   dict reprs instead of the response text.
2. ``EnterpriseAuthProviderNode._ai_risk_assessment``
   (src/kaizen/nodes/auth/enterprise_auth_provider.py) read
   ``result.get("content")`` — the key-miss yielded "{}" so every AI-path
   risk assessment silently returned score 0.0 / "allow" (fail-open; AI
   fraud detection disabled in production).
3. ``SSOAuthenticationNode`` AI-path tests routed through the rule-based
   fallback via wrong-shape envelopes (production parse was correct).

These tests feed the DOCS-EXACT production envelope through each fixed path.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from tests.fixtures.consolidated_test_fixtures import consolidated_fixtures

PRODUCTION_TEXT = "Hello from agent B"


@pytest.fixture(autouse=True)
def _default_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Framework/node creation resolves the model from the environment;
    supply a deterministic unit-tier value (issue-822 pattern)."""
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")


def _production_envelope(content: str) -> dict:
    """The LLMAgentNode result envelope (llm_agent.py:993-1012)."""
    return {
        "success": True,
        "response": {"content": content, "role": "assistant"},
    }


@pytest.mark.regression
@patch("kailash.runtime.local.LocalRuntime.execute")
def test_communicate_with_extracts_content_from_production_envelope(mock_execute):
    """communicate_with must return the response TEXT, never the dict repr."""
    import kaizen

    mock_execute.return_value = (
        {"comm_response_agent_b": _production_envelope(PRODUCTION_TEXT)},
        "test_run_id",
    )

    config = consolidated_fixtures.get_configuration("minimal")
    framework = kaizen.Framework(config=config)
    agent_a = framework.create_agent(config={"name": "agent_a", "role": "analyst"})
    agent_b = framework.create_agent(config={"name": "agent_b", "role": "researcher"})

    response = agent_a.communicate_with(
        target_agent=agent_b, message="What's your analysis?", context={}
    )

    # Equality, not substring: the pre-fix dict repr CONTAINED the text,
    # so a substring assertion would false-green.
    assert response["message"] == PRODUCTION_TEXT
    # Conversation history must carry the text too (agents.py history entry)
    history = agent_a._conversation_history["agent_b"]
    assert history[-1]["response"] == PRODUCTION_TEXT


@pytest.mark.regression
def test_communicate_with_still_accepts_legacy_flat_string():
    """Dual-shape contract: a legacy flat-string response still extracts."""
    import kaizen

    with patch("kailash.runtime.local.LocalRuntime.execute") as mock_execute:
        mock_execute.return_value = (
            {"comm_response_agent_b": {"response": PRODUCTION_TEXT}},
            "test_run_id",
        )
        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)
        agent_a = framework.create_agent(config={"name": "agent_a", "role": "analyst"})
        agent_b = framework.create_agent(
            config={"name": "agent_b", "role": "researcher"}
        )

        response = agent_a.communicate_with(
            target_agent=agent_b, message="ping", context={}
        )
        assert response["message"] == PRODUCTION_TEXT


@pytest.mark.regression
@pytest.mark.asyncio
async def test_enterprise_auth_ai_risk_parses_production_envelope():
    """AI risk assessment must parse the nested envelope — pre-fix it
    silently returned score 0.0/'allow' for EVERY production response."""
    from kaizen.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode()
    analysis = {
        "risk_score": 0.95,
        "additional_factors": ["credential_stuffing"],
        "reasoning": "High-velocity failures from anonymized IP",
        "recommended_action": "block",
    }
    node.llm_agent.async_run = AsyncMock(
        return_value=_production_envelope(json.dumps(analysis))
    )

    result = await node._ai_risk_assessment(
        "user@company.com", {"ip_address": "203.0.113.42"}, []
    )

    assert result["score"] == 0.95
    assert result["recommended_action"] == "block"
    assert result["factors"] == ["credential_stuffing"]


@pytest.mark.regression
@pytest.mark.asyncio
async def test_enterprise_auth_malformed_envelope_fails_closed_to_rule_based():
    """A malformed envelope (the OLD flat shape) must route to the
    rule-based fallback — never the silent 0.0/'allow' default."""
    from kailash.nodes.auth.enterprise_auth_provider import (
        EnterpriseAuthProviderNode as CoreEnterpriseAuthNode,
    )

    from kaizen.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    node = EnterpriseAuthProviderNode()
    # The OLD wrong shape: flat top-level "content", no nested response
    node.llm_agent.async_run = AsyncMock(
        return_value={"content": json.dumps({"risk_score": 0.95})}
    )

    sentinel = {
        "score": 0.42,
        "factors": ["rule_based_sentinel"],
        "reasoning": "rule-based fallback engaged",
        "recommended_action": "require_additional_verification",
    }
    with patch.object(
        CoreEnterpriseAuthNode,
        "_ai_risk_assessment",
        new=AsyncMock(return_value=sentinel),
    ):
        result = await node._ai_risk_assessment(
            "user@company.com", {"ip_address": "203.0.113.42"}, []
        )

    # Fallback engaged — NOT the fail-open silent default (0.0/"allow")
    assert result == sentinel


@pytest.mark.regression
@pytest.mark.asyncio
async def test_directory_security_settings_parse_production_envelope():
    """R1 security-reviewer sibling sweep: directory_integration.py carried
    the same flat-shape parse at 4 sites — _ai_security_settings is the
    security-relevant one (AI-driven MFA tightening was silently dead)."""
    from kaizen.nodes.auth.directory_integration import DirectoryIntegrationNode

    node = DirectoryIntegrationNode()
    node.llm_agent.async_run = AsyncMock(
        return_value=_production_envelope(
            json.dumps(
                {
                    "mfa_required": True,
                    "password_expiry_days": 60,
                    "session_timeout_minutes": 240,
                }
            )
        )
    )

    settings = await node._ai_security_settings(
        {"job_title": "Infrastructure Admin", "groups": ["admin"]}
    )

    # Pre-fix: every production envelope key-missed -> "{}" -> settings == {}
    # and the AI's MFA escalation never fired.
    assert settings["mfa_required"] is True
    assert settings["password_expiry_days"] == 60


@pytest.mark.regression
@pytest.mark.asyncio
async def test_directory_security_settings_malformed_envelope_fails_closed():
    """A malformed envelope (the OLD flat shape) must engage the documented
    safe-defaults fallback — never the silent empty dict."""
    from kaizen.nodes.auth.directory_integration import DirectoryIntegrationNode

    node = DirectoryIntegrationNode()
    node.llm_agent.async_run = AsyncMock(
        return_value={"content": json.dumps({"mfa_required": True})}
    )

    settings = await node._ai_security_settings({"job_title": "Admin"})

    # The documented except-branch fallback, not {} (pre-fix) and not the
    # attacker-influencable parsed value.
    assert settings == {
        "mfa_required": False,
        "password_expiry_days": 90,
        "session_timeout_minutes": 480,
    }


@pytest.mark.regression
@pytest.mark.asyncio
async def test_directory_role_assignment_parses_production_envelope_and_fails_closed():
    """_ai_role_assignment: production envelope parses; malformed envelope
    engages the documented least-privilege ["user"] fallback."""
    from kaizen.nodes.auth.directory_integration import DirectoryIntegrationNode

    node = DirectoryIntegrationNode()
    node.llm_agent.async_run = AsyncMock(
        return_value=_production_envelope(json.dumps(["user", "developer"]))
    )
    roles = await node._ai_role_assignment(
        {"email": "dev@company.com", "job_title": "Engineer"}
    )
    assert roles == ["user", "developer"]

    node.llm_agent.async_run = AsyncMock(
        return_value={"content": json.dumps(["admin"])}  # OLD flat shape
    )
    fallback_roles = await node._ai_role_assignment(
        {"email": "dev@company.com", "job_title": "Engineer"}
    )
    # Least-privilege fallback — the flat shape must never grant "admin".
    assert fallback_roles == ["user"]


class _EnvelopeLLMAgentNodeStub:
    """Stands in for the module-level LLMAgentNode the security nodes
    instantiate inside their _call_llm_* methods."""

    return_value: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    def execute(self, *args, **kwargs):
        return type(self).return_value


@pytest.mark.regression
def test_threat_detection_parses_production_envelope_and_fails_closed(monkeypatch):
    """R2 security sweep sibling: ai_threat_detection.py read the flat shape —
    AI threat intelligence was silently dead (dict.split AttributeError
    swallowed by the except)."""
    import kaizen.nodes.security.ai_threat_detection as td_mod

    monkeypatch.setattr(td_mod, "LLMAgentNode", _EnvelopeLLMAgentNodeStub)
    node = td_mod.AIThreatDetectionNode()

    text = "Narrative.\nThreat Intelligence: lateral movement suspected."
    _EnvelopeLLMAgentNodeStub.return_value = _production_envelope(text)
    out = node._call_llm_for_intelligence({"threats": []}, [])
    assert out["ai_available"] is True
    assert out["narrative"] == text
    assert out["intelligence"] == {"analysis": "lateral movement suspected."}

    # Malformed (OLD flat) envelope -> documented ai_available=False degrade
    _EnvelopeLLMAgentNodeStub.return_value = {"success": True, "response": text}
    out2 = node._call_llm_for_intelligence({"threats": []}, [])
    # flat STRING is the legacy-tolerated shape and still parses
    assert out2["ai_available"] is True
    _EnvelopeLLMAgentNodeStub.return_value = {"success": True, "response": {}}
    out3 = node._call_llm_for_intelligence({"threats": []}, [])
    assert out3["ai_available"] is False
    assert "error" in out3


@pytest.mark.regression
def test_behavior_analysis_parses_production_envelope_and_fails_closed(monkeypatch):
    """Same sibling class in ai_behavior_analysis.py."""
    import kaizen.nodes.security.ai_behavior_analysis as ba_mod

    monkeypatch.setattr(ba_mod, "LLMAgentNode", _EnvelopeLLMAgentNodeStub)
    node = ba_mod.AIBehaviorAnalysisNode()

    text = "Explanation.\nResponse Recommendations:\n- rotate credentials"
    _EnvelopeLLMAgentNodeStub.return_value = _production_envelope(text)
    out = node._call_llm_for_analysis({}, [], {})
    assert out["ai_available"] is True
    assert out["explanation"] == text
    assert out["recommendations"] == ["rotate credentials"]

    _EnvelopeLLMAgentNodeStub.return_value = {"success": True, "response": {}}
    out2 = node._call_llm_for_analysis({}, [], {})
    assert out2["ai_available"] is False
    assert "error" in out2


@pytest.mark.regression
def test_gdpr_ai_compliance_parses_production_envelope_and_fails_closed():
    """Same sibling class in compliance/gdpr.py — AI compliance analysis
    returned None on every production envelope (json.loads(dict) TypeError
    swallowed)."""
    from unittest.mock import Mock

    from kaizen.nodes.compliance.gdpr import GDPRComplianceNode

    node = GDPRComplianceNode(ai_analysis=True)
    analysis = {
        "risk_level": "high",
        "legal_implications": ["Art. 32"],
        "best_practices": [],
        "remediation_steps": ["encrypt at rest"],
        "additional_insights": [],
    }
    node.ai_agent = Mock()
    node.ai_agent.execute = Mock(
        return_value=_production_envelope(json.dumps(analysis))
    )

    out = node._ai_analyze_compliance({}, "user_record", [], [], [])
    assert out is not None
    assert out["risk_level"] == "high"
    assert out["remediation_steps"] == ["encrypt at rest"]

    # Malformed envelope -> documented None degrade (never a parsed value)
    node.ai_agent.execute = Mock(return_value={"success": True, "response": {}})
    assert node._ai_analyze_compliance({}, "user_record", [], [], []) is None


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sso_ai_field_mapping_exercises_ai_path_with_production_envelope():
    """SSO AI field mapping under the production envelope surfaces the
    AI-mapped fields — the rule-based fallback would yield None for these."""
    from kaizen.nodes.auth.sso import SSOAuthenticationNode

    node = SSOAuthenticationNode()
    node.llm_agent.async_run = AsyncMock(
        return_value=_production_envelope(
            json.dumps(
                {"first_name": "Test", "last_name": "User", "email": "test@azure.com"}
            )
        )
    )

    result = await node._ai_field_mapping({"email": "test@azure.com"}, "azure")

    assert result["first_name"] == "Test"
    assert result["last_name"] == "User"
    assert result["email"] == "test@azure.com"
