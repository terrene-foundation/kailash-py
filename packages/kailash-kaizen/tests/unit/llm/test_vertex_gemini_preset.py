# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""vertex_gemini_preset shape tests (#498 S5)."""

from __future__ import annotations

import pytest

from kaizen.llm.auth.gcp import GcpOauth
from kaizen.llm.deployment import Endpoint, LlmDeployment, WireProtocol
from kaizen.llm.errors import ModelRequired
from kaizen.llm.presets import vertex_gemini_preset


SA_KEY = "/fake/service-account.json"


def test_vertex_gemini_preset_shape() -> None:
    d = vertex_gemini_preset(
        service_account_key=SA_KEY,
        project="my-project-1234",
        region="us-central1",
        model="gemini-1.5-pro",
    )
    assert isinstance(d, LlmDeployment)
    assert d.wire == WireProtocol.VertexGenerateContent
    assert isinstance(d.endpoint, Endpoint)
    assert str(d.endpoint.base_url).startswith(
        "https://us-central1-aiplatform.googleapis.com"
    )
    assert "publishers/google" in d.endpoint.path_prefix
    assert d.default_model == "gemini-1.5-pro"
    assert isinstance(d.auth, GcpOauth)


def test_vertex_gemini_preset_classmethod_matches_free_function() -> None:
    cm = LlmDeployment.vertex_gemini(
        SA_KEY, "my-project-1234", "us-central1", "gemini-1.5-pro"
    )
    fn = vertex_gemini_preset(
        SA_KEY, "my-project-1234", "us-central1", "gemini-1.5-pro"
    )
    assert cm.wire == fn.wire
    assert cm.default_model == fn.default_model


def test_vertex_gemini_preset_rejects_empty_model() -> None:
    with pytest.raises(ModelRequired):
        vertex_gemini_preset(SA_KEY, "my-project-1234", "us-central1", "")


def test_vertex_gemini_preset_rejects_empty_project() -> None:
    with pytest.raises(ValueError):
        vertex_gemini_preset(SA_KEY, "", "us-central1", "gemini-1.5-pro")


def test_vertex_gemini_preset_rejects_malformed_region() -> None:
    with pytest.raises(ValueError):
        vertex_gemini_preset(SA_KEY, "my-project-1234", "bad_region", "gemini-1.5-pro")


def test_vertex_gemini_preset_accepts_multiple_canonical_models() -> None:
    for model in ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash"]:
        d = vertex_gemini_preset(SA_KEY, "my-project-1234", "us-central1", model)
        assert d.default_model == model
