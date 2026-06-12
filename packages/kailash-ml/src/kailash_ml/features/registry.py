# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``FeatureRegistry`` — durable, DataFlow-backed store of authored feature groups.

The registry persists registered :class:`~kailash_ml.features.feature_group.FeatureGroup`
/ :class:`~kailash_ml.features.schema.FeatureSchema` definitions (name, version,
content_hash, tenant, serialized schema) in a DataFlow ``@db.model``-backed table
and ENFORCES version immutability at the registry-mutation site.

**Composition, not a constructor flag (spec §11.6).** The registry is a SEPARATE
object the caller constructs and holds — it is NOT a ``FeatureStore.__init__``
kwarg. ``FeatureStore``'s constructor surface stays intentionally narrow
(``rules/facade-manager-detection.md`` Rule 3); registry persistence is added by
composition, mirroring the design constraint in
``workspaces/fm2-feature-store-m2-py/01-analysis/02-m2-surface-design.md`` § E.

**Immutability is a DB constraint, not a hand-rolled dict check (framework-first /
zero-tolerance Rule 4).** The backing model carries a DB-enforced
``UNIQUE(tenant_id, name, version)`` index (DataFlow ``__dataflow__["indexes"]``
with ``unique: True`` → ``CREATE UNIQUE INDEX``). A re-registration that would
mutate a frozen ``(tenant, name, version)`` is rejected at the DB boundary; the
registry pairs that structural guard with a ``content_hash`` cross-check so the
typed error names WHY (different content) and an IDENTICAL re-registration is
idempotent rather than an error.

Per ``rules/orphan-detection.md §6`` the public symbol is eagerly importable from
``kailash_ml.features`` and listed in its ``__all__``.

See ``specs/ml-feature-store.md §11.3`` (version immutability) + §6.3 (error
taxonomy).
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from kailash_ml.features.cache_keys import (
    CANONICAL_SINGLE_TENANT_SENTINEL,
    validate_tenant_id,
)
from kailash_ml.features.feature_group import FeatureGroup
from kailash_ml.features.schema import FeatureSchema

if TYPE_CHECKING:  # avoid eager DataFlow import on type-only paths
    from dataflow.core.engine import DataFlow

__all__ = ["FeatureRegistry"]

logger = logging.getLogger(__name__)

# DataFlow model name + the DB-enforced composite-unique index name. The model is
# registered lazily on first use (see :meth:`FeatureRegistry._ensure_model`) so
# importing this module never forces a DataFlow import.
_MODEL_NAME = "KmlFeatureRegistry"
_UNIQUE_INDEX_NAME = "uq_kml_feature_registry_tnv"

# Substring the DataFlow Express layer surfaces when the DB-enforced
# UNIQUE(tenant_id, name, version) index rejects a conflicting INSERT. The
# registry translates this structural signal into the typed immutability error
# so the DB constraint — not a Python-only check — is the load-bearing guard
# (closes the check-then-insert race window a dict check would leave open).
# DataFlow does not surface a typed integrity exception (it propagates the raw
# driver IntegrityError), so we match the per-dialect UNIQUE-violation text.
# SQLite: "UNIQUE constraint failed: ..."; PostgreSQL: "duplicate key value
# violates unique constraint ..."; MySQL/MariaDB: "Duplicate entry '...' for
# key ...". (Follow-up: a typed dataflow integrity exception would let this
# catch a class instead of string-sniffing — tracked out of FM2 scope.)
_DB_UNIQUE_VIOLATION_MARKERS = (
    "unique constraint failed",  # SQLite
    "duplicate key value violates unique constraint",  # PostgreSQL
    "duplicate entry",  # MySQL / MariaDB
)


