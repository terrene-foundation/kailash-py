# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression test for #794 — Cohere endpoint cross-SDK parity with kailash-rs.

Per ``rules/cross-sdk-inspection.md`` § 3 (EATP D6: matching semantics) and
§ 4 (cross-SDK parity helpers MUST pin byte-vector test cases), this test
locks the Python ``cohere_preset`` endpoint byte-for-byte against the
kailash-rs ``LlmDeployment::cohere()`` literal at
``crates/kailash-kaizen/src/llm/deployment/presets.rs:386-396``.

Failure-mode this prevents: a future refactor reverts the default to
``api.cohere.com/v1`` (legacy v1 Generate API), silently breaking
cross-SDK code-portability — a Rust user porting
``LlmDeployment::cohere()`` to Python lands on a different host AND
different on-wire request shape.
"""

from __future__ import annotations

import pytest

from kaizen.llm.deployment import LlmDeployment, WireProtocol
from kaizen.llm.presets import cohere_preset

# ---------------------------------------------------------------------------
# Cross-SDK byte-pinning — endpoint literal MUST match kailash-rs
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_cohere_preset_endpoint_pins_kailash_rs_v2_literal() -> None:
    """Pin the Cohere endpoint byte-for-byte to kailash-rs presets.rs:387.

    The Rust SDK constructs::

        Endpoint::new("https://api.cohere.ai/v2")

    Python MUST emit a structurally-equivalent endpoint. ``HttpUrl``
    normalises to a trailing slash; the test asserts the canonical
    base-url-prefix + path-prefix decomposition Rust passes to
    ``Endpoint::new``.
    """
    d = cohere_preset(api_key="co-test", model="command-r-plus")
    # Host parity — Rust uses api.cohere.ai (NOT api.cohere.com legacy host)
    assert str(d.endpoint.base_url).startswith(
        "https://api.cohere.ai"
    ), f"endpoint host drifted from kailash-rs api.cohere.ai: {d.endpoint.base_url}"
    # Path parity — Rust uses /v2 (NOT /v1 legacy Generate API)
    assert d.endpoint.path_prefix == "/v2", (
        f"endpoint path drifted from kailash-rs /v2 (Chat API) to "
        f"{d.endpoint.path_prefix!r}"
    )


@pytest.mark.regression
def test_cohere_preset_classmethod_endpoint_matches_module_function() -> None:
    """Both surfaces (``LlmDeployment.cohere()`` classmethod and
    ``cohere_preset()`` module function) MUST produce byte-identical
    endpoints. A drift between them means one path hit a refactor and
    the other did not.
    """
    a = cohere_preset(api_key="co-test", model="command-r-plus")
    b = LlmDeployment.cohere(api_key="co-test", model="command-r-plus")
    assert str(a.endpoint.base_url) == str(b.endpoint.base_url)
    assert a.endpoint.path_prefix == b.endpoint.path_prefix


@pytest.mark.regression
def test_cohere_preset_wire_tag_unchanged_after_v2_default() -> None:
    """Wire tag MUST stay ``CohereGenerate`` even though the default
    endpoint advanced to v2. Rust comment at ``presets.rs:378-380``
    confirms v2 delegates through ``OpenAiAdapter`` under the same
    ``WireProtocol::CohereGenerate`` tag — the wire tag is the
    adapter-routing key, NOT the API generation indicator. Renaming
    the wire tag in either SDK is a coordinated cross-SDK enum change
    (issue #794 AC option (a)) and breaks this assertion loudly.
    """
    d = cohere_preset(api_key="co-test", model="command-r-plus")
    assert d.wire is WireProtocol.CohereGenerate


@pytest.mark.regression
def test_cohere_preset_legacy_v1_callable_via_explicit_overrides() -> None:
    """Migration safety net: callers who require the legacy v1 Generate
    API MUST be able to opt in via explicit ``base_url``/``path_prefix``
    overrides. If a future refactor removes those parameters or hard-codes
    the v2 endpoint, this test fails loudly and forces a CHANGELOG
    migration entry.
    """
    d = cohere_preset(
        api_key="co-test",
        model="command-r-plus",
        base_url="https://api.cohere.com",
        path_prefix="/v1",
    )
    assert str(d.endpoint.base_url).startswith("https://api.cohere.com")
    assert d.endpoint.path_prefix == "/v1"
    # Wire tag unchanged on legacy path — same WireProtocol routes both
    # endpoints; the ``base_url``/``path_prefix`` is the only divergence
    # the user controls.
    assert d.wire is WireProtocol.CohereGenerate
