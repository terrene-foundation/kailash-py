# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK parity: Vertex-Claude on-wire request shape (#1717 AC #7).

Per specs/kaizen-llm-deployments.md § Cross-SDK Parity, a fixed Vertex-Claude
deployment MUST produce byte-equivalent on-wire URL + body on both kailash-py
and the Rust SDK (EATP D6: independent implementation, matching semantics).

This pins the three load-bearing Vertex-Claude wire invariants that the Rust
adapter's per-preset routing also enforces:

* the completion verb is `:rawPredict` (unary) / `:streamRawPredict` (stream),
  appended directly to the model-carrying path with no `/` separator;
* the platform-Anthropic body carries the literal `anthropic_version`
  `"vertex-2023-10-16"`;
* `model` is STRIPPED from the body (Vertex carries it in the URL path).

The assertions read the exact payload dict + URL string the send-path
serializes, so they ARE the on-wire shape — no live GCP call is made (the
grammar-resolved model id `claude-opus-4-8@latest` and the routing verb are
deterministic pure-function outputs of the deployment).
"""

from __future__ import annotations

from kaizen.llm import LlmClient
from kaizen.llm.presets import vertex_claude_preset


def _fake_sa() -> dict:
    """Minimal service-account dict — construction only, no google-auth call."""
    return {
        "type": "service_account",
        "project_id": "my-test-project",
        "private_key_id": "k",
        "private_key": "-----BEGIN PRIVATE KEY-----\nX\n-----END PRIVATE KEY-----",
        "client_email": "sa@my-test-project.iam.gserviceaccount.com",
        "client_id": "i",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def _client_and_request(*, stream: bool):
    dep = vertex_claude_preset(
        _fake_sa(),
        "my-proj-1234",
        "us-central1",
        "claude-opus-4-8",
    )
    client = LlmClient.from_deployment(dep)
    req = client._build_completion_request(
        [{"role": "user", "content": "hi"}],
        model=None,
        temperature=None,
        top_p=None,
        max_tokens=32,
        stop=None,
        user=None,
        stream=stream,
    )
    return client, req


def test_vertex_claude_unary_wire_shape_matches_rust_contract() -> None:
    """Unary Vertex-Claude request: `:rawPredict` verb + version-stripped body."""
    client, req = _client_and_request(stream=False)
    payload, url = client._build_completion_payload_and_url(req, stream=False)

    # Verb: `:rawPredict` appended to the model-carrying path.
    assert url.endswith(":rawPredict")
    assert "/publishers/anthropic/models/claude-opus-4-8" in url
    # Platform-Anthropic body transform: version literal present, model stripped.
    assert payload["anthropic_version"] == "vertex-2023-10-16"
    assert "model" not in payload


def test_vertex_claude_streaming_verb_matches_rust_contract() -> None:
    """Streaming Vertex-Claude request routes to the `:streamRawPredict` verb."""
    client, req = _client_and_request(stream=True)
    _, stream_url = client._build_completion_payload_and_url(req, stream=True)

    assert stream_url.endswith(":streamRawPredict")
    # Distinct from the unary verb — a streaming send must NOT hit `:rawPredict`.
    assert not stream_url.endswith(":rawPredict")
    assert "/publishers/anthropic/models/claude-opus-4-8" in stream_url
