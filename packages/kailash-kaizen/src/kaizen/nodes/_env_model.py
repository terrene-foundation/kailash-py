"""Env-var model resolution + provider detection for AI-enhanced nodes.

Per ``rules/env-models.md``, model identifiers MUST come from ``.env``
(``KAIZEN_DEFAULT_MODEL``); hardcoded constructor defaults are BLOCKED
because they lock deployments to a single provider and prevent
per-environment model selection. Every AI-enhanced node constructor that
accepts an optional model argument resolves it through
:func:`resolve_default_model` so the failure mode is one actionable
:class:`kaizen.errors.EnvModelMissing` instead of a stale hardcoded literal.
"""

from __future__ import annotations

import os

from kaizen.errors import EnvModelMissing, ProviderUndetectable

KAIZEN_DEFAULT_MODEL_ENV = "KAIZEN_DEFAULT_MODEL"


def resolve_default_model(component: str, model: str | None = None) -> str:
    """Return ``model`` if given, else ``KAIZEN_DEFAULT_MODEL``, else raise.

    Args:
        component: Short identifier for the calling node class, surfaced in
            the :class:`~kaizen.errors.EnvModelMissing` message
            (e.g. ``"SSOAuthenticationNode"``).
        model: Caller-supplied model identifier; wins over the env var.

    Raises:
        EnvModelMissing: ``model`` is falsy and ``KAIZEN_DEFAULT_MODEL``
            is unset — the message names the env var so the user sees a
            single actionable instruction.
    """
    if model:
        return model
    env_model = os.environ.get(KAIZEN_DEFAULT_MODEL_ENV)
    if not env_model:
        raise EnvModelMissing(env_var=KAIZEN_DEFAULT_MODEL_ENV, component=component)
    return env_model


def detect_provider(model: str, component: str = "") -> str:
    """Provider detection from a model identifier — fail-closed.

    Detects the four known provider families (matching the wider
    ``agent_config`` convention). An unrecognized model raises a typed
    :class:`~kaizen.errors.ProviderUndetectable` instead of falling back:
    the prior inline convention silently routed unknown models to the MOCK
    provider, which in production security/auth/compliance nodes is a
    fail-open (the node "works" while its AI path returns canned mock
    output). Callers that genuinely want the mock provider pass
    ``provider="mock"`` explicitly.
    """
    lowered = model.lower()
    if "gpt" in lowered or "o1" in lowered or "davinci" in lowered:
        return "openai"
    if "claude" in lowered:
        return "anthropic"
    if any(t in lowered for t in ("llama", "mistral", "mixtral", "bakllava")):
        return "ollama"
    if "gemini" in lowered:
        return "google"
    raise ProviderUndetectable(model=model, component=component)
