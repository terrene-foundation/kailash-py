# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shape tests for `LlmDeployment.bedrock_cohere(...)` (#498 S4b-ii)."""

from __future__ import annotations

import logging

import pytest

from kaizen.llm.auth.aws import AwsBearerToken
from kaizen.llm.deployment import Endpoint, LlmDeployment, WireProtocol
from kaizen.llm.errors import ModelRequired
from kaizen.llm.presets import bedrock_cohere_preset, get_preset, list_presets


def test_bedrock_cohere_preset_shape() -> None:
    d = LlmDeployment.bedrock_cohere(
        "tok", region="us-east-1", model="cohere-command-r"
    )
    assert isinstance(d, LlmDeployment)
    assert d.wire == WireProtocol.BedrockInvoke
    assert isinstance(d.endpoint, Endpoint)
    assert str(d.endpoint.base_url).startswith(
        "https://bedrock-runtime.us-east-1.amazonaws.com"
    )
    assert d.default_model == "cohere.command-r-v1:0"
    assert isinstance(d.auth, AwsBearerToken)
    assert d.auth.auth_strategy_kind() == "aws_bearer_token"
    assert d.auth.region == "us-east-1"


def test_bedrock_cohere_preset_classmethod_matches_free_function() -> None:
    cm = LlmDeployment.bedrock_cohere(
        "tok", region="eu-west-1", model="cohere-command-r-plus"
    )
    fn = bedrock_cohere_preset("tok", region="eu-west-1", model="cohere-command-r-plus")
    assert cm.wire == fn.wire
    assert cm.default_model == fn.default_model


def test_bedrock_cohere_preset_stores_resolved_on_wire_model() -> None:
    d = LlmDeployment.bedrock_cohere(
        "tok", region="us-east-1", model="cohere-command-r-plus"
    )
    assert d.default_model == "cohere.command-r-plus-v1:0"


def test_bedrock_cohere_preset_distinct_from_cohere_direct() -> None:
    """`bedrock_cohere` and `cohere` are distinct presets with different
    wires and endpoints."""
    bedrock = LlmDeployment.bedrock_cohere(
        "bedrock-tok", region="us-east-1", model="cohere-command-r"
    )
    direct = LlmDeployment.cohere("direct-key", model="command-r-plus")
    assert bedrock.wire == WireProtocol.BedrockInvoke
    assert direct.wire == WireProtocol.CohereGenerate
    assert "bedrock-runtime" in str(bedrock.endpoint.base_url)
    assert "api.cohere.com" in str(direct.endpoint.base_url)


def test_bedrock_cohere_preset_rejects_empty_api_key() -> None:
    with pytest.raises(ValueError, match=r"api_key"):
        LlmDeployment.bedrock_cohere("", region="us-east-1", model="cohere-command-r")


def test_bedrock_cohere_preset_rejects_unknown_region() -> None:
    from kaizen.llm.auth.aws import RegionNotAllowed

    with pytest.raises(RegionNotAllowed):
        LlmDeployment.bedrock_cohere(
            "tok", region="mars-east-1", model="cohere-command-r"
        )


def test_bedrock_cohere_preset_raises_model_required_on_empty_model() -> None:
    with pytest.raises(ModelRequired) as excinfo:
        LlmDeployment.bedrock_cohere("tok", region="us-east-1", model="")
    assert excinfo.value.deployment_preset == "bedrock_cohere"
    assert excinfo.value.env_hint == "BEDROCK_COHERE_MODEL_ID"


def test_bedrock_cohere_preset_rejects_unknown_model() -> None:
    from kaizen.llm.errors import ModelGrammarInvalid

    with pytest.raises(ModelGrammarInvalid):
        LlmDeployment.bedrock_cohere("tok", region="us-east-1", model="gpt-4o-mini")


def test_bedrock_cohere_registered_in_preset_registry() -> None:
    assert "bedrock_cohere" in list_presets()
    assert get_preset("bedrock_cohere") is bedrock_cohere_preset


def test_bedrock_cohere_construction_emits_structured_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="kaizen.llm.presets"):
        LlmDeployment.bedrock_cohere(
            "tok-log", region="us-west-2", model="cohere-command-r"
        )
    record = next(
        (
            r
            for r in caplog.records
            if r.name == "kaizen.llm.presets"
            and r.message == "llm.deployment.bedrock_cohere.constructed"
        ),
        None,
    )
    assert record is not None
    assert record.deployment_preset == "bedrock_cohere"
    assert record.auth_strategy_kind == "aws_bearer_token"
    assert record.endpoint_host == "bedrock-runtime.us-west-2.amazonaws.com"
