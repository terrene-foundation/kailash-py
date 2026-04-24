# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tenant-scoped model registry (W16 — ``ml-registry.md`` §3-§7).

Implements :class:`ModelRegistry` with the monotonic-version registration
primitive. Scope matches the W16 wave plan:

* ``(tenant_id, name, version)`` uniqueness with atomic version bump.
* Reserved-name + regex validation per §3.3.
* Explicit :class:`Lineage` and :class:`ModelSignature` (no heuristic
  inference at this wave — §5.1 and §6.2 error when absent).
* Single-transaction insert (§7.2) via the store's
  ``insert_model_registration`` primitive.
* Idempotency by ``sha256(dataset_hash + code_sha + params)`` default
  key (§7.3).
* One audit row per successful register per §8.

W17 additions:

* :class:`~kailash_ml.tracking.artifacts.AbstractArtifactStore` plumbed
  through ``__init__(store, artifact_store=None)``. When
  ``artifact_store`` is supplied the caller MAY pass ``artifact_bytes``
  (pre-serialized) in place of an explicit ``artifact_uri`` —
  registration writes the bytes to the store and derives URI +
  sha256 + probe columns itself.
* :func:`~kailash_ml.tracking.artifacts.onnx_probe.classify_onnx_bytes`
  populates ``onnx_status`` / ``onnx_opset_imports`` / ``ort_extensions``
  on the ``format="onnx"`` path per §5.6.

Deferred to later waves (noted so readers know not to search for the
symbols):

* Alias mutations (§4.1) — ``set_alias`` / ``clear_alias`` /
  ``promote_model`` / ``demote_model`` — W18.
* Lineage-DAG walk + ``diff_versions`` + ``search_models`` — W18.
* Direct ``trainable=...`` kwarg on ``register_model`` that runs
  ``export_to_onnx`` internally — W21 (the ``MLEngine.register``
  convenience surface). W17 ships the bytes-accepting form; the engine
  produces bytes via ``OnnxBridge`` and hands them here.
* ``allow_pickle_fallback=True`` → ``onnx_status="legacy_pickle_only"``
  disposition — W18 (paired with alias promotion so serving has a
  fallback policy to honor).
* Package-level ``km.register(...)`` wrapper — W33.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal, Mapping, Optional

if TYPE_CHECKING:
    import polars as pl  # type-checker-only; runtime import is lazy inside methods

from kailash_ml._result import TrainingResult
from kailash_ml.errors import fingerprint_classified_value
from kailash_ml.tracking.artifacts import AbstractArtifactStore
from kailash_ml.tracking.artifacts.onnx_probe import (
    OnnxProbeResult,
    classify_onnx_bytes,
)

__all__ = [
    "ModelRegistry",
    "ModelSignature",
    "Lineage",
    "RegisterResult",
    "ModelHandle",
    "ModelDiff",
    "SetAliasResult",
    "ClearAliasResult",
    "PromoteResult",
    "DemoteResult",
    "ModelRegistryError",
    "InvalidModelNameError",
    "InvalidAliasError",
    "AliasOccupiedError",
    "AliasNotFoundError",
    "ModelNotFoundError",
    "CrossTenantLineageError",
    "LineageRequiredError",
    "SignatureMismatchError",
    "ArtifactStoreRequiredError",
    "FilterParseError",
    "RESERVED_MODEL_NAME_PREFIXES",
    "RESERVED_ALIASES",
    "MODEL_NAME_REGEX",
    "ALIAS_REGEX",
    "default_idempotency_key",
]

logger = logging.getLogger(__name__)

# --- Validation -----------------------------------------------------------

RESERVED_MODEL_NAME_PREFIXES: tuple[str, ...] = (
    "_kml_",
    "system_",
    "internal_",
    "__",
)
MODEL_NAME_REGEX = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]{0,127}$")

# Alias regex per ``ml-registry.md`` §4.1 MUST 2.
ALIAS_REGEX = re.compile(r"^@[a-zA-Z][a-zA-Z0-9_-]{0,63}$")

# Reserved alias strings default resolution recognises (§4.1 MUST 2).
# User-defined aliases are tenant-scoped and subject to the regex; these
# strings additionally carry operational semantics enforced elsewhere
# (``@archived`` is auto-set by :meth:`demote_model`; the full list is
# reproduced here for public consumers that want to pattern-match).
RESERVED_ALIASES: tuple[str, ...] = (
    "@production",
    "@staging",
    "@champion",
    "@challenger",
    "@shadow",
    "@archived",
)

# Columns the restricted ``search_models`` DSL may filter on or order
# by. Every identifier referenced by ``filter`` / ``order_by`` MUST
# appear here — a strict allowlist keeps
# ``rules/dataflow-identifier-safety.md`` MUST Rule 1 holding without a
# dialect helper (``search_registry_versions`` in the store is a thin
# executor that interpolates only pre-validated fragments).
SEARCH_ALLOWED_COLUMNS: tuple[str, ...] = (
    "name",
    "version",
    "format",
    "is_golden",
    "actor_id",
    "created_at",
    "lineage_run_id",
    "lineage_dataset_hash",
    "lineage_code_sha",
    "onnx_status",
)
# Binary operators the DSL permits. Strict — no ``LIKE`` / subquery /
# function-call surface.
SEARCH_ALLOWED_OPS: tuple[str, ...] = ("=", "!=", "<", "<=", ">", ">=")


# --- Exceptions -----------------------------------------------------------


class ModelRegistryError(ValueError):
    """Root of registry-raised exceptions."""


class InvalidModelNameError(ModelRegistryError):
    """Model name failed regex or reserved-prefix validation (§3.3)."""


class LineageRequiredError(ModelRegistryError):
    """``register_model`` called without resolvable lineage (§6.2)."""


class SignatureMismatchError(ModelRegistryError):
    """Signature inference failed AND no explicit signature supplied (§5.1)."""


class ArtifactStoreRequiredError(ModelRegistryError):
    """``register_model`` passed ``artifact_bytes`` but no ``artifact_store``.

    Raised when the caller wants the registry to derive ``artifact_uri``
    + ``artifact_sha256`` from pre-serialized bytes but forgot to wire
    an :class:`AbstractArtifactStore` into the registry. The message
    points to the ``ModelRegistry(store, artifact_store=...)`` slot so
    the fix is O(one line).
    """


class InvalidAliasError(ModelRegistryError):
    """Alias string failed regex validation (§4.1 MUST 2)."""


class AliasOccupiedError(ModelRegistryError):
    """``promote_model`` / ``set_alias`` refused because the alias
    already points at a different version AND ``force=False`` (§8.1).

    The message MUST name the current occupant so the operator can
    audit the replacement intent before retrying with ``force=True``.
    """


class AliasNotFoundError(ModelRegistryError):
    """Alias lookup (``get_model(alias=...)``) resolved to nothing —
    either the alias was never set under ``(tenant_id, name)`` or it
    was cleared and not re-pointed."""


class ModelNotFoundError(ModelRegistryError):
    """``get_model`` / ``diff_versions`` could not resolve a version."""


class CrossTenantLineageError(ModelRegistryError):
    """Lineage chain resolved into a different tenant (§6.3)."""


class FilterParseError(ModelRegistryError):
    """``search_models`` filter string failed the restricted DSL
    validation. Message MUST NOT echo the raw filter (log-poisoning
    defense — same discipline as the dialect identifier helper)."""


