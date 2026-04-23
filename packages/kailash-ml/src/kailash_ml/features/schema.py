# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""FeatureSchema — frozen content-addressed feature specification.

The 1.0.0 spec (``specs/ml-feature-store.md §3``) keys features by
``(name, version, fields)``. Version bumps are explicit — a caller who
edits feature semantics bumps ``version`` to force a new registry row.

Polars dtype strings are validated against a small allowlist so a typo
fails at construction rather than at materialisation time.

Per ``rules/orphan-detection.md §6`` every public symbol is eagerly
imported from ``kailash_ml.features`` and listed in ``__all__``.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field as _dc_field
from typing import Any

__all__ = [
    "ALLOWED_DTYPES",
    "FeatureField",
    "FeatureSchema",
]

# ---------------------------------------------------------------------------
# Dtype allowlist
# ---------------------------------------------------------------------------

# Polars-first dtype string registry. Synonyms are normalised to the canonical
# left-hand key at construction time so comparison is deterministic.
ALLOWED_DTYPES: frozenset[str] = frozenset(
    {
        # integers
        "int8",
        "int16",
        "int32",
        "int64",
        "uint8",
        "uint16",
        "uint32",
        "uint64",
        # floats
        "float32",
        "float64",
        # text
        "utf8",
        "string",
        # bool
        "bool",
        # temporal
        "date",
        "datetime",
        "duration",
        "time",
        # binary
        "binary",
        # categorical
        "categorical",
    }
)

_DTYPE_SYNONYMS: dict[str, str] = {
    # numpy-style floats
    "float": "float64",
    "double": "float64",
    # numpy-style ints
    "int": "int64",
    "long": "int64",
    # text
    "str": "utf8",
    "text": "utf8",
    "string": "utf8",
    # bool
    "boolean": "bool",
}

# Identifier regex — letters, digits, underscores, leading letter/underscore.
_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _normalise_dtype(dtype: str) -> str:
    """Lowercase + synonym-resolve a dtype string; validate against allowlist."""
    if not isinstance(dtype, str):
        raise TypeError(
            f"FeatureField.dtype must be a string, got {type(dtype).__name__}"
        )
    lower = dtype.strip().lower()
    canonical = _DTYPE_SYNONYMS.get(lower, lower)
    if canonical not in ALLOWED_DTYPES:
        raise ValueError(
            f"FeatureField.dtype {dtype!r} is not a polars-native dtype. "
            f"Allowed: {sorted(ALLOWED_DTYPES)}. See "
            f"specs/ml-feature-store.md §3 for the polars-native contract."
        )
    return canonical


def _validate_name(name: str, *, label: str) -> None:
    """Validate identifier-like strings (schema name, field name)."""
    if not isinstance(name, str):
        raise TypeError(f"{label} must be a string, got {type(name).__name__}")
    if not name:
        raise ValueError(f"{label} must be non-empty")
    if not _NAME_RE.match(name):
        # Do NOT echo the raw name back — per `rules/dataflow-identifier-safety.md`
        # error messages never echo potentially-hostile identifier content.
        raise ValueError(
            f"{label} must match ^[a-zA-Z_][a-zA-Z0-9_]*$ "
            f"(fingerprint={hash(name) & 0xFFFF:04x})"
        )


# ---------------------------------------------------------------------------
# FeatureField — single feature column
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FeatureField:
    """Single feature column within a :class:`FeatureSchema`.

    Parameters
    ----------
    name:
        Column identifier. Validated against the standard SQL identifier
        regex so materialisation cannot hit an injection vector downstream.
    dtype:
        Polars-native dtype string. See :data:`ALLOWED_DTYPES` for the
        canonical set. Synonyms (``float`` / ``int`` / ``str`` / ``text`` /
        ``boolean``) are normalised to the canonical form.
    nullable:
        Whether the column may contain nulls. Default ``True``.
    description:
        Free-form human description (stored in the registry row).
    """

    name: str
    dtype: str
    nullable: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        _validate_name(self.name, label="FeatureField.name")
        # Normalise dtype via frozen-dataclass workaround
        object.__setattr__(self, "dtype", _normalise_dtype(self.dtype))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "nullable": self.nullable,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeatureField:
        return cls(
            name=data["name"],
            dtype=data["dtype"],
            nullable=bool(data.get("nullable", True)),
            description=data.get("description", ""),
        )


