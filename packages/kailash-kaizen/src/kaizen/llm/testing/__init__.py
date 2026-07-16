# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Test-only deployment factories — physically separated from the
production import surface (#788).

Cross-SDK parity with kailash-rs ``LlmDeployment::mock()`` at
``crates/kailash-kaizen/src/llm/deployment/presets.rs:1183``, which is
gated behind ``#[cfg(any(test, feature = "test-utils"))]`` so production
builds without the ``test-utils`` feature CANNOT construct a mock
deployment at compile time.

Python lacks cargo features, so an equivalent compile-time gate does not
exist. The structural defense here is **physical module separation**:

- Production code imports ``kaizen.llm.presets`` (or
  ``kaizen.llm.deployment.LlmDeployment``); neither exposes a ``mock``
  classmethod or factory.
- Test code that wants a mock deployment imports
  ``kaizen.llm.testing.mock_preset`` explicitly.

The split is structurally enforced — the symbol simply does not exist on
the production import surface. ``LlmDeployment.mock()`` raises
``AttributeError`` and ``from kaizen.llm.presets import mock_preset``
raises ``ImportError``. The Tier-1 test suite at
``tests/unit/llm/test_mock_preset_isolation.py`` asserts both invariants.

Use this module ONLY in test code (``tests/`` directories,
``conftest.py``, ``test_*.py`` files). Importing
``kaizen.llm.testing.mock_preset`` from production code is a
``rules/zero-tolerance.md`` Rule 2 violation (no mock data in
production); the import path is the deliberate red flag — production
code that imports from a module named ``testing`` is structurally
identifiable by ``grep -rn 'kaizen.llm.testing' src/``.

Capability matrix: Rust's ``CapabilityMatrix::for_preset("mock")`` falls
through to ``Self::all_false()`` (no explicit row at
``crates/kailash-kaizen/src/llm/deployment/capabilities.rs:120-250``).
Python preserves the same behavior — ``"mock"`` is intentionally absent
from ``_PRESET_CAPABILITIES`` so ``mock.supports()`` returns the
fail-closed all-False default. Cross-SDK parity per
``rules/cross-sdk-inspection.md`` § 3a.
"""

from __future__ import annotations

from kaizen.llm.auth.bearer import StaticNone
from kaizen.llm.deployment import Endpoint, LlmDeployment, WireProtocol
from kaizen.llm.testing.mock_transport import MockLlmHttpClient, UnsupportedMockRequest


def mock_preset(model: str = "mock-model") -> LlmDeployment:
    """Mock LLM deployment for testing.

    Constructs an :class:`LlmDeployment` with ``preset_name="mock"``,
    ``WireProtocol.OpenAiChat``, ``StaticNone`` auth, and an endpoint
    pointing at the RFC-2606 reserved test host ``https://example.com``.
    Cross-SDK parity with kailash-rs ``LlmDeployment::mock()`` at
    ``crates/kailash-kaizen/src/llm/deployment/presets.rs:1183``.

    The deployment is NOT intended to make real HTTP calls — test code
    routes requests through the existing ``MockLlmProvider`` registered
    under the ``"mock"`` provider name. The preset exists so the
    abstraction surfaces a ``"mock"`` preset literal consistently
    across SDKs.

    The default ``model="mock-model"`` matches Rust's hardcoded test
    model literal, keeping cross-SDK ported test code byte-identical.
    Callers may override for tests that need a specific model name in
    assertions.

    Capability matrix: ``mock_preset(...).supports()`` returns the
    fail-closed all-False matrix because ``"mock"`` is intentionally
    absent from :data:`kaizen.llm.capabilities._PRESET_CAPABILITIES` —
    matches Rust's ``CapabilityMatrix::for_preset("mock")`` fall-through
    behavior. Tests that need to assert non-trivial capabilities must
    use a real preset (``LlmDeployment.openai("sk-test", ...)``).

    Example::

        from kaizen.llm.testing import mock_preset

        def test_my_feature():
            dep = mock_preset()
            assert dep.preset_name == "mock"
            assert dep.default_model == "mock-model"
    """
    endpoint = Endpoint(base_url="https://example.com", path_prefix="/v1")
    return LlmDeployment(
        wire=WireProtocol.OpenAiChat,
        endpoint=endpoint,
        auth=StaticNone(),
        default_model=model,
        preset_name="mock",
    )


__all__ = ["mock_preset", "MockLlmHttpClient", "UnsupportedMockRequest"]
