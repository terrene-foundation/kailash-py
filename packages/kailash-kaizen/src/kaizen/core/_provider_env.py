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


def resolve_agent_provider(model: Optional[str], *, component: str = "") -> str:
    """Public provider resolution for an agent config (#2022).

    WHICH RESOLVER OWNS WHICH QUESTION
    ----------------------------------
    Kaizen deliberately keeps several provider resolvers, because they answer
    genuinely different questions with genuinely different failure contracts.
    #1952 ratified that non-equivalence; what it did NOT do is say which one a
    caller building an agent config should reach for. This function is that
    answer, and it is the ONLY one callers outside kaizen should use.

    * "Given a MODEL, which provider serves it?" -> canonical:
      :meth:`kaizen.llm.LlmProvider.from_model`. Its prefix table is DERIVED
      from the provider registry (``_PREFIX_TO_NAME``), so it cannot drift, and
      it fails closed with ``UnknownModelProvider``.
    * "Given the ENVIRONMENT, which provider is usable?" -> canonical:
      :func:`detect_provider_from_env` above.
    * "Given a full config, which provider plus credentials and endpoint?" ->
      canonical: ``kaizen.config.auto_detect_provider``.

    This function ADDS NO MAPPING OF ITS OWN. It composes the first two in a
    defined order, which is the whole reason it exists: publishing a fourth
    model->provider table would recreate exactly the drift #1952 ended. In
    particular it deliberately does NOT publish
    ``kaizen.nodes._env_model.detect_provider``, whose hand-maintained
    substring table is a weaker duplicate of the registry-derived one and is
    pinned to no registry.

    ORDER, AND WHY MODEL BEATS ENVIRONMENT
    --------------------------------------
    The model wins. A ``claude-*`` model must dispatch to Anthropic even when
    ``OPENAI_API_KEY`` happens to be set; the env-first order sent it to
    OpenAI, which is a silent wrong-vendor dispatch.

    The env fallback is retained for models OUTSIDE the registry's prefixes
    (local/Ollama builds, ``chatgpt-4o-latest``, fine-tuned names). Stated
    plainly rather than glossed: for such a model the fallback is a GUESS, and
    it can pick a vendor that does not serve the model. That is not a
    regression — it is exactly what every caller already got by leaving
    ``llm_provider`` unset — and it is strictly narrowed here, because every
    registry-recognised model now bypasses the guess entirely. Callers who
    need certainty for an unregistered model pass ``llm_provider`` explicitly.

    Args:
        model: The model identifier the agent will run.
        component: Short caller identifier surfaced in the error message.

    Returns:
        A provider name suitable for ``BaseAgentConfig.llm_provider``.

    Raises:
        ConfigurationError: The provider could not be resolved from either the
            model or the environment. Fails LOUD and names the fix — never
            returns ``None`` into the ``LLMAgentNode`` #1947 gate, whose error
            cannot say which model or component was responsible.
    """
    from kaizen.config.providers import ConfigurationError
    from kaizen.llm.provider import LlmProvider, UnknownModelProvider

    where = f" (component: {component})" if component else ""

    if isinstance(model, str) and model.strip():
        try:
            return LlmProvider.from_model(model).name
        except UnknownModelProvider:
            from_env = detect_provider_from_env()
            if from_env is not None:
                return from_env
        raise ConfigurationError(
            f"Could not resolve an LLM provider for model {model!r}{where}. "
            "The model is not served by any registered provider prefix, and no "
            "provider could be detected from the environment. Fix by passing "
            "llm_provider= explicitly on the agent config, or by setting a "
            "provider credential (e.g. OPENAI_API_KEY / ANTHROPIC_API_KEY)."
        )

    # Distinguish "no model" from "a model of the wrong type" — reporting
    # b"gpt-4o" as "no model was supplied" sends the reader looking for a
    # missing env var instead of at the value they actually passed.
    if model is None or (isinstance(model, str) and not model.strip()):
        detail = "no model was supplied"
    else:
        detail = f"model must be a non-empty string, got {type(model).__name__}"
    raise ConfigurationError(
        f"Could not resolve an LLM provider: {detail}{where}. "
        "Pass a model, and pass llm_provider= explicitly if the model is not "
        "served by a registered provider prefix."
    )
