# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#2209 — a configured LLM timeout must actually reach the wire call.

Before the fix the chain was broken at BOTH ends:

* ``LLMAgentNode`` declared a documented ``timeout`` NodeParameter
  (``llm_agent.py:465``), read it (``:980``), and forwarded it ONLY into the
  ``_langchain_llm_response`` branch. The real dispatch,
  ``_provider_llm_response``, was never called with it — the issue's own
  mechanical check was ``grep -n -A9 'response = self._provider_llm_response('
  llm_agent.py | grep -c timeout`` returning **0**. That is
  ``zero-tolerance`` Rule 3c exactly: a documented kwarg accepted in the public
  signature with zero effect on the body.
* ``LlmClient`` constructed every ``LlmHttpClient`` with a HARDCODED
  ``timeout=60.0`` (7 sites) and neither ``complete()`` nor ``stream()``
  accepted a ``timeout`` at all — so no configuration path existed. A
  generation exceeding 60 s failed and could not be configured around.

These assert on the TRANSPORT CALL rather than a live request: a recording
``LlmHttpClient`` captures the kwargs the client hands httpx, which pins the
exact value deterministically and needs no credential.

BOTH POLES for every axis, so a fix that merely hardcodes a different constant
would still be caught — a non-default value must be DISTINGUISHABLE from the
60 s default:

* per-request ``timeout=X``        -> ``timeout=X`` on the transport call
* per-request timeout unset        -> NO ``timeout`` kwarg (transport default)
* ``LlmDeployment.timeout=X``      -> client-level transport built with X
* ``LlmDeployment.timeout`` unset  -> client-level transport built with 60.0
"""

from __future__ import annotations

from typing import Any, Dict, List

import httpx
import pytest

from kaizen.llm import LlmClient
from kaizen.llm.deployment import LlmDeployment
from kaizen.llm.http_client import LlmHttpClient, SafeDnsResolver
from kaizen.llm.presets import openai_preset

_MESSAGES = [{"role": "user", "content": "hi"}]


class _AllowAllResolver(SafeDnsResolver):
    """SafeDnsResolver that skips the real DNS lookup (test-only)."""

    __slots__ = ()

    def check_host(self, host: str) -> None:  # noqa: D401 - test stub resolver
        return None


class _RecordingHttpClient(LlmHttpClient):
    """LlmHttpClient that records send kwargs instead of hitting the network.

    Subclasses the REAL transport (never a hand-rolled fake) so the recorded
    kwargs are exactly what the production call site passes.
    """

    def __init__(self) -> None:
        super().__init__(deployment_preset="test", resolver=_AllowAllResolver())
        self.post_kwargs: List[Dict[str, Any]] = []
        self.stream_kwargs: List[Dict[str, Any]] = []

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.post_kwargs.append(kwargs)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                "model": "test-model",
            },
            request=httpx.Request("POST", url),
        )

    async def stream_lines(self, method: str, url: str, **kwargs: Any):
        self.stream_kwargs.append(kwargs)
        yield 'data: {"choices":[{"delta":{"content":"ok"}}]}'
        yield "data: [DONE]"


def _client(*, deployment_timeout: float | None = None) -> LlmClient:
    dep = openai_preset(api_key="sk-test-not-a-real-key", model="test-model")
    if deployment_timeout is not None:
        dep = dep.model_copy(update={"timeout": deployment_timeout})
    return LlmClient.from_deployment(dep, ungoverned=True)


# ---------------------------------------------------------------------------
# Per-request timeout -> the transport call.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_forwards_per_request_timeout_to_transport():
    http = _RecordingHttpClient()
    await _client().complete(
        _MESSAGES, model="test-model", timeout=300.0, http_client=http
    )
    assert len(http.post_kwargs) == 1
    assert http.post_kwargs[0]["timeout"] == 300.0


@pytest.mark.asyncio
async def test_complete_omits_timeout_kwarg_when_unset():
    """Opposite pole: unset must leave the transport's own default in force.

    Asserting only that ``timeout`` is PRESENT could not distinguish the fix
    from one that always sends a constant.
    """
    http = _RecordingHttpClient()
    await _client().complete(_MESSAGES, model="test-model", http_client=http)
    assert len(http.post_kwargs) == 1
    assert "timeout" not in http.post_kwargs[0]


@pytest.mark.asyncio
async def test_complete_timeout_value_is_the_configured_one_not_the_default():
    """A non-default value must be DISTINGUISHABLE from the 60 s default."""
    http = _RecordingHttpClient()
    await _client().complete(
        _MESSAGES, model="test-model", timeout=17.5, http_client=http
    )
    sent = http.post_kwargs[0]["timeout"]
    assert sent == 17.5
    assert sent != LlmClient._DEFAULT_TRANSPORT_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_stream_forwards_per_request_timeout_to_transport():
    http = _RecordingHttpClient()
    client = _client()
    async for _chunk in client.stream(
        _MESSAGES, model="test-model", timeout=300.0, http_client=http
    ):
        pass
    assert len(http.stream_kwargs) == 1
    assert http.stream_kwargs[0]["timeout"] == 300.0


@pytest.mark.asyncio
async def test_stream_omits_timeout_kwarg_when_unset():
    http = _RecordingHttpClient()
    client = _client()
    async for _chunk in client.stream(_MESSAGES, model="test-model", http_client=http):
        pass
    assert len(http.stream_kwargs) == 1
    assert "timeout" not in http.stream_kwargs[0]


# ---------------------------------------------------------------------------
# Deployment-level timeout -> the client-level transport construction.
# ---------------------------------------------------------------------------


def test_deployment_timeout_drives_the_client_level_transport():
    assert _client(deployment_timeout=300.0)._transport_timeout() == 300.0


def test_unset_deployment_timeout_keeps_the_historical_60s_default():
    """Opposite pole: the pre-#2209 hardcoded 60.0 is preserved exactly."""
    assert _client()._transport_timeout() == 60.0
    assert LlmClient._DEFAULT_TRANSPORT_TIMEOUT_SECONDS == 60.0


@pytest.mark.parametrize("bad", [0, 0.0, -1.0])
def test_deployment_timeout_rejects_non_positive_values(bad):
    """A 0/negative timeout is a config error, not a "no limit" idiom.

    httpx spells "no limit" as ``None``, which is this field's default, so there
    is no legitimate non-positive value; accepting one silently would be the
    ``zero-tolerance`` Rule 3 failure mode at the config surface.
    """
    dep = openai_preset(api_key="sk-test-not-a-real-key", model="test-model")
    with pytest.raises(ValueError, match="must be > 0 seconds"):
        LlmDeployment.model_validate({**dep.model_dump(), "timeout": bad})


@pytest.mark.parametrize("good", [0.5, 60.0, 300.0])
def test_deployment_timeout_accepts_positive_values(good):
    """Opposite pole: the validator must NOT reject every value."""
    dep = openai_preset(api_key="sk-test-not-a-real-key", model="test-model")
    revalidated = LlmDeployment.model_validate({**dep.model_dump(), "timeout": good})
    assert revalidated.timeout == good


def test_deployment_timeout_defaults_to_none():
    """Every existing deployment is untouched: the field is opt-in."""
    assert "timeout" in LlmDeployment.model_fields
    assert (
        openai_preset(api_key="sk-test-not-a-real-key", model="test-model").timeout
        is None
    )
