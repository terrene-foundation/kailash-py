# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shape tests for `LlmDeployment.bedrock_llama(...)` (#498 S4b-ii).

Mirrors `test_bedrock_claude_preset.py` structure. The Llama preset
differs from Claude in one dimension only -- the wire protocol is
`BedrockInvoke` rather than `AnthropicMessages` because Llama on Bedrock
speaks the native Bedrock `invoke-model` schema.
"""

from __future__ import annotations

import logging

import pytest

from kaizen.llm.auth.aws import AwsBearerToken
from kaizen.llm.deployment import Endpoint, LlmDeployment, WireProtocol
from kaizen.llm.errors import ModelRequired
from kaizen.llm.presets import bedrock_llama_preset, get_preset, list_presets


def test_bedrock_llama_preset_shape() -> None:
    d = LlmDeployment.bedrock_llama(
        "bearer-tok", region="us-east-1", model="llama-3.1-70b"
    )
    assert isinstance(d, LlmDeployment)
    assert d.wire == WireProtocol.BedrockInvoke
    assert isinstance(d.endpoint, Endpoint)
    assert str(d.endpoint.base_url).startswith(
        "https://bedrock-runtime.us-east-1.amazonaws.com"
    )
    assert d.default_model == "meta.llama3-1-70b-instruct-v1:0"
    assert isinstance(d.auth, AwsBearerToken)
    assert d.auth.auth_strategy_kind() == "aws_bearer_token"
    assert d.auth.region == "us-east-1"


def test_bedrock_llama_preset_classmethod_matches_free_function() -> None:
    cm = LlmDeployment.bedrock_llama("tok", region="eu-west-1", model="llama-3.3-70b")
    fn = bedrock_llama_preset("tok", region="eu-west-1", model="llama-3.3-70b")
    assert cm.wire == fn.wire
    assert cm.default_model == fn.default_model
    assert str(cm.endpoint.base_url) == str(fn.endpoint.base_url)


def test_bedrock_llama_preset_stores_resolved_on_wire_model() -> None:
    d = LlmDeployment.bedrock_llama("tok", region="us-east-1", model="llama-3.2-11b")
    assert d.default_model == "meta.llama3-2-11b-instruct-v1:0"


def test_bedrock_llama_preset_passes_through_inference_profile() -> None:
    d = LlmDeployment.bedrock_llama(
        "tok",
        region="us-east-1",
        model="us.meta.llama3-1-70b-instruct-v1:0",
    )
    assert d.default_model == "us.meta.llama3-1-70b-instruct-v1:0"


def test_bedrock_llama_preset_passes_through_native_on_wire_id() -> None:
    d = LlmDeployment.bedrock_llama(
        "tok", region="us-east-1", model="meta.llama3-3-70b-instruct-v1:0"
    )
    assert d.default_model == "meta.llama3-3-70b-instruct-v1:0"


def test_bedrock_llama_preset_rejects_empty_api_key() -> None:
    with pytest.raises(ValueError, match=r"api_key"):
        LlmDeployment.bedrock_llama("", region="us-east-1", model="llama-3.1-70b")


def test_bedrock_llama_preset_rejects_unknown_region() -> None:
    from kaizen.llm.auth.aws import RegionNotAllowed

    with pytest.raises(RegionNotAllowed):
        LlmDeployment.bedrock_llama("tok", region="mars-east-1", model="llama-3.1-70b")


def test_bedrock_llama_preset_raises_model_required_on_empty_model() -> None:
    with pytest.raises(ModelRequired) as excinfo:
        LlmDeployment.bedrock_llama("tok", region="us-east-1", model="")
    assert excinfo.value.deployment_preset == "bedrock_llama"
    assert excinfo.value.env_hint == "BEDROCK_LLAMA_MODEL_ID"


def test_bedrock_llama_preset_rejects_unknown_model() -> None:
    from kaizen.llm.errors import ModelGrammarInvalid

    with pytest.raises(ModelGrammarInvalid):
        LlmDeployment.bedrock_llama("tok", region="us-east-1", model="gpt-4o-mini")


def test_bedrock_llama_registered_in_preset_registry() -> None:
    assert "bedrock_llama" in list_presets()
    assert get_preset("bedrock_llama") is bedrock_llama_preset


def test_bedrock_llama_construction_emits_structured_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="kaizen.llm.presets"):
        LlmDeployment.bedrock_llama(
            "tok-log", region="us-west-2", model="llama-3.1-70b"
        )
    record = next(
        (
            r
            for r in caplog.records
            if r.name == "kaizen.llm.presets"
            and r.message == "llm.deployment.bedrock_llama.constructed"
        ),
        None,
    )
    assert record is not None
    assert record.deployment_preset == "bedrock_llama"
    assert record.auth_strategy_kind == "aws_bearer_token"
    assert record.endpoint_host == "bedrock-runtime.us-west-2.amazonaws.com"
    assert record.region == "us-west-2"


def test_bedrock_llama_construction_does_not_log_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "bedrock-bearer-super-secret-llama-12345"
    with caplog.at_level(logging.DEBUG, logger="kaizen.llm.presets"):
        LlmDeployment.bedrock_llama(secret, region="us-east-1", model="llama-3.1-70b")
    for rec in caplog.records:
        assert secret not in rec.getMessage()
        for val in getattr(rec, "__dict__", {}).values():
            assert secret != val
