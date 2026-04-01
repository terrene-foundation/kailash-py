# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""FileSourceNode -- CSV, Excel, Parquet, JSON/JSONL ingestion.

Reads tabular data from files and produces records compatible with
``BulkCreateNode`` and ``BulkUpsertNode``.  Registered as a standalone
utility node (not per-model).

Lazy imports for ``openpyxl`` (Excel) and ``pyarrow`` (Parquet) ensure
``pip install kailash-dataflow`` (base) works without these heavy
optional dependencies.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from kailash.nodes.base_async import AsyncNode

logger = logging.getLogger(__name__)

__all__ = ["FileSourceNode"]

# ---------------------------------------------------------------------------
# Format constants
# ---------------------------------------------------------------------------

SUPPORTED_FORMATS = {"csv", "tsv", "excel", "parquet", "json", "jsonl"}

EXTENSION_MAP: Dict[str, str] = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".xlsx": "excel",
    ".xls": "excel",
    ".parquet": "parquet",
    ".json": "json",
    ".jsonl": "jsonl",
}

TYPE_COERCIONS: Dict[str, Callable[[Any], Any]] = {
    "int": int,
    "float": float,
    "str": str,
    "bool": lambda v: (
        v if isinstance(v, bool) else str(v).lower() in ("true", "1", "yes")
    ),
    "datetime": lambda v: datetime.fromisoformat(str(v)),
}


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class DataFlowDependencyError(ImportError):
    """Raised when an optional dependency is missing for a file format."""

    pass


# ---------------------------------------------------------------------------
# FileSourceNode
# ---------------------------------------------------------------------------


