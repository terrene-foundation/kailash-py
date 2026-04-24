# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Discovery-driven ML tool-set construction for Kaizen agents.

Per ``specs/kaizen-ml-integration.md`` §2.4 (Agent Tool Discovery) and
the binding MUST clause in ``ml-engines-v2-addendum §E11.3 MUST 1``:
Kaizen agents (``BaseAgent``, ``DelegateEngine``, ``SupervisorAgent``,
and every descendant) MUST obtain ML-method signatures AT runtime via
``km.engine_info(engine_name)`` / ``km.list_engines()``. Hardcoded
``from kailash_ml.engines.<foo> import <Foo>`` imports in an agent's
tool-set construction path are a ``rules/specs-authority.md §5b`` drift
violation (HIGH) and are BLOCKED.

This module provides the single entry point agents use:

    from kaizen.ml import discover_ml_tools
    engines = discover_ml_tools(tenant_id=self._tenant_id)
    # → tuple of (name, version, module_path, signatures) descriptors
    # built by walking km.list_engines() + filtering by PACT envelope

No decision logic lives here — ``rules/agent-reasoning.md`` mandates
that the LLM reasons about which tool to call. This module is a dumb
data endpoint: it enumerates what's available and returns the full
list (optionally tenant-filtered). The LLM selects.

Version-sync invariant (§E11.3 MUST 3): ``EngineInfo.version`` MUST
equal ``kailash_ml.__version__`` at discovery time — the structural
defense against agents shipping compiled-in tool surfaces that drift
from the runtime package.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Protocol, runtime_checkable

__all__ = [
    "MLEngineDescriptor",
    "MLToolDiscoveryError",
    "MLRegistryUnavailableError",
    "discover_ml_tools",
]

logger = logging.getLogger(__name__)


class MLToolDiscoveryError(RuntimeError):
    """Base class for errors raised by the discovery path."""


class MLRegistryUnavailableError(MLToolDiscoveryError):
    """Raised when ``kailash_ml`` does not yet expose the registry helpers.

    Per spec §2.4 + §2.4.5: hardcoded engine imports are a ``§5b``
    drift violation. When the registry is not yet installed, agents
    MUST raise this typed error with an actionable message, NOT fall
    back to direct imports.
    """


@runtime_checkable
class _EngineInfoLike(Protocol):
    """Structural Protocol for ``kailash_ml.engines.registry.EngineInfo``.

    Agents MUST NOT re-declare the shape (``rules/specs-authority.md §5b``
    one-canonical-shape); this Protocol merely documents the attributes
    read at discovery time so the helper can type-check the response
    without importing the concrete class.
    """

    name: str
    version: str
    module_path: str
    signatures: tuple


class MLEngineDescriptor:
    """Opaque, read-only snapshot of one ``EngineInfo`` result.

    Held by agents at tool-set construction time. Immutable so the
    LLM's tool-spec list cannot be mutated mid-turn — a tool-list
    snapshot captured at agent start stays consistent across every
    LLM call inside that turn.

    Re-exports the ``EngineInfo`` public fields without re-declaring
    the dataclass shape (per spec §2.4.2: Kaizen agents import
    ``EngineInfo`` from ``kailash_ml.engines.registry`` rather than
    redefining it; this descriptor is a thin read-only projection).
    """

    __slots__ = ("_info",)

    def __init__(self, info: _EngineInfoLike) -> None:
        self._info = info

    @property
    def name(self) -> str:
        return str(self._info.name)

    @property
    def version(self) -> str:
        return str(self._info.version)

    @property
    def module_path(self) -> str:
        return str(self._info.module_path)

    @property
    def signatures(self) -> tuple:
        return tuple(self._info.signatures)

    @property
    def raw(self) -> _EngineInfoLike:
        """The underlying ``EngineInfo`` for direct field access."""
        return self._info

    def __repr__(self) -> str:  # pragma: no cover — debug aid
        return (
            f"MLEngineDescriptor(name={self.name!r}, version={self.version!r}, "
            f"module_path={self.module_path!r}, signatures=<{len(self.signatures)}>)"
        )


