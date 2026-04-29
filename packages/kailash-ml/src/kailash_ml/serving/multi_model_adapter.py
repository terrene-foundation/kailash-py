# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``MultiModelAdapter`` -- 1.1.x-shape back-compat shim for ``InferenceServer``.

Per ``specs/ml-serving.md §1.1`` + §2.1 the canonical 1.5.x architecture
ships ONE :class:`InferenceServer` per model: callers construct N
servers for N models. The 1.1.x architecture (which 1.5.0 hard-removed
without a deprecation cycle) shipped ONE server with an internal LRU
cache of MANY models accessed via ``warm_cache``/``load_model`` /
``predict(name, payload)``.

GH issue #700 surfaced the silent removal as a regression for users on
the 1.1.x signature. This adapter is the back-compat path:

* Accepts the 1.1.x ``__init__(*, registry=, cache_size=)``.
* Lazy-constructs one canonical :class:`InferenceServer` per model name
  via :meth:`InferenceServer.from_registry`, populated by
  :meth:`warm_cache`.
* Routes :meth:`predict(name, payload)` to the per-model server.
* Refuses :meth:`load_model(name, model)` -- registry is the
  authoritative source of truth in 1.5.x; user-supplied bytes are
  BLOCKED with a typed ``TypeError`` carrying the migration hint.

