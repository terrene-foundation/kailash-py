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

from kaizen.errors import EnvModelMissing

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


def detect_provider(model: str) -> str:
    """Best-effort provider detection from a model identifier.

    Mirrors the auth-node family convention: ``gpt-*``/``o1-*`` map to
    openai, ``claude-*`` maps to anthropic, anything else maps to mock
    (test-friendly default; callers that need a different real provider
    pass ``provider=`` explicitly).
    """
    lowered = model.lower()
    if "gpt" in lowered or "o1" in lowered:
        return "openai"
    if "claude" in lowered:
        return "anthropic"
    return "mock"
