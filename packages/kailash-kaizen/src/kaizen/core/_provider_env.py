"""Shared env-first provider-detection fallback.

Single source of truth for the narrow "which provider gets dispatched when
none was explicitly configured" fallback used across the Agent deployment
surface (`kaizen/core/agents.py`, `kaizen/core/base_agent.py`,
`kaizen/signatures/core.py`, `kaizen/integrations/nexus/base.py`). Extracted
after the SAME openai/anthropic/mock env-check logic was found duplicated
across 3-4 LLMAgentNode-param-building sites during the provider-gate
hardening sweep (rules/security.md "Multi-Site Kwarg Plumbing" — a helper
this widely duplicated drifts silently unless consolidated).

This is intentionally NOT `kaizen.config.providers.auto_detect_provider()`:
that function checks 7 providers (openai/azure/anthropic/google/perplexity/
ollama/docker) and RAISES `ConfigurationError` when none is available — a
different, fail-loud contract used by a different call path. This helper
mirrors only `Agent._get_provider_for_config()`'s narrower openai -> anthropic
order for the KEYED case.

#1952 — keyless NO LONGER silently resolves to "mock". #1947 closed the
silent-mock/fabricated-content class at the NODE: `LLMAgentNode` raises a
typed `ConfigurationError` when `provider` resolves to `None`, and the mock
provider stays reachable only when `provider="mock"` is passed EXPLICITLY.
This helper is the residual keyless surface #1947 left open: a real (non-test)
caller with no OPENAI/ANTHROPIC key and no explicit provider used to receive
"mock" here and dispatch fabricated content as a real answer, PASSING the
#1947 gate. It now returns `None` for the keyless case, so the unresolved
provider flows to the node's #1947 fail-loud gate — the single, structural
fail-loud point. The mock provider is legitimate; ONLY the silent keyless
default was the hazard.

The kaizen test harness runs deliberately keyless (the root `conftest.py`
cost-guard actively scrubs provider secrets) with the mock provider registered
in `tests/conftest.py`. It opts back into keyless->mock via the EXPLICIT
`KAIZEN_ALLOW_KEYLESS_MOCK=1` env flag (set only by `tests/conftest.py`, in the
same unit-mode branch that patches the mock provider registry) — mirroring the
existing `KAIZEN_ALLOW_REAL_LLM` / `USE_REAL_PROVIDERS` opt-in shape. A real
user never sets it, so real keyless callers fail loud.
"""

import os
from typing import Optional


def _keyless_mock_allowed() -> bool:
    """True only when a test harness has EXPLICITLY opted into keyless->mock.

    Real callers never set ``KAIZEN_ALLOW_KEYLESS_MOCK``; a keyless resolution
    therefore returns ``None`` for them and fails loud at the node's #1947 gate.
    The kaizen unit harness sets it in ``tests/conftest.py`` so the deliberately
    keyless unit suite keeps dispatching to the registered mock provider.
    """
    return os.environ.get("KAIZEN_ALLOW_KEYLESS_MOCK") == "1"


def detect_provider_from_env() -> Optional[str]:
    """
    Env-first provider fallback: openai -> anthropic -> None (keyless).

    Returns:
        "openai" if OPENAI_API_KEY is set, else "anthropic" if
        ANTHROPIC_API_KEY is set, else ``None`` (#1952 — keyless no longer
        silently resolves to "mock"). Callers with an explicit provider
        configured MUST check that first and only fall back to this helper when
        none was given, so a real API key is never silently ignored. When this
        returns ``None`` the unresolved provider flows to ``LLMAgentNode``'s
        #1947 fail-loud ``ConfigurationError`` gate rather than dispatching
        fabricated mock content as a real answer.

        Exception (explicit test-harness opt-in): when
        ``KAIZEN_ALLOW_KEYLESS_MOCK=1`` is set — only the kaizen unit harness
        sets it — the keyless case returns "mock" so the deliberately-keyless
        unit suite keeps working. Real callers never set it and fail loud.
    """
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if _keyless_mock_allowed():
        return "mock"
    return None
