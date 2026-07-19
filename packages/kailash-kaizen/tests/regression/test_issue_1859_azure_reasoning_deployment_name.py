# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: Azure reasoning-model detection keys off the model FAMILY, not
the deployment name (#1859).

Bug: the four-axis Azure path built the deployment with
``default_model = <deployment name>`` (Azure's caller-chosen deployment name is
the URL / wire ``model`` field). The OpenAI-chat wire shaper then ran
``filter_reasoning_model_params`` + the ``max_tokens``/``max_completion_tokens``
selection against that deployment name. When the deployment name is not the
canonical model id (the common case — Azure deployment names are user-chosen),
the anchored patterns (``^gpt-?5`` / ``^o1`` / …) miss, the reasoning-param strip
is skipped, and Azure returns ``400 unsupported_value`` on the default
``temperature: 0.7`` (or on ``max_tokens``).

Fix: the deployment carries a separate ``canonical_model`` (the family), threaded
onto ``CompletionRequest.canonical_model`` and consumed by the wire shaper for
DETECTION only — the wire ``model`` field + URL keep the deployment name.

These tests exercise the param-filtering / request-construction logic directly
and OFFLINE (no Azure call): they build the Azure deployment via the shared
resolver, construct the wire request through ``LlmClient``, and inspect the
shaped payload / URL bytes.
"""

from __future__ import annotations

import pytest

from kaizen.llm.client import LlmClient
from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.deployment_resolver import resolve_deployment_for
from kaizen.llm.wire_protocols import openai_chat

_RESOURCE_BASE_URL = "https://my-openai-resource.openai.azure.com"
_API_KEY = "test-key-not-a-real-secret"


def _azure_deployment(model: str, deployment: str):
    """Build the four-axis Azure deployment the live path builds (#1859 shape:
    ``model`` = canonical family, ``deployment`` = caller-chosen deployment name).
    """
    dep = resolve_deployment_for(
        "azure_openai",
        model,
        api_key=_API_KEY,
        base_url=_RESOURCE_BASE_URL,
        deployment=deployment,
    )
    assert dep is not None, "resolver returned None (credential resolution failed)"
    return dep


def _payload_and_url(
    deployment,
    *,
    temperature=0.7,
    max_tokens=500,
    top_p=0.9,
    frequency_penalty=0.1,
    presence_penalty=0.1,
):
    """Build the wire payload + URL through the real client + shaper (offline)."""
    client = LlmClient.from_deployment(deployment, ungoverned=True)
    request = client._build_completion_request(
        [{"role": "user", "content": "hello"}],
        model=None,  # falls back to deployment.default_model (the deployment name)
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        stop=None,
        user=None,
        stream=False,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
    )
    payload, url = client._build_completion_payload_and_url(request, stream=False)
    return request, payload, url


# ---------------------------------------------------------------------------
# (1) gpt-5 family, NON-canonical deployment name -> reasoning strip fires
# ---------------------------------------------------------------------------


def test_gpt5_deployment_noncanonical_name_strips_reasoning_params():
    """model='gpt-5' + deployment='my-gpt5-deploy': the strip fires off the
    FAMILY. gpt-5 forces temperature=1.0 and drops top_p/frequency/presence;
    max_tokens becomes max_completion_tokens.
    """
    dep = _azure_deployment("gpt-5", "my-gpt5-deploy")
    request, payload, url = _payload_and_url(dep)

    # canonical family threaded onto the request (detection input)
    assert request.canonical_model == "gpt-5"
    # gpt-5 REQUIRES temperature=1.0 (the 0.7 default is what caused the 400)
    assert payload.get("temperature") == 1.0
    # the other sampling params gpt-5 rejects are dropped
    assert "top_p" not in payload
    assert "frequency_penalty" not in payload
    assert "presence_penalty" not in payload
    # token-limit field is family-aware: max_completion_tokens, NOT max_tokens
    assert payload.get("max_completion_tokens") == 500
    assert "max_tokens" not in payload


def test_o1_deployment_noncanonical_name_strips_temperature():
    """o1-family with a non-canonical deployment name: temperature is dropped
    entirely (o1/o3/o4 reject it outright).
    """
    dep = _azure_deployment("o1", "prod-reasoner")
    request, payload, _url = _payload_and_url(dep)

    assert request.canonical_model == "o1"
    assert "temperature" not in payload
    assert "top_p" not in payload
    assert "frequency_penalty" not in payload
    assert "presence_penalty" not in payload
    assert payload.get("max_completion_tokens") == 500
    assert "max_tokens" not in payload


# ---------------------------------------------------------------------------
# (2) the wire request STILL targets the deployment name (Azure URL/model field)
# ---------------------------------------------------------------------------


def test_wire_still_targets_deployment_name():
    """The reasoning-detection input changed to the family, but the wire
    ``model`` field AND the URL path MUST still carry the Azure deployment name.
    """
    dep = _azure_deployment("gpt-5", "my-gpt5-deploy")
    _request, payload, url = _payload_and_url(dep)

    # wire body model field = deployment name (NOT the family)
    assert payload["model"] == "my-gpt5-deploy"
    # URL path targets the deployment
    assert "/openai/deployments/my-gpt5-deploy/chat/completions" in url
    assert "api-version=" in url
    # the family never leaks into the URL
    assert "/deployments/gpt-5/" not in url


# ---------------------------------------------------------------------------
# (3) non-reasoning model KEEPS temperature (no false-positive strip)
# ---------------------------------------------------------------------------


def test_non_reasoning_model_keeps_temperature_and_max_tokens():
    """gpt-4o (non-reasoning) with any deployment name: temperature stays,
    max_tokens stays max_tokens — the fix does not over-strip.
    """
    dep = _azure_deployment("gpt-4o", "my-gpt4o-deploy")
    request, payload, _url = _payload_and_url(dep)

    assert request.canonical_model == "gpt-4o"
    assert payload.get("temperature") == 0.7
    assert payload.get("top_p") == 0.9
    assert payload.get("frequency_penalty") == 0.1
    assert payload.get("presence_penalty") == 0.1
    assert payload.get("max_tokens") == 500
    assert "max_completion_tokens" not in payload
    assert payload["model"] == "my-gpt4o-deploy"


# ---------------------------------------------------------------------------
# (4) the resolver carries family vs deployment name distinctly
# ---------------------------------------------------------------------------


def test_resolver_separates_family_from_deployment_name():
    dep = _azure_deployment("gpt-5", "my-gpt5-deploy")
    # wire / URL identifier = deployment name
    assert dep.default_model == "my-gpt5-deploy"
    # reasoning-detection identifier = canonical family
    assert dep.canonical_model == "gpt-5"


def test_resolver_backward_compat_single_arg_shape():
    """Legacy shape (no separate deployment): ``model`` IS the deployment name,
    so family == deployment name (byte-neutral, pre-#1859 behavior)."""
    dep = resolve_deployment_for(
        "azure_openai",
        "gpt-4o",
        api_key=_API_KEY,
        base_url=_RESOURCE_BASE_URL,
    )
    assert dep is not None
    assert dep.default_model == "gpt-4o"
    assert dep.canonical_model == "gpt-4o"


# ---------------------------------------------------------------------------
# Guard: the OLD behavior (detection off the deployment name) IS the bug.
# This documents what the fix corrects — a request whose canonical_model is the
# deployment name (the pre-#1859 shape) skips the strip and would 400.
# ---------------------------------------------------------------------------


def test_pre_fix_shape_would_not_strip_reasoning_params():
    """A CompletionRequest whose canonical_model is the non-canonical deployment
    name (== the pre-#1859 behavior) does NOT get its reasoning params stripped —
    demonstrating the bug the fix closes.
    """
    request = CompletionRequest(
        model="my-gpt5-deploy",
        canonical_model="my-gpt5-deploy",  # pre-fix: detection off deployment name
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.7,
        max_tokens=500,
    )
    payload = openai_chat.build_request_payload(request)
    # the bug: temperature 0.7 survives (Azure would 400 on this) and max_tokens
    # is NOT converted — exactly what keying detection off the deployment name does
    assert payload.get("temperature") == 0.7
    assert payload.get("max_tokens") == 500
    assert "max_completion_tokens" not in payload

    # ...whereas keying off the FAMILY (the fix) strips it:
    fixed = CompletionRequest(
        model="my-gpt5-deploy",
        canonical_model="gpt-5",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.7,
        max_tokens=500,
    )
    fixed_payload = openai_chat.build_request_payload(fixed)
    assert fixed_payload.get("temperature") == 1.0
    assert fixed_payload.get("max_completion_tokens") == 500
    assert "max_tokens" not in fixed_payload
    assert fixed_payload["model"] == "my-gpt5-deploy"  # wire still the deployment


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
