"""Regression: model defaults resolve from .env, never a hardcoded literal.

Issue #1825 — the env-models rule requires model names to come from the
environment (``OPENAI_PROD_MODEL`` -> ``DEFAULT_LLM_MODEL`` -> ``gpt-4o``), not
inline ``model="gpt-4"`` executable defaults. These tests pin the resolution
behaviour so a future edit that re-hardcodes a default fails loudly.
"""

from __future__ import annotations

import pytest

from kaizen_agents._model_env import resolve_default_model

pytestmark = pytest.mark.regression


def _clear_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_PROD_MODEL", raising=False)
    monkeypatch.delenv("DEFAULT_LLM_MODEL", raising=False)


def test_resolve_default_model_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. OPENAI_PROD_MODEL wins.
    monkeypatch.setenv("OPENAI_PROD_MODEL", "prod-model")
    monkeypatch.setenv("DEFAULT_LLM_MODEL", "fallback-model")
    assert resolve_default_model() == "prod-model"

    # 2. DEFAULT_LLM_MODEL when prod is unset.
    monkeypatch.delenv("OPENAI_PROD_MODEL", raising=False)
    assert resolve_default_model() == "fallback-model"

    # 3. gpt-4o final fallback when neither is set.
    _clear_model_env(monkeypatch)
    assert resolve_default_model() == "gpt-4o"


def test_agent_config_model_defaults_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from kaizen_agents.api.config import AgentConfig

    monkeypatch.setenv("OPENAI_PROD_MODEL", "config-env-model")
    assert AgentConfig().model == "config-env-model"
    # Never the retired hardcoded default.
    assert AgentConfig().model != "gpt-4"


def test_preset_model_defaults_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from kaizen_agents.api.presets import CapabilityPresets

    monkeypatch.setenv("OPENAI_PROD_MODEL", "preset-env-model")
    assert CapabilityPresets.qa_assistant()["model"] == "preset-env-model"
    assert CapabilityPresets.researcher()["model"] == "preset-env-model"


def test_code_reviewer_preset_is_provider_intrinsic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # code_reviewer is provider-intrinsic (Claude excels at review): it does NOT
    # follow the general resolver, and is overridable via KAIZEN_CODE_REVIEW_MODEL.
    from kaizen_agents.api.presets import CapabilityPresets

    monkeypatch.setenv("OPENAI_PROD_MODEL", "some-openai-model")
    monkeypatch.delenv("KAIZEN_CODE_REVIEW_MODEL", raising=False)
    assert CapabilityPresets.code_reviewer()["model"] == "claude-3-opus"

    monkeypatch.setenv("KAIZEN_CODE_REVIEW_MODEL", "claude-custom")
    assert CapabilityPresets.code_reviewer()["model"] == "claude-custom"


def test_get_recommended_configuration_defaults_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kaizen_agents.api.validation import get_recommended_configuration

    monkeypatch.setenv("OPENAI_PROD_MODEL", "reco-env-model")
    cfg = get_recommended_configuration("summarize this document")
    assert cfg["model"] == "reco-env-model"


def test_no_executable_hardcoded_gpt4_defaults() -> None:
    """Structural: no executable ``model: str = "gpt-4"`` / ``.get("model", "gpt-4")``
    default remains in kaizen_agents source (docstrings + carve-out constants excluded).
    """
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "src" / "kaizen_agents"
    pattern = re.compile(r'model:\s*str\s*=\s*"gpt|\.get\("model",\s*"gpt')
    offenders: list[str] = []
    for py in src.rglob("*.py"):
        for i, line in enumerate(py.read_text().splitlines(), 1):
            stripped = line.lstrip()
            if (
                stripped.startswith("#")
                or stripped.startswith("...")
                or "_DEFAULT" in line
            ):
                continue
            if pattern.search(line):
                offenders.append(f"{py.relative_to(src)}:{i}: {stripped}")
    assert not offenders, "executable hardcoded-model defaults found:\n" + "\n".join(
        offenders
    )
