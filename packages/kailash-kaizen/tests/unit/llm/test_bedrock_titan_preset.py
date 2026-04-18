# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shape tests for `LlmDeployment.bedrock_titan(...)` (#498 S4b-ii)."""

from __future__ import annotations

import logging

import pytest

from kaizen.llm.auth.aws import AwsBearerToken
from kaizen.llm.deployment import Endpoint, LlmDeployment, WireProtocol
from kaizen.llm.errors import ModelRequired
from kaizen.llm.presets import bedrock_titan_preset, get_preset, list_presets


def test_bedrock_titan_preset_shape() -> None:
    d = LlmDeployment.bedrock_titan(
        "tok", region="us-east-1", model="titan-text-express"
    )
    assert isinstance(d, LlmDeployment)
    assert d.wire == WireProtocol.BedrockInvoke
    assert isinstance(d.endpoint, Endpoint)
    assert str(d.endpoint.base_url).startswith(
        "https://bedrock-runtime.us-east-1.amazonaws.com"
    )
    assert d.default_model == "amazon.titan-text-express-v1"
    assert isinstance(d.auth, AwsBearerToken)
    assert d.auth.auth_strategy_kind() == "aws_bearer_token"
    assert d.auth.region == "us-east-1"


def test_bedrock_titan_preset_classmethod_matches_free_function() -> None:
    cm = LlmDeployment.bedrock_titan(
        "tok", region="eu-west-1", model="titan-text-premier"
    )
    fn = bedrock_titan_preset("tok", region="eu-west-1", model="titan-text-premier")
    assert cm.wire == fn.wire
    assert cm.default_model == fn.default_model


def test_bedrock_titan_preset_stores_resolved_on_wire_model() -> None:
    d = LlmDeployment.bedrock_titan(
        "tok", region="us-east-1", model="titan-embed-text-v2"
    )
    assert d.default_model == "amazon.titan-embed-text-v2:0"


def test_bedrock_titan_preset_rejects_empty_api_key() -> None:
    with pytest.raises(ValueError, match=r"api_key"):
        LlmDeployment.bedrock_titan("", region="us-east-1", model="titan-text-express")


def test_bedrock_titan_preset_rejects_unknown_region() -> None:
    from kaizen.llm.auth.aws import RegionNotAllowed

    with pytest.raises(RegionNotAllowed):
        LlmDeployment.bedrock_titan(
            "tok", region="mars-east-1", model="titan-text-express"
        )


def test_bedrock_titan_preset_raises_model_required_on_empty_model() -> None:
    with pytest.raises(ModelRequired) as excinfo:
        LlmDeployment.bedrock_titan("tok", region="us-east-1", model="")
    assert excinfo.value.deployment_preset == "bedrock_titan"
    assert excinfo.value.env_hint == "BEDROCK_TITAN_MODEL_ID"


def test_bedrock_titan_preset_rejects_unknown_model() -> None:
    from kaizen.llm.errors import ModelGrammarInvalid

    with pytest.raises(ModelGrammarInvalid):
        LlmDeployment.bedrock_titan("tok", region="us-east-1", model="gpt-4o")


def test_bedrock_titan_registered_in_preset_registry() -> None:
    assert "bedrock_titan" in list_presets()
    assert get_preset("bedrock_titan") is bedrock_titan_preset


def test_bedrock_titan_construction_emits_structured_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="kaizen.llm.presets"):
        LlmDeployment.bedrock_titan(
            "tok-log", region="us-west-2", model="titan-text-express"
        )
    record = next(
        (
            r
            for r in caplog.records
            if r.name == "kaizen.llm.presets"
            and r.message == "llm.deployment.bedrock_titan.constructed"
        ),
        None,
    )
    assert record is not None
    assert record.deployment_preset == "bedrock_titan"
    assert record.auth_strategy_kind == "aws_bearer_token"
    assert record.endpoint_host == "bedrock-runtime.us-west-2.amazonaws.com"
