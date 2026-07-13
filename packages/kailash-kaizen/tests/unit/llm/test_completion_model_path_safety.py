# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Security regression (#1717 security-review MEDIUM): a caller-controlled
``model`` is interpolated into the outbound URL path for the ``{model}``-template
wires (GoogleGenerateContent, BedrockInvoke, HuggingFaceInference). An app that
routes untrusted input into ``model=`` must not be able to path-traverse or
inject URL-control characters onto the provider host. The completion path
validates the resolved model fail-closed before building the request.
"""

from __future__ import annotations

import pytest

from kaizen.llm import LlmClient
from kaizen.llm.client import _validate_completion_model
from kaizen.llm.presets import bedrock_claude_preset, openai_preset


# Legitimate ids across providers MUST pass unchanged (byte-preserving).
@pytest.mark.parametrize(
    "model",
    [
        "gpt-4o",
        "gemini-2.0-flash",
        "gemini-1.5-pro-002",
        "claude-opus-4-8",
        "claude-opus-4-8@latest",  # Vertex version pin
        "anthropic.claude-3-5-sonnet-20241022-v2:0",  # Bedrock version suffix (':')
        "us.anthropic.claude-3-5-sonnet",  # bedrock inference profile
        "meta-llama/Llama-3-8b-Instruct",  # HuggingFace org/model needs '/'
        "mistralai/Mistral-7B",
    ],
)
def test_valid_model_ids_pass_and_are_byte_preserved(model: str) -> None:
    assert _validate_completion_model(model) == model


# Traversal / URL-control injection MUST be rejected fail-closed.
@pytest.mark.parametrize(
    "model",
    [
        "../../v1beta/models/other",  # path traversal
        "../etc/passwd",
        "a/../b",  # embedded traversal segment
        "/etc/passwd",  # leading slash (absolute)
        "a//b",  # empty segment
        "//evil.com/path",  # protocol-relative host smuggle
        "model with space",
        "model?inject=1",  # query smuggle
        "model#frag",
        "model%2e%2e",  # percent-encoded dot
        ".hidden",  # leading dot
        "gpt-4o\n",  # trailing newline (Python $ edge — must NOT slip through)
        "gpt-4o\r",  # trailing carriage return
        "model\ttab",  # embedded control
        "",  # empty
        "x" * 129,  # over length
    ],
)
def test_traversal_and_control_models_rejected(model: str) -> None:
    with pytest.raises(ValueError, match="path segment"):
        _validate_completion_model(model)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_complete_rejects_traversal_model_before_network() -> None:
    """End-to-end: complete() raises ValueError from _build_completion_request,
    before any transport is acquired or any byte leaves the process."""
    dep = openai_preset(api_key="sk-test-not-real", model="gpt-4o")
    client = LlmClient.from_deployment(dep)
    with pytest.raises(ValueError, match="path segment"):
        await client.complete(
            [{"role": "user", "content": "hi"}],
            model="../../v1beta/models/other",
        )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_complete_rejects_traversal_on_model_template_wire() -> None:
    """End-to-end through an actual {model}-template wire (Bedrock puts the model
    in the URL path); the guard must reject before any transport is acquired."""
    dep = bedrock_claude_preset(
        api_key="bedrock-token-not-real",
        region="us-east-1",
        model="anthropic.claude-3-5-sonnet-20241022-v2:0",
    )
    client = LlmClient.from_deployment(dep)
    with pytest.raises(ValueError, match="path segment"):
        await client.complete(
            [{"role": "user", "content": "hi"}],
            model="../../foo/invoke",
        )
