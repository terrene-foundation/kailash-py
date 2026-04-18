# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""LlmDeployment.openai() shape tests (#498 S2).

Note: `model` is REQUIRED per rules/env-models.md — tests pass an explicit
model string rather than relying on a default.
"""

from __future__ import annotations

import pytest

from kaizen.llm.auth.bearer import ApiKeyBearer, ApiKeyHeaderKind
from kaizen.llm.deployment import Endpoint, LlmDeployment, WireProtocol
from kaizen.llm.presets import openai_preset


def test_openai_preset_shape() -> None:
    d = LlmDeployment.openai("sk-test", model="gpt-4o-mini")
    assert isinstance(d, LlmDeployment)
    assert d.wire == WireProtocol.OpenAiChat
    assert isinstance(d.endpoint, Endpoint)
    # base_url is HttpUrl — stringify for compare
    assert str(d.endpoint.base_url).startswith("https://api.openai.com")
    assert d.endpoint.path_prefix == "/v1"
    assert d.default_model == "gpt-4o-mini"
    assert isinstance(d.auth, ApiKeyBearer)
    assert d.auth.kind == ApiKeyHeaderKind.Authorization_Bearer


def test_openai_preset_classmethod_matches_free_function() -> None:
    """Both `LlmDeployment.openai(...)` and `openai_preset(...)` are legal."""
    classmethod_form = LlmDeployment.openai("sk-test", model="gpt-4o-mini")
    func_form = openai_preset("sk-test", model="gpt-4o-mini")
    assert classmethod_form.wire == func_form.wire
    assert classmethod_form.default_model == func_form.default_model
    assert str(classmethod_form.endpoint.base_url) == str(func_form.endpoint.base_url)


def test_openai_preset_rejects_empty_api_key() -> None:
    with pytest.raises(ValueError):
        LlmDeployment.openai("", model="gpt-4o-mini")


def test_openai_preset_rejects_none_api_key() -> None:
    with pytest.raises((ValueError, TypeError)):
        LlmDeployment.openai(None, model="gpt-4o-mini")  # type: ignore[arg-type]


def test_openai_preset_rejects_empty_model() -> None:
    """Empty model violates env-models.md — preset raises with actionable message."""
    with pytest.raises(ValueError, match=r"OPENAI_PROD_MODEL"):
        LlmDeployment.openai("sk-test", model="")


def test_openai_preset_rejects_missing_model_positional() -> None:
    """model is a required positional — omitting it is a TypeError."""
    with pytest.raises(TypeError):
        LlmDeployment.openai("sk-test")  # type: ignore[call-arg]


def test_llm_deployment_is_frozen() -> None:
    d = LlmDeployment.openai("sk-test", model="gpt-4o-mini")
    with pytest.raises((ValueError, TypeError)):
        d.wire = WireProtocol.AnthropicMessages  # type: ignore[misc]


def test_deferred_presets_raise_not_implemented() -> None:
    """Every non-openai preset must raise with a session marker."""
    with pytest.raises(NotImplementedError, match=r"session"):
        LlmDeployment.anthropic("k")
    with pytest.raises(NotImplementedError, match=r"session"):
        LlmDeployment.bedrock_claude("k")
    with pytest.raises(NotImplementedError, match=r"session"):
        LlmDeployment.azure_entra("k")
