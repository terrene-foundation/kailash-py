# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shape tests for `LlmDeployment.vertex_gemini(...)` (#498 S5).

Covers:

* Classmethod + module function both work, produce identical shape
* Wire protocol is `VertexGenerateContent`
* Endpoint host is `{region}-aiplatform.googleapis.com`
* Endpoint path embeds project + region + publisher (`google`) + model
* Auth is `GcpOauth` with `auth_strategy_kind == "gcp_oauth"`
* `default_model` is the resolved on-wire model id
* `ModelRequired` raised on empty/missing model
* Project + region validated against strict regexes
* Registry parity: `vertex_gemini` is registered in `_PRESETS`
"""

from __future__ import annotations

import logging

import pytest

from kaizen.llm.auth.gcp import GcpOauth
from kaizen.llm.deployment import Endpoint, LlmDeployment, WireProtocol
from kaizen.llm.errors import ModelRequired
from kaizen.llm.presets import get_preset, list_presets, vertex_gemini_preset


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


def test_vertex_gemini_preset_shape() -> None:
    d = LlmDeployment.vertex_gemini(
        _service_account_dict(),
        project="my-gcp-project-1234",
        region="us-central1",
        model="gemini-1.5-pro",
    )
    assert isinstance(d, LlmDeployment)
    assert d.wire == WireProtocol.VertexGenerateContent
    assert isinstance(d.endpoint, Endpoint)
    assert "us-central1-aiplatform.googleapis.com" in str(d.endpoint.base_url)
    assert (
        "/v1/projects/my-gcp-project-1234/locations/us-central1"
        in d.endpoint.path_prefix
    )
    assert "/publishers/google/models/gemini-1.5-pro" in d.endpoint.path_prefix
    assert d.default_model == "gemini-1.5-pro"
    assert isinstance(d.auth, GcpOauth)
    assert d.auth.auth_strategy_kind() == "gcp_oauth"


def test_vertex_gemini_preset_classmethod_matches_free_function() -> None:
    sa = _service_account_dict()
    classmethod_form = LlmDeployment.vertex_gemini(
        sa,
        project="my-gcp-project-1234",
        region="europe-west4",
        model="gemini-2.0-flash",
    )
    func_form = vertex_gemini_preset(
        sa,
        project="my-gcp-project-1234",
        region="europe-west4",
        model="gemini-2.0-flash",
    )
    assert classmethod_form.wire == func_form.wire
    assert classmethod_form.default_model == func_form.default_model
    assert str(classmethod_form.endpoint.base_url) == str(func_form.endpoint.base_url)
    assert classmethod_form.endpoint.path_prefix == func_form.endpoint.path_prefix


def test_vertex_gemini_preset_region_is_reflected_in_endpoint() -> None:
    d = LlmDeployment.vertex_gemini(
        _service_account_dict(),
        project="my-gcp-project-1234",
        region="asia-northeast1",
        model="gemini-1.5-flash",
    )
    assert "asia-northeast1-aiplatform.googleapis.com" in str(d.endpoint.base_url)
    assert "/locations/asia-northeast1" in d.endpoint.path_prefix


def test_vertex_gemini_preset_passes_through_native_id() -> None:
    """Any `gemini-*` id passes through unchanged into the URL path."""
    d = LlmDeployment.vertex_gemini(
        _service_account_dict(),
        project="my-gcp-project-1234",
        region="us-central1",
        model="gemini-2.0-flash-exp",
    )
    assert d.default_model == "gemini-2.0-flash-exp"
    assert "/publishers/google/models/gemini-2.0-flash-exp" in d.endpoint.path_prefix


def test_vertex_gemini_preset_accepts_path_string_for_service_account() -> None:
    d = LlmDeployment.vertex_gemini(
        "/tmp/fake-sa.json",
        project="my-gcp-project-1234",
        region="us-central1",
        model="gemini-1.5-pro",
    )
    assert isinstance(d.auth, GcpOauth)


# ---------------------------------------------------------------------------
# Validation -- project, region, model
# ---------------------------------------------------------------------------


def test_vertex_gemini_preset_rejects_empty_project() -> None:
    with pytest.raises(ValueError, match=r"project"):
        LlmDeployment.vertex_gemini(
            _service_account_dict(),
            project="",
            region="us-central1",
            model="gemini-1.5-pro",
        )


def test_vertex_gemini_preset_rejects_invalid_project_with_uppercase() -> None:
    with pytest.raises(ValueError, match=r"project"):
        LlmDeployment.vertex_gemini(
            _service_account_dict(),
            project="MyProject",
            region="us-central1",
            model="gemini-1.5-pro",
        )


def test_vertex_gemini_preset_rejects_empty_region() -> None:
    with pytest.raises(ValueError, match=r"region"):
        LlmDeployment.vertex_gemini(
            _service_account_dict(),
            project="my-gcp-project-1234",
            region="",
            model="gemini-1.5-pro",
        )


def test_vertex_gemini_preset_rejects_invalid_region_format() -> None:
    with pytest.raises(ValueError, match=r"region"):
        LlmDeployment.vertex_gemini(
            _service_account_dict(),
            project="my-gcp-project-1234",
            region="not-a-region",
            model="gemini-1.5-pro",
        )


def test_vertex_gemini_preset_rejects_attacker_host_in_region() -> None:
    with pytest.raises(ValueError, match=r"region"):
        LlmDeployment.vertex_gemini(
            _service_account_dict(),
            project="my-gcp-project-1234",
            region="evil.attacker.com",
            model="gemini-1.5-pro",
        )


def test_vertex_gemini_preset_raises_model_required_on_empty_model() -> None:
    with pytest.raises(ModelRequired) as excinfo:
        LlmDeployment.vertex_gemini(
            _service_account_dict(),
            project="my-gcp-project-1234",
            region="us-central1",
            model="",
        )
    assert excinfo.value.deployment_preset == "vertex_gemini"
    assert excinfo.value.env_hint == "VERTEX_GEMINI_MODEL_ID"


def test_vertex_gemini_preset_rejects_unknown_model() -> None:
    from kaizen.llm.errors import ModelGrammarInvalid

    with pytest.raises(ModelGrammarInvalid):
        LlmDeployment.vertex_gemini(
            _service_account_dict(),
            project="my-gcp-project-1234",
            region="us-central1",
            model="claude-3-opus",
        )


# ---------------------------------------------------------------------------
# Registry parity
# ---------------------------------------------------------------------------


def test_vertex_gemini_registered_in_preset_registry() -> None:
    assert "vertex_gemini" in list_presets()
    factory = get_preset("vertex_gemini")
    assert factory is vertex_gemini_preset


def test_vertex_gemini_preset_name_matches_rust_literal() -> None:
    """`vertex_gemini` MUST byte-match the Rust SDK literal for cross-SDK
    parity."""
    assert "vertex_gemini" in list_presets()


# ---------------------------------------------------------------------------
# Observability log shape
# ---------------------------------------------------------------------------


def test_vertex_gemini_construction_emits_structured_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="kaizen.llm.presets"):
        LlmDeployment.vertex_gemini(
            _service_account_dict(),
            project="my-gcp-project-1234",
            region="us-west1",
            model="gemini-2.5-pro",
        )
    record = next(
        (
            r
            for r in caplog.records
            if r.name == "kaizen.llm.presets"
            and r.message == "llm.deployment.vertex_gemini.constructed"
        ),
        None,
    )
    assert record is not None, "expected structured log line not emitted"
    assert record.deployment_preset == "vertex_gemini"
    assert record.project == "my-gcp-project-1234"
    assert record.region == "us-west1"
    assert record.publisher == "google"
    assert record.auth_strategy_kind == "gcp_oauth"
    assert record.endpoint_host == "us-west1-aiplatform.googleapis.com"
