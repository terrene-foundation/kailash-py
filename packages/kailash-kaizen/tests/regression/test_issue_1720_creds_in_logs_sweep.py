# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 creds-in-logs sweep — MED-1 sibling regressions (post-2.34.0).

An adversarial classification sweep over every raw-``{e}`` logger site in
kaizen surfaced credential-bearing log leaks of the SAME bug class the 2.34.0
MED-1 fix closed on the MCP *retrieval* branch. This module pins the fixes so a
future refactor cannot silently reintroduce them (``rules/security.md`` § "No
secrets in logs"; ``rules/observability.md`` Rule 6):

* **rate_limiter** — ``ExternalAgentRateLimiter.initialize`` logged the full
  ``redis_url`` verbatim on the SUCCESS path (``redis://user:PASSWORD@host``),
  an unconditional credential leak on any authenticated deployment. Now routed
  through the canonical ``_mask_redis_url`` (``scheme://***@host`` form).
* **provider error logs** — the legacy ``providers/llm/{openai,anthropic,
  google,perplexity}`` chat/stream/embed error handlers logged the raw
  exception via ``logger.error("... %s", e, exc_info=True)`` while re-raising a
  sanitized copy on the next line (the MED-1 asymmetry: sanitized on raise, raw
  on log; ``exc_info=True`` additionally resurfaces the raw original via the
  implicit exception-context chain). Reachable via the deprecated
  direct-provider / ``get_provider()`` API during the deprecation soak.
* **MCP discovery branch** — ``_discover_mcp_tools`` was the same-class sibling
  of the 2.34.0 MED-1 retrieval-branch fix: it logged the raw transport
  exception while the retrieval branch two methods away sanitized. An MCP
  server URL can embed basic-auth credentials.

Tier-1 offline + deterministic (no network, no live keys). Behavioral asserts
per ``rules/testing.md`` § "Behavioral Regression Tests Over Source-Grep".
"""

from __future__ import annotations

import logging

import pytest

_SECRET = "SUPERSECRETCRED0123456789"


# ---------------------------------------------------------------------------
# rate_limiter — the redis_url mask (the unconditional success-path leak).
# ---------------------------------------------------------------------------


def test_mask_redis_url_hides_password_canonical_form():
    from kaizen.governance.rate_limiter import _mask_redis_url

    masked = _mask_redis_url(f"redis://appuser:{_SECRET}@cache.internal:6379/0")
    assert _SECRET not in masked
    assert "appuser" not in masked  # userinfo stripped, not partially masked
    assert "***@" in masked  # canonical grep-able form (observability.md 6.2)
    assert "cache.internal" in masked
    assert "6379" in masked


def test_mask_redis_url_scrubs_credential_embedded_in_error_message():
    """Line 266 feeds a connection-error *message* (not a bare URL) through the
    mask; any ``scheme://user:pass@`` embedded in it must be scrubbed in place."""
    from kaizen.governance.rate_limiter import _mask_redis_url

    msg = f"Error connecting: rediss://:{_SECRET}@cache.internal:6380 timed out"
    masked = _mask_redis_url(msg)
    assert _SECRET not in masked
    assert "***@" in masked


def test_mask_redis_url_localhost_no_credentials_is_stable():
    from kaizen.governance.rate_limiter import _mask_redis_url

    masked = _mask_redis_url("redis://localhost:6379/0")
    assert "localhost" in masked and "6379" in masked


# ---------------------------------------------------------------------------
# provider error logs — the legacy providers/llm/{openai,anthropic,google,
# perplexity} chat/stream/embed error handlers were retired + DELETED in #1720
# Wave-2, so their raw-``{e}`` log sites no longer exist. The four-axis error
# surface's no-credential-leak contract is covered by
# tests/unit/llm/test_errors_no_credential_leak.py (sk- keys / URLs not echoed
# on the error path). The former legacy-provider sanitization test was removed
# here — its code-under-test no longer exists.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# MCP discovery branch — same-class sibling of the 2.34.0 MED-1 retrieval fix.
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_mcp_discovery_error_log_sanitized_no_credential_leak(caplog):
    """``_discover_mcp_tools`` logged the raw MCP transport exception; a server
    URL embedding basic-auth credentials must not reach the log surface."""
    from kaizen.nodes.ai.llm_agent import LLMAgentNode

    secret = "MCPDISCOVERYCANARY0123456789"

    class _FakeMCPClient:
        async def discover_tools(self, server_config):
            raise RuntimeError(f"connect failed at https://user:{secret}@mcp.host/v1")

    node = LLMAgentNode()
    # Setting ``_mcp_client`` makes ``use_real_mcp`` True and drives the
    # per-server ``except Exception`` discovery-branch log path.
    node._mcp_client = _FakeMCPClient()

    with caplog.at_level(logging.ERROR):
        node._discover_mcp_tools(
            [{"name": "s1", "transport": "http", "url": "https://mcp.host"}]
        )

    assert secret not in caplog.text


@pytest.mark.regression
def test_mcp_tool_execution_error_log_matches_sanitized_return(caplog):
    """``_execute_mcp_tool_call`` sanitized its RETURN (``error`` field) but
    logged the raw exception — a return/log asymmetry. A ``call_tool`` transport
    error embedding a URL credential must not reach the log surface."""
    import asyncio

    from kaizen.nodes.ai.llm_agent import LLMAgentNode

    secret = "TOOLEXECCANARY0123456789"

    class _FakeMCPClient:
        async def call_tool(self, server_config, tool_name, tool_args):
            raise RuntimeError(f"connect failed at https://user:{secret}@mcp.host/v1")

    node = LLMAgentNode()
    node._mcp_client = _FakeMCPClient()

    tool_call = {"id": "1", "function": {"name": "mytool", "arguments": "{}"}}
    mcp_tools = [
        {
            "function": {
                "name": "mytool",
                "mcp_server_config": {"name": "s1", "url": "https://mcp.host"},
            }
        }
    ]

    with caplog.at_level(logging.ERROR):
        result = asyncio.run(node._execute_mcp_tool_call(tool_call, mcp_tools))

    assert result["success"] is False
    assert secret not in caplog.text  # the log surface is sanitized
    assert secret not in str(result["error"])  # the return was already sanitized


# ---------------------------------------------------------------------------
# NOTE (#1820): the AzureOpenAIBackend creds-in-logs case was REMOVED here when
# the unified-azure provider stack (unified_azure_provider / azure_backends /
# azure_capabilities / azure_detection) was retired. The four-axis Azure path
# (llm_agent._provider_llm_response / embedding_generator) carries its own
# error-sanitization parity via kaizen.nodes.ai.error_sanitizer, exercised by
# the mcp/discovery cases above and the four-axis wire tests.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# alert_manager — webhook URL secret lives in the PATH (Slack/Discord token),
# a distinct class the provider-error sanitizer does NOT cover. Convergence
# finding: the full webhook_url was logged verbatim on the success path.
# ---------------------------------------------------------------------------


def test_mask_webhook_url_strips_path_token():
    from kaizen.monitoring.alert_manager import _mask_webhook_url

    secret = "XXXWEBHOOKSECRETTOKENXXX"
    url = f"https://hooks.slack.com/services/T00000/B00000/{secret}"
    masked = _mask_webhook_url(url)
    assert secret not in masked
    assert "hooks.slack.com" in masked  # host kept for diagnosability
    assert "[REDACTED]" in masked
    # also scrubs a webhook URL embedded in an arbitrary error string
    embedded = _mask_webhook_url(f"POST to {url} timed out")
    assert secret not in embedded
    assert "timed out" in embedded  # trailing text after the URL survives


def test_mask_webhook_url_strips_userinfo_and_query():
    """A webhook secret can live in the userinfo (basic-auth) or the query
    string, not only the path — all three must be redacted (security-review
    MEDIUM: the host-portion regex previously kept ``user:pass@``)."""
    from kaizen.monitoring.alert_manager import _mask_webhook_url

    # userinfo (self-hosted basic-auth webhook)
    m1 = _mask_webhook_url("https://alertbot:s3cr3tPASSWORD@webhooks.internal/notify")
    assert "s3cr3tPASSWORD" not in m1
    assert "webhooks.internal" in m1
    # query-string token with NO path segment
    m2 = _mask_webhook_url("https://hooks.example.com?token=QUERYSECRET")
    assert "QUERYSECRET" not in m2
    # bare host with no credential stays intact
    assert _mask_webhook_url("https://hooks.example.com") == "https://hooks.example.com"


def test_mask_redis_url_masks_every_url_in_multi_url_string():
    """A redis error message can list multiple credentialed node URLs (cluster);
    every ``user:pass@`` must be masked, not only the first (security-review
    LOW: the bare-URL branch reconstructed ``parsed.path`` verbatim)."""
    from kaizen.governance.rate_limiter import _mask_redis_url

    masked = _mask_redis_url("redis://u:p1@h1:6379/0 fallback redis://u:p2@h2:6379/0")
    assert "p1" not in masked and "p2" not in masked
