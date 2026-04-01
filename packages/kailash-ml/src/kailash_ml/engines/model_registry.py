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
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from kailash.db.connection import ConnectionManager
from kailash.db.dialect import _validate_identifier
from kailash_ml_protocols import MetricSpec, ModelSignature

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


class ModelNotFoundError(Exception):
    """Raised when a model or version is not found."""


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


async def _create_registry_tables(conn: ConnectionManager) -> None:
    """Create the model registry tables if they do not exist."""
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS _kml_models ("
        "  name TEXT PRIMARY KEY,"
        "  latest_version INTEGER NOT NULL DEFAULT 0,"
        "  created_at TEXT NOT NULL,"
        "  updated_at TEXT NOT NULL"
        ")"
    )
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS _kml_model_versions ("
        "  name TEXT NOT NULL,"
        "  version INTEGER NOT NULL,"
        "  stage TEXT NOT NULL DEFAULT 'staging',"
        "  metrics_json TEXT NOT NULL DEFAULT '[]',"
        "  signature_json TEXT,"
        "  onnx_status TEXT NOT NULL DEFAULT 'pending',"
        "  onnx_error TEXT,"
        "  artifact_path TEXT NOT NULL DEFAULT '',"
        "  model_uuid TEXT NOT NULL,"
        "  created_at TEXT NOT NULL,"
        "  PRIMARY KEY (name, version)"
        ")"
    )
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS _kml_model_transitions ("
        "  id TEXT PRIMARY KEY,"
        "  name TEXT NOT NULL,"
        "  version INTEGER NOT NULL,"
        "  from_stage TEXT NOT NULL,"
        "  to_stage TEXT NOT NULL,"
        "  reason TEXT NOT NULL DEFAULT '',"
        "  transitioned_at TEXT NOT NULL"
        ")"
    )


async def _get_model_row(conn: ConnectionManager, name: str) -> dict[str, Any] | None:
    return await conn.fetchone("SELECT * FROM _kml_models WHERE name = ?", name)


async def _get_version_row(
    conn: ConnectionManager, name: str, version: int
) -> dict[str, Any] | None:
    return await conn.fetchone(
        "SELECT * FROM _kml_model_versions WHERE name = ? AND version = ?",
        name,
        version,
    )


async def _get_version_by_stage(
    conn: ConnectionManager, name: str, stage: str
) -> dict[str, Any] | None:
    return await conn.fetchone(
        "SELECT * FROM _kml_model_versions WHERE name = ? AND stage = ? "
        "ORDER BY version DESC LIMIT 1",
        name,
        stage,
    )


