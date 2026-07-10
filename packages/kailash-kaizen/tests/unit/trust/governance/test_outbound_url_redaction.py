# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for L1 (LOW) -- HTTP target URL credential leak into the audit trail.

Wave-2 holistic /redteam finding against #1517-b outbound governance:
``GovernedHTTPClient._effect_builder`` set ``OutboundEffect.target`` to the RAW
request URL, which flows verbatim into ``OutboundVerdict``, the bounded audit
deque, any ``audit_sink``, and ``OutboundEffectRefused.details``. A URL with
userinfo (``https://user:pass@host``) or a secret query parameter
(``?api_key=...``) thus wrote a credential into the audit record
(``rules/security.md`` § "No secrets in logs").

Fix: redact the URL (strip userinfo AND the query string, keep
``scheme://host[:port]/path``) before it becomes the audit target.
"""

from __future__ import annotations

import pytest

from kaizen.trust.governance.outbound import (
    GovernedHTTPClient,
    redact_http_target,
)
from kailash.trust.pact.outbound import (
    EffectGovernor,
    OutboundEffect,
    OutboundEffectInterceptor,
    OutboundEffectRefused,
    OutboundVerdict,
)

pytestmark = pytest.mark.regression

_SECRET_URL = "https://alice:s3cr3t@api.example.com:8443/v1/users?api_key=topsecret&x=1"


# --------------------------------------------------------------------------- #
# Pure helper
# --------------------------------------------------------------------------- #
def test_redact_strips_userinfo_and_query():
    redacted = redact_http_target(_SECRET_URL)
    assert redacted == "https://api.example.com:8443/v1/users"
    for leak in ("alice", "s3cr3t", "api_key", "topsecret"):
        assert leak not in redacted


def test_redact_keeps_clean_url_path():
    assert redact_http_target("https://host/a/b") == "https://host/a/b"


def test_redact_strips_query_even_without_userinfo():
    assert redact_http_target("https://host/p?api_key=leak") == "https://host/p"


def test_redact_handles_ipv6_host():
    assert (
        redact_http_target("https://u:p@[2001:db8::1]:443/p?token=x")
        == "https://[2001:db8::1]:443/p"
    )


def test_redact_unparseable_url_returns_sentinel_not_verbatim():
    # An invalid port makes urlsplit().port raise ValueError -> fail-closed sentinel.
    out = redact_http_target("http://user:pass@host:notaport/p?api_key=leak")
    assert out == "<redacted url>"
    assert "pass" not in out and "leak" not in out


def test_redact_empty_and_nonstring():
    assert redact_http_target("") == ""
    assert redact_http_target(None) == ""  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# End-to-end through the governed HTTP client (audit trail + refusal details)
# --------------------------------------------------------------------------- #
class _AllowGovernor(EffectGovernor):
    def evaluate(self, effect: OutboundEffect) -> OutboundVerdict:
        return OutboundVerdict(
            allowed=True, level="auto_approved", reason="ok", effect=effect
        )


class _DenyGovernor(EffectGovernor):
    def evaluate(self, effect: OutboundEffect) -> OutboundVerdict:
        return OutboundVerdict(
            allowed=False, level="blocked", reason="denied", effect=effect
        )


def test_audit_record_target_has_secret_stripped():
    interceptor = OutboundEffectInterceptor(_AllowGovernor())
    client = GovernedHTTPClient(
        request_fn=lambda method, url, **kw: {"status": 200},
        interceptor=interceptor,
        caller="Eng-CTO",
    )
    client.request("GET", _SECRET_URL)

    target = interceptor.audit_log()[-1].effect.target
    assert target == "https://api.example.com:8443/v1/users"
    for leak in ("alice", "s3cr3t", "api_key", "topsecret"):
        assert leak not in target


def test_refusal_details_target_has_secret_stripped():
    interceptor = OutboundEffectInterceptor(_DenyGovernor())
    client = GovernedHTTPClient(
        request_fn=lambda method, url, **kw: {"status": 200},
        interceptor=interceptor,
        caller="Eng-CTO",
    )
    with pytest.raises(OutboundEffectRefused) as exc:
        client.request("POST", _SECRET_URL)

    details_target = exc.value.details["target"]
    assert details_target == "https://api.example.com:8443/v1/users"
    for leak in ("alice", "s3cr3t", "api_key", "topsecret"):
        assert leak not in details_target
