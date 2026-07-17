# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 kaizen 2.34.0 pre-release redteam fixes — behavioral regressions.

Pins the two MEDIUM findings the mandatory pre-release security review surfaced
against the merged four-axis cutover (``llm_agent._provider_llm_response`` +
outer ``run`` handler), so a future refactor cannot silently reintroduce them:

* **MED-2** — an ``ImportError`` in the four-axis / legacy provider stack MUST
  RAISE loudly (parity with the embedding path's unresolvable-provider raise),
  NOT return a fabricated completion presented as a real provider answer
  (``rules/zero-tolerance.md`` Rule 2/3, ``rules/observability.md`` Rule 3). The
  fabricating ``_fallback_llm_response`` method is deleted outright
  (``rules/orphan-detection.md`` Rule 3).
* **MED-1** — a provider error whose message embeds a URL credential MUST be
  routed through ``sanitize_provider_error`` before it reaches the LOG surface
  (previously logged raw via ``exc_info=True`` — the caller-facing raise was
  sanitized but the server log was not). ``rules/security.md`` § "No secrets in
  logs".

Tier-1 offline + deterministic (no network, no live keys). Behavioral asserts
per ``rules/testing.md`` § "Behavioral Regression Tests Over Source-Grep".
"""

from __future__ import annotations

import logging

import pytest

import kaizen.llm.deployment_resolver as resolver_mod
from kaizen.nodes.ai.llm_agent import LLMAgentNode

_MESSAGES = [{"role": "user", "content": "hi"}]


# ---------------------------------------------------------------------------
# MED-2 — import failure RAISES, does NOT fabricate a completion.
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_provider_import_failure_raises_not_fabricated_completion(monkeypatch):
    """An ``ImportError`` in the provider stack surfaces as a loud ``RuntimeError``
    — never a fabricated ``{"content": "Direct API response from ..."}`` dict
    that a caller would consume as a real LLM answer."""

    def _raise_import(*args, **kwargs):
        raise ImportError("provider stack import failed")

    monkeypatch.setattr(resolver_mod, "resolve_deployment_for", _raise_import)

    node = LLMAgentNode()
    with pytest.raises(RuntimeError, match="provider stack unavailable"):
        node._provider_llm_response("openai", "gpt-x", _MESSAGES, [], {})


@pytest.mark.regression
def test_fabricated_fallback_method_removed():
    """The fabricating ``_fallback_llm_response`` method is deleted, so no future
    refactor can silently route the import-failure branch back to fake data."""
    assert not hasattr(LLMAgentNode, "_fallback_llm_response")


# ---------------------------------------------------------------------------
# MED-1 — provider error is sanitized before it reaches the LOG surface.
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_provider_error_log_is_sanitized_no_credential_leak(monkeypatch, caplog):
    """A provider error whose message embeds a URL credential is sanitized both
    in the raised message AND on the log surface — the raw credential must not
    reach either (previously ``exc_info=True`` logged the raw exception)."""
    secret = "SUPERSECRETCRED0123456789"

    def _raise_with_cred(*args, **kwargs):
        raise RuntimeError(f"wire failed at https://user:{secret}@host:443/v1")

    monkeypatch.setattr(resolver_mod, "resolve_deployment_for", _raise_with_cred)

    node = LLMAgentNode()
    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as excinfo:
            node._provider_llm_response("openai", "gpt-x", _MESSAGES, [], {})

    # The raised (caller-facing) message is sanitized.
    assert secret not in str(excinfo.value)
    # AND the log surface carries no raw credential (the MED-1 fix — the log
    # previously used raw ``e`` + ``exc_info=True``).
    assert secret not in caplog.text


# ---------------------------------------------------------------------------
# MED-1 sibling — the MCP retrieval path sanitizes its connection-error log.
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_mcp_connection_error_log_is_sanitized_no_credential_leak(caplog):
    """The MCP per-server connection-failure path (``_retrieve_mcp_context``) was
    the same-class sibling of MED-1: it logged the raw exception while a
    sanitized copy was computed two lines later for the return. Confirm a
    URL-embedded credential in an MCP transport error does not reach the log."""
    secret = "MCPSECRETCANARY0123456789"

    class _FakeMCPClient:
        async def list_resources(self, server_config):
            raise RuntimeError(f"connect failed at https://user:{secret}@mcp.host/v1")

    node = LLMAgentNode()
    # Setting ``_mcp_client`` makes ``use_real_mcp`` True and supplies the client,
    # so ``list_resources`` drives the per-server ``except Exception`` log path.
    node._mcp_client = _FakeMCPClient()

    with caplog.at_level(logging.ERROR):
        node._retrieve_mcp_context(
            [{"name": "s1", "transport": "http", "url": "https://mcp.host"}],
            ["resource://x/y"],
            {},
        )

    assert secret not in caplog.text