def _load_km_registry() -> tuple[Any, Any]:
    """Return ``(engine_info_fn, list_engines_fn)`` from the ``kailash_ml`` namespace.

    Raises :class:`MLRegistryUnavailableError` when the registry
    helpers are not yet installed in the running ``kailash_ml``. This
    is the single choke point that enforces §2.4.5 (no hardcoded
    engine imports): callers receive a typed error naming the missing
    registry rather than a ``ModuleNotFoundError`` from a surreptitious
    ``from kailash_ml.engines.training_pipeline import ...``.
    """
    try:
        import kailash_ml as km  # noqa: F401 — presence-probe
    except ImportError as e:
        raise MLRegistryUnavailableError(
            "kailash-ml is not installed — ML tool discovery unavailable; "
            "`pip install kailash-ml>=1.0` to enable km.engine_info / "
            "km.list_engines (spec kaizen-ml-integration.md §2.4)."
        ) from e

    engine_info = getattr(km, "engine_info", None)
    list_engines = getattr(km, "list_engines", None)
    if engine_info is None or list_engines is None:
        raise MLRegistryUnavailableError(
            "kailash_ml.engine_info / kailash_ml.list_engines are not yet "
            "exposed by the installed kailash-ml; upgrade to the release that "
            "ships ml-engines-v2-addendum §E11 registry before constructing "
            "ML-aware Kaizen agents. Hardcoded engine imports are BLOCKED per "
            "specs/kaizen-ml-integration.md §2.4.5 (§5b drift HIGH)."
        )
    return engine_info, list_engines


def discover_ml_tools(
    *,
    tenant_id: Optional[str] = None,
    clearance_filter: Optional[Any] = None,
) -> tuple[MLEngineDescriptor, ...]:
    """Return a tuple of engine descriptors for tool-set construction.

    Args:
        tenant_id: Optional tenant scope. When present, descriptors
            whose ``clearance_level`` exceeds the tenant's PACT envelope
            are filtered out via the caller-supplied ``clearance_filter``.
            Single-tenant deployments pass ``tenant_id=None`` and see
            every engine.
        clearance_filter: Optional callable
            ``(engine_info, tenant_id) -> bool``. When supplied, only
            engines for which the callable returns ``True`` are included.
            Per ``rules/agent-reasoning.md`` the LLM does ALL reasoning
            about which tool to USE — this filter is a PACT-envelope
            structural gate, not agent decision logic.

    Returns:
        An immutable tuple of :class:`MLEngineDescriptor` — ordering is
        preserved from the underlying ``km.list_engines()`` call.

    Raises:
        MLRegistryUnavailableError: ``km.engine_info`` / ``km.list_engines``
            not yet exposed (spec §2.4.5 — hardcoded imports are BLOCKED).

    Note:
        Per spec §2.4.4 (Version-Sync Invariant from §E11.3 MUST 3) the
        ``EngineInfo.version`` returned by the registry MUST equal
        ``kailash_ml.__version__`` — agents that observe drift between
        the two SHOULD surface it loudly; this helper DOES NOT hide the
        mismatch. The invariant is validated per-call by the Tier 2
        wiring test, not by this helper (which must work even in
        pre-release windows where the registry ships ahead of
        ``__version__``).
    """
    engine_info_fn, list_engines_fn = _load_km_registry()

    logger.info(
        "kaizen.ml.tool_discovery.start",
        extra={
            "tenant_id_present": tenant_id is not None,
            "clearance_filter_active": clearance_filter is not None,
            "mode": "real",
        },
    )

    raw_engines = tuple(list_engines_fn())

    if clearance_filter is not None:
        raw_engines = tuple(e for e in raw_engines if clearance_filter(e, tenant_id))

    descriptors = tuple(MLEngineDescriptor(e) for e in raw_engines)

    logger.info(
        "kaizen.ml.tool_discovery.ok",
        extra={
            "engine_count": len(descriptors),
            "mode": "real",
        },
    )

    # engine_info_fn is returned for callers that need per-engine lookup
    # (e.g. a BaseAgent that resolves an LLM tool-name choice back to the
    # canonical EngineInfo before invoking). Keeping it as a side-effect
    # of the helper (vs a separate import) preserves the §2.4.5 invariant
    # that every km.* discovery entry point is reached through this module.
    _ = engine_info_fn  # explicitly acknowledged — kept accessible via module
    return descriptors


def engine_info(engine_name: str) -> _EngineInfoLike:
    """Pass-through to ``km.engine_info`` with registry-availability guard.

    Agents that need per-engine metadata MUST call this helper rather
    than ``from kailash_ml import engine_info`` directly — routing
    through the helper is what prevents a future refactor from
    introducing a hardcoded engine import path under the discovery
    flag.
    """
    engine_info_fn, _ = _load_km_registry()
    return engine_info_fn(engine_name)
