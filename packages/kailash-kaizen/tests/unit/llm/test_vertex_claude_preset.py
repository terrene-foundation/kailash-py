# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shape tests for `LlmDeployment.vertex_claude(...)` (#498 S5).

Covers:

* Classmethod + module function both work, produce identical shape
* Default wire protocol is `AnthropicMessages` (Vertex-Claude speaks
  the Anthropic Messages schema)
* Endpoint host is `{region}-aiplatform.googleapis.com`
* Endpoint path embeds project + region + publisher + model
* Auth is `GcpOauth` with `auth_strategy_kind == "gcp_oauth"`
* `default_model` is the RESOLVED on-wire model id (post-grammar)
* `ModelRequired` raised on empty/missing model
* Project + region validated against strict regexes
* Registry parity: `vertex_claude` is registered in `_PRESETS`
* Cross-SDK: preset name string matches Rust literal byte-for-byte
"""

from __future__ import annotations

import logging

import pytest

from kaizen.llm.auth.gcp import GcpOauth
from kaizen.llm.deployment import Endpoint, LlmDeployment, WireProtocol
from kaizen.llm.errors import ModelRequired
from kaizen.llm.presets import (
    get_preset,
    list_presets,
    vertex_claude_preset,
)


def _service_account_dict() -> dict:
    return {
        "type": "service_account",
        "project_id": "my-test-project",
        "private_key_id": "k",
        "private_key": (
            "-----BEGIN PRIVATE KEY-----\nTESTKEY\n-----END PRIVATE KEY-----"
        ),
        "client_email": "sa@my-test-project.iam.gserviceaccount.com",
        "client_id": "i",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://x.example",
    }


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_vertex_claude_preset_shape() -> None:
    d = LlmDeployment.vertex_claude(
        _service_account_dict(),
        project="my-gcp-project-1234",
        region="us-central1",
        model="claude-3-opus",
    )
    assert isinstance(d, LlmDeployment)
    assert d.wire == WireProtocol.AnthropicMessages
    assert isinstance(d.endpoint, Endpoint)
    assert "us-central1-aiplatform.googleapis.com" in str(d.endpoint.base_url)
    assert (
        "/v1/projects/my-gcp-project-1234/locations/us-central1"
        in d.endpoint.path_prefix
    )
    assert (
        "/publishers/anthropic/models/claude-3-opus@20240229" in d.endpoint.path_prefix
    )
    assert d.default_model == "claude-3-opus@20240229"
    assert isinstance(d.auth, GcpOauth)
    assert d.auth.auth_strategy_kind() == "gcp_oauth"


def test_vertex_claude_preset_classmethod_matches_free_function() -> None:
    sa = _service_account_dict()
    classmethod_form = LlmDeployment.vertex_claude(
        sa,
        project="my-gcp-project-1234",
        region="europe-west4",
        model="claude-opus-4-5",
    )
    func_form = vertex_claude_preset(
        sa,
        project="my-gcp-project-1234",
        region="europe-west4",
        model="claude-opus-4-5",
    )
    assert classmethod_form.wire == func_form.wire
    assert classmethod_form.default_model == func_form.default_model
    assert str(classmethod_form.endpoint.base_url) == str(func_form.endpoint.base_url)
    assert classmethod_form.endpoint.path_prefix == func_form.endpoint.path_prefix


def test_vertex_claude_preset_region_is_reflected_in_endpoint() -> None:
    d = LlmDeployment.vertex_claude(
        _service_account_dict(),
        project="my-gcp-project-1234",
        region="asia-northeast1",
        model="claude-haiku-4-5",
    )
    assert "asia-northeast1-aiplatform.googleapis.com" in str(d.endpoint.base_url)
    assert "/locations/asia-northeast1" in d.endpoint.path_prefix


def test_vertex_claude_preset_stores_resolved_on_wire_model() -> None:
    """`default_model` is the grammar-resolved on-wire id, not the alias."""
    d = LlmDeployment.vertex_claude(
        _service_account_dict(),
        project="my-gcp-project-1234",
        region="us-central1",
        model="claude-3-5-sonnet",
    )
    assert d.default_model == "claude-3-5-sonnet@20240620"


def test_vertex_claude_preset_passes_through_already_versioned_model() -> None:
    d = LlmDeployment.vertex_claude(
        _service_account_dict(),
        project="my-gcp-project-1234",
        region="us-central1",
        model="claude-sonnet-4-6@20250101",
    )
    assert d.default_model == "claude-sonnet-4-6@20250101"


def test_vertex_claude_preset_accepts_path_string_for_service_account() -> None:
    d = LlmDeployment.vertex_claude(
        "/tmp/fake-sa.json",
        project="my-gcp-project-1234",
        region="us-central1",
        model="claude-3-opus",
    )
    assert isinstance(d.auth, GcpOauth)


# ---------------------------------------------------------------------------
# Validation -- project, region, model
# ---------------------------------------------------------------------------


def test_vertex_claude_preset_rejects_empty_project() -> None:
    with pytest.raises(ValueError, match=r"project"):
        LlmDeployment.vertex_claude(
            _service_account_dict(),
            project="",
            region="us-central1",
            model="claude-3-opus",
        )


def test_vertex_claude_preset_rejects_invalid_project_with_uppercase() -> None:
    """Project IDs are lowercase only."""
    with pytest.raises(ValueError, match=r"project"):
        LlmDeployment.vertex_claude(
            _service_account_dict(),
            project="MyProject",
            region="us-central1",
            model="claude-3-opus",
        )


def test_vertex_claude_preset_rejects_too_short_project() -> None:
    """Project IDs must be 6-30 chars."""
    with pytest.raises(ValueError, match=r"project"):
        LlmDeployment.vertex_claude(
            _service_account_dict(),
            project="abc",
            region="us-central1",
            model="claude-3-opus",
        )


def test_vertex_claude_preset_rejects_empty_region() -> None:
    with pytest.raises(ValueError, match=r"region"):
        LlmDeployment.vertex_claude(
            _service_account_dict(),
            project="my-gcp-project-1234",
            region="",
            model="claude-3-opus",
        )


def test_vertex_claude_preset_rejects_invalid_region_format() -> None:
    """Region must match `^[a-z]{2,20}-[a-z]+\\d{1,2}$`."""
    with pytest.raises(ValueError, match=r"region"):
        LlmDeployment.vertex_claude(
            _service_account_dict(),
            project="my-gcp-project-1234",
            region="not-a-region",
            model="claude-3-opus",
        )


def test_vertex_claude_preset_rejects_attacker_host_in_region() -> None:
    """A region that looks like a hostname fragment MUST be rejected -- the
    region is interpolated into the endpoint hostname."""
    with pytest.raises(ValueError, match=r"region"):
        LlmDeployment.vertex_claude(
            _service_account_dict(),
            project="my-gcp-project-1234",
            region="evil.attacker.com",
            model="claude-3-opus",
        )


def test_vertex_claude_preset_raises_model_required_on_empty_model() -> None:
    with pytest.raises(ModelRequired) as excinfo:
        LlmDeployment.vertex_claude(
            _service_account_dict(),
            project="my-gcp-project-1234",
            region="us-central1",
            model="",
        )
    assert excinfo.value.deployment_preset == "vertex_claude"
    assert excinfo.value.env_hint == "VERTEX_CLAUDE_MODEL_ID"


def test_vertex_claude_preset_rejects_unknown_model() -> None:
    from kaizen.llm.errors import ModelGrammarInvalid

    with pytest.raises(ModelGrammarInvalid):
        LlmDeployment.vertex_claude(
            _service_account_dict(),
            project="my-gcp-project-1234",
            region="us-central1",
            model="gpt-4o-mini",
        )


# ---------------------------------------------------------------------------
# Registry parity (cross-SDK)
# ---------------------------------------------------------------------------


def test_vertex_claude_registered_in_preset_registry() -> None:
    assert "vertex_claude" in list_presets()
    factory = get_preset("vertex_claude")
    assert factory is vertex_claude_preset


def test_vertex_claude_preset_name_matches_rust_literal() -> None:
    """`vertex_claude` MUST byte-match the Rust SDK literal for cross-SDK
    parity. Source: `kailash-rs/crates/kailash-kaizen/src/llm/deployment/
    presets.rs`."""
    assert "vertex_claude" in list_presets()


# ---------------------------------------------------------------------------
# Observability log shape
# ---------------------------------------------------------------------------


def test_vertex_claude_construction_emits_structured_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log fields canonical: deployment_preset, project, region, publisher,
    auth_strategy_kind, endpoint_host."""
    with caplog.at_level(logging.INFO, logger="kaizen.llm.presets"):
        LlmDeployment.vertex_claude(
            _service_account_dict(),
            project="my-gcp-project-1234",
            region="us-west1",
            model="claude-sonnet-4-6",
        )
    record = next(
        (
            r
            for r in caplog.records
            if r.name == "kaizen.llm.presets"
            and r.message == "llm.deployment.vertex_claude.constructed"
        ),
        None,
    )
    assert record is not None, "expected structured log line not emitted"
    assert record.deployment_preset == "vertex_claude"
    assert record.project == "my-gcp-project-1234"
    assert record.region == "us-west1"
    assert record.publisher == "anthropic"
    assert record.auth_strategy_kind == "gcp_oauth"
    assert record.endpoint_host == "us-west1-aiplatform.googleapis.com"


def test_vertex_claude_construction_does_not_log_service_account(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sa = _service_account_dict()
    secret_key_marker = sa["private_key"]
    with caplog.at_level(logging.DEBUG, logger="kaizen.llm.presets"):
        LlmDeployment.vertex_claude(
            sa,
            project="my-gcp-project-1234",
            region="us-central1",
            model="claude-3-opus",
        )
    for rec in caplog.records:
        assert secret_key_marker not in rec.getMessage()
        for val in getattr(rec, "__dict__", {}).values():
            assert secret_key_marker != val
