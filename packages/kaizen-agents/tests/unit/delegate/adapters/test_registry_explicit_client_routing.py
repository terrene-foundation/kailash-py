# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1899 — an explicitly-passed deployment client's
provider/endpoint MUST win over model-name-prefix detection.

Before the fix, ``Delegate(model="gpt-...", base_url=..., api_key=...)`` dropped
the ``base_url``/``api_key`` (the OpenAI-compatible / Azure / custom-endpoint
deployment client) and routed the completion by the ``model`` string's prefix,
sending every request to ``api.openai.com`` and demanding ``OPENAI_API_KEY``.
The passed deployment client was never used.

These tests exercise the routing DISPATCH only (adapter construction), not a
live LLM call. The model-name literals below are prefix-SHAPE fixtures for the
detection logic, not production model selection (rules/env-models.md applies to
production paths; test fixtures are exempt).
"""

from __future__ import annotations

import pytest

from kaizen_agents.delegate.adapters.anthropic_adapter import AnthropicStreamAdapter
from kaizen_agents.delegate.adapters.openai_adapter import OpenAIStreamAdapter
from kaizen_agents.delegate.adapters.registry import get_adapter_for_model

# An OpenAI-compatible deployment endpoint (e.g. Azure OpenAI / custom proxy).
# A deployment client is identified by its endpoint, not a routable model prefix.
_DEPLOYMENT_BASE_URL = "https://my-deployment.example.com/v1"
_DEPLOYMENT_KEY = "test-deployment-key"  # not a real secret; test-only fixture


def _client_base_url(adapter: OpenAIStreamAdapter) -> str:
    """The endpoint the constructed adapter's underlying client will call."""
    return str(adapter._client.base_url).rstrip("/")


# --- AC #1 / #2: the passed client's endpoint wins over the model prefix ------


@pytest.mark.parametrize(
    "model",
    [
        "gpt-4o",  # short alias — AC #2
        "gpt-4",  # short alias — AC #2
        "o1",  # short alias — AC #2
        "gpt-3.5-turbo",  # short alias — AC #2
        "gpt-5-my-deployment",  # gpt-* deployment name — AC #1
        "claude-3-5-sonnet",  # non-openai prefix on an openai-compatible client — AC #1
        "my-custom-deployment",  # non-prefixed deployment name — AC #1
    ],
)
def test_explicit_client_endpoint_wins_over_model_prefix(model: str) -> None:
    """A deployment client (base_url + api_key) MUST be used regardless of the
    model string's provider prefix — including a gpt-* / claude-* shape."""
    adapter = get_adapter_for_model(
        model=model,
        api_key=_DEPLOYMENT_KEY,
        base_url=_DEPLOYMENT_BASE_URL,
        ungoverned=True,  # routing test; not exercising the governance gate
    )
    assert isinstance(adapter, OpenAIStreamAdapter), (
        f"model {model!r} with an explicit deployment endpoint must route to the "
        f"OpenAI-compatible adapter, got {type(adapter).__name__}"
    )
    assert _client_base_url(adapter) == _DEPLOYMENT_BASE_URL, (
        f"model {model!r} routed to {_client_base_url(adapter)!r}, not the passed "
        f"deployment endpoint {_DEPLOYMENT_BASE_URL!r} — the client was ignored"
    )


def test_explicit_provider_still_wins_over_endpoint_and_prefix() -> None:
    """An explicit provider name remains authoritative (unchanged precedence)."""
    adapter = get_adapter_for_model(
        model="gpt-4o",
        provider="anthropic",
        api_key=_DEPLOYMENT_KEY,
        base_url=_DEPLOYMENT_BASE_URL,
        ungoverned=True,
    )
    assert isinstance(adapter, AnthropicStreamAdapter)


# --- AC #3: prefix detection stays the FALLBACK for zero-config callers --------


def test_zero_config_claude_prefix_unchanged() -> None:
    """No explicit client → claude-* still detects Anthropic (fallback intact)."""
    adapter = get_adapter_for_model(
        model="claude-3-5-sonnet",
        api_key=_DEPLOYMENT_KEY,  # anthropic adapter reads its own key; harmless here
        ungoverned=True,
    )
    assert isinstance(adapter, AnthropicStreamAdapter)


def test_zero_config_gpt_prefix_uses_default_openai_endpoint() -> None:
    """No explicit client → gpt-* routes to plain OpenAI at the default endpoint."""
    adapter = get_adapter_for_model(
        model="gpt-4o",
        api_key=_DEPLOYMENT_KEY,
        ungoverned=True,
    )
    assert isinstance(adapter, OpenAIStreamAdapter)
    assert _client_base_url(adapter) != _DEPLOYMENT_BASE_URL
    assert "api.openai.com" in _client_base_url(adapter)


# --- End-to-end: Delegate threads the passed client through to the loop --------


def test_delegate_threads_explicit_client_endpoint_to_loop_adapter() -> None:
    """Delegate(model=gpt-*, base_url=, api_key=) must build a loop adapter that
    targets the passed deployment endpoint — not drop it and hit api.openai.com."""
    from kaizen_agents.delegate.delegate import Delegate

    delegate = Delegate(
        model="gpt-5-my-deployment",
        base_url=_DEPLOYMENT_BASE_URL,
        api_key=_DEPLOYMENT_KEY,
        ungoverned=True,
    )
    adapter = delegate._loop._adapter
    assert isinstance(adapter, OpenAIStreamAdapter)
    assert _client_base_url(adapter) == _DEPLOYMENT_BASE_URL
