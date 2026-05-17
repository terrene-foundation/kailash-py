"""Deprecated compatibility shim for the historical ``kaizen.api`` module.

The unified Agent API historically lived under ``kaizen.api`` (``from
kaizen.api import Agent``). The structural-split refactor (#75) relocated the
canonical async Agent API to ``kaizen_agents.api`` and re-exported the primary
entry point at the package root (``from kaizen import Agent``). The
``kaizen.api`` module was removed outright with no deprecation cycle, so
``from kaizen.api import Agent`` began raising ``ModuleNotFoundError`` on every
published release — a hard break for every downstream caller on first
``pip install --upgrade``.

This module restores ``kaizen.api`` as a deprecation shim per the SDK's
remove-fully discipline (``rules/zero-tolerance.md`` Rule 6a): every public
symbol that historically lived under ``kaizen.api`` resolves through this
module and emits a ``DeprecationWarning`` naming the new import path on
attribute access.

Migration
---------
    # Old (deprecated):
    from kaizen.api import Agent

    # New:
    from kaizen import Agent

The historical surface (recovered from the pre-#75 ``kaizen/api/__init__.py``
and the canonical ``kaizen_agents/api/__init__.py``):

    Agent, AgentConfig, AgentResult, ToolCallRecord, CapabilityPresets,
    AgentCapabilities, ExecutionMode, MemoryDepth, ToolAccess,
    ConfigurationError, validate_configuration,
    validate_model_runtime_compatibility, resolve_memory_shortcut,
    resolve_runtime_shortcut, resolve_tool_access_shortcut

``Agent`` resolves through ``kaizen`` itself so the established
``kaizen_agents`` → ``kaizen.core.agents`` fallback chain is preserved on
installs without the optional ``kaizen-agents`` package. Every other symbol
lived only in the canonical ``kaizen_agents.api`` module; resolving one of
them without ``kaizen-agents`` installed raises a typed ``ImportError`` that
names the missing package and the new import path.
"""

from __future__ import annotations

import warnings

# Public symbols that historically lived under ``kaizen.api``. ``Agent`` is
# resolved via ``kaizen`` (preserving the kaizen_agents → CoreAgent fallback);
# every other symbol lived only in ``kaizen_agents.api``.
_KAIZEN_ROOT_SYMBOLS = frozenset({"Agent"})
_KAIZEN_AGENTS_API_SYMBOLS = frozenset(
    {
        "AgentConfig",
        "AgentResult",
        "ToolCallRecord",
        "CapabilityPresets",
        "AgentCapabilities",
        "ExecutionMode",
        "MemoryDepth",
        "ToolAccess",
        "ConfigurationError",
        "validate_configuration",
        "validate_model_runtime_compatibility",
        "resolve_memory_shortcut",
        "resolve_runtime_shortcut",
        "resolve_tool_access_shortcut",
    }
)

__all__ = sorted(_KAIZEN_ROOT_SYMBOLS | _KAIZEN_AGENTS_API_SYMBOLS)


def __getattr__(name: str) -> object:
    """Resolve a historical ``kaizen.api`` symbol, emitting a deprecation.

    PEP 562 module ``__getattr__`` so the ``DeprecationWarning`` fires on
    attribute access (including ``from kaizen.api import Agent``), not merely
    on package import.
    """
    if name in _KAIZEN_ROOT_SYMBOLS:
        warnings.warn(
            f"'kaizen.api.{name}' is deprecated and will be removed in a "
            f"future major release. Import from 'kaizen' instead: "
            f"'from kaizen import {name}'.",
            DeprecationWarning,
            stacklevel=2,
        )
        import kaizen

        return getattr(kaizen, name)

    if name in _KAIZEN_AGENTS_API_SYMBOLS:
        warnings.warn(
            f"'kaizen.api.{name}' is deprecated and will be removed in a "
            f"future major release. Import from 'kaizen_agents.api' instead: "
            f"'from kaizen_agents.api import {name}'.",
            DeprecationWarning,
            stacklevel=2,
        )
        try:
            import kaizen_agents.api as _kaizen_agents_api
        except ImportError as exc:  # pragma: no cover - optional sibling
            raise ImportError(
                f"'kaizen.api.{name}' requires the optional 'kaizen-agents' "
                f"package. Install it ('pip install kaizen-agents') and import "
                f"from 'kaizen_agents.api' instead: "
                f"'from kaizen_agents.api import {name}'."
            ) from exc
        return getattr(_kaizen_agents_api, name)

    raise AttributeError(f"module 'kaizen.api' has no attribute {name!r}")


def __dir__() -> list[str]:
    return list(__all__)
