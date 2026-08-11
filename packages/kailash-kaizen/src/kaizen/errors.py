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


def configuration_error_types() -> tuple[type[BaseException], ...]:
    """Error classes meaning "this was never wired", not "the run failed" (#2022).

    Imported lazily: ``kaizen.config`` and ``kaizen.llm`` sit above this module
    in the import graph, so module-scope imports would create a cycle.
    """
    from kaizen.config.providers import ConfigurationError
    from kaizen.llm.errors import MissingCredential
    from kaizen.llm.provider import UnknownModelProvider

    return (
        ConfigurationError,
        EnvModelMissing,
        ProviderUndetectable,
        UnknownModelProvider,
        MissingCredential,
    )


def unwrap_configuration_error(exc: BaseException) -> BaseException | None:
    """Return the configuration-class error in ``exc``'s cause chain, else None.

    The chain walk is the load-bearing part. A ``ConfigurationError`` raised
    inside ``LLMAgentNode`` reaches the strategy already wrapped by the runtime
    as ``WorkflowExecutionError("Node 'agent_exec' execution failed: ...")``, so
    a plain ``isinstance(exc, ConfigurationError)`` is FALSE exactly where the
    decision has to be made. Walking the cause chain is what makes the check
    discriminate a broken SETUP from a failed RUN.

    ONLY ``__cause__`` is followed, deliberately — NOT ``__context__``.
    ``__context__`` is set IMPLICITLY on any exception raised while another is
    being handled, so following it would mean an unrelated failure inside an
    ``except ConfigurationError:`` block gets REPLACED by that unrelated
    ConfigurationError on the way out. ``__cause__`` is only ever set by an
    explicit ``raise ... from``, which is the deliberate "this wraps that"
    signal — and it is what every wrapping site on this path actually uses
    (``raise WorkflowExecutionError(...) from e`` in both the sync and async
    runtimes). Following ``__context__`` would buy nothing here and would open
    a false-positive class.

    ``seen`` guards against a self-referential chain, which is reachable: the
    ``AgentLoop`` handler re-raises a deep cause from inside ``except
    Exception as error``, so the raised error's ``__context__`` points back at
    the wrapper whose ``__cause__`` is the raised error.
    """
    types = configuration_error_types()
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, types):
            return current
        current = current.__cause__
    return None


def raise_if_configuration_error(results: object) -> None:
    """Re-raise a configuration error the RUNTIME turned into a result dict (#2022).

    ``LocalRuntime`` does not raise when a node fails: it returns

        {node_id: {"failed": True, "error": "...", "error_type": "...",
                   "_exception": <the real exception object>}}

    so a strategy that only guards with ``try/except`` around ``runtime.execute``
    never sees an exception at all. That is a THIRD swallow, below the two in
    the strategies, and it is why the sync strategies kept reporting an
    unresolved provider as malformed model output.

    ``_exception`` preserves the exception OBJECT, which is what keeps this
    check structural — an ``isinstance`` walk over the cause chain, not
    substring matching on a rendered message. Matching on message text is the
    thing that missed this class in the first place.

    Silent by design when nothing failed, so it is safe to call unconditionally
    after every ``execute``.
    """
    if not isinstance(results, dict):
        return
    for node_result in results.values():
        if not isinstance(node_result, dict) or not node_result.get("failed"):
            continue
        exception = node_result.get("_exception")
        if isinstance(exception, BaseException):
            configuration_error = unwrap_configuration_error(exception)
            if configuration_error is not None:
                raise configuration_error


__all__ = [
    "EnvModelMissing",
    "ProviderUndetectable",
    "configuration_error_types",
    "unwrap_configuration_error",
    "raise_if_configuration_error",
]
