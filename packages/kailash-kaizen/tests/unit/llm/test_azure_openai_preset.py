# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""azure_openai preset shape tests (#498 S6)."""

from __future__ import annotations

import pytest

from kaizen.llm.auth.azure import AzureEntra
from kaizen.llm.deployment import Endpoint, LlmDeployment, WireProtocol
from kaizen.llm.presets import (
    AZURE_OPENAI_DEFAULT_API_VERSION,
    azure_openai_preset,
)


def _api_key_auth() -> AzureEntra:
    return AzureEntra(api_key="test-azure-api-key")


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_azure_openai_preset_shape() -> None:
    d = azure_openai_preset(
        resource_name="my-openai-resource",
        deployment_name="gpt-4o-prod",
        auth=_api_key_auth(),
    )
    assert isinstance(d, LlmDeployment)
    assert d.wire == WireProtocol.OpenAiChat
    assert isinstance(d.endpoint, Endpoint)
    assert str(d.endpoint.base_url).startswith(
        "https://my-openai-resource.openai.azure.com"
    )
    assert "deployments/gpt-4o-prod" in d.endpoint.path_prefix
    assert d.default_model == "gpt-4o-prod"
    assert isinstance(d.auth, AzureEntra)


def test_azure_openai_preset_classmethod_matches_free_function() -> None:
    cm = LlmDeployment.azure_openai(
        "my-openai-resource",
        "gpt-4o-prod",
        _api_key_auth(),
    )
    fn = azure_openai_preset(
        "my-openai-resource",
        "gpt-4o-prod",
        _api_key_auth(),
    )
    assert cm.wire == fn.wire
    assert cm.default_model == fn.default_model


def test_azure_openai_preset_rejects_empty_resource() -> None:
    with pytest.raises(ValueError):
        azure_openai_preset("", "gpt-4o", _api_key_auth())


def test_azure_openai_preset_rejects_malformed_resource() -> None:
    # Uppercase not allowed.
    with pytest.raises(ValueError):
        azure_openai_preset("My-Bad-Resource", "gpt-4o", _api_key_auth())
    # Leading digit not allowed.
    with pytest.raises(ValueError):
        azure_openai_preset("1badresource", "gpt-4o", _api_key_auth())


def test_azure_openai_preset_rejects_bad_deployment_name() -> None:
    from kaizen.llm.errors import ModelGrammarInvalid

    with pytest.raises(ModelGrammarInvalid):
        azure_openai_preset(
            "my-openai-resource",
            "has space",
            _api_key_auth(),
        )


def test_azure_openai_preset_rejects_non_azure_entra_auth() -> None:
    with pytest.raises(TypeError):
        azure_openai_preset(
            "my-openai-resource",
            "gpt-4o",
            auth="not-an-AzureEntra",  # type: ignore[arg-type]
        )


def test_azure_openai_preset_api_version_defaults_pinned() -> None:
    """Default api-version is the cross-SDK pinned constant."""
    assert AZURE_OPENAI_DEFAULT_API_VERSION == "2024-06-01"


def test_azure_openai_preset_accepts_explicit_api_version() -> None:
    # This succeeds silently; api_version is carried implicitly for now.
    d = azure_openai_preset(
        "my-openai-resource",
        "gpt-4o",
        _api_key_auth(),
        api_version="2024-10-21",
    )
    assert isinstance(d, LlmDeployment)


def test_azure_openai_preset_rejects_empty_api_version() -> None:
    with pytest.raises(ValueError):
        azure_openai_preset(
            "my-openai-resource",
            "gpt-4o",
            _api_key_auth(),
            api_version="",
        )


# ---------------------------------------------------------------------------
# LlmDeployment.azure_entra classmethod
# ---------------------------------------------------------------------------


def test_azure_entra_classmethod_returns_auth_instance() -> None:
    """`LlmDeployment.azure_entra(...)` returns an AzureEntra, not a deployment.

    Matches Rust SDK shape: auth + deployment constructed separately.
    """
    auth = LlmDeployment.azure_entra(api_key="test-k")
    assert isinstance(auth, AzureEntra)
    assert auth.auth_strategy_kind() == "azure_entra_api_key"
