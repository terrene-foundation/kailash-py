"""
Kaizen top-level error types.

This module hosts errors that span the kaizen package surface — not the
LLM-provider-specific errors (`kaizen.llm.errors`) or the L3-runtime errors
(`kaizen.l3.*.errors`). Place a typed error here when it is raised by a
public-API entry point (CoreAgent, GovernedSupervisor, top-level pipelines)
and consumers need to catch it without depending on a deep submodule.

Errors:
    EnvModelMissing — raised when a required model-name env var
        (e.g. ``KAIZEN_DEFAULT_MODEL``) is unset and no caller-supplied
        override is given. Per ``rules/env-models.md``, model strings
        MUST come from ``.env``; hardcoded fallbacks are BLOCKED.
"""

from __future__ import annotations


class EnvModelMissing(RuntimeError):
    """A required model-name environment variable is unset.

    Raised when an entry point (CoreAgent default config, GovernedSupervisor
    default ``model`` argument, ...) needs a model identifier and neither the
    caller nor any environment variable provided one. The default fallback to
    a hardcoded literal (e.g. ``"gpt-3.5-turbo"``, ``"claude-sonnet-4-6"``)
    is BLOCKED by ``rules/env-models.md`` because it locks deployments to a
    single provider and prevents per-environment model selection.

    The error message MUST name the env var the caller can set, so the user
    sees a single actionable instruction instead of a generic missing-config
    failure deep in the call stack.

    Attributes:
        env_var: Name of the environment variable that was checked and
            found unset.
        component: Short identifier for the component that raised
            (e.g. ``"CoreAgent"``, ``"GovernedSupervisor"``) — used to
            disambiguate when multiple call sites surface the same error.
    """

    def __init__(self, env_var: str, component: str = "") -> None:
        self.env_var = env_var
        self.component = component
        location = f" ({component})" if component else ""
        super().__init__(
            f"{env_var} environment variable is required but not set{location}. "
            f"Set {env_var} in your .env file (e.g. {env_var}=gpt-4o-mini) or "
            f"pass an explicit model= argument. Per rules/env-models.md, "
            f"hardcoded model strings are BLOCKED — model identifiers must "
            f"come from .env."
        )


class ProviderUndetectable(RuntimeError):
    """No LLM provider could be inferred from a model identifier.

    Raised by :func:`kaizen.nodes._env_model.detect_provider` when a model
    name matches no known provider family AND the caller did not pass an
    explicit ``provider=``. Falling back silently (to a mock provider or an
    arbitrary real one) is BLOCKED in production node constructors — for
    security/auth/compliance nodes a silent mock route is a fail-open
    (``rules/zero-tolerance.md`` Rule 3).

    Attributes:
        model: The model identifier that could not be classified.
        component: Short identifier for the component that raised.
    """

    def __init__(self, model: str, component: str = "") -> None:
        self.model = model
        self.component = component
        location = f" ({component})" if component else ""
        super().__init__(
            f"Could not detect an LLM provider for model {model!r}{location}. "
            f"Pass an explicit provider= argument (e.g. provider='openai', "
            f"'anthropic', 'ollama', 'google', or 'mock' for tests). Known "
            f"auto-detected families: gpt-*/o1-*/davinci-* -> openai, "
            f"claude-* -> anthropic, llama/mistral/mixtral/bakllava -> ollama, "
            f"gemini-* -> google."
        )


__all__ = ["EnvModelMissing", "ProviderUndetectable"]
