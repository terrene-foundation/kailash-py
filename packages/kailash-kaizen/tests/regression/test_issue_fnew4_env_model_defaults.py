"""FNEW-4 regression — AI-enhanced nodes resolve models from env, never hardcode.

The auth/security AI node family previously shipped hardcoded constructor
defaults (``ai_model="gpt-4o-mini"`` / ``model="gpt-4o-mini"`` and
``provider="openai"``), violating ``rules/env-models.md`` (model identifiers
MUST come from ``.env``; hardcoded literals lock deployments to a single
provider). All five constructors now resolve through
``kaizen.nodes._env_model.resolve_default_model`` (caller arg wins, else
``KAIZEN_DEFAULT_MODEL``, else a typed ``EnvModelMissing``) and auto-detect
the provider from the resolved model via ``detect_provider``.

Env-var isolation (rules/testing.md § Env-Var Test Isolation MUST): tests that
mutate KAIZEN_DEFAULT_MODEL via monkeypatch acquire the module-scope
``_ENV_LOCK`` via the ``_env_serialized`` fixture so xdist-parallel runs
cannot race.
"""

import threading
from typing import Iterator

import pytest

from kaizen.errors import EnvModelMissing
from kaizen.nodes._env_model import detect_provider, resolve_default_model
from kaizen.nodes.auth.directory_integration import DirectoryIntegrationNode
from kaizen.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode
from kaizen.nodes.auth.sso import SSOAuthenticationNode
from kaizen.nodes.compliance.gdpr import GDPRComplianceNode
from kaizen.nodes.security.ai_behavior_analysis import AIBehaviorAnalysisNode
from kaizen.nodes.security.ai_threat_detection import AIThreatDetectionNode

# Module-scope env lock per rules/testing.md.
_ENV_LOCK = threading.Lock()


@pytest.fixture
def _env_serialized() -> Iterator[None]:
    with _ENV_LOCK:
        yield


# (constructor, model-kwarg name, attribute carrying the resolved model,
#  attribute carrying the resolved provider)
NODE_CASES = [
    pytest.param(
        SSOAuthenticationNode, "ai_model", "ai_model", "ai_provider", id="sso"
    ),
    pytest.param(
        DirectoryIntegrationNode,
        "ai_model",
        "ai_model",
        "ai_provider",
        id="directory_integration",
    ),
    pytest.param(
        EnterpriseAuthProviderNode,
        "ai_model",
        "ai_model",
        "ai_provider",
        id="enterprise_auth_provider",
    ),
    pytest.param(
        AIThreatDetectionNode, "model", "model", "provider", id="ai_threat_detection"
    ),
    pytest.param(
        AIBehaviorAnalysisNode, "model", "model", "provider", id="ai_behavior_analysis"
    ),
]


@pytest.mark.regression
@pytest.mark.parametrize("node_cls, kwarg, model_attr, provider_attr", NODE_CASES)
def test_unset_env_and_no_arg_raises_env_model_missing(
    node_cls,
    kwarg,
    model_attr,
    provider_attr,
    monkeypatch: pytest.MonkeyPatch,
    _env_serialized: None,
):
    monkeypatch.delenv("KAIZEN_DEFAULT_MODEL", raising=False)
    with pytest.raises(EnvModelMissing) as excinfo:
        node_cls()
    # Message names the env var — one actionable instruction for the user.
    assert "KAIZEN_DEFAULT_MODEL" in str(excinfo.value)


@pytest.mark.regression
@pytest.mark.parametrize("node_cls, kwarg, model_attr, provider_attr", NODE_CASES)
def test_env_var_resolves_model_and_provider(
    node_cls,
    kwarg,
    model_attr,
    provider_attr,
    monkeypatch: pytest.MonkeyPatch,
    _env_serialized: None,
):
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "claude-sonnet-test")
    node = node_cls()
    assert getattr(node, model_attr) == "claude-sonnet-test"
    # Provider auto-detected from the env-resolved model — a hardcoded
    # "openai" default here would mismatch the claude-* model.
    assert getattr(node, provider_attr) == "anthropic"


@pytest.mark.regression
@pytest.mark.parametrize("node_cls, kwarg, model_attr, provider_attr", NODE_CASES)
def test_explicit_model_arg_wins_over_env(
    node_cls,
    kwarg,
    model_attr,
    provider_attr,
    monkeypatch: pytest.MonkeyPatch,
    _env_serialized: None,
):
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "claude-sonnet-test")
    node = node_cls(**{kwarg: "gpt-4o-custom"})
    assert getattr(node, model_attr) == "gpt-4o-custom"
    assert getattr(node, provider_attr) == "openai"


