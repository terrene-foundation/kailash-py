# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shape tests for `LlmDeployment.bedrock_claude(...)` (#498 S4a).

Covers:

* Classmethod + module function both work, produce identical shape
* Default wire protocol is `AnthropicMessages` (cross-SDK parity with Rust)
* Endpoint host is `bedrock-runtime.{region}.amazonaws.com`
* Auth is `AwsBearerToken` with `auth_strategy_kind == "aws_bearer_token"`
* `default_model` is the RESOLVED on-wire model id (post-grammar)
* ModelRequired raised on empty/missing model
* Registry parity: `bedrock_claude` is registered in `_PRESETS`
* Cross-SDK: preset name string matches Rust literal byte-for-byte
"""

from __future__ import annotations

import logging

import pytest

from kaizen.llm.auth.aws import AwsBearerToken
from kaizen.llm.deployment import Endpoint, LlmDeployment, WireProtocol
from kaizen.llm.errors import ModelRequired
from kaizen.llm.presets import bedrock_claude_preset, get_preset, list_presets

# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_bedrock_claude_preset_shape() -> None:
    d = LlmDeployment.bedrock_claude(
        "bedrock-bearer-token", region="us-east-1", model="claude-sonnet-4-6"
    )
    assert isinstance(d, LlmDeployment)
    assert d.wire == WireProtocol.AnthropicMessages
    assert isinstance(d.endpoint, Endpoint)
    assert str(d.endpoint.base_url).startswith(
        "https://bedrock-runtime.us-east-1.amazonaws.com"
    )
    assert d.default_model == "anthropic.claude-sonnet-4-6-v1:0"
    assert isinstance(d.auth, AwsBearerToken)
    assert d.auth.auth_strategy_kind() == "aws_bearer_token"
    assert d.auth.region == "us-east-1"


def test_bedrock_claude_preset_classmethod_matches_free_function() -> None:
    classmethod_form = LlmDeployment.bedrock_claude(
        "bearer-tok", region="eu-west-1", model="claude-opus-4-5"
    )
    func_form = bedrock_claude_preset(
        "bearer-tok", region="eu-west-1", model="claude-opus-4-5"
    )
    assert classmethod_form.wire == func_form.wire
    assert classmethod_form.default_model == func_form.default_model
    assert str(classmethod_form.endpoint.base_url) == str(func_form.endpoint.base_url)


def test_bedrock_claude_preset_region_is_reflected_in_endpoint() -> None:
    d = LlmDeployment.bedrock_claude(
        "bearer", region="ap-northeast-1", model="claude-haiku-4-5"
    )
    assert "ap-northeast-1" in str(d.endpoint.base_url)


def test_bedrock_claude_preset_stores_resolved_on_wire_model() -> None:
    """`default_model` is the grammar-resolved on-wire id, not the alias."""
    d = LlmDeployment.bedrock_claude(
        "bearer", region="us-east-1", model="claude-3-5-sonnet"
    )
    assert d.default_model == "anthropic.claude-3-5-sonnet-20240620-v1:0"


def test_bedrock_claude_preset_passes_through_inference_profile() -> None:
    d = LlmDeployment.bedrock_claude(
        "bearer",
        region="us-east-1",
        model="global.anthropic.claude-sonnet-4-6",
    )
    assert d.default_model == "global.anthropic.claude-sonnet-4-6"


def test_bedrock_claude_preset_passes_through_native_on_wire_id() -> None:
    d = LlmDeployment.bedrock_claude(
        "bearer",
        region="us-east-1",
        model="anthropic.claude-3-opus-20240229-v1:0",
    )
    assert d.default_model == "anthropic.claude-3-opus-20240229-v1:0"


# ---------------------------------------------------------------------------
# Validation (invariants 1, 2, 5)
# ---------------------------------------------------------------------------


def test_bedrock_claude_preset_rejects_empty_api_key() -> None:
    with pytest.raises(ValueError, match=r"api_key"):
        LlmDeployment.bedrock_claude("", region="us-east-1", model="claude-sonnet-4-6")


def test_bedrock_claude_preset_rejects_none_api_key() -> None:
    with pytest.raises((ValueError, TypeError)):
        LlmDeployment.bedrock_claude(
            None,  # type: ignore[arg-type]
            region="us-east-1",
            model="claude-sonnet-4-6",
        )


def test_bedrock_claude_preset_rejects_unknown_region() -> None:
    from kaizen.llm.auth.aws import RegionNotAllowed

    with pytest.raises(RegionNotAllowed):
        LlmDeployment.bedrock_claude(
            "bearer", region="mars-east-1", model="claude-sonnet-4-6"
        )


def test_bedrock_claude_preset_raises_model_required_on_empty_model() -> None:
    """Invariant 5: empty model raises ModelRequired with the preset label."""
    with pytest.raises(ModelRequired) as excinfo:
        LlmDeployment.bedrock_claude("bearer", region="us-east-1", model="")
    assert excinfo.value.deployment_preset == "bedrock_claude"
    assert excinfo.value.env_hint == "BEDROCK_MODEL_ID"


def test_bedrock_claude_preset_raises_model_required_on_non_string_model() -> None:
    with pytest.raises((ModelRequired, TypeError)):
        LlmDeployment.bedrock_claude(
            "bearer", region="us-east-1", model=None  # type: ignore[arg-type]
        )


def test_bedrock_claude_preset_rejects_unknown_model() -> None:
    from kaizen.llm.errors import ModelGrammarInvalid

    with pytest.raises(ModelGrammarInvalid):
        LlmDeployment.bedrock_claude("bearer", region="us-east-1", model="gpt-4o-mini")


# ---------------------------------------------------------------------------
# Registry parity (cross-SDK)
# ---------------------------------------------------------------------------


def test_bedrock_claude_registered_in_preset_registry() -> None:
    assert "bedrock_claude" in list_presets()
    factory = get_preset("bedrock_claude")
    assert factory is bedrock_claude_preset


def test_bedrock_claude_preset_name_matches_rust_literal() -> None:
    """`bedrock_claude` MUST byte-match the Rust SDK literal for cross-SDK
    parity. Source: `kailash-rs/crates/kailash-kaizen/src/llm/deployment/
    presets.rs` line 407.
    """
    assert "bedrock_claude" in list_presets()


# ---------------------------------------------------------------------------
# Observability log shape (invariant 4)
# ---------------------------------------------------------------------------


def test_bedrock_claude_construction_emits_structured_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Invariant 4: log fields canonical --
    deployment_preset='bedrock_claude', auth_strategy_kind='aws_bearer_token',
    endpoint_host='bedrock-runtime.<region>.amazonaws.com'.
    """
    with caplog.at_level(logging.INFO, logger="kaizen.llm.presets"):
        LlmDeployment.bedrock_claude(
            "bearer-log-test", region="us-west-2", model="claude-sonnet-4-6"
        )
    # Find the structured log record.
    record = next(
        (
            r
            for r in caplog.records
            if r.name == "kaizen.llm.presets"
            and r.message == "llm.deployment.bedrock_claude.constructed"
        ),
        None,
    )
    assert record is not None, "expected structured log line not emitted"
    assert record.deployment_preset == "bedrock_claude"
    assert record.auth_strategy_kind == "aws_bearer_token"
    assert record.endpoint_host == "bedrock-runtime.us-west-2.amazonaws.com"
    assert record.region == "us-west-2"


def test_bedrock_claude_construction_does_not_log_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_token = "bedrock-bearer-super-secret-xyz-12345"
    with caplog.at_level(logging.DEBUG, logger="kaizen.llm.presets"):
        LlmDeployment.bedrock_claude(
            secret_token, region="us-east-1", model="claude-sonnet-4-6"
        )
    for rec in caplog.records:
        assert secret_token not in rec.getMessage()
        for val in getattr(rec, "__dict__", {}).values():
            assert secret_token != val