class FileSourceNode(AsyncNode):
    """Read tabular data from CSV, Excel, Parquet, or JSON files.

    Produces output compatible with ``BulkCreateNode`` / ``BulkUpsertNode``::

        {"records": [...], "count": N, "errors": [...]}

    Supports column renaming (``column_mapping``), type coercion
    (``type_coercion``), and batched output (``batch_size``).
    """

    node_type = "FileSourceNode"

    def get_parameters(self) -> dict:  # type: ignore[override]
        """Return parameter definitions for the node."""
        from kailash.nodes.base import NodeParameter

        return {
            "file_path": NodeParameter(
                name="file_path",
                type=str,
                required=True,
                description="Path to the input file",
            ),
            "format": NodeParameter(
                name="format",
                type=str,
                required=False,
                default="auto",
                description="File format (auto, csv, tsv, excel, parquet, json, jsonl)",
            ),
            "column_mapping": NodeParameter(
                name="column_mapping",
                type=dict,
                required=False,
                default=None,
                description="Column rename mapping {source: target}",
            ),
            "type_coercion": NodeParameter(
                name="type_coercion",
                type=dict,
                required=False,
                default=None,
                description="Type coercion mapping {field: type_name}",
            ),
            "batch_size": NodeParameter(
                name="batch_size",
                type=int,
                required=False,
                default=1000,
                description="Records per batch",
            ),
            "skip_rows": NodeParameter(
                name="skip_rows",
                type=int,
                required=False,
                default=0,
                description="Number of leading rows to skip (CSV only)",
            ),
            "encoding": NodeParameter(
                name="encoding",
                type=str,
                required=False,
                default="utf-8",
                description="File encoding",
            ),
            "delimiter": NodeParameter(
                name="delimiter",
                type=str,
                required=False,
                default=None,
                description="CSV delimiter override",
            ),
        }

    async def async_run(  # type: ignore[override]
        self,
        file_path: str,
        format: str = "auto",
        column_mapping: Optional[Dict[str, str]] = None,
        type_coercion: Optional[Dict[str, str]] = None,
        skip_rows: int = 0,
        encoding: str = "utf-8",
        delimiter: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Read tabular data from a file.

        Args:
            file_path: Path to the input file.
            format: File format (``"auto"`` detects from extension).
            column_mapping: ``{source_col: target_col}`` renames applied first.
            type_coercion: ``{field: type_name}`` coercions applied after mapping.
            batch_size: Maximum records per batch (output is always flat).
            skip_rows: Number of leading rows to skip (CSV only).
            encoding: File encoding (CSV / JSONL).
            delimiter: CSV delimiter override (``None`` = auto).

        Returns:
            ``{"records": [...], "count": int, "errors": [...]}``
        """
        path = Path(file_path).resolve()
        # Security: prevent path traversal (H-NEW-01)
        if ".." in Path(file_path).parts:
            raise ValueError(
                f"Path traversal detected in file_path: {file_path}. "
                f"Use absolute paths or paths without '..' components."
            )
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        detected_format = self._detect_format(str(path), format)

        # Read raw records
        records = self._read(
            path,
            detected_format,
            encoding=encoding,
            skip_rows=skip_rows,
            delimiter=delimiter,
        )

        # Apply column mapping
        if column_mapping:
            records = self._apply_mapping(records, column_mapping)

        # Apply type coercion
        errors: List[str] = []
        if type_coercion:
            records, errors = self._apply_coercion(records, type_coercion)

        return {
            "records": records,
            "count": len(records),
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Format detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_format(file_path: str, requested: str) -> str:
        """Resolve the file format from extension or explicit override."""
        if requested != "auto":
            fmt = requested.lower()
            if fmt not in SUPPORTED_FORMATS:
                raise ValueError(
                    f"Unsupported format '{fmt}'. "
                    f"Supported: {', '.join(sorted(SUPPORTED_FORMATS))}"
                )
            return fmt

        ext = Path(file_path).suffix.lower()
        fmt = EXTENSION_MAP.get(ext)
        if fmt is None:
            raise ValueError(
                f"Cannot detect format from extension '{ext}'. "
                f"Supported extensions: {', '.join(sorted(EXTENSION_MAP.keys()))}. "
                f"Use the 'format' parameter to specify explicitly."
            )
        return fmt

    # ------------------------------------------------------------------
    # Reader dispatch
    # ------------------------------------------------------------------

    def _read(
        self,
        path: Path,
        fmt: str,
        *,
        encoding: str,
        skip_rows: int,
        delimiter: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Dispatch to the appropriate reader."""
        if fmt == "csv" or fmt == "tsv":
            effective_delimiter = (
                delimiter if delimiter is not None else ("\t" if fmt == "tsv" else ",")
            )
            return self._read_csv(path, encoding, skip_rows, effective_delimiter)
        elif fmt == "json":
            return self._read_json(path, encoding)
        elif fmt == "jsonl":
            return self._read_jsonl(path, encoding)
        elif fmt == "excel":
            return self._read_excel(path)
        elif fmt == "parquet":
            return self._read_parquet(path)
        else:
            raise ValueError(f"Unsupported format: {fmt}")

    # ------------------------------------------------------------------
    # Individual readers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_csv(
        path: Path, encoding: str, skip_rows: int, delimiter: str
    ) -> List[Dict[str, Any]]:
        """Read CSV / TSV using stdlib ``csv.DictReader``."""
        records: List[Dict[str, Any]] = []
        with open(path, newline="", encoding=encoding) as fh:
            # Skip leading rows
            for _ in range(skip_rows):
                next(fh, None)
            reader = csv.DictReader(fh, delimiter=delimiter)
            for row in reader:
                records.append(dict(row))
        return records

    @staticmethod
    def _read_json(path: Path, encoding: str) -> List[Dict[str, Any]]:
        """Read a JSON file containing a ``List[Dict]``."""
        with open(path, encoding=encoding) as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            raise ValueError(
                f"JSON file must contain a list of objects, got {type(data).__name__}"
            )
        return data

    @staticmethod
    def _read_jsonl(path: Path, encoding: str) -> List[Dict[str, Any]]:
        """Read a JSONL file (one JSON object per line)."""
        records: List[Dict[str, Any]] = []
        with open(path, encoding=encoding) as fh:
            for line_no, line in enumerate(fh, 1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    obj = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON on line {line_no}: {exc}") from exc
                records.append(obj)
        return records

    @staticmethod
    def _read_excel(path: Path) -> List[Dict[str, Any]]:
        """Read an Excel file via lazy ``openpyxl`` import."""
        try:
            import openpyxl
        except ImportError as exc:
            raise DataFlowDependencyError(
                "openpyxl is required for Excel files. "
                "Install with: pip install kailash-dataflow[excel]"
            ) from exc

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        if ws is None:
            wb.close()
            return []
        rows = list(ws.iter_rows(values_only=True))
        wb.close()

        if not rows:
            return []

        headers = [
            str(h) if h is not None else f"col_{i}" for i, h in enumerate(rows[0])
        ]
        records: List[Dict[str, Any]] = []
        for row in rows[1:]:
            record = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
            records.append(record)
        return records

    @staticmethod
    def _read_parquet(path: Path) -> List[Dict[str, Any]]:
        """Read a Parquet file via lazy ``pyarrow`` import."""
        try:
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise DataFlowDependencyError(
                "pyarrow is required for Parquet files. "
                "Install with: pip install kailash-dataflow[parquet]"
            ) from exc

        table = pq.read_table(str(path))
        return table.to_pylist()

    # ------------------------------------------------------------------
    # Transforms
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_mapping(
        records: List[Dict[str, Any]], mapping: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """Rename columns according to *mapping* (source -> target)."""
        mapped: List[Dict[str, Any]] = []
        for record in records:
            new_record: Dict[str, Any] = {}
            for key, value in record.items():
                new_key = mapping.get(key, key)
                new_record[new_key] = value
            mapped.append(new_record)
        return mapped

    @staticmethod
    def _apply_coercion(
        records: List[Dict[str, Any]], coercion: Dict[str, str]
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Coerce field values; fail-soft (warnings + errors list)."""
        errors: List[str] = []
        for row_idx, record in enumerate(records):
            for field_name, type_name in coercion.items():
                if field_name not in record:
                    continue
                coerce_fn = TYPE_COERCIONS.get(type_name)
                if coerce_fn is None:
                    errors.append(
                        f"Row {row_idx}: unknown coercion type '{type_name}' "
                        f"for field '{field_name}'"
                    )
                    continue
                try:
                    record[field_name] = coerce_fn(record[field_name])
                except (ValueError, TypeError) as exc:
                    errors.append(
                        f"Row {row_idx}: failed to coerce field '{field_name}' "
                        f"value {record[field_name]!r} to {type_name}: {exc}"
                    )
                    logger.warning(
                        "Coercion failed for row %d field '%s': %s",
                        row_idx,
                        field_name,
                        exc,
                    )
        return records, errors