@pytest.mark.regression
def test_explicit_provider_wins_over_auto_detect(
    monkeypatch: pytest.MonkeyPatch,
    _env_serialized: None,
):
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "claude-sonnet-test")
    node = AIThreatDetectionNode(provider="ollama")
    assert node.provider == "ollama"


@pytest.mark.regression
def test_resolve_default_model_helper_contract(
    monkeypatch: pytest.MonkeyPatch,
    _env_serialized: None,
):
    monkeypatch.delenv("KAIZEN_DEFAULT_MODEL", raising=False)
    with pytest.raises(EnvModelMissing):
        resolve_default_model("HelperContractTest")
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "gpt-test")
    assert resolve_default_model("HelperContractTest") == "gpt-test"
    assert resolve_default_model("HelperContractTest", "claude-x") == "claude-x"


@pytest.mark.regression
def test_gdpr_unset_env_raises_only_when_ai_analysis_enabled(
    monkeypatch: pytest.MonkeyPatch, _env_serialized: None
):
    monkeypatch.delenv("KAIZEN_DEFAULT_MODEL", raising=False)
    with pytest.raises(EnvModelMissing):
        GDPRComplianceNode()
    # AI path disabled -> no model needed, no raise.
    node = GDPRComplianceNode(ai_analysis=False)
    assert node.ai_model is None
    assert node.ai_agent is None


@pytest.mark.regression
def test_gdpr_env_resolution_and_ollama_prefix(
    monkeypatch: pytest.MonkeyPatch, _env_serialized: None
):
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "claude-sonnet-test")
    node = GDPRComplianceNode()
    assert node.ai_model == "claude-sonnet-test"
    assert node.ai_agent is not None
    # Explicit "ollama:<model>" prefix still pins the ollama provider.
    pinned = GDPRComplianceNode(ai_model="ollama:llama3.2:3b")
    assert pinned.ai_model == "ollama:llama3.2:3b"
    assert pinned.ai_agent is not None


@pytest.mark.regression
def test_llm_router_default_model_env_resolution(
    monkeypatch: pytest.MonkeyPatch, _env_serialized: None
):
    from kaizen.llm.routing.router import LLMRouter

    monkeypatch.delenv("KAIZEN_DEFAULT_MODEL", raising=False)
    with pytest.raises(EnvModelMissing):
        LLMRouter()
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "claude-sonnet-test")
    assert LLMRouter().default_model == "claude-sonnet-test"
    assert LLMRouter(default_model="gpt-4o-custom").default_model == "gpt-4o-custom"


@pytest.mark.regression
def test_kaizen_node_model_env_resolution(
    monkeypatch: pytest.MonkeyPatch, _env_serialized: None
):
    from kaizen.nodes.base import KaizenNode

    monkeypatch.delenv("KAIZEN_DEFAULT_MODEL", raising=False)
    with pytest.raises(EnvModelMissing):
        KaizenNode()
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "claude-sonnet-test")
    assert KaizenNode().model == "claude-sonnet-test"
    assert KaizenNode(model="gpt-4o-custom").model == "gpt-4o-custom"


@pytest.mark.regression
def test_detect_provider_family_convention():
    assert detect_provider("gpt-4o-mini") == "openai"
    assert detect_provider("o1-preview") == "openai"
    assert detect_provider("claude-sonnet-4-6") == "anthropic"
    assert detect_provider("llama3.2:3b") == "ollama"
    assert detect_provider("mistral-large") == "ollama"
    assert detect_provider("gemini-2.0-flash") == "google"


@pytest.mark.regression
def test_detect_provider_unrecognized_model_raises_typed_error():
    """Fail-closed: an unrecognized model MUST NOT silently route to the
    mock provider in production node ctors (security fail-open class).
    Explicit provider="mock" remains the test opt-in."""
    from kaizen.errors import ProviderUndetectable

    with pytest.raises(ProviderUndetectable) as excinfo:
        detect_provider("some-unknown-model", "RegressionProbe")
    msg = str(excinfo.value)
    assert "some-unknown-model" in msg
    assert "provider=" in msg  # actionable instruction


@pytest.mark.regression
def test_unrecognized_env_model_raises_at_node_construction(
    monkeypatch: pytest.MonkeyPatch, _env_serialized: None
):
    from kaizen.errors import ProviderUndetectable

    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "totally-unknown-model")
    with pytest.raises(ProviderUndetectable):
        AIThreatDetectionNode()
    # Explicit provider opt-out still constructs.
    node = AIThreatDetectionNode(provider="mock")
    assert node.provider == "mock"