# ---------------------------------------------------------------------------
# FeatureSchema — content-addressed, frozen
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FeatureSchema:
    """Content-addressed schema for a feature set.

    Keyed by ``(name, version)`` inside the registry; fingerprinted by a
    stable sha256 of the ordered field list so two byte-identical schemas
    at the same version resolve to the same ``content_hash``.

    Parameters
    ----------
    name:
        Schema identifier. Validated against the standard SQL identifier
        regex (``^[a-zA-Z_][a-zA-Z0-9_]*$``). Downstream DDL emitted by the
        migrations layer quotes this via ``dialect.quote_identifier`` — we
        still validate here so the call site fails loudly if someone
        constructs a FeatureSchema with a bogus name.
    version:
        Monotonic integer. Callers bump this to force a new registry row
        on semantic changes.
    fields:
        Ordered list of :class:`FeatureField`. At least one field is
        required; names within a schema must be unique.
    entity_id_column:
        Primary entity key (e.g. ``user_id``). Defaults to ``"entity_id"``.
    timestamp_column:
        Optional event-time column used by point-in-time joins (``as_of``).
    """

    name: str
    version: int = 1
    fields: tuple[FeatureField, ...] = ()
    entity_id_column: str = "entity_id"
    timestamp_column: str | None = None

    # Derived, deterministic
    content_hash: str = _dc_field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        _validate_name(self.name, label="FeatureSchema.name")
        if not isinstance(self.version, int) or isinstance(self.version, bool):
            raise TypeError(
                f"FeatureSchema.version must be int, got "
                f"{type(self.version).__name__}"
            )
        if self.version < 1:
            raise ValueError(f"FeatureSchema.version must be >= 1, got {self.version}")

        # Normalise `fields` to a tuple of FeatureField — accept list at input time
        if isinstance(self.fields, list):
            object.__setattr__(self, "fields", tuple(self.fields))
        if not self.fields:
            raise ValueError("FeatureSchema.fields must contain at least one field")
        for f in self.fields:
            if not isinstance(f, FeatureField):
                raise TypeError(
                    f"FeatureSchema.fields must contain FeatureField instances, "
                    f"got {type(f).__name__}"
                )
        seen: set[str] = set()
        for f in self.fields:
            if f.name in seen:
                raise ValueError(
                    f"FeatureSchema.fields contains duplicate field name "
                    f"(fingerprint={hash(f.name) & 0xFFFF:04x})"
                )
            seen.add(f.name)

        _validate_name(self.entity_id_column, label="FeatureSchema.entity_id_column")
        if self.timestamp_column is not None:
            _validate_name(
                self.timestamp_column, label="FeatureSchema.timestamp_column"
            )

        # Compute deterministic content hash.
        payload = json.dumps(self._canonical_payload(), sort_keys=True).encode("utf-8")
        object.__setattr__(
            self, "content_hash", hashlib.sha256(payload).hexdigest()[:16]
        )

    def _canonical_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "entity_id_column": self.entity_id_column,
            "timestamp_column": self.timestamp_column,
            "fields": [f.to_dict() for f in self.fields],
        }

    @property
    def field_names(self) -> list[str]:
        """Ordered list of field names (does NOT include entity_id / timestamp)."""
        return [f.name for f in self.fields]

    def to_dict(self) -> dict[str, Any]:
        payload = self._canonical_payload()
        payload["content_hash"] = self.content_hash
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeatureSchema:
        return cls(
            name=data["name"],
            version=int(data.get("version", 1)),
            fields=tuple(FeatureField.from_dict(f) for f in data["fields"]),
            entity_id_column=data.get("entity_id_column", "entity_id"),
            timestamp_column=data.get("timestamp_column"),
        )
