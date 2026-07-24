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
different, fail-loud contract used by a different call path. Every site this
module serves currently defaults to the mock/test provider when no real key
is present (a deliberate, existing, lenient-construction contract), so this
helper mirrors ONLY `Agent._get_provider_for_config()`'s narrower 3-way
order. Changing that contract (e.g. raising instead of defaulting to mock)
is out of scope for this fix — see the LLMAgentNode provider `default="mock"`
fail-loud change tracked as a separate, higher-blast-radius follow-up.
"""

import os


def detect_provider_from_env() -> str:
    """
    Env-first provider fallback: openai -> anthropic -> mock.

    Returns:
        "openai" if OPENAI_API_KEY is set, else "anthropic" if
        ANTHROPIC_API_KEY is set, else "mock". Mirrors
        `Agent._get_provider_for_config()`'s exact fallback order — callers
        with an explicit provider configured MUST check that first and only
        fall back to this helper when none was given, so a real API key is
        never silently ignored in favor of LLMAgentNode's own "mock"
        parameter default.
    """
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "mock"