Per ``rules/facade-manager-detection.md`` MUST Rule 3 the adapter takes
its dependency (the framework's :class:`ModelRegistry`) explicitly --
no global lookup, no parallel construction. Per Rule 2 the wiring is
exercised by ``test_multi_model_adapter_wiring.py``.

Per ``rules/zero-tolerance.md`` Rule 6 (Implement Fully) every method
returns real data or raises a typed error -- there are no stubs or
silent drops.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Mapping, NoReturn

if TYPE_CHECKING:  # pragma: no cover - typing only
    from kailash_ml.engines.model_registry import ModelRegistry
    from kailash_ml.serving.server import InferenceServer


logger = logging.getLogger(__name__)


__all__ = ["MultiModelAdapter"]


class MultiModelAdapter:
    """Back-compat adapter for the 1.1.x ``InferenceServer`` signature.

    1.1.x users wrote::

        server = InferenceServer(registry=my_registry, cache_size=8)
        await server.warm_cache(["fraud", "churn"])
        result = await server.predict("fraud", {"amount": 1.2, ...})

    1.5.x removed that surface; the canonical replacement is per-model
    construction via :meth:`InferenceServer.from_registry`. This
    adapter restores the 1.1.x shape behind a ``DeprecationWarning``
    routed through :meth:`InferenceServer.__new__` so existing code
    keeps running while users migrate.

    Per ``rules/facade-manager-detection.md`` MUST Rule 3 the
    constructor takes the :class:`ModelRegistry` explicitly. Per
    ``rules/orphan-detection.md`` Rule 1 the adapter has a production
    call site (``InferenceServer.__new__`` routing) and a Tier-2
    wiring test.

    Parameters
    ----------
    registry:
        The framework's :class:`ModelRegistry`. The adapter does NOT
        construct its own registry -- it uses the caller-supplied
        instance so audit/tenant scoping flow through one source of
        truth (Rule 3).
    cache_size:
        1.1.x signature parameter. Retained for back-compat with the
        constructor shape; the internal cache is unbounded by default
        (lazy population via :meth:`warm_cache`). When the dict grows
        past ``cache_size``, the adapter logs a WARN -- per
        ``rules/observability.md`` Rule 3 it does NOT silently evict,
        which would surprise callers who relied on warmed entries. The
        canonical migration is to drop ``cache_size`` and call
        :meth:`InferenceServer.from_registry_many` instead.
    """

    def __init__(
        self,
        *,
        registry: "ModelRegistry",
        cache_size: int,
    ) -> None:
        if registry is None:
            raise ValueError(
                "MultiModelAdapter requires a registry; per "
                "rules/facade-manager-detection.md MUST Rule 3 the framework "
                "instance is a constructor argument, not a global lookup."
            )
        if not isinstance(cache_size, int) or cache_size < 1:
            raise ValueError(
                f"MultiModelAdapter.cache_size must be a positive integer, "
                f"got {cache_size!r}"
            )
        self._registry = registry
        self._cache_size = cache_size
        self._servers: dict[str, "InferenceServer"] = {}

    # ------------------------------------------------------------------
    # Public surface (read-only)
    # ------------------------------------------------------------------
    @property
    def registry(self) -> "ModelRegistry":
        """The :class:`ModelRegistry` this adapter routes through."""
        return self._registry

    @property
    def cache_size(self) -> int:
        """The 1.1.x ``cache_size`` setting (advisory)."""
        return self._cache_size

    @property
    def servers(self) -> Mapping[str, "InferenceServer"]:
        """Read-only view of the per-model server cache."""
        return dict(self._servers)

    # ------------------------------------------------------------------
    # warm_cache -- 1.1.x signature
    # ------------------------------------------------------------------
    async def warm_cache(self, names: list[str]) -> None:
        """Lazy-construct one :class:`InferenceServer` per model name.

        Per ``rules/observability.md`` Rule 2 every cross-boundary call
        (registry resolution) is logged. Per Rule 7 partial failures
        across the batch surface as WARN (not silent). Already-cached
        entries are skipped (idempotent).

        Parameters
        ----------
        names:
            List of model names. Each routes through
            :meth:`InferenceServer.from_registry` to resolve via the
            registry's alias layer (1.1.x callers typically pass bare
            names; the resolver raises if alias/version is required).

        Raises
        ------
        TypeError
            When ``names`` is not a list of strings.
        """
        # Lazy import to avoid a serving<->server cycle at module load.
        from kailash_ml.serving.server import InferenceServer

        if not isinstance(names, list):
            raise TypeError(
                f"MultiModelAdapter.warm_cache(names=...) expects list[str], "
                f"got {type(names).__name__}"
            )
        for name in names:
            if not isinstance(name, str) or not name:
                raise TypeError(
                    f"MultiModelAdapter.warm_cache(names=...) every entry "
                    f"must be a non-empty string; got {name!r}"
                )

        logger.info(
            "multi_model_adapter.warm_cache.start",
            extra={"names": list(names), "already_cached": list(self._servers.keys())},
        )

        errors: list[tuple[str, BaseException]] = []
        for name in names:
            if name in self._servers:
                continue  # idempotent
            try:
                server = await InferenceServer.from_registry(
                    name,
                    registry=self._registry,
                )
            except Exception as exc:  # surface partial failure per Rule 7
                errors.append((name, exc))
                logger.warning(
                    "multi_model_adapter.warm_cache.entry_failed",
                    extra={
                        "name": name,
                        "exc_type": type(exc).__name__,
                    },
                )
                continue
            self._servers[name] = server

        if len(self._servers) > self._cache_size:
            # Advisory WARN per Rule 7 (partial path) -- adapter does NOT
            # evict because eviction would silently invalidate predictions
            # on names the caller already warmed. Migration path is
            # InferenceServer.from_registry_many.
            logger.warning(
                "multi_model_adapter.cache_size_exceeded",
                extra={
                    "cache_size": self._cache_size,
                    "current_count": len(self._servers),
                },
            )

        if errors:
            # Match 1.1.x semantics: raise after the batch so the caller
            # sees the first failure but the successful entries are
            # available in self._servers. Per Rule 7 the WARN above
            # gives operators per-entry visibility.
            first_name, first_exc = errors[0]
            raise type(first_exc)(
                f"MultiModelAdapter.warm_cache failed on {first_name!r} "
                f"({len(errors)} of {len(names)} failed): {first_exc}"
            ) from first_exc

        logger.info(
            "multi_model_adapter.warm_cache.ok",
            extra={
                "warmed": len(self._servers),
                "requested": len(names),
            },
        )

    # ------------------------------------------------------------------
    # load_model -- BLOCKED in 1.5.x architecture
    # ------------------------------------------------------------------
    async def load_model(self, name: str, model: Any) -> NoReturn:
        """Refuse user-supplied bytes per spec §1.1 + §2.1.

        The 1.1.x ``load_model(name, model)`` accepted user-supplied
        bytes/dicts. The 1.5.x architecture has the
        :class:`ModelRegistry` as the sole authoritative source of
        truth -- byte injection bypasses signature validation, audit,
        and tenant isolation. This method MUST raise.

        Per ``rules/zero-tolerance.md`` Rule 3 the failure is loud +
        typed, never a silent drop.

        Parameters
        ----------
        name, model:
            Documented for signature parity with 1.1.x. Both arguments
            are inspected only to compose the error message; the model
            object is never deserialized or stored.

        Raises
        ------
        TypeError
            Always. The message includes the migration path:
            register the model via
            :meth:`ModelRegistry.register_model` first, then call
            :meth:`warm_cache` (or rely on lazy resolution via
            :meth:`predict`).
        """
        # Reference the args so static analyzers do not flag them as
        # unused; the values are inspected via repr() for the error.
        _name = repr(name)
        _model_kind = type(model).__name__
        raise TypeError(
            "MultiModelAdapter.load_model with user-supplied bytes is removed "
            "in kailash-ml 1.5.x; the ModelRegistry is the authoritative "
            "source of truth (specs/ml-serving.md §1.1 + §2.1). "
            f"Migration: await registry.register_model({_name}, artifact_bytes, "
            f"signature=...) first, then await adapter.warm_cache([{_name}]) "
            f"or rely on lazy load via adapter.predict({_name}, payload). "
            f"(Got name={_name}, model={_model_kind}.)"
        )

    # ------------------------------------------------------------------
    # predict -- name-keyed dispatch
    # ------------------------------------------------------------------
    async def predict(self, name: str, payload: Any) -> Any:
        """Dispatch a prediction request to the per-model server.

        Per ``rules/observability.md`` Rule 1 entry+exit log lines are
        emitted for the dispatch boundary. The per-model server has
        its own observability stack (see :meth:`InferenceServer.predict`).

        Parameters
        ----------
        name:
            Model name. Must already be present in the cache (call
            :meth:`warm_cache` first). The adapter does NOT lazy-load
            on miss because the 1.1.x semantic was "warm explicitly,
            then predict"; auto-loading would surprise callers who
            relied on the warm-set as a authorization boundary.
        payload:
            Forwarded to :meth:`InferenceServer.predict`. Either a
            single-record mapping or a batch payload.

        Returns
        -------
        Whatever :meth:`InferenceServer.predict` returns.

        Raises
        ------
        KeyError
            When ``name`` is not in the cache. The message includes
            the migration hint to call :meth:`warm_cache` first.
        TypeError
            When ``name`` is not a non-empty string.
        """
        if not isinstance(name, str) or not name:
            raise TypeError(
                f"MultiModelAdapter.predict(name, ...) -- name must be a "
                f"non-empty string, got {name!r}"
            )
        if name not in self._servers:
            raise KeyError(
                f"model {name!r} not in cache; call warm_cache([{name!r}]) first"
            )

        server = self._servers[name]
        # If the per-model server hasn't been started yet, start it now.
        # 1.1.x semantics did not require an explicit start -- warm_cache +
        # predict was the contract -- so we restore that by starting on
        # first predict. Per rules/observability.md Rule 4 we log the
        # transition.
        if server.status == "starting":
            logger.info(
                "multi_model_adapter.predict.starting_server_lazy",
                extra={"name": name},
            )
            await server.start()

        return await server.predict(payload)