class FeatureRegistry:
    """Durable registry of authored feature groups with version immutability.

    Mirrors the ``FeatureStore`` Rule-3 constructor shape: takes the live
    ``DataFlow`` instance the registry persists through. The backing table is
    created lazily (DataFlow ``auto_migrate``) on first ``register`` / ``get`` /
    ``list`` so constructing a registry is cheap and import-safe.

    Parameters
    ----------
    dataflow:
        The live ``DataFlow`` instance backing persistence. Required — a
        registry with no backing store cannot persist or read (composition,
        ``rules/facade-manager-detection.md`` Rule 3).
    default_tenant_id:
        Tenant used when ``register`` / ``get`` / ``list`` are called without an
        explicit ``tenant_id``. Defaults to the canonical single-tenant sentinel
        ``"_single"`` (``ml-tracking.md §7.2``).
    """

    def __init__(
        self,
        dataflow: "DataFlow",
        *,
        default_tenant_id: str = CANONICAL_SINGLE_TENANT_SENTINEL,
    ) -> None:
        if dataflow is None:
            raise TypeError(
                "FeatureRegistry(dataflow=...) requires a live DataFlow instance "
                "(composition, not a FeatureStore kwarg — spec §11.6)"
            )
        # Validate the default tenant eagerly so a bad sentinel fails at
        # construction, not at first write.
        self._default_tenant_id = validate_tenant_id(
            default_tenant_id, operation="FeatureRegistry.__init__"
        )
        self._df = dataflow
        self._model_ready = False

    # ------------------------------------------------------------------
    # Lazy model registration
    # ------------------------------------------------------------------

    def _ensure_model(self) -> None:
        """Register the backing ``@db.model`` once, with the DB-unique index.

        The model carries ``__dataflow__["indexes"]`` with ``unique: True`` over
        ``(tenant_id, name, version)``; DataFlow auto-migration emits a real
        ``CREATE UNIQUE INDEX`` (verified DB-enforced on SQLite + parameterised
        by DataFlow — no raw SQL, no hand-rolled uniqueness).
        """
        if self._model_ready:
            return

        df = self._df

        @df.model
        class KmlFeatureRegistry:  # noqa: N801 — DataFlow model name is the class name
            tenant_id: str
            name: str
            version: int
            content_hash: str
            # Canonical JSON of FeatureSchema.to_dict() — rehydrated on get().
            schema_json: str
            __dataflow__ = {
                "indexes": [
                    {
                        "name": _UNIQUE_INDEX_NAME,
                        "fields": ["tenant_id", "name", "version"],
                        "unique": True,
                    },
                ]
            }

        # auto_migrate creates the table + the UNIQUE index on first connect.
        df._ensure_connected()
        self._model_ready = True

    # ------------------------------------------------------------------
    # Tenant resolution
    # ------------------------------------------------------------------

    def _resolve_tenant(self, tenant_id: str | None, *, operation: str) -> str:
        return validate_tenant_id(
            tenant_id if tenant_id is not None else self._default_tenant_id,
            operation=operation,
        )

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    async def register(
        self,
        feature_group: FeatureGroup,
        *,
        tenant_id: str | None = None,
    ) -> None:
        """Persist a :class:`FeatureGroup`'s schema under ``(tenant, name, version)``.

        Version immutability is enforced two ways that compose:

        * **DB UNIQUE constraint** — the backing model's
          ``UNIQUE(tenant_id, name, version)`` index rejects any second INSERT
          for an already-registered tuple at the database boundary.
        * **content_hash cross-check** — on a conflict the registry compares the
          incoming ``content_hash`` against the frozen row's. If they MATCH the
          call is idempotent (no error, no duplicate row). If they DIFFER the
          caller is attempting to mutate a frozen version and
          :class:`~kailash_ml.errors.FeatureVersionImmutableError` is raised.

        Evolution must be a forward version bump: registering a NEW
        ``content_hash`` under an EXISTING ``(tenant, name)`` at a version that
        is NOT strictly greater than the highest frozen version raises
        :class:`~kailash_ml.errors.FeatureEvolutionError` — route evolution
        through :meth:`FeatureSchema.with_features` (``bump_version=True``).

        Parameters
        ----------
        feature_group:
            The authored group to persist. Only its frozen
            :class:`FeatureSchema` (name / version / content_hash / fields) is
            stored — the bound ``dataflow`` / ``@feature`` callables are NOT
            persisted (a rehydrated group from :meth:`get` is a pure declarative
            handle).
        tenant_id:
            Tenant scope; defaults to the registry's ``default_tenant_id``.
            Version immutability is per-tenant — tenant A's ``(x, v1)`` and
            tenant B's ``(x, v1)`` are independent rows.

        Raises
        ------
        kailash_ml.errors.FeatureVersionImmutableError
            Re-registering ``(tenant, name, version)`` with a different
            ``content_hash``.
        kailash_ml.errors.FeatureEvolutionError
            Registering a changed schema at a non-forward version.
        """
        if not isinstance(feature_group, FeatureGroup):
            raise TypeError(
                "FeatureRegistry.register(...) expects a FeatureGroup, got "
                f"{type(feature_group).__name__}"
            )
        self._ensure_model()
        tenant = self._resolve_tenant(tenant_id, operation="FeatureRegistry.register")

        schema = feature_group.schema
        name = schema.name
        version = schema.version
        content_hash = schema.content_hash

        # Read every frozen version for this (tenant, name) up front. This drives
        # BOTH the idempotency/immutability decision AND the evolution
        # monotonicity check. The DB UNIQUE index is the structural backstop that
        # closes the check-then-insert race even if two callers race here.
        existing = await self._df.express.list(
            _MODEL_NAME,
            filter={"tenant_id": tenant, "name": name},
            limit=10_000,  # frozen-version scan drives immutability/evolution; no 100-row cap
        )

        same_version = next(
            (row for row in existing if int(row["version"]) == version), None
        )
        if same_version is not None:
            frozen_hash = same_version["content_hash"]
            if frozen_hash == content_hash:
                # Idempotent re-registration of the identical frozen schema.
                logger.debug(
                    "feature_registry.register.idempotent",
                    extra={
                        "tenant_id": tenant,
                        "name": name,
                        "version": version,
                    },
                )
                return
            from kailash_ml.errors import FeatureVersionImmutableError

            raise FeatureVersionImmutableError(
                reason=(
                    f"feature version {name!r} v{version} is frozen; a different "
                    f"content_hash cannot be registered (frozen={frozen_hash!r}, "
                    f"incoming={content_hash!r}). Evolve via "
                    f"FeatureSchema.with_features(bump_version=True)."
                ),
                tenant_id=tenant,
            )

        # No row at this exact version. If OTHER versions exist for this
        # (tenant, name), the new registration is an evolution and MUST bump
        # forward: the new version must be strictly greater than every frozen
        # version. A non-monotonic evolution (same/lower version carrying a new
        # schema under an existing name) is rejected.
        if existing:
            highest_frozen = max(int(row["version"]) for row in existing)
            if version <= highest_frozen:
                from kailash_ml.errors import FeatureEvolutionError

                raise FeatureEvolutionError(
                    reason=(
                        f"invalid evolution for {name!r}: version {version} is not "
                        f"strictly greater than the highest frozen version "
                        f"{highest_frozen}. Schema evolution MUST advance the "
                        f"version — use FeatureSchema.with_features(bump_version=True)."
                    ),
                    tenant_id=tenant,
                )

        # Persist. The DB UNIQUE(tenant_id, name, version) index is the
        # load-bearing immutability guard: if a concurrent caller inserted the
        # same tuple between the read above and this write, the DB rejects it and
        # we translate the structural signal into the typed immutability error.
        try:
            await self._df.express.create(
                _MODEL_NAME,
                {
                    "tenant_id": tenant,
                    "name": name,
                    "version": version,
                    "content_hash": content_hash,
                    "schema_json": json.dumps(schema.to_dict(), sort_keys=True),
                },
            )
        except Exception as exc:  # noqa: BLE001 — re-raised below; not swallowed
            _err = str(exc).lower()
            if any(_m in _err for _m in _DB_UNIQUE_VIOLATION_MARKERS):
                from kailash_ml.errors import FeatureVersionImmutableError

                raise FeatureVersionImmutableError(
                    reason=(
                        f"feature version {name!r} v{version} is frozen "
                        f"(DB UNIQUE(tenant_id, name, version) rejected a "
                        f"conflicting registration)."
                    ),
                    tenant_id=tenant,
                ) from exc
            # Any other persistence failure is a real error — never swallow
            # (rules/zero-tolerance.md Rule 3).
            raise

        logger.debug(
            "feature_registry.register.ok",
            extra={
                "tenant_id": tenant,
                "name": name,
                "version": version,
                "content_hash": content_hash,
            },
        )

    async def get(
        self,
        name: str,
        version: int,
        *,
        tenant_id: str | None = None,
    ) -> FeatureGroup:
        """Read back a registered :class:`FeatureGroup` by ``(name, version)``.

        Returns a PURE-DECLARATIVE :class:`FeatureGroup` (no bound ``dataflow``
        / no ``@feature`` callables — those are not persisted). The rehydrated
        group's ``schema`` / ``content_hash`` / ``version`` match what was
        registered.

        Parameters
        ----------
        name:
            The group / schema name.
        version:
            The exact frozen version to read.
        tenant_id:
            Tenant scope; defaults to the registry's ``default_tenant_id``.
            Reads are tenant-isolated — a version registered for tenant A is
            NOT visible under tenant B.

        Raises
        ------
        kailash_ml.errors.FeatureGroupNotFoundError
            No group of ``name`` is registered for the tenant at ANY version.
        kailash_ml.errors.FeatureVersionNotFoundError
            The group ``name`` is registered but not at the requested
            ``version`` for the tenant.
        """
        self._ensure_model()
        tenant = self._resolve_tenant(tenant_id, operation="FeatureRegistry.get")

        rows = await self._df.express.list(
            _MODEL_NAME,
            filter={"tenant_id": tenant, "name": name},
            limit=10_000,  # version lookup must not be capped at the default 100
        )
        if not rows:
            from kailash_ml.errors import FeatureGroupNotFoundError

            raise FeatureGroupNotFoundError(
                reason=(
                    "no FeatureGroup registered for the requested name "
                    f"(fingerprint={hash(name) & 0xFFFF:04x}) under tenant "
                    f"(fingerprint={hash(tenant) & 0xFFFF:04x})"
                ),
                tenant_id=tenant,
            )

        match = next((row for row in rows if int(row["version"]) == version), None)
        if match is None:
            from kailash_ml.errors import FeatureVersionNotFoundError

            available = sorted(int(row["version"]) for row in rows)
            raise FeatureVersionNotFoundError(
                reason=(
                    f"feature group {name!r} has no version {version} for the "
                    f"tenant (registered versions: {available})"
                ),
                tenant_id=tenant,
            )

        schema = FeatureSchema.from_dict(json.loads(match["schema_json"]))
        # Pure declarative handle — no dataflow bound (persisted schema only).
        return FeatureGroup(schema)

    async def list(
        self,
        *,
        tenant_id: str | None = None,
    ) -> list[FeatureGroup]:
        """List every registered :class:`FeatureGroup` for the tenant.

        Returns one pure-declarative :class:`FeatureGroup` per registered
        ``(name, version)`` row, ordered by ``(name, version)``. Tenant-isolated:
        only the requested tenant's rows are returned.

        Parameters
        ----------
        tenant_id:
            Tenant scope; defaults to the registry's ``default_tenant_id``.
        """
        self._ensure_model()
        tenant = self._resolve_tenant(tenant_id, operation="FeatureRegistry.list")

        rows = await self._df.express.list(
            _MODEL_NAME,
            filter={"tenant_id": tenant},
            limit=10_000,
        )
        groups: list[tuple[str, int, FeatureGroup]] = []
        for row in rows:
            schema = FeatureSchema.from_dict(json.loads(row["schema_json"]))
            groups.append((schema.name, schema.version, FeatureGroup(schema)))
        groups.sort(key=lambda t: (t[0], t[1]))
        return [g for _, _, g in groups]
