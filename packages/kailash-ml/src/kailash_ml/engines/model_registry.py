# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ModelRegistry engine -- model lifecycle, MLflow format, ONNX status tracking.

Manages model versions through stages (staging -> shadow -> production -> archived).
Stores artifacts locally with optional ONNX export. Reads and writes MLflow MLmodel
format v1 for interoperability.

All persistence is via ConnectionManager (same pattern as FeatureStore).
No DataFlow Express -- we need DDL control and transactions.
"""
from __future__ import annotations

import json
import logging
import pickle
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from kailash_ml.errors import ModelNotFoundError
from kailash_ml.types import MetricSpec, ModelSignature

from kailash.db.connection import ConnectionManager

logger = logging.getLogger(__name__)

__all__ = [
    "ModelRegistry",
    "ArtifactStore",
    "LocalFileArtifactStore",
    "ModelVersion",
    "ModelNotFoundError",
]

# ---------------------------------------------------------------------------
# Valid stage transitions
# ---------------------------------------------------------------------------

VALID_TRANSITIONS: dict[str, set[str]] = {
    "staging": {"shadow", "production", "archived"},
    "shadow": {"production", "archived", "staging"},
    "production": {"archived", "shadow"},
    "archived": {"staging"},
}

ALL_STAGES = {"staging", "shadow", "production", "archived"}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
#
# ``ModelNotFoundError`` is re-exported from ``kailash_ml.errors`` (canonical
# location at ``kailash.ml.errors.ModelNotFoundError``, subclass of
# ``ModelRegistryError`` → ``MLError``). Prior to W7 follow-up there was a
# distinct local ``class ModelNotFoundError(Exception)`` here; the divergence
# meant `except ModelNotFoundError:` in user code caught one OR the other
# depending on import path, never both. Routing all paths to canonical closes
# the bug class. See ``rules/orphan-detection.md`` § 1.


# ---------------------------------------------------------------------------
# ArtifactStore protocol + local implementation
# ---------------------------------------------------------------------------


class ArtifactStore(Protocol):
    """Protocol for model artifact storage."""

    async def save(
        self, name: str, version: int, data: bytes, filename: str
    ) -> str: ...

    async def load(self, name: str, version: int, filename: str) -> bytes: ...

    async def exists(self, name: str, version: int, filename: str) -> bool: ...

    async def delete(self, name: str, version: int) -> None: ...


def _validate_artifact_name(name: str) -> None:
    """Prevent path traversal in artifact names."""
    import os

    if os.sep in name or "/" in name or "\\" in name or ".." in name:
        raise ValueError(
            f"Invalid artifact name '{name}': must not contain path separators or '..'"
        )


class LocalFileArtifactStore:
    """Filesystem-based artifact storage."""

    def __init__(self, root_dir: str | Path = ".kailash_ml/artifacts") -> None:
        self._root = Path(root_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    async def save(self, name: str, version: int, data: bytes, filename: str) -> str:
        _validate_artifact_name(name)
        _validate_artifact_name(filename)
        path = (self._root / name / str(version) / filename).resolve()
        if not str(path).startswith(str(self._root.resolve())):
            raise ValueError(f"Path traversal detected: {name}/{filename}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)

    async def load(self, name: str, version: int, filename: str) -> bytes:
        _validate_artifact_name(name)
        _validate_artifact_name(filename)
        path = (self._root / name / str(version) / filename).resolve()
        if not str(path).startswith(str(self._root.resolve())):
            raise ValueError(f"Path traversal detected: {name}/{filename}")
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {path}")
        return path.read_bytes()

    async def exists(self, name: str, version: int, filename: str) -> bool:
        _validate_artifact_name(name)
        _validate_artifact_name(filename)
        return (self._root / name / str(version) / filename).exists()

    async def delete(self, name: str, version: int) -> None:
        import shutil

        _validate_artifact_name(name)
        dir_path = self._root / name / str(version)
        if dir_path.exists():
            shutil.rmtree(dir_path)


# ---------------------------------------------------------------------------
# ModelVersion dataclass
# ---------------------------------------------------------------------------


@dataclass
class ModelVersion:
    """A versioned model entry returned by the registry."""

    name: str
    version: int
    stage: str
    metrics: list[MetricSpec] = field(default_factory=list)
    signature: ModelSignature | None = None
    onnx_status: str = "pending"  # "pending" | "success" | "failed" | "not_applicable"
    onnx_error: str | None = None
    artifact_path: str = ""
    model_uuid: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "stage": self.stage,
            "metrics": [m.to_dict() for m in self.metrics],
            "signature": self.signature.to_dict() if self.signature else None,
            "onnx_status": self.onnx_status,
            "onnx_error": self.onnx_error,
            "artifact_path": self.artifact_path,
            "model_uuid": self.model_uuid,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelVersion:
        return cls(
            name=data["name"],
            version=data["version"],
            stage=data["stage"],
            metrics=[MetricSpec.from_dict(m) for m in data.get("metrics", [])],
            signature=(
                ModelSignature.from_dict(data["signature"])
                if data.get("signature")
                else None
            ),
            onnx_status=data.get("onnx_status", "pending"),
            onnx_error=data.get("onnx_error"),
            artifact_path=data.get("artifact_path", ""),
            model_uuid=data.get("model_uuid", ""),
            created_at=data.get("created_at", ""),
        )


# ---------------------------------------------------------------------------
# SQL helpers (encapsulated, same pattern as _feature_sql.py)
# ---------------------------------------------------------------------------


async def _ensure_registry_tables_via_migration(conn: ConnectionManager) -> None:
    """Apply pending numbered migrations so the registry schema is canonical.

    Per ``rules/schema-migration.md`` Rule 1, all DDL lives in numbered
    migrations — NOT in inline application code. Migrations 0002 + 0005
    own the registry's three tables (``_kml_model_versions``,
    ``_kml_models``, ``_kml_model_transitions``); this helper bridges the
    registry's :class:`ConnectionManager` shape to the migration
    framework's expected ``conn.execute(sql, params_tuple)`` form via
    :class:`_MigrationConnAdapter` and applies every pending migration
    idempotently.

    Closes GH issue #699: replaces the inline ``CREATE TABLE IF NOT
    EXISTS`` block (formerly at L194-229) which was a no-op against
    migration 0002's tenant-aware schema and silently broke
    ``register_model`` for every 1.5.0/1.5.1 user.
    """
    # Local import — keeps the registry module's import graph minimal
    # for unit tests that don't exercise migration. Also matches the
    # pattern used by ``ExperimentTracker._apply_pending_migrations``.
    from kailash_ml.tracking.tracker import _MigrationConnAdapter

    from kailash.tracking.migrations._registry import get_registry

    registry = get_registry()
    await registry.apply_pending(_MigrationConnAdapter(conn))


async def _get_model_row(
    conn: ConnectionManager, name: str, *, tenant_id: str
) -> dict[str, Any] | None:
    """Fetch a row from ``_kml_models`` by ``(tenant_id, model_name)``.

    Per ``rules/tenant-isolation.md`` Rule 1, every read against a
    tenant-scoped table includes the ``tenant_id`` predicate. The
    column is named ``model_name`` to match migration 0005's schema.
    """
    return await conn.fetchone(
        "SELECT * FROM _kml_models WHERE tenant_id = ? AND model_name = ?",
        tenant_id,
        name,
    )


async def _get_version_row(
    conn: ConnectionManager, name: str, version: int, *, tenant_id: str
) -> dict[str, Any] | None:
    """Fetch a row from ``_kml_model_versions`` by
    ``(tenant_id, model_name, version)``.

    Composite-PK predicate matching migration 0002's schema. ``model_name``
    (not ``name``) is the canonical column.
    """
    return await conn.fetchone(
        "SELECT * FROM _kml_model_versions WHERE tenant_id = ? "
        "AND model_name = ? AND version = ?",
        tenant_id,
        name,
        version,
    )


async def _get_version_by_stage(
    conn: ConnectionManager, name: str, stage: str, *, tenant_id: str
) -> dict[str, Any] | None:
    """Fetch the latest ``_kml_model_versions`` row at ``stage`` for
    ``(tenant_id, model_name)``."""
    return await conn.fetchone(
        "SELECT * FROM _kml_model_versions WHERE tenant_id = ? "
        "AND model_name = ? AND stage = ? "
        "ORDER BY version DESC LIMIT 1",
        tenant_id,
        name,
        stage,
    )


def _row_to_model_version(row: dict[str, Any]) -> ModelVersion:
    metrics_json = row.get("metrics_json", "[]")
    metrics = [MetricSpec.from_dict(m) for m in json.loads(metrics_json)]

    sig_json = row.get("signature_json")
    signature = ModelSignature.from_dict(json.loads(sig_json)) if sig_json else None

    return ModelVersion(
        # Migration 0002 + 0005 use ``model_name`` as the canonical
        # column (vs. spec §5A.2's ``name``). Per ``rules/specs-authority.md``
        # Rule 5, code is canonical when the spec follows established
        # migrations. The dataclass ``ModelVersion.name`` field is part
        # of the public API and stays stable.
        name=row["model_name"],
        version=row["version"],
        stage=row["stage"],
        metrics=metrics,
        signature=signature,
        onnx_status=row.get("onnx_status", "pending"),
        onnx_error=row.get("onnx_error"),
        artifact_path=row.get("artifact_path", ""),
        model_uuid=row.get("model_uuid", ""),
        created_at=row.get("created_at", ""),
    )


# ---------------------------------------------------------------------------
# ONNX export helper
# ---------------------------------------------------------------------------


def _attempt_onnx_export(
    model_bytes: bytes,
    signature: ModelSignature | None,
) -> tuple[str, str | None, bytes | None]:
    """Attempt ONNX export. Returns (status, error_or_none, onnx_bytes_or_none)."""
    try:
        # SECURITY: pickle deserialization executes arbitrary code.
        # Only load artifacts from TRUSTED sources (models you trained yourself).
        # Do NOT load artifacts from untrusted users or external sources.
        model = pickle.loads(model_bytes)
    except Exception:
        return ("not_applicable", "Cannot unpickle model for ONNX export", None)

    if signature is None:
        return ("not_applicable", "No signature provided for ONNX export", None)

    # Check if model is a supported sklearn/lightgbm type
    model_type = type(model).__module__
    if not (model_type.startswith("sklearn") or model_type.startswith("lightgbm")):
        return (
            "not_applicable",
            f"Model type {type(model).__name__} not supported for ONNX",
            None,
        )

    try:
        import skl2onnx
        from skl2onnx.common.data_types import FloatTensorType

        n_features = len(signature.input_schema.features)
        initial_type = [("input", FloatTensorType([None, n_features]))]
        # convert_sklearn returns ModelProto with default intermediate=False.
        # The skl2onnx type stub declares a Union including the
        # (ModelProto, Topology) tuple shape (intermediate=True path).
        onnx_model: Any = skl2onnx.convert_sklearn(model, initial_types=initial_type)
        return ("success", None, onnx_model.SerializeToString())
    except ImportError:
        return ("not_applicable", "skl2onnx not installed", None)
    except Exception as exc:
        return ("failed", str(exc), None)


# ---------------------------------------------------------------------------
# MLflow serialization
# ---------------------------------------------------------------------------


def _write_mlmodel_yaml(model_info: dict[str, Any]) -> str:
    """Write MLflow MLmodel YAML format v1 (simplified).

    kailash-ml exports ONLY:
        - artifact_path
        - flavors (python_function, sklearn, lightgbm)
        - signature (inputs, outputs as column_based)
        - model_uuid
        - run_id (maps to kailash-ml version)
    """
    try:
        import yaml
    except ImportError:
        # Fallback: manual YAML-like format
        lines = []
        lines.append(f"artifact_path: {model_info.get('artifact_path', 'model')}")
        lines.append(f"model_uuid: {model_info.get('model_uuid', '')}")
        lines.append(f"run_id: {model_info.get('run_id', '')}")
        lines.append("flavors:")
        lines.append("  python_function:")
        lines.append("    loader_module: kailash_ml")
        if model_info.get("signature"):
            sig = model_info["signature"]
            lines.append("signature:")
            lines.append("  inputs: '[" + json.dumps(sig.get("inputs", [])) + "]'")
            lines.append("  outputs: '[" + json.dumps(sig.get("outputs", [])) + "]'")
        if model_info.get("metrics"):
            lines.append("metrics:")
            for m in model_info["metrics"]:
                lines.append(f"  - name: {m['name']}")
                lines.append(f"    value: {m['value']}")
        return "\n".join(lines) + "\n"

    data = {
        "artifact_path": model_info.get("artifact_path", "model"),
        "model_uuid": model_info.get("model_uuid", ""),
        "run_id": model_info.get("run_id", ""),
        "flavors": {
            "python_function": {
                "loader_module": "kailash_ml",
            }
        },
    }
    if model_info.get("signature"):
        data["signature"] = model_info["signature"]
    if model_info.get("metrics"):
        data["metrics"] = model_info["metrics"]
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


def _read_mlmodel_yaml(path: str | Path) -> dict[str, Any]:
    """Read MLflow MLmodel YAML and extract model metadata."""
    mlmodel_path = Path(path)
    if mlmodel_path.is_dir():
        mlmodel_path = mlmodel_path / "MLmodel"
    content = mlmodel_path.read_text()
    try:
        import yaml

        return yaml.safe_load(content)
    except ImportError:
        # Parse manually for basic fields
        result: dict[str, Any] = {}
        for line in content.splitlines():
            if ":" in line and not line.startswith(" "):
                key, _, val = line.partition(":")
                result[key.strip()] = val.strip()
        return result


# ---------------------------------------------------------------------------
# ModelRegistry
# ---------------------------------------------------------------------------


class ModelRegistry:
    """[P0: Production] Model registry for versioned model management.

    Parameters
    ----------
    conn:
        An initialized :class:`~kailash.db.connection.ConnectionManager`.
    artifact_store:
        Where to store model artifacts. Defaults to local filesystem.
    auto_migrate:
        If True, create tables on first use.
    """

    def __init__(
        self,
        conn: ConnectionManager,
        artifact_store: ArtifactStore | None = None,
        *,
        auto_migrate: bool = True,
    ) -> None:
        self._conn = conn
        self._artifact_store = artifact_store or LocalFileArtifactStore()
        self._auto_migrate = auto_migrate
        self._initialized = False

    async def _ensure_tables(self) -> None:
        if not self._initialized:
            if self._auto_migrate:
                # Per rules/schema-migration.md Rule 1, all DDL lives in
                # numbered migrations. Migrations 0002 + 0005 own the
                # registry's three tables; this call is idempotent.
                await _ensure_registry_tables_via_migration(self._conn)
            self._initialized = True

    @staticmethod
    def _resolve_tenant_id(tenant_id: str | None) -> str:
        """Resolve the effective tenant_id for a registry call.

        Returns ``tenant_id`` when explicitly provided; otherwise emits
        a DEBUG log line per ``rules/observability.md`` Rule 3 (schema-
        revealing default-applied is NOT WARN — it would leak schema
        identifiers to log aggregators) and returns the canonical
        single-tenant sentinel ``"default"``. Multi-tenant deployments
        MUST pass tenant_id explicitly.
        """
        if tenant_id is None or tenant_id == "":
            logger.debug(
                "model_registry.tenant_default_applied",
                extra={"resolved_tenant_id": "default"},
            )
            return "default"
        return tenant_id

    # ------------------------------------------------------------------
    # register_model
    # ------------------------------------------------------------------

    async def register_model(
        self,
        name: str,
        artifact: bytes,
        *,
        metrics: list[MetricSpec] | None = None,
        signature: ModelSignature | None = None,
        tenant_id: str = "default",
    ) -> ModelVersion:
        """Register a new model version at STAGING.

        Parameters
        ----------
        name:
            Model name (creates the model entry if new).
        artifact:
            Serialized model bytes (pickle, joblib, etc.).
        metrics:
            Evaluation metrics.
        signature:
            Input/output schema.
        tenant_id:
            Tenant scope. Defaults to the canonical single-tenant
            sentinel ``"default"``. Multi-tenant deployments MUST pass
            this explicitly. Per ``rules/tenant-isolation.md`` MUST
            Rule 1, this dimension is required on every write to the
            tenant-scoped tables.

        Returns
        -------
        ModelVersion
            The newly created version.
        """
        await self._ensure_tables()
        tenant_id = self._resolve_tenant_id(tenant_id)

        metrics = metrics or []
        model_uuid = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()

        # Prepare artifact-store writes outside transaction (filesystem, not DB)
        # ONNX export also happens outside the transaction
        onnx_status, onnx_error, onnx_bytes = _attempt_onnx_export(artifact, signature)

        # Wrap all DB reads and writes in a transaction to prevent TOCTOU race (H2)
        async with self._conn.transaction() as tx:
            # Get or create model entry, determine next version. Composite-PK
            # predicate ``(tenant_id, model_name)`` matches migration 0005.
            model_row = await tx.fetchone(
                "SELECT * FROM _kml_models WHERE tenant_id = ? " "AND model_name = ?",
                tenant_id,
                name,
            )
            if model_row is None:
                version = 1
                await tx.execute(
                    "INSERT INTO _kml_models "
                    "(tenant_id, model_name, latest_version, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    tenant_id,
                    name,
                    version,
                    now_iso,
                    now_iso,
                )
            else:
                version = model_row["latest_version"] + 1
                await tx.execute(
                    "UPDATE _kml_models SET latest_version = ?, updated_at = ? "
                    "WHERE tenant_id = ? AND model_name = ?",
                    version,
                    now_iso,
                    tenant_id,
                    name,
                )

            # Use logical artifact path (protocol-agnostic, no private access)
            artifact_path_str = f"{name}/v{version}/model.pkl"

            # Insert version row — migration 0002 + 0005 column shape:
            # (tenant_id, model_name, version, stage, run_id, created_at,
            #  promoted_at, archived_at, metrics_json, signature_json,
            #  onnx_status, onnx_error, artifact_path, model_uuid).
            # Composite PK = (tenant_id, model_name, version).
            metrics_json = json.dumps([m.to_dict() for m in metrics])
            sig_json = json.dumps(signature.to_dict()) if signature else None

            await tx.execute(
                "INSERT INTO _kml_model_versions "
                "(tenant_id, model_name, version, stage, "
                " metrics_json, signature_json, "
                " onnx_status, onnx_error, artifact_path, model_uuid, "
                " created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                tenant_id,
                name,
                version,
                "staging",
                metrics_json,
                sig_json,
                onnx_status,
                onnx_error,
                artifact_path_str,
                model_uuid,
                now_iso,
            )

        # Save artifacts to filesystem (after DB transaction commits)
        artifact_path = await self._artifact_store.save(
            name, version, artifact, "model.pkl"
        )
        if onnx_bytes is not None:
            await self._artifact_store.save(name, version, onnx_bytes, "model.onnx")

        # Write model metadata alongside artifact
        metadata = {
            "name": name,
            "version": version,
            "signature": signature.to_dict() if signature else None,
            "metrics": [m.to_dict() for m in metrics],
            "onnx_status": onnx_status,
            "model_uuid": model_uuid,
        }
        metadata_bytes = json.dumps(metadata, indent=2).encode()
        await self._artifact_store.save(
            name, version, metadata_bytes, "model_metadata.json"
        )

        logger.info("Registered model '%s' v%d (onnx=%s).", name, version, onnx_status)

        return ModelVersion(
            name=name,
            version=version,
            stage="staging",
            metrics=metrics,
            signature=signature,
            onnx_status=onnx_status,
            onnx_error=onnx_error,
            artifact_path=artifact_path,
            model_uuid=model_uuid,
            created_at=now_iso,
        )

    # ------------------------------------------------------------------
    # get_model
    # ------------------------------------------------------------------

    async def get_model(
        self,
        name: str,
        version: int | None = None,
        *,
        stage: str | None = None,
        tenant_id: str = "default",
    ) -> ModelVersion:
        """Retrieve a model version.

        Parameters
        ----------
        name:
            Model name.
        version:
            Specific version number. If None, returns latest.
        stage:
            Filter by stage (e.g. "production").
        tenant_id:
            Tenant scope. Defaults to ``"default"`` (single-tenant
            sentinel). Multi-tenant deployments MUST pass explicitly
            per ``rules/tenant-isolation.md`` MUST Rule 1.

        Returns
        -------
        ModelVersion

        Raises
        ------
        ModelNotFoundError
            If the model or version does not exist.
        """
        await self._ensure_tables()
        tenant_id = self._resolve_tenant_id(tenant_id)

        if stage is not None:
            row = await _get_version_by_stage(
                self._conn, name, stage, tenant_id=tenant_id
            )
            if row is None:
                raise ModelNotFoundError(
                    reason=f"No version of model '{name}' at stage '{stage}'.",
                    resource_id=name,
                )
            return _row_to_model_version(row)

        if version is not None:
            row = await _get_version_row(self._conn, name, version, tenant_id=tenant_id)
            if row is None:
                raise ModelNotFoundError(
                    reason=f"Model '{name}' version {version} not found.",
                    resource_id=name,
                    version=version,
                )
            return _row_to_model_version(row)

        # Latest version
        model_row = await _get_model_row(self._conn, name, tenant_id=tenant_id)
        if model_row is None:
            raise ModelNotFoundError(
                reason=f"Model '{name}' not found.", resource_id=name
            )
        row = await _get_version_row(
            self._conn, name, model_row["latest_version"], tenant_id=tenant_id
        )
        if row is None:
            raise ModelNotFoundError(
                reason=f"Model '{name}' has no versions.", resource_id=name
            )
        return _row_to_model_version(row)

    # ------------------------------------------------------------------
    # list_models
    # ------------------------------------------------------------------

    async def list_models(self, *, tenant_id: str = "default") -> list[dict[str, Any]]:
        """List all registered models within ``tenant_id``.

        Parameters
        ----------
        tenant_id:
            Tenant scope. Defaults to ``"default"``.

        Returns
        -------
        list[dict]
            Model metadata dicts with model_name, latest_version, etc.
        """
        await self._ensure_tables()
        tenant_id = self._resolve_tenant_id(tenant_id)
        return await self._conn.fetch(
            "SELECT model_name, latest_version, created_at, updated_at "
            "FROM _kml_models WHERE tenant_id = ? ORDER BY model_name",
            tenant_id,
        )

    # ------------------------------------------------------------------
    # promote_model
    # ------------------------------------------------------------------

    async def promote_model(
        self,
        name: str,
        version: int,
        target_stage: str,
        *,
        reason: str = "",
        tenant_id: str = "default",
    ) -> ModelVersion:
        """Transition a model version to a new stage.

        Parameters
        ----------
        name:
            Model name.
        version:
            Version number.
        target_stage:
            Target stage ("staging", "shadow", "production", "archived").
        reason:
            Optional reason for the transition.

        Returns
        -------
        ModelVersion
            Updated version.

        Raises
        ------
        ValueError
            If the transition is not valid.
        ModelNotFoundError
            If the model version does not exist.
        """
        await self._ensure_tables()
        tenant_id = self._resolve_tenant_id(tenant_id)

        if target_stage not in ALL_STAGES:
            raise ValueError(f"Invalid stage: {target_stage}")

        model_version = await self.get_model(name, version, tenant_id=tenant_id)
        current_stage = model_version.stage

        valid = VALID_TRANSITIONS.get(current_stage, set())
        if target_stage not in valid:
            raise ValueError(
                f"Invalid transition: {current_stage} -> {target_stage}. "
                f"Valid targets from '{current_stage}': {sorted(valid)}"
            )

        # If promoting to production, demote current production version
        if target_stage == "production":
            try:
                current_prod = await self.get_model(
                    name, stage="production", tenant_id=tenant_id
                )
                await self._update_stage(
                    name, current_prod.version, "archived", tenant_id=tenant_id
                )
                await self._record_transition(
                    name,
                    current_prod.version,
                    "production",
                    "archived",
                    f"replaced by v{version}",
                    tenant_id=tenant_id,
                )
            except ModelNotFoundError:
                pass  # No existing production version

        await self._update_stage(name, version, target_stage, tenant_id=tenant_id)
        await self._record_transition(
            name, version, current_stage, target_stage, reason, tenant_id=tenant_id
        )

        return await self.get_model(name, version, tenant_id=tenant_id)

    # ------------------------------------------------------------------
    # get_model_versions
    # ------------------------------------------------------------------

    async def get_model_versions(
        self, name: str, *, tenant_id: str = "default"
    ) -> list[ModelVersion]:
        """Return all versions of a model, newest first.

        Parameters
        ----------
        name:
            Model name.
        tenant_id:
            Tenant scope. Defaults to ``"default"``.

        Returns
        -------
        list[ModelVersion]
        """
        await self._ensure_tables()
        tenant_id = self._resolve_tenant_id(tenant_id)

        rows = await self._conn.fetch(
            "SELECT * FROM _kml_model_versions WHERE tenant_id = ? "
            "AND model_name = ? ORDER BY version DESC",
            tenant_id,
            name,
        )
        return [_row_to_model_version(r) for r in rows]

    # ------------------------------------------------------------------
    # compare
    # ------------------------------------------------------------------

    async def compare(
        self,
        name: str,
        version_a: int,
        version_b: int,
    ) -> dict[str, Any]:
        """Compare two model versions on their stored metrics.

        Returns a dict with metrics for each version and the deltas.

        Raises
        ------
        ValueError
            If either version does not exist.
        """
        await self._ensure_tables()

        mv_a = await self.get_model(name, version_a)
        mv_b = await self.get_model(name, version_b)

        if mv_a is None:
            raise ValueError(f"Model '{name}' version {version_a} not found")
        if mv_b is None:
            raise ValueError(f"Model '{name}' version {version_b} not found")

        metrics_a = {m.name: m.value for m in mv_a.metrics}
        metrics_b = {m.name: m.value for m in mv_b.metrics}

        all_metric_names = sorted(set(metrics_a) | set(metrics_b))
        deltas: dict[str, float] = {}
        for m in all_metric_names:
            val_a = metrics_a.get(m, 0.0)
            val_b = metrics_b.get(m, 0.0)
            deltas[m] = val_b - val_a

        return {
            "name": name,
            "version_a": version_a,
            "version_b": version_b,
            "metrics_a": metrics_a,
            "metrics_b": metrics_b,
            "deltas": deltas,
            "better_version": (version_b if sum(deltas.values()) > 0 else version_a),
        }

    # ------------------------------------------------------------------
    # load_artifact
    # ------------------------------------------------------------------

    async def load_artifact(
        self,
        name: str,
        version: int,
        filename: str = "model.pkl",
    ) -> bytes:
        """Load a model artifact from the artifact store."""
        return await self._artifact_store.load(name, version, filename)

    # ------------------------------------------------------------------
    # MLflow export/import
    # ------------------------------------------------------------------

    async def export_mlflow(
        self,
        name: str,
        version: int,
        output_dir: str | Path,
    ) -> Path:
        """Export model to MLflow MLmodel format v1.

        Returns the directory containing the MLmodel file and artifact.
        """
        await self._ensure_tables()

        mv = await self.get_model(name, version)
        out = Path(output_dir) / name / str(version)
        out.mkdir(parents=True, exist_ok=True)

        # Copy model artifact
        artifact_data = await self._artifact_store.load(name, version, "model.pkl")
        (out / "model.pkl").write_bytes(artifact_data)

        # Write MLmodel YAML
        model_info: dict[str, Any] = {
            "artifact_path": "model.pkl",
            "model_uuid": mv.model_uuid,
            "run_id": f"{name}-v{version}",
        }
        if mv.signature:
            model_info["signature"] = mv.signature.to_dict()
        if mv.metrics:
            model_info["metrics"] = [m.to_dict() for m in mv.metrics]
        mlmodel_content = _write_mlmodel_yaml(model_info)
        (out / "MLmodel").write_text(mlmodel_content)

        # Copy metadata
        try:
            meta_data = await self._artifact_store.load(
                name, version, "model_metadata.json"
            )
            (out / "model_metadata.json").write_bytes(meta_data)
        except FileNotFoundError:
            pass

        logger.info("Exported MLflow for '%s' v%d to %s.", name, version, out)
        return out

    async def import_mlflow(self, mlmodel_dir: str | Path) -> ModelVersion:
        """Import a model from MLflow MLmodel format v1.

        Reads the MLmodel YAML and model artifact, registers in the registry.
        """
        await self._ensure_tables()

        mlmodel_dir = Path(mlmodel_dir)
        mlmodel_data = _read_mlmodel_yaml(mlmodel_dir)

        # Load artifact
        artifact_filename = mlmodel_data.get("artifact_path", "model.pkl")
        artifact_path = mlmodel_dir / artifact_filename
        if not artifact_path.exists():
            raise FileNotFoundError(f"Artifact not found: {artifact_path}")
        artifact_bytes = artifact_path.read_bytes()

        # Extract metadata
        metrics: list[MetricSpec] = []
        if "metrics" in mlmodel_data and isinstance(mlmodel_data["metrics"], list):
            for m in mlmodel_data["metrics"]:
                if isinstance(m, dict):
                    metrics.append(MetricSpec.from_dict(m))

        signature: ModelSignature | None = None
        if "signature" in mlmodel_data and isinstance(mlmodel_data["signature"], dict):
            try:
                signature = ModelSignature.from_dict(mlmodel_data["signature"])
            except (KeyError, TypeError):
                pass

        # Derive name from directory structure or model_uuid
        name = mlmodel_dir.parent.name if mlmodel_dir.parent.name != "." else "imported"

        # Check for metadata file
        meta_path = mlmodel_dir / "model_metadata.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            if "metrics" in meta and not metrics:
                metrics = [MetricSpec.from_dict(m) for m in meta["metrics"]]
            if "signature" in meta and meta["signature"] and not signature:
                try:
                    signature = ModelSignature.from_dict(meta["signature"])
                except (KeyError, TypeError):
                    pass
            if "name" in meta:
                name = meta["name"]

        return await self.register_model(
            name,
            artifact_bytes,
            metrics=metrics,
            signature=signature,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _update_stage(
        self, name: str, version: int, stage: str, *, tenant_id: str
    ) -> None:
        """Update the stage of a model version. Composite-PK predicate
        ``(tenant_id, model_name, version)`` matches migration 0002.
        """
        await self._conn.execute(
            "UPDATE _kml_model_versions SET stage = ? "
            "WHERE tenant_id = ? AND model_name = ? AND version = ?",
            stage,
            tenant_id,
            name,
            version,
        )

    async def _record_transition(
        self,
        name: str,
        version: int,
        from_stage: str,
        to_stage: str,
        reason: str = "",
        *,
        tenant_id: str,
    ) -> None:
        """Append an immutable row to ``_kml_model_transitions``.

        Per migration 0005's schema, the row carries ``(id, tenant_id,
        model_name, version, from_stage, to_stage, reason,
        transitioned_at)``. ``tenant_id`` is required so transition
        queries can scope to the caller's tenant.
        """
        tid = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            "INSERT INTO _kml_model_transitions "
            "(id, tenant_id, model_name, version, from_stage, to_stage, "
            " reason, transitioned_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            tid,
            tenant_id,
            name,
            version,
            from_stage,
            to_stage,
            reason,
            now_iso,
        )

    # ------------------------------------------------------------------
    # Lineage (W7-001 — closes issue #657)
    # ------------------------------------------------------------------

    async def record_lineage(
        self,
        *,
        name: str,
        version: int,
        tenant_id: str,
        tracker_run_id: str,
        parent_version: int | None = None,
        training_data_uri: str | None = None,
        feature_store_version: str | None = None,
        base_model_uri: str | None = None,
    ) -> None:
        """Persist one ``_kml_lineage`` row for a registered model version.

        Idempotent on the PK ``(tenant_id, name, version)`` — repeated
        calls for the same triple replace the prior row's mutable
        fields (``parent_version`` / ``training_data_uri`` /
        ``feature_store_version`` / ``base_model_uri``) so a re-run of
        ``km.train`` followed by ``km.register`` updates the existing
        lineage row rather than failing on a UNIQUE-constraint
        violation. The ``tracker_run_id`` is the audit-trail correlation
        key per ``ml-tracking.md §6.3``.

        Args:
            name: Model name (matches ``_kml_model_versions.name``).
            version: Model version (matches ``_kml_model_versions.version``).
            tenant_id: Tenant scope. Required — the lineage table has
                no single-tenant fast path; callers MUST resolve via
                :func:`kailash_ml.tracking.get_current_tenant_id` and
                fall through the canonical sentinel ``"_single"`` per
                ``ml-tracking.md §7.2``.
            tracker_run_id: ID of the producing
                :class:`~kailash_ml.tracking.runner.ExperimentRun`.
            parent_version: When this model derives from another version
                of the same model (transfer learning, fine-tuning), the
                parent's version integer.
            training_data_uri: SHA-prefixed dataset hash or storage URI.
            feature_store_version: ``group@version`` of the feature
                store snapshot consumed.
            base_model_uri: Pretrained base-model URI when applicable
                (LoRA / fine-tuning / continued-training).
        """
        from kailash_ml.engines.lineage import (  # local-import to keep startup graph clean
            LINEAGE_TABLE,
        )

        # Idempotent UPSERT — DELETE + INSERT round-trip avoids dialect
        # divergence between Postgres ``ON CONFLICT`` and SQLite
        # ``ON CONFLICT``. The framework's ConnectionManager handles
        # the parameter binding for the VALUES — only the table name is
        # interpolated, and it's a Python-literal constant from the
        # canonical ``LINEAGE_TABLE``.
        async with self._conn.transaction() as tx:
            await tx.execute(
                f"DELETE FROM {LINEAGE_TABLE} WHERE tenant_id = ? "
                f"AND model_name = ? AND version = ?",
                tenant_id,
                name,
                version,
            )
            await tx.execute(
                f"INSERT INTO {LINEAGE_TABLE} ("
                f"tenant_id, model_name, version, tracker_run_id, "
                f"parent_version, training_data_uri, "
                f"feature_store_version, base_model_uri"
                f") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                tenant_id,
                name,
                version,
                tracker_run_id,
                parent_version,
                training_data_uri,
                feature_store_version,
                base_model_uri,
            )

    async def build_lineage_graph(
        self,
        *,
        ref: str,
        tenant_id: str,
        max_depth: int = 10,
    ):
        """Construct the cross-engine lineage graph rooted at ``ref``.

        ``ref`` is the canonical ``model@vN`` form (e.g. ``"churn@v3"``)
        OR a bare model name (the latest version is resolved). Per
        ``ml-engines-v2-addendum §E10.3``, cross-tenant traversal raises
        :class:`~kailash_ml.errors.CrossTenantLineageError`.

        See :func:`kailash_ml.engines.lineage.build_lineage_graph` for
        the walker contract.
        """
        from kailash_ml.engines.lineage import LineageGraph, build_lineage_graph

        name, version = _parse_model_ref(ref)
        if version is None:
            await self._ensure_tables()
            model_row = await _get_model_row(self._conn, name, tenant_id=tenant_id)
            if model_row is None:
                raise ModelNotFoundError(
                    reason=f"Model {name!r} not found; cannot build lineage graph.",
                    resource_id=name,
                )
            version = int(model_row["latest_version"])

        graph: LineageGraph = await build_lineage_graph(
            self._conn,
            name=name,
            version=version,
            tenant_id=tenant_id,
            max_depth=max_depth,
        )
        return graph


def _parse_model_ref(ref: str) -> tuple[str, int | None]:
    """Split ``ref`` into ``(name, version|None)``.

    Accepts ``"name"`` and ``"name@vN"``. Anything else raises
    :class:`ValueError` so the caller can surface the malformed ref to
    the user before the walker fires.
    """
    if not isinstance(ref, str) or not ref:
        raise ValueError(f"lineage ref must be a non-empty string; got {ref!r}")
    if "@" not in ref:
        return (ref, None)
    name, _, vpart = ref.rpartition("@")
    if not vpart.startswith("v"):
        raise ValueError(
            f"lineage ref version segment MUST start with 'v' (e.g. 'name@v3'); "
            f"got {ref!r}"
        )
    try:
        version = int(vpart[1:])
    except ValueError as exc:
        raise ValueError(
            f"lineage ref version segment MUST be an integer; got {ref!r}"
        ) from exc
    return (name, version)