# --- Signatures + Lineage ------------------------------------------------


@dataclass(frozen=True, slots=True)
class ModelSignature:
    """Input/output schema persisted with every version (§5.1).

    ``inputs`` and ``outputs`` are tuples of
    ``(name, dtype, nullable, shape_or_None)`` where ``dtype`` is a
    polars-native type name (``Float64``, ``Int64``, ``Utf8``, …) per
    ``ml-engines.md`` §4.
    """

    inputs: tuple[tuple[str, str, bool, Optional[tuple[int, ...]]], ...]
    outputs: tuple[tuple[str, str, bool, Optional[tuple[int, ...]]], ...]
    params: Optional[Mapping[str, Any]] = None

    def canonical_json(self) -> str:
        """Stable JSON form used for hashing and persistence.

        Sort keys + compact separators → identical bytes for identical
        semantic content. The ``sha256`` helper below is the public
        content-hash anchor for ``RegisterResult.signature_sha256``.
        """

        def _serialise(pt: tuple) -> list:
            name, dtype, nullable, shape = pt
            return [name, dtype, nullable, list(shape) if shape else None]

        payload = {
            "inputs": [_serialise(pt) for pt in self.inputs],
            "outputs": [_serialise(pt) for pt in self.outputs],
            "params": dict(self.params) if self.params else None,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def sha256(self) -> str:
        """64-hex SHA-256 of ``canonical_json``."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Lineage:
    """Provenance a version MUST carry (§6.1)."""

    run_id: str
    dataset_hash: str
    code_sha: str
    parent_version_id: Optional[str] = None


# --- RegisterResult -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RegisterResult:
    """Canonical return shape of ``ModelRegistry.register_model`` (§7.1)."""

    tenant_id: str
    model_name: str
    version: int
    actor_id: str
    registered_at: datetime
    artifact_uris: Mapping[str, str]
    signature_sha256: str
    lineage_run_id: str
    lineage_dataset_hash: str
    lineage_code_sha: str
    onnx_status: Optional[Literal["clean", "custom_ops", "legacy_pickle_only"]] = None
    is_golden: bool = False
    idempotent_dedup: bool = False

    @property
    def artifact_uri(self) -> str:
        """DEPRECATED v1.x back-compat shim (§7.1.1). Removed at v2.0.

        Returns ``artifact_uris["onnx"]`` when present, else the single
        entry in the dict (v1.0.0 single-format-per-row invariant §7.1.2).
        Raises ``KeyError`` when ``artifact_uris`` is empty.
        """
        warnings.warn(
            "RegisterResult.artifact_uri (singular) is deprecated; use "
            "RegisterResult.artifact_uris[format] (plural dict). "
            "Removed at v2.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        if "onnx" in self.artifact_uris:
            return self.artifact_uris["onnx"]
        if len(self.artifact_uris) == 1:
            return next(iter(self.artifact_uris.values()))
        raise KeyError("artifact_uris is empty; read artifact_uris directly")


# --- W18 alias + query result dataclasses --------------------------------


@dataclass(frozen=True, slots=True)
class SetAliasResult:
    """Return shape of :meth:`ModelRegistry.set_alias` (§4.1 + §8.3).

    Carries enough state for the caller to diff the alias transition
    without re-reading the registry: ``prev_version`` is ``None`` when
    the alias was absent OR cleared before the call.
    """

    tenant_id: str
    model_name: str
    alias: str
    prev_version: Optional[int]
    new_version: int
    actor_id: str
    set_at: datetime
    sequence_num: int


@dataclass(frozen=True, slots=True)
class ClearAliasResult:
    """Return shape of :meth:`ModelRegistry.clear_alias`."""

    tenant_id: str
    model_name: str
    alias: str
    prev_version: int
    actor_id: str
    cleared_at: datetime
    sequence_num: int


@dataclass(frozen=True, slots=True)
class PromoteResult:
    """Return shape of :meth:`ModelRegistry.promote_model` (§8.1)."""

    tenant_id: str
    model_name: str
    alias: str
    prev_version: Optional[int]
    new_version: int
    actor_id: str
    set_at: datetime
    reason: str
    sequence_num: int


@dataclass(frozen=True, slots=True)
class DemoteResult:
    """Return shape of :meth:`ModelRegistry.demote_model` (§8.2).

    ``archived_set`` is ``True`` when ``demote_model`` auto-set
    ``@archived`` on the previously-pointed version (§8.2 — only when
    no other alias still points at it).
    """

    tenant_id: str
    model_name: str
    alias: str
    prev_version: Optional[int]
    actor_id: str
    cleared_at: datetime
    reason: str
    archived_set: bool
    sequence_num: Optional[int]


@dataclass(frozen=True, slots=True)
class ModelHandle:
    """Resolved-version reference returned by :meth:`ModelRegistry.get_model`.

    Carries the metadata a caller needs without eagerly loading the
    artifact bytes. ``load()`` dereferences the artifact through the
    attached :class:`AbstractArtifactStore` (added in W17) and returns
    the raw bytes on demand; the default when no store is attached is
    to return the ``artifact_uri`` so callers can resolve bytes via
    their own mechanism.
    """

    tenant_id: str
    model_name: str
    version: int
    actor_id: str
    registered_at: datetime
    format: str
    artifact_uri: str
    artifact_sha256: str
    signature: ModelSignature
    lineage: Lineage
    aliases: tuple[str, ...]
    is_golden: bool
    onnx_status: Optional[Literal["clean", "custom_ops", "legacy_pickle_only"]]
    # Internal references — private, used by :meth:`load`.
    _version_id: str
    _artifact_store: Optional[AbstractArtifactStore]

    async def load(self) -> bytes:
        """Return the raw artifact bytes.

        Requires the registry to have been constructed with an
        :class:`AbstractArtifactStore`. Without one, raises
        :class:`ArtifactStoreRequiredError` — the handle cannot
        dereference the URI on its own.
        """
        if self._artifact_store is None:
            raise ArtifactStoreRequiredError(
                "ModelHandle.load() requires the registry to be constructed "
                "with an artifact_store. Read .artifact_uri directly and "
                "resolve bytes via your own backend, or construct the "
                "registry with ModelRegistry(store, artifact_store=...)."
            )
        return await self._artifact_store.get(
            self.artifact_uri, tenant_id=self.tenant_id
        )


@dataclass(frozen=True, slots=True)
class ModelDiff:
    """Structured diff between two versions of a single model name
    (§9.4). Metric diff is reserved for the tracker-run integration;
    this wave populates the structural fields.

    Every field is a plain Python dict to keep the diff JSON-
    serialisable without a dependency on polars / pandas.
    """

    tenant_id: str
    model_name: str
    version_a: int
    version_b: int
    signature_diff: Mapping[str, Any]
    lineage_diff: Mapping[str, Any]
    format_diff: Mapping[str, Any]
    onnx_status_diff: Mapping[str, Any]


# --- Idempotency key helper ----------------------------------------------


def default_idempotency_key(lineage: Lineage, signature: ModelSignature) -> str:
    """Default idempotency key per §7.3.

    ``sha256(dataset_hash + code_sha + signature.canonical_json())``.
    When the tuple of inputs is bit-identical a subsequent register
    returns the existing row (§7.3) rather than creating a new version.
    """
    h = hashlib.sha256()
    h.update(lineage.dataset_hash.encode("utf-8"))
    h.update(b"\x00")
    h.update(lineage.code_sha.encode("utf-8"))
    h.update(b"\x00")
    h.update(signature.canonical_json().encode("utf-8"))
    return h.hexdigest()


# --- Registry ------------------------------------------------------------


class ModelRegistry:
    """Tenant-scoped model registry (W16).

    Holds a reference to an :class:`AbstractTrackerStore`. The store
    owns schema creation + the monotonic-version atomic insert; the
    registry owns validation, idempotency, and audit-row emission.

    Full alias surface, lineage-DAG walks, ONNX probe, and the
    package-level ``km.register(...)`` wrapper all live in later waves
    (see the module docstring).
    """

    def __init__(
        self,
        store: Any,
        *,
        artifact_store: Optional[AbstractArtifactStore] = None,
    ) -> None:
        # ``store`` is the AbstractTrackerStore (W14b) owning the SQL
        # tables. ``artifact_store`` is the W17 byte layer — when
        # supplied the caller MAY pass pre-serialized bytes via
        # ``register_model(artifact_bytes=..., format=...)`` and the
        # registry handles URI + sha256 derivation internally. When
        # omitted the caller MUST pass an explicit ``artifact_uri`` +
        # ``artifact_sha256`` (W16 back-compat path).
        #
        # Typed as ``Any`` for the tracker store to avoid a cyclic
        # Protocol import; runtime checks happen in the store when the
        # registry primitives fire.
        self._store = store
        self._artifact_store = artifact_store

    async def register_model(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        name: str,
        lineage: Optional[Lineage] = None,
        signature: Optional[ModelSignature] = None,
        training_result: Optional[TrainingResult] = None,
        format: Literal["onnx", "torchscript", "gguf", "pickle"] = "onnx",
        artifact_uri: Optional[str] = None,
        artifact_sha256: Optional[str] = None,
        artifact_bytes: Optional[bytes] = None,
        idempotency_key: Optional[str] = None,
        is_golden: bool = False,
        metadata: Optional[Mapping[str, Any]] = None,
        alias: Optional[str] = None,
    ) -> RegisterResult:
        """Register a new model version atomically.

        Required: ``tenant_id``, ``actor_id``, ``name``, plus enough
        context for the registry to populate lineage + signature. Either
        pass explicit ``lineage=Lineage(...)`` + ``signature=ModelSignature(...)``,
        or pass ``training_result`` (the registry infers ``lineage.run_id``
        from ``training_result.tracker_run_id`` and leaves ``dataset_hash``
        / ``code_sha`` / ``signature`` to the caller — they MUST be supplied
        explicitly at this wave).

        ``artifact_uri`` + ``artifact_sha256`` MUST be supplied by the
        caller in W16. The W17 ``ArtifactStore`` shard takes ownership
        of writing the artifact and returning the URI + SHA.

        The ``alias=`` kwarg (W18) optionally sets the given alias on
        the registered version in the same call; the alias string is
        validated against ``ALIAS_REGEX`` before registration and set
        after the version row lands so a failed alias mutation does
        not leak a half-registered state.
        """
        if alias is not None:
            self._validate_alias(alias)

        self._validate_name(name)

        resolved_lineage = self._resolve_lineage(lineage, training_result)
        resolved_signature = self._require_signature(signature, training_result)

        # Resolve artifact_uri / artifact_sha256 / probe columns.
        # Three mutually-exclusive paths:
        # (A) caller supplies ``artifact_uri`` + ``artifact_sha256``
        #     explicitly — W16 back-compat; probe columns stay NULL.
        # (B) caller supplies ``artifact_bytes`` and the registry has
        #     an ``artifact_store`` — W17 path: store bytes, derive URI
        #     + sha256 + (for format="onnx") populate probe columns.
        # (C) neither — raise so callers know the contract.
        (
            artifact_uri,
            artifact_sha256,
            probe_result,
        ) = await self._resolve_artifact(
            tenant_id=tenant_id,
            name=name,
            format=format,
            artifact_uri=artifact_uri,
            artifact_sha256=artifact_sha256,
            artifact_bytes=artifact_bytes,
        )

        if idempotency_key is None:
            idempotency_key = default_idempotency_key(
                resolved_lineage, resolved_signature
            )

        # Idempotency check (§7.3): if an existing row matches, return
        # it verbatim rather than bump a new version.
        existing = await self._store.find_model_registration_by_idempotency_key(
            tenant_id=tenant_id,
            name=name,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            logger.debug(
                "model_registry.register.idempotent_dedup",
                extra={
                    "tenant_id_fp": fingerprint_classified_value(tenant_id),
                    "name": name,
                    "version": existing["version"],
                },
            )
            return self._row_to_result(existing, idempotent_dedup=True)

        now = datetime.now(timezone.utc)
        signature_json = resolved_signature.canonical_json()
        signature_sha256 = resolved_signature.sha256()
        metadata_json = json.dumps(dict(metadata)) if metadata else None

        # Atomic single-transaction insert (§7.2). The store computes
        # the next version via ``COALESCE(MAX(version), 0) + 1`` inside
        # the INSERT so a concurrent register cannot observe a stale
        # max and collide at the unique index.
        row = await self._store.insert_model_registration(
            tenant_id=tenant_id,
            actor_id=actor_id,
            name=name,
            format=format,
            artifact_uri=artifact_uri,
            artifact_sha256=artifact_sha256,
            signature_json=signature_json,
            signature_sha256=signature_sha256,
            lineage_run_id=resolved_lineage.run_id,
            lineage_dataset_hash=resolved_lineage.dataset_hash,
            lineage_code_sha=resolved_lineage.code_sha,
            lineage_parent_version_id=resolved_lineage.parent_version_id,
            idempotency_key=idempotency_key,
            is_golden=is_golden,
            onnx_status=probe_result.onnx_status if probe_result else None,
            onnx_unsupported_ops=None,  # probe raises on unsupported ops
            onnx_opset_imports=(
                json.dumps(probe_result.opset_imports, sort_keys=True)
                if probe_result
                else None
            ),
            ort_extensions=(
                json.dumps(probe_result.ort_extensions)
                if probe_result and probe_result.ort_extensions
                else None
            ),
            metadata_json=metadata_json,
            created_at=now.isoformat(),
        )

        # Audit row per §8 — one row per mutation. The payload is
        # deliberately schema-free (no raw classified values) so the
        # audit trail is safe for operational consumers.
        try:
            await self._store.insert_audit_row(
                tenant_id=tenant_id,
                actor_id=actor_id,
                timestamp=now.isoformat(),
                resource_kind="model_version",
                resource_id=f"{name}:v{row['version']}",
                action="register",
                new_state=json.dumps(
                    {
                        "format": format,
                        "signature_sha256": signature_sha256,
                        "is_golden": is_golden,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        except Exception as exc:  # pragma: no cover — operational fallback
            # Audit emission MUST NOT break registration; a missed audit
            # row is a WARN, not a failure. Same discipline as
            # ExperimentRun._emit_audit (W15).
            logger.warning(
                "model_registry.audit.emit_failed",
                extra={
                    "name": name,
                    "version": row["version"],
                    "error": str(exc),
                },
            )

        logger.info(
            "model_registry.register.ok",
            extra={
                "tenant_id_fp": fingerprint_classified_value(tenant_id),
                "name": name,
                "version": row["version"],
                "format": format,
                "is_golden": is_golden,
            },
        )
        # Apply alias in a second atomic step so a failed alias set
        # does not leak a half-registered state. Any AliasOccupiedError
        # raised here aborts the caller — the version row persists and
        # the caller can retry with ``force=True`` on promote_model.
        if alias is not None:
            await self.set_alias(
                tenant_id=tenant_id,
                actor_id=actor_id,
                name=name,
                version=int(row["version"]),
                alias=alias,
            )
        return self._row_to_result(row, idempotent_dedup=False)

    # --- readers (minimal W16 surface) ---------------------------------

    async def get_model_version(
        self, *, tenant_id: str, name: str, version: int
    ) -> Optional[RegisterResult]:
        """Look up a registered version, or ``None`` if absent."""
        row = await self._store.get_model_version(
            tenant_id=tenant_id, name=name, version=version
        )
        if row is None:
            return None
        return self._row_to_result(row, idempotent_dedup=False)

    async def list_model_versions(
        self, *, tenant_id: str, name: str
    ) -> list[RegisterResult]:
        """Every registered version for ``(tenant_id, name)``.

        Ordered by ``version`` ascending so downstream callers can
        easily find ``max(version)``. Full search / diff / alias
        surfaces are W18.
        """
        rows = await self._store.list_model_versions_by_name(
            tenant_id=tenant_id, name=name
        )
        return [self._row_to_result(r, idempotent_dedup=False) for r in rows]

    # --- W18: alias mutations (§4.1 + §8) ------------------------------

    async def set_alias(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        name: str,
        version: int,
        alias: str,
        force: bool = True,
        reason: Optional[str] = None,
    ) -> SetAliasResult:
        """Point ``alias`` at ``(name, version)`` under the tenant.

        Generic alias-mutation surface (§8.3) — both user-defined
        aliases and reserved ones are accepted. :meth:`promote_model`
        is the opinionated wrapper that adds the ``AliasOccupiedError``
        gate around ``@production`` / reserved aliases; ``set_alias``
        defaults to ``force=True`` because custom aliases often re-
        point.
        """
        self._validate_name(name)
        self._validate_alias(alias)
        # Resolve (name, version) to a concrete version row so
        # ``upsert_alias`` gets a verified FK target. This fails loudly
        # (ModelNotFoundError) when the version is absent — otherwise
        # the alias would point at a non-existent row.
        version_row = await self._store.get_model_version(
            tenant_id=tenant_id, name=name, version=int(version)
        )
        if version_row is None:
            raise ModelNotFoundError(
                f"set_alias: version {int(version)} of model {name!r} not "
                f"found under tenant "
                f"{fingerprint_classified_value(tenant_id)}"
            )
        if not force:
            existing = await self._store.get_alias(
                tenant_id=tenant_id, model_name=name, alias=alias
            )
            if existing is not None and int(existing["version"]) != int(version):
                raise AliasOccupiedError(
                    f"alias {alias!r} currently points at version "
                    f"{int(existing['version'])} of model {name!r}; pass "
                    f"force=True to replace"
                )
        now = datetime.now(timezone.utc)
        logger.info(
            "model_registry.set_alias.start",
            extra={
                "tenant_id_fp": fingerprint_classified_value(tenant_id),
                "name": name,
                "alias": alias,
                "version": int(version),
            },
        )
        result = await self._store.upsert_alias(
            tenant_id=tenant_id,
            model_name=name,
            alias=alias,
            model_version_id=version_row["id"],
            actor_id=actor_id,
            set_at=now.isoformat(),
        )
        prev_version = await self._resolve_version_int(
            tenant_id, result.get("prev_model_version_id")
        )
        await self._emit_alias_audit(
            tenant_id=tenant_id,
            actor_id=actor_id,
            timestamp=now.isoformat(),
            name=name,
            alias=alias,
            action="set_alias",
            prev_version=prev_version,
            new_version=int(version),
            reason=reason,
        )
        logger.info(
            "model_registry.set_alias.ok",
            extra={
                "tenant_id_fp": fingerprint_classified_value(tenant_id),
                "name": name,
                "alias": alias,
                "version": int(version),
                "prev_version": prev_version,
                "sequence_num": result["sequence_num"],
            },
        )
        return SetAliasResult(
            tenant_id=tenant_id,
            model_name=name,
            alias=alias,
            prev_version=prev_version,
            new_version=int(version),
            actor_id=actor_id,
            set_at=now,
            sequence_num=int(result["sequence_num"]),
        )

    async def clear_alias(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        name: str,
        alias: str,
        reason: Optional[str] = None,
    ) -> Optional[ClearAliasResult]:
        """Soft-delete the alias (§4.1 MUST 5).

        Returns ``None`` when the alias was absent / already cleared —
        idempotent. A non-None return carries the previous version
        pointer so callers can audit what they unpointed.
        """
        self._validate_name(name)
        self._validate_alias(alias)
        now = datetime.now(timezone.utc)
        logger.info(
            "model_registry.clear_alias.start",
            extra={
                "tenant_id_fp": fingerprint_classified_value(tenant_id),
                "name": name,
                "alias": alias,
            },
        )
        result = await self._store.clear_alias(
            tenant_id=tenant_id,
            model_name=name,
            alias=alias,
            actor_id=actor_id,
            cleared_at=now.isoformat(),
        )
        if result is None:
            return None
        prev_version = await self._resolve_version_int(
            tenant_id, result["prev_model_version_id"]
        )
        if prev_version is None:
            # Defense-in-depth — clear_alias only fires on an active
            # row, so the version_id MUST resolve. A None here signals
            # a backend bug (row deleted between lookup and clear).
            raise ModelRegistryError(
                f"clear_alias: store returned model_version_id "
                f"{result['prev_model_version_id']!r} but no matching "
                "version row was found"
            )
        await self._emit_alias_audit(
            tenant_id=tenant_id,
            actor_id=actor_id,
            timestamp=now.isoformat(),
            name=name,
            alias=alias,
            action="clear_alias",
            prev_version=prev_version,
            new_version=None,
            reason=reason,
        )
        logger.info(
            "model_registry.clear_alias.ok",
            extra={
                "tenant_id_fp": fingerprint_classified_value(tenant_id),
                "name": name,
                "alias": alias,
                "prev_version": prev_version,
                "sequence_num": result["sequence_num"],
            },
        )
        return ClearAliasResult(
            tenant_id=tenant_id,
            model_name=name,
            alias=alias,
            prev_version=prev_version,
            actor_id=actor_id,
            cleared_at=now,
            sequence_num=int(result["sequence_num"]),
        )

    async def promote_model(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        name: str,
        version: int,
        alias: str = "@production",
        reason: str,
        force: bool = False,
    ) -> PromoteResult:
        """Promote ``(name, version)`` to hold ``alias`` (§8.1).

        Unlike :meth:`set_alias`, ``promote_model`` defaults to
        ``force=False`` so an already-occupied alias raises
        :class:`AliasOccupiedError` — callers MUST explicitly
        acknowledge the replacement. ``reason`` is required for audit
        clarity (the audit row records it verbatim).
        """
        if not isinstance(reason, str) or not reason.strip():
            raise ModelRegistryError(
                "promote_model requires a non-empty reason kwarg for audit "
                "clarity (ml-registry.md §8.1)"
            )
        set_result = await self.set_alias(
            tenant_id=tenant_id,
            actor_id=actor_id,
            name=name,
            version=int(version),
            alias=alias,
            force=force,
            reason=reason,
        )
        # Overwrite the audit with a more specific ``promote`` action —
        # set_alias wrote a ``set_alias`` row, we emit the ``promote``
        # row as a sibling so the full history is preserved.
        await self._emit_alias_audit(
            tenant_id=tenant_id,
            actor_id=actor_id,
            timestamp=set_result.set_at.isoformat(),
            name=name,
            alias=alias,
            action="promote",
            prev_version=set_result.prev_version,
            new_version=int(version),
            reason=reason,
        )
        return PromoteResult(
            tenant_id=tenant_id,
            model_name=name,
            alias=alias,
            prev_version=set_result.prev_version,
            new_version=int(version),
            actor_id=actor_id,
            set_at=set_result.set_at,
            reason=reason,
            sequence_num=set_result.sequence_num,
        )

    async def demote_model(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        name: str,
        alias: str = "@production",
        reason: str,
    ) -> DemoteResult:
        """Demote whatever version currently holds ``alias`` (§8.2).

        Clears the pointer (soft delete), then — when no other alias
        still points at the previously-held version — auto-sets
        ``@archived`` on that version. Writes audit rows for each
        mutation.
        """
        if not isinstance(reason, str) or not reason.strip():
            raise ModelRegistryError(
                "demote_model requires a non-empty reason kwarg for audit "
                "clarity (ml-registry.md §8.2)"
            )
        clear_result = await self.clear_alias(
            tenant_id=tenant_id,
            actor_id=actor_id,
            name=name,
            alias=alias,
            reason=reason,
        )
        if clear_result is None:
            # Nothing pointed at ``alias`` — idempotent no-op. Emit a
            # demote audit row with prev_version=None so the action is
            # still observable in the trail.
            now = datetime.now(timezone.utc)
            await self._emit_alias_audit(
                tenant_id=tenant_id,
                actor_id=actor_id,
                timestamp=now.isoformat(),
                name=name,
                alias=alias,
                action="demote",
                prev_version=None,
                new_version=None,
                reason=reason,
            )
            return DemoteResult(
                tenant_id=tenant_id,
                model_name=name,
                alias=alias,
                prev_version=None,
                actor_id=actor_id,
                cleared_at=now,
                reason=reason,
                archived_set=False,
                sequence_num=None,
            )
        # Record the demote-specific audit row (complements the
        # clear_alias audit clear_alias already wrote).
        await self._emit_alias_audit(
            tenant_id=tenant_id,
            actor_id=actor_id,
            timestamp=clear_result.cleared_at.isoformat(),
            name=name,
            alias=alias,
            action="demote",
            prev_version=clear_result.prev_version,
            new_version=None,
            reason=reason,
        )
        # Auto-set ``@archived`` when no other alias still points at
        # the demoted version (§8.2). The check runs AFTER the clear so
        # the just-cleared alias is excluded automatically.
        prev_version_row = await self._store.get_model_version(
            tenant_id=tenant_id,
            name=name,
            version=clear_result.prev_version,
        )
        archived_set = False
        if prev_version_row is not None:
            remaining = await self._store.list_aliases_for_version(
                tenant_id=tenant_id,
                model_version_id=prev_version_row["id"],
            )
            if not remaining and alias != "@archived":
                await self.set_alias(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    name=name,
                    version=clear_result.prev_version,
                    alias="@archived",
                    force=True,
                    reason=f"auto-archived on demote of {alias}: {reason}",
                )
                archived_set = True
        return DemoteResult(
            tenant_id=tenant_id,
            model_name=name,
            alias=alias,
            prev_version=clear_result.prev_version,
            actor_id=actor_id,
            cleared_at=clear_result.cleared_at,
            reason=reason,
            archived_set=archived_set,
            sequence_num=clear_result.sequence_num,
        )

    # --- W18: query API (§9) -------------------------------------------

    async def get_model(
        self,
        *,
        tenant_id: str,
        name: str,
        version: Optional[int] = None,
        alias: Optional[str] = None,
    ) -> ModelHandle:
        """Resolve ``(name[, version|alias])`` to a :class:`ModelHandle`.

        Resolution order per §9.1:

        1. If ``version`` given, fetch directly.
        2. Else if ``alias`` given, resolve to a version via the alias
           table (raises :class:`AliasNotFoundError` if absent or
           cleared).
        3. Else fetch the highest version for ``(tenant_id, name)``.
        4. If nothing resolves, raise :class:`ModelNotFoundError`.
        """
        self._validate_name(name)
        if version is not None and alias is not None:
            raise ModelRegistryError(
                "get_model: pass EITHER version OR alias, not both"
            )
        if version is not None:
            row = await self._store.get_model_version(
                tenant_id=tenant_id, name=name, version=int(version)
            )
            if row is None:
                raise ModelNotFoundError(
                    f"get_model: version {int(version)} of {name!r} not "
                    f"found under tenant "
                    f"{fingerprint_classified_value(tenant_id)}"
                )
        elif alias is not None:
            self._validate_alias(alias)
            row = await self._store.get_alias(
                tenant_id=tenant_id, model_name=name, alias=alias
            )
            if row is None:
                raise AliasNotFoundError(
                    f"get_model: alias {alias!r} not set (or cleared) on "
                    f"{name!r} under tenant "
                    f"{fingerprint_classified_value(tenant_id)}"
                )
        else:
            rows = await self._store.list_model_versions_by_name(
                tenant_id=tenant_id, name=name
            )
            if not rows:
                raise ModelNotFoundError(
                    f"get_model: no versions registered for {name!r} under "
                    f"tenant {fingerprint_classified_value(tenant_id)}"
                )
            row = rows[-1]  # list_model_versions_by_name orders ASC
        return await self._row_to_handle(row)

    async def list_models(
        self,
        *,
        tenant_id: str,
        name: Optional[str] = None,
        alias: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> "pl.DataFrame":  # type: ignore[name-defined]
        """Tenant-scoped listing returning a polars DataFrame (§9.2).

        Columns: ``name``, ``version``, ``registered_at``, ``actor_id``,
        ``format``, ``aliases`` (list[str]), ``lineage_run_id``,
        ``signature_sha256``, ``is_golden``, ``onnx_status``.
        """
        import polars as pl

        if alias is not None:
            self._validate_alias(alias)
        rows = await self._store.list_registry_versions(
            tenant_id=tenant_id,
            name=name,
            alias=alias,
            limit=limit,
            offset=offset,
        )
        records: list[dict[str, Any]] = []
        for r in rows:
            aliases = await self._store.list_aliases_for_version(
                tenant_id=tenant_id, model_version_id=r["id"]
            )
            records.append(
                {
                    "name": r["name"],
                    "version": int(r["version"]),
                    "registered_at": r["created_at"],
                    "actor_id": r["actor_id"],
                    "format": r["format"],
                    "aliases": aliases,
                    "lineage_run_id": r["lineage_run_id"],
                    "signature_sha256": r["signature_sha256"],
                    "is_golden": bool(r.get("is_golden", False)),
                    "onnx_status": r.get("onnx_status"),
                }
            )
        if not records:
            # Empty DataFrames need an explicit schema so downstream
            # .filter() / .join() against the canonical column set
            # works even when zero rows match the tenant.
            return pl.DataFrame(
                schema={
                    "name": pl.Utf8,
                    "version": pl.Int64,
                    "registered_at": pl.Utf8,
                    "actor_id": pl.Utf8,
                    "format": pl.Utf8,
                    "aliases": pl.List(pl.Utf8),
                    "lineage_run_id": pl.Utf8,
                    "signature_sha256": pl.Utf8,
                    "is_golden": pl.Boolean,
                    "onnx_status": pl.Utf8,
                }
            )
        return pl.DataFrame(records)

    async def search_models(
        self,
        *,
        tenant_id: str,
        filter: Optional[str] = None,
        order_by: Optional[list[str]] = None,
        limit: int = 100,
    ) -> "pl.DataFrame":  # type: ignore[name-defined]
        """Execute a restricted filter DSL against the registry (§9.3).

        Grammar: ``col <op> <literal> [AND col <op> <literal>]*``
        where ``col`` ∈ :data:`SEARCH_ALLOWED_COLUMNS`,
        ``op`` ∈ :data:`SEARCH_ALLOWED_OPS`, and literals are quoted
        strings or unsigned integers. Raw SQL is BLOCKED by the
        validator — unknown identifiers raise :class:`FilterParseError`.
        """
        import polars as pl

        where_sql, params = self._parse_search_filter(filter)
        order_by_sql = self._parse_search_order_by(order_by)
        rows = await self._store.search_registry_versions(
            tenant_id=tenant_id,
            where_sql=where_sql,
            params=params,
            order_by_sql=order_by_sql,
            limit=int(limit),
        )
        records: list[dict[str, Any]] = []
        for r in rows:
            aliases = await self._store.list_aliases_for_version(
                tenant_id=tenant_id, model_version_id=r["id"]
            )
            records.append(
                {
                    "name": r["name"],
                    "version": int(r["version"]),
                    "registered_at": r["created_at"],
                    "actor_id": r["actor_id"],
                    "format": r["format"],
                    "aliases": aliases,
                    "lineage_run_id": r["lineage_run_id"],
                    "signature_sha256": r["signature_sha256"],
                    "is_golden": bool(r.get("is_golden", False)),
                    "onnx_status": r.get("onnx_status"),
                }
            )
        if not records:
            return pl.DataFrame(
                schema={
                    "name": pl.Utf8,
                    "version": pl.Int64,
                    "registered_at": pl.Utf8,
                    "actor_id": pl.Utf8,
                    "format": pl.Utf8,
                    "aliases": pl.List(pl.Utf8),
                    "lineage_run_id": pl.Utf8,
                    "signature_sha256": pl.Utf8,
                    "is_golden": pl.Boolean,
                    "onnx_status": pl.Utf8,
                }
            )
        return pl.DataFrame(records)

    async def diff_versions(
        self,
        *,
        tenant_id: str,
        name: str,
        version_a: int,
        version_b: int,
    ) -> ModelDiff:
        """Structured diff between two versions (§9.4).

        Resolves metric deltas separately — W18 populates the
        structural fields (signature, lineage, format, onnx_status).
        """
        self._validate_name(name)
        row_a = await self._store.get_model_version(
            tenant_id=tenant_id, name=name, version=int(version_a)
        )
        row_b = await self._store.get_model_version(
            tenant_id=tenant_id, name=name, version=int(version_b)
        )
        if row_a is None or row_b is None:
            missing = int(version_a) if row_a is None else int(version_b)
            raise ModelNotFoundError(
                f"diff_versions: version {missing} of {name!r} not found "
                f"under tenant {fingerprint_classified_value(tenant_id)}"
            )
        sig_a = json.loads(row_a["signature_json"])
        sig_b = json.loads(row_b["signature_json"])
        return ModelDiff(
            tenant_id=tenant_id,
            model_name=name,
            version_a=int(version_a),
            version_b=int(version_b),
            signature_diff=_diff_signature(sig_a, sig_b),
            lineage_diff={
                "run_id_a": row_a["lineage_run_id"],
                "run_id_b": row_b["lineage_run_id"],
                "dataset_hash_a": row_a["lineage_dataset_hash"],
                "dataset_hash_b": row_b["lineage_dataset_hash"],
                "code_sha_a": row_a["lineage_code_sha"],
                "code_sha_b": row_b["lineage_code_sha"],
                "parent_version_id_a": row_a.get("lineage_parent_version_id"),
                "parent_version_id_b": row_b.get("lineage_parent_version_id"),
            },
            format_diff={
                "a": row_a["format"],
                "b": row_b["format"],
                "changed": row_a["format"] != row_b["format"],
            },
            onnx_status_diff={
                "a": row_a.get("onnx_status"),
                "b": row_b.get("onnx_status"),
                "changed": row_a.get("onnx_status") != row_b.get("onnx_status"),
            },
        )

    async def get_lineage_parent(
        self,
        *,
        tenant_id: str,
        name: str,
        version: int,
    ) -> Optional[RegisterResult]:
        """Resolve the lineage parent of ``(name, version)`` (§6.1).

        Walks one step up the lineage DAG: reads
        ``lineage_parent_version_id`` and looks up the parent row
        tenant-scoped. Cross-tenant lineage refusal: the parent lookup
        is tenant-filtered in the store, so a pointer to another
        tenant's row returns ``None`` and raises
        :class:`CrossTenantLineageError`.
        """
        self._validate_name(name)
        row = await self._store.get_model_version(
            tenant_id=tenant_id, name=name, version=int(version)
        )
        if row is None:
            raise ModelNotFoundError(
                f"get_lineage_parent: version {int(version)} of {name!r} " f"not found"
            )
        parent_id = row.get("lineage_parent_version_id")
        if not parent_id:
            return None
        parent_row = await self._store.get_model_version_by_id(
            tenant_id=tenant_id, version_id=parent_id
        )
        if parent_row is None:
            raise CrossTenantLineageError(
                f"get_lineage_parent: parent version id {parent_id!r} "
                f"either does not exist or belongs to a different tenant — "
                f"cross-tenant lineage refusal per ml-registry.md §6.3"
            )
        return self._row_to_result(parent_row, idempotent_dedup=False)

    # --- internals -----------------------------------------------------

    @staticmethod
    def _validate_name(name: Any) -> None:
        if not isinstance(name, str):
            raise InvalidModelNameError(
                f"model name must be a string, got {type(name).__name__}"
            )
        for prefix in RESERVED_MODEL_NAME_PREFIXES:
            if name.startswith(prefix):
                raise InvalidModelNameError(
                    f"model name rejected — reserved prefix {prefix!r} "
                    f"(ml-registry.md §3.3)"
                )
        if not MODEL_NAME_REGEX.match(name):
            raise InvalidModelNameError(
                "model name failed regex ^[a-zA-Z_][a-zA-Z0-9_-]{0,127}$ "
                "(ml-registry.md §3.3)"
            )
        # Single-underscore-prefix is permitted per §3.3 but emits a
        # DEBUG line so operators auditing convention usage can grep
        # for it.
        if name.startswith("_"):
            logger.debug(
                "model_registry.name.single_underscore_convention",
                extra={"name": name},
            )

    async def _resolve_artifact(
        self,
        *,
        tenant_id: str,
        name: str,
        format: str,
        artifact_uri: Optional[str],
        artifact_sha256: Optional[str],
        artifact_bytes: Optional[bytes],
    ) -> tuple[str, str, Optional[OnnxProbeResult]]:
        """Resolve ``(uri, sha256, probe_result)`` per the §5.6 contract.

        Three paths (§7.1 + W17.C plumbing):

        (A) Explicit ``artifact_uri`` + ``artifact_sha256`` — W16
            back-compat. Probe columns stay NULL because the registry
            has no bytes to probe. Mutually exclusive with
            ``artifact_bytes`` (passing both is caller confusion, not a
            contract we can silently arbitrate).

        (B) ``artifact_bytes`` + a configured ``artifact_store`` —
            registry writes the bytes to the store, derives URI +
            sha256 from the store's return, and (for ``format="onnx"``)
            runs :func:`classify_onnx_bytes` to populate probe columns.

        (C) Neither — raise a typed error naming the missing kwarg so
            the caller fixes the right end.
        """
        # Path (A): explicit URI + sha — early return, no probe.
        if artifact_uri is not None and artifact_sha256 is not None:
            if artifact_bytes is not None:
                raise ValueError(
                    "register_model: pass EITHER (artifact_uri + "
                    "artifact_sha256) OR artifact_bytes, not both — "
                    "the registry cannot arbitrate between caller-"
                    "supplied metadata and bytes the store would derive."
                )
            return artifact_uri, artifact_sha256, None

        # Path (C): neither — surface the missing-kwarg contract loudly.
        if artifact_bytes is None:
            raise ValueError(
                "register_model requires EITHER explicit "
                "(artifact_uri + artifact_sha256) OR artifact_bytes + "
                "a configured artifact_store. See "
                "ModelRegistry(store, artifact_store=...)."
            )

        # Path (B): bytes → store → URI + sha + probe.
        if self._artifact_store is None:
            raise ArtifactStoreRequiredError(
                "register_model(artifact_bytes=...) requires "
                "ModelRegistry(store, artifact_store=LocalFileArtifactStore("
                "root_dir) | CasSha256ArtifactStore(...) | ...). "
                "Construct the registry with an artifact_store and retry."
            )

        uri, sha256_hex = await self._artifact_store.put(
            artifact_bytes, tenant_id=tenant_id
        )

        if format != "onnx":
            return uri, sha256_hex, None

        probe: OnnxProbeResult = classify_onnx_bytes(artifact_bytes)
        # Defence-in-depth: the store's digest and the probe's sha256
        # MUST match — they're both sha256(plaintext). A divergence
        # signals a backend bug (wrong hash algorithm) or a
        # bytes-mutated-mid-flight bug. Raising here is the §10.1
        # integrity invariant at the registry layer.
        if probe.sha256_hex != sha256_hex:
            raise ValueError(
                f"artifact_store digest {sha256_hex!r} != probe "
                f"digest {probe.sha256_hex!r} for "
                f"name={name!r} — backend contract broken"
            )
        return uri, sha256_hex, probe

    @staticmethod
    def _resolve_lineage(
        lineage: Optional[Lineage], training_result: Optional[TrainingResult]
    ) -> Lineage:
        if lineage is not None:
            # Minimal validity — empty run_id / dataset_hash / code_sha
            # produces unhelpful downstream failures, so reject early.
            if not lineage.run_id:
                raise LineageRequiredError(
                    "Lineage.run_id is required (ml-registry.md §6.1)"
                )
            if not lineage.dataset_hash:
                raise LineageRequiredError(
                    "Lineage.dataset_hash is required (ml-registry.md §6.1)"
                )
            if not lineage.code_sha:
                raise LineageRequiredError(
                    "Lineage.code_sha is required (ml-registry.md §6.1)"
                )
            return lineage
        raise LineageRequiredError(
            "register_model requires lineage.run_id — either\n"
            "  pass lineage=Lineage(run_id=..., dataset_hash=..., code_sha=...)\n"
            "  or attach a TrainingResult produced inside a `with km.track(): ...` block.\n"
            "TrainingResult-inferred dataset_hash / code_sha will ship with "
            "dataflow-ml-integration — until then, supply Lineage explicitly."
        )

    @staticmethod
    def _require_signature(
        signature: Optional[ModelSignature],
        training_result: Optional[TrainingResult],
    ) -> ModelSignature:
        if signature is not None:
            return signature
        # Schema inference from TrainingResult is deferred — feature_schema /
        # target_schema do not live on the current TrainingResult shape (they
        # come with the dataflow-ml-integration wave). Raise the spec-mandated
        # error so callers know to supply it explicitly.
        raise SignatureMismatchError(
            "register_model requires signature=ModelSignature(...) at this wave. "
            "Inference from TrainingResult.feature_schema / target_schema ships "
            "with dataflow-ml-integration (ml-registry.md §5.1)."
        )

    @staticmethod
    def _row_to_result(
        row: Mapping[str, Any], *, idempotent_dedup: bool
    ) -> RegisterResult:
        created_at = row["created_at"]
        if isinstance(created_at, str):
            registered_at = datetime.fromisoformat(created_at)
        else:
            registered_at = created_at
        return RegisterResult(
            tenant_id=row["tenant_id"],
            model_name=row["name"],
            version=int(row["version"]),
            actor_id=row["actor_id"],
            registered_at=registered_at,
            artifact_uris={row["format"]: row["artifact_uri"]},
            signature_sha256=row["signature_sha256"],
            lineage_run_id=row["lineage_run_id"],
            lineage_dataset_hash=row["lineage_dataset_hash"],
            lineage_code_sha=row["lineage_code_sha"],
            onnx_status=row.get("onnx_status"),
            is_golden=bool(row.get("is_golden", False)),
            idempotent_dedup=idempotent_dedup,
        )

    # --- W18 internals -------------------------------------------------

    @staticmethod
    def _validate_alias(alias: Any) -> None:
        if not isinstance(alias, str):
            raise InvalidAliasError(
                f"alias must be a string, got {type(alias).__name__}"
            )
        if not ALIAS_REGEX.match(alias):
            # Message does NOT echo the raw alias — log-poisoning
            # defense aligned with the dialect helper's fingerprint
            # discipline (``rules/dataflow-identifier-safety.md`` §2).
            raise InvalidAliasError(
                "alias failed regex ^@[a-zA-Z][a-zA-Z0-9_-]{0,63}$ "
                "(ml-registry.md §4.1 MUST 2)"
            )

    async def _resolve_version_int(
        self, tenant_id: str, version_id: Optional[str]
    ) -> Optional[int]:
        """Map a version UUID → integer version under the tenant."""
        if not version_id:
            return None
        row = await self._store.get_model_version_by_id(
            tenant_id=tenant_id, version_id=version_id
        )
        return int(row["version"]) if row is not None else None

    async def _emit_alias_audit(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        timestamp: str,
        name: str,
        alias: str,
        action: Literal["set_alias", "clear_alias", "promote", "demote"],
        prev_version: Optional[int],
        new_version: Optional[int],
        reason: Optional[str],
    ) -> None:
        """Append an alias-mutation audit row. Best-effort — a failed
        audit write is a WARN, not a gate (§8.4 discipline inherited
        from W15 ``ExperimentRun._emit_audit``)."""
        payload = {
            "alias": alias,
            "prev_version": prev_version,
            "new_version": new_version,
        }
        if reason is not None:
            payload["reason"] = reason
        try:
            await self._store.insert_audit_row(
                tenant_id=tenant_id,
                actor_id=actor_id,
                timestamp=timestamp,
                resource_kind="model_alias",
                resource_id=f"{name}@{alias}",
                action=action,
                new_state=json.dumps(payload, sort_keys=True, separators=(",", ":")),
            )
        except Exception as exc:  # pragma: no cover — operational fallback
            logger.warning(
                "model_registry.alias_audit.emit_failed",
                extra={
                    "name": name,
                    "alias": alias,
                    "action": action,
                    "error": str(exc),
                },
            )

    async def _row_to_handle(self, row: Mapping[str, Any]) -> ModelHandle:
        """Hydrate a ``_kml_model_versions`` row into a
        :class:`ModelHandle` (§9.1)."""
        created_at = row["created_at"]
        if isinstance(created_at, str):
            registered_at = datetime.fromisoformat(created_at)
        else:
            registered_at = created_at
        sig_payload = json.loads(row["signature_json"])

        def _tuples(items: list) -> tuple:
            out = []
            for entry in items:
                name_, dtype, nullable, shape = entry
                shape_tup = tuple(shape) if shape else None
                out.append((name_, dtype, bool(nullable), shape_tup))
            return tuple(out)

        signature = ModelSignature(
            inputs=_tuples(sig_payload["inputs"]),
            outputs=_tuples(sig_payload["outputs"]),
            params=sig_payload.get("params"),
        )
        lineage = Lineage(
            run_id=row["lineage_run_id"],
            dataset_hash=row["lineage_dataset_hash"],
            code_sha=row["lineage_code_sha"],
            parent_version_id=row.get("lineage_parent_version_id"),
        )
        aliases = await self._store.list_aliases_for_version(
            tenant_id=row["tenant_id"], model_version_id=row["id"]
        )
        return ModelHandle(
            tenant_id=row["tenant_id"],
            model_name=row["name"],
            version=int(row["version"]),
            actor_id=row["actor_id"],
            registered_at=registered_at,
            format=row["format"],
            artifact_uri=row["artifact_uri"],
            artifact_sha256=row["artifact_sha256"],
            signature=signature,
            lineage=lineage,
            aliases=tuple(aliases),
            is_golden=bool(row.get("is_golden", False)),
            onnx_status=row.get("onnx_status"),
            _version_id=row["id"],
            _artifact_store=self._artifact_store,
        )

    @staticmethod
    def _parse_search_filter(
        filter_str: Optional[str],
    ) -> tuple[str, list[Any]]:
        """Parse the restricted DSL into a validated ``WHERE`` fragment.

        Grammar: ``col <op> <literal> [AND col <op> <literal>]*``. All
        identifiers checked against :data:`SEARCH_ALLOWED_COLUMNS`, all
        operators against :data:`SEARCH_ALLOWED_OPS`. Literals become
        parameter placeholders — raw SQL interpolation is BLOCKED.
        """
        if filter_str is None or not filter_str.strip():
            return "", []
        # Tokenise on whitespace-separated AND boundaries.
        parts = re.split(r"\s+AND\s+", filter_str.strip(), flags=re.IGNORECASE)
        clauses: list[str] = []
        params: list[Any] = []
        # Regex: col op literal. Literal is either ``'...'`` (single-
        # quoted string) or a bare int. Raw SQL + subqueries + LIKE are
        # BLOCKED — the grammar is deliberately narrow.
        literal_clause_re = re.compile(
            r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*"
            r"(=|!=|<=|>=|<|>)\s*"
            r"(?:'([^']*)'|(-?\d+))\s*$"
        )
        for p in parts:
            m = literal_clause_re.match(p)
            if not m:
                raise FilterParseError(
                    "filter fragment failed grammar — allowed form: "
                    "col <op> <literal> [AND ...] with op in "
                    f"{SEARCH_ALLOWED_OPS}"
                )
            col, op, str_lit, int_lit = m.groups()
            if col not in SEARCH_ALLOWED_COLUMNS:
                raise FilterParseError(
                    f"filter column not in allowlist "
                    f"(allowed: {SEARCH_ALLOWED_COLUMNS})"
                )
            if op not in SEARCH_ALLOWED_OPS:
                raise FilterParseError(
                    f"filter operator not in allowlist (allowed: "
                    f"{SEARCH_ALLOWED_OPS})"
                )
            if str_lit is not None:
                value: Any = str_lit
            else:
                value = int(int_lit)
            clauses.append(f"{col} {op} ?")
            params.append(value)
        return " AND ".join(clauses), params

    @staticmethod
    def _parse_search_order_by(order_by: Optional[list[str]]) -> str:
        """Validate + serialise the ``order_by`` list.

        Each entry must be ``"<col>"`` or ``"<col> ASC|DESC"``. The
        default (None or empty) produces an empty string so the store
        falls back to its natural ordering.
        """
        if not order_by:
            return ""
        parts: list[str] = []
        for entry in order_by:
            tokens = entry.strip().split()
            if not tokens:
                raise FilterParseError("order_by entry is empty")
            col = tokens[0]
            if col not in SEARCH_ALLOWED_COLUMNS:
                raise FilterParseError(
                    f"order_by column not in allowlist "
                    f"(allowed: {SEARCH_ALLOWED_COLUMNS})"
                )
            direction = "ASC"
            if len(tokens) == 2:
                direction = tokens[1].upper()
                if direction not in ("ASC", "DESC"):
                    raise FilterParseError("order_by direction must be ASC or DESC")
            elif len(tokens) > 2:
                raise FilterParseError(
                    "order_by entry accepts at most two tokens "
                    "('<col>' or '<col> ASC|DESC')"
                )
            parts.append(f"{col} {direction}")
        return ", ".join(parts)


def _diff_signature(
    sig_a: Mapping[str, Any], sig_b: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Produce a structured diff of two canonical-JSON signatures.

    Compares ``inputs`` and ``outputs`` column-by-column: any column
    name present in one but not the other goes into ``added`` /
    ``removed``; same-name columns with different dtype / nullable /
    shape go into ``changed``.
    """

    def _index(pts: list) -> dict[str, list]:
        return {pt[0]: pt for pt in pts}

    def _diff_section(a_items: list, b_items: list) -> Mapping[str, Any]:
        a_idx = _index(a_items)
        b_idx = _index(b_items)
        added = [b_idx[n] for n in sorted(set(b_idx) - set(a_idx))]
        removed = [a_idx[n] for n in sorted(set(a_idx) - set(b_idx))]
        changed = []
        for n in sorted(set(a_idx) & set(b_idx)):
            if a_idx[n] != b_idx[n]:
                changed.append({"column": n, "a": a_idx[n], "b": b_idx[n]})
        return {"added": added, "removed": removed, "changed": changed}

    return {
        "inputs": _diff_section(sig_a.get("inputs", []), sig_b.get("inputs", [])),
        "outputs": _diff_section(sig_a.get("outputs", []), sig_b.get("outputs", [])),
        "params_changed": sig_a.get("params") != sig_b.get("params"),
    }