def _row_to_model_version(row: dict[str, Any]) -> ModelVersion:
    metrics_json = row.get("metrics_json", "[]")
    metrics = [MetricSpec.from_dict(m) for m in json.loads(metrics_json)]

    sig_json = row.get("signature_json")
    signature = ModelSignature.from_dict(json.loads(sig_json)) if sig_json else None

    return ModelVersion(
        name=row["name"],
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
        onnx_model = skl2onnx.convert_sklearn(model, initial_types=initial_type)
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
                await _create_registry_tables(self._conn)
            self._initialized = True

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

        Returns
        -------
        ModelVersion
            The newly created version.
        """
        await self._ensure_tables()

        metrics = metrics or []
        model_uuid = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()

        # Prepare artifact-store writes outside transaction (filesystem, not DB)
        # ONNX export also happens outside the transaction
        onnx_status, onnx_error, onnx_bytes = _attempt_onnx_export(artifact, signature)

        # Wrap all DB reads and writes in a transaction to prevent TOCTOU race (H2)
        async with self._conn.transaction() as tx:
            # Get or create model entry, determine next version
            model_row = await tx.fetchone(
                "SELECT * FROM _kml_models WHERE name = ?", name
            )
            if model_row is None:
                version = 1
                await tx.execute(
                    "INSERT INTO _kml_models (name, latest_version, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    name,
                    version,
                    now_iso,
                    now_iso,
                )
            else:
                version = model_row["latest_version"] + 1
                await tx.execute(
                    "UPDATE _kml_models SET latest_version = ?, updated_at = ? WHERE name = ?",
                    version,
                    now_iso,
                    name,
                )

            # Compute artifact path (store saves happen after transaction)
            artifact_path_str = str(
                self._artifact_store._root / name / str(version) / "model.pkl"
            )

            # Insert version row
            metrics_json = json.dumps([m.to_dict() for m in metrics])
            sig_json = json.dumps(signature.to_dict()) if signature else None

            await tx.execute(
                "INSERT INTO _kml_model_versions "
                "(name, version, stage, metrics_json, signature_json, "
                " onnx_status, onnx_error, artifact_path, model_uuid, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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

        Returns
        -------
        ModelVersion

        Raises
        ------
        ModelNotFoundError
            If the model or version does not exist.
        """
        await self._ensure_tables()

        if stage is not None:
            row = await _get_version_by_stage(self._conn, name, stage)
            if row is None:
                raise ModelNotFoundError(
                    f"No version of model '{name}' at stage '{stage}'."
                )
            return _row_to_model_version(row)

        if version is not None:
            row = await _get_version_row(self._conn, name, version)
            if row is None:
                raise ModelNotFoundError(f"Model '{name}' version {version} not found.")
            return _row_to_model_version(row)

        # Latest version
        model_row = await _get_model_row(self._conn, name)
        if model_row is None:
            raise ModelNotFoundError(f"Model '{name}' not found.")
        row = await _get_version_row(self._conn, name, model_row["latest_version"])
        if row is None:
            raise ModelNotFoundError(f"Model '{name}' has no versions.")
        return _row_to_model_version(row)

    # ------------------------------------------------------------------
    # list_models
    # ------------------------------------------------------------------

    async def list_models(self) -> list[dict[str, Any]]:
        """List all registered models.

        Returns
        -------
        list[dict]
            Model metadata dicts with name, latest_version, etc.
        """
        await self._ensure_tables()
        return await self._conn.fetch(
            "SELECT name, latest_version, created_at, updated_at "
            "FROM _kml_models ORDER BY name"
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

        if target_stage not in ALL_STAGES:
            raise ValueError(f"Invalid stage: {target_stage}")

        model_version = await self.get_model(name, version)
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
                current_prod = await self.get_model(name, stage="production")
                await self._update_stage(name, current_prod.version, "archived")
                await self._record_transition(
                    name,
                    current_prod.version,
                    "production",
                    "archived",
                    f"replaced by v{version}",
                )
            except ModelNotFoundError:
                pass  # No existing production version

        await self._update_stage(name, version, target_stage)
        await self._record_transition(
            name, version, current_stage, target_stage, reason
        )

        return await self.get_model(name, version)

    # ------------------------------------------------------------------
    # get_model_versions
    # ------------------------------------------------------------------

    async def get_model_versions(self, name: str) -> list[ModelVersion]:
        """Return all versions of a model, newest first.

        Returns
        -------
        list[ModelVersion]
        """
        await self._ensure_tables()

        rows = await self._conn.fetch(
            "SELECT * FROM _kml_model_versions WHERE name = ? ORDER BY version DESC",
            name,
        )
        return [_row_to_model_version(r) for r in rows]

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

    async def _update_stage(self, name: str, version: int, stage: str) -> None:
        await self._conn.execute(
            "UPDATE _kml_model_versions SET stage = ? WHERE name = ? AND version = ?",
            stage,
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
    ) -> None:
        tid = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            "INSERT INTO _kml_model_transitions "
            "(id, name, version, from_stage, to_stage, reason, transitioned_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            tid,
            name,
            version,
            from_stage,
            to_stage,
            reason,
            now_iso,
        )
