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

Deferred to later waves (noted so readers know not to search for the
symbols):

* ONNX export probe (§5.6) populating ``onnx_status`` /
  ``onnx_unsupported_ops`` — W17 ships the probe; the columns are
  persisted now with ``None`` defaults.
* Alias mutations (§4.1) — ``set_alias`` / ``clear_alias`` /
  ``promote_model`` / ``demote_model`` — W18.
* Lineage-DAG walk + ``diff_versions`` + ``search_models`` — W18.
* ``artifact_uri`` derivation from an artifact writer — W17 (today the
  caller supplies both ``artifact_uri`` and ``artifact_sha256``).
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
from typing import Any, Literal, Mapping, Optional

from kailash_ml._result import TrainingResult
from kailash_ml.errors import fingerprint_classified_value

__all__ = [
    "ModelRegistry",
    "ModelSignature",
    "Lineage",
    "RegisterResult",
    "ModelRegistryError",
    "InvalidModelNameError",
    "LineageRequiredError",
    "SignatureMismatchError",
    "RESERVED_MODEL_NAME_PREFIXES",
    "MODEL_NAME_REGEX",
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


# --- Exceptions -----------------------------------------------------------


class ModelRegistryError(ValueError):
    """Root of registry-raised exceptions."""


class InvalidModelNameError(ModelRegistryError):
    """Model name failed regex or reserved-prefix validation (§3.3)."""


class LineageRequiredError(ModelRegistryError):
    """``register_model`` called without resolvable lineage (§6.2)."""


class SignatureMismatchError(ModelRegistryError):
    """Signature inference failed AND no explicit signature supplied (§5.1)."""


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

    def __init__(self, store: Any) -> None:
        # Typed as ``Any`` to avoid a cyclic Protocol import; runtime
        # checks happen in the store when the registry primitives fire.
        self._store = store

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

        The ``alias=`` kwarg is reserved for W18 and raises
        ``NotImplementedError`` if supplied today so the wire deferral
        is loud, not silent.
        """
        if alias is not None:
            raise NotImplementedError(
                "alias= kwarg on register_model() is owned by W18 "
                "(ml-registry.md §4). Land W18 before supplying aliases."
            )

        self._validate_name(name)

        resolved_lineage = self._resolve_lineage(lineage, training_result)
        resolved_signature = self._require_signature(signature, training_result)

        if artifact_uri is None or artifact_sha256 is None:
            raise ValueError(
                "register_model requires artifact_uri AND artifact_sha256 "
                "at this wave — the W17 ArtifactStore shard takes ownership "
                "of both once it lands."
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
            onnx_status=None,
            onnx_unsupported_ops=None,
            onnx_opset_imports=None,
            ort_extensions=None,
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
