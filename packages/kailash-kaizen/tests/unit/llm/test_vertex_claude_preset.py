# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""vertex_claude_preset shape tests (#498 S5)."""

from __future__ import annotations

import pytest

from kaizen.llm.auth.gcp import GcpOauth
from kaizen.llm.deployment import Endpoint, LlmDeployment, WireProtocol
from kaizen.llm.errors import ModelRequired
from kaizen.llm.presets import vertex_claude_preset


SA_KEY = "/fake/service-account.json"


def test_vertex_claude_preset_shape() -> None:
    d = vertex_claude_preset(
        service_account_key=SA_KEY,
        project="my-project-1234",
        region="us-central1",
        model="claude-3-opus",
    )
    assert isinstance(d, LlmDeployment)
    assert d.wire == WireProtocol.AnthropicMessages
    assert isinstance(d.endpoint, Endpoint)
    assert str(d.endpoint.base_url).startswith(
        "https://us-central1-aiplatform.googleapis.com"
    )
    assert "projects/my-project-1234" in d.endpoint.path_prefix
    assert "publishers/anthropic" in d.endpoint.path_prefix
    assert d.default_model == "claude-3-opus@20240229"
    assert isinstance(d.auth, GcpOauth)


def test_vertex_claude_preset_classmethod_matches_free_function() -> None:
    cm_form = LlmDeployment.vertex_claude(
        SA_KEY, "my-project-1234", "us-central1", "claude-3-opus"
    )
    fn_form = vertex_claude_preset(
        SA_KEY, "my-project-1234", "us-central1", "claude-3-opus"
    )
    assert cm_form.wire == fn_form.wire
    assert cm_form.default_model == fn_form.default_model


def test_vertex_claude_preset_rejects_empty_model() -> None:
    with pytest.raises(ModelRequired):
        vertex_claude_preset(SA_KEY, "my-project-1234", "us-central1", "")


def test_vertex_claude_preset_rejects_empty_project() -> None:
    with pytest.raises(ValueError):
        vertex_claude_preset(SA_KEY, "", "us-central1", "claude-3-opus")


def test_vertex_claude_preset_rejects_malformed_project() -> None:
    # Starts with digit — rejected by regex.
    with pytest.raises(ValueError):
        vertex_claude_preset(SA_KEY, "1bad-project", "us-central1", "claude-3-opus")


def test_vertex_claude_preset_rejects_empty_region() -> None:
    with pytest.raises(ValueError):
        vertex_claude_preset(SA_KEY, "my-project-1234", "", "claude-3-opus")


def test_vertex_claude_preset_rejects_malformed_region() -> None:
    # Doesn't match `<area>-<locality><digit>`.
    with pytest.raises(ValueError):
        vertex_claude_preset(SA_KEY, "my-project-1234", "not_a_region", "claude-3-opus")


def test_vertex_claude_preset_rejects_unknown_model() -> None:
    from kaizen.llm.errors import ModelGrammarInvalid

    with pytest.raises(ModelGrammarInvalid):
        vertex_claude_preset(SA_KEY, "my-project-1234", "us-central1", "gpt-4")
