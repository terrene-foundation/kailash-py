# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 wiring: AzureEntra constructs via preset facade (#498 S6, MED-1).

Per `rules/facade-manager-detection.md` §2, `AzureEntra` is a
manager-shape class (stateful, token cache, refresh lock) and MUST
have a Tier 2 wiring file whose absence is grep-able.

Structural tests always run; live workload/managed-identity tests
gated on Azure env signals.
"""

from __future__ import annotations

import os

import pytest

from kaizen.llm.auth.azure import AzureEntra, COGNITIVE_SERVICES_SCOPE
from kaizen.llm.deployment import LlmDeployment


@pytest.mark.integration
def test_azure_openai_preset_composes_api_key_auth_structurally() -> None:
    """Structural: azure_openai preset accepts an api-key AzureEntra."""
    auth = LlmDeployment.azure_entra(api_key="test-key")
    d = LlmDeployment.azure_openai("my-openai-resource", "gpt-4o-prod", auth)
    assert isinstance(d.auth, AzureEntra)
    assert d.auth.auth_strategy_kind() == "azure_entra_api_key"


@pytest.mark.integration
def test_cognitive_services_scope_is_hardcoded_not_configurable() -> None:
    """The Entra audience scope must be the canonical cognitive-services scope."""
    assert COGNITIVE_SERVICES_SCOPE == ("https://cognitiveservices.azure.com/.default")


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("AZURE_OPENAI_API_KEY"),
    reason="Requires AZURE_OPENAI_API_KEY for live wiring check",
)
def test_azure_entra_api_key_live_header_install() -> None:
    """Live: api-key variant installs the header against a real request shape."""
    key = os.environ["AZURE_OPENAI_API_KEY"]
    auth = AzureEntra(api_key=key)
    req: dict = {"headers": {}}
    auth.apply(req)
    assert req["headers"]["api-key"] == key
