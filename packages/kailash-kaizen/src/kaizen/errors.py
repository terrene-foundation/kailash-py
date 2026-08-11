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


class ObservabilityNotImplemented(RuntimeError):
    """An observability subsystem was explicitly requested but does not exist.

    Raised by :meth:`kaizen.smart_defaults.SmartDefaultsManager.create_observability`
    when a caller sets ``enable_tracing`` / ``enable_metrics`` /
    ``enable_logging`` / ``enable_audit`` to ``True`` explicitly. None of the
    four subsystems is implemented: the hook classes the call site imports do
    not exist, and neither do the handler methods it registers.

    Previously each import raised ``ImportError``, which was caught and logged
    as "not available, skipping" — so the flags reported success while
    registering nothing (``rules/zero-tolerance.md`` Rule 2 stub + Rule 3
    silent fallback). ``enable_audit`` is the sharp case: audit trails that
    silently record nothing are invisible exactly when they matter.

    Raised ONLY for an EXPLICIT ``True``. The flags default to ``None``, which
    warns loudly and otherwise behaves as before — raising on the default
    would break every agent construction, including callers who never
    mentioned observability.

    Tracking issue for whether these subsystems get implemented or removed:
    #2084.

    Attributes:
        subsystem: Human name of the missing subsystem (e.g. ``"audit"``).
        flag: The config flag the caller set (e.g. ``"enable_audit"``).
    """

    def __init__(self, subsystem: str, flag: str, provides: str) -> None:
        self.subsystem = subsystem
        self.flag = flag
        super().__init__(
            f"{flag}=True was requested, but the {subsystem} subsystem is NOT "
            f"IMPLEMENTED — it would have provided {provides}. There is "
            f"nothing to install; the hook class and its handlers do not "
            f"exist in this package. Set {flag}=False to proceed without it, "
            f"or leave it unset to get a warning instead of this error. "
            f"Tracking: https://github.com/terrene-foundation/kailash-py/issues/2084"
        )


__all__ = ["EnvModelMissing", "ObservabilityNotImplemented", "ProviderUndetectable"]
