# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``dataflow.hash`` — stable content hash for lineage provenance.

Returns ``"sha256:<64hex>"``. Consumed by
``ModelRegistry.register_version(lineage_dataset_hash=...)`` as the
mandatory lineage field (spec § 4.4).

The full 64-hex form is intentionally distinct from the 8-hex short form
used for event-payload fingerprints (see
``rules/event-payload-classification.md`` § 2). Lineage needs full
collision resistance because the hash indexes the registry; event
fingerprints only need forensic correlation.
"""

from __future__ import annotations

import hashlib
import io
from typing import Any, Union

from dataflow.ml._errors import LineageHashError

__all__ = ["hash"]


def _canonicalize_frame(df: "Any") -> "Any":
    """Sort columns ascending, then sort rows by all columns ascending.

    Two semantically-equal frames (same rows, same values) produce the
    same canonical byte stream regardless of insertion order. Column
    dtype changes DO change the hash because dtype is part of the
    schema.
    """
    # Delayed import so users on kailash-dataflow that never touch the ML
    # module don't pay the polars import cost.
    import polars as pl  # noqa: F401

    sorted_cols = sorted(df.columns)
    df = df.select(sorted_cols)
    # Sort by ALL columns ascending — deterministic for non-null values.
    # When the caller has null cells this produces a well-defined order
    # because polars' sort puts nulls at the end by default.
    try:
        df = df.sort(by=sorted_cols)
    except Exception as exc:  # pragma: no cover — sort failures surface here
        raise LineageHashError(
            f"dataflow.hash(stable=True) could not sort frame: {exc!r}. "
            "If your frame contains unhashable dtypes (nested Python objects, "
            "unsorted dicts), call stable=False or pre-canonicalize the rows."
        ) from exc
    return df


def hash(
    df: Any,
    *,
    algorithm: str = "sha256",
    stable: bool = True,
) -> str:
    """Return a stable content hash of a polars DataFrame or LazyFrame.

    Args:
        df: A ``polars.DataFrame`` or ``polars.LazyFrame``. LazyFrames
            are collected before hashing.
        algorithm: Hash algorithm. Only ``"sha256"`` is supported in
            2.1.0. Any other value raises :class:`LineageHashError`
            immediately — supporting other algorithms would defeat the
            cross-SDK parity contract (spec § 7) because kailash-rs
            emits SHA-256 in the same canonical form.
        stable: When ``True`` (default), canonicalize column and row
            order before hashing. When ``False``, hash the frame's
            Arrow IPC stream as-is — faster, but order-sensitive. Use
            only when upstream already guarantees canonical order.

    Returns:
        ``"sha256:<64 hex chars>"``.

    Raises:
        LineageHashError: If ``algorithm`` is unsupported, if the frame
            contains dtypes that cannot be canonicalized, or if polars
            cannot serialize the frame to an Arrow IPC stream.
    """
    if algorithm != "sha256":
        raise LineageHashError(
            f"dataflow.hash: unsupported algorithm {algorithm!r}. "
            "Only 'sha256' is supported in 2.1.0 (cross-SDK parity contract)."
        )

    try:
        import polars as pl
    except ImportError as exc:  # pragma: no cover — polars is a hard dep of dataflow
        raise LineageHashError(
            "dataflow.hash requires polars — install kailash-dataflow>=2.1.0."
        ) from exc

    # Accept both DataFrame and LazyFrame.
    if isinstance(df, pl.LazyFrame):
        try:
            frame = df.collect()
        except Exception as exc:
            raise LineageHashError(
                f"dataflow.hash could not collect LazyFrame: {exc!r}"
            ) from exc
    elif isinstance(df, pl.DataFrame):
        frame = df
    else:
        raise LineageHashError(
            "dataflow.hash requires polars.DataFrame or polars.LazyFrame; got "
            f"{type(df).__name__}"
        )

    if stable:
        frame = _canonicalize_frame(frame)

    # Serialize to Arrow IPC stream — the canonical cross-language byte
    # form. kailash-rs emits the identical stream for the same
    # canonicalized frame, so hashes match byte-for-byte across SDKs.
    buf = io.BytesIO()
    try:
        frame.write_ipc(buf)
    except Exception as exc:
        raise LineageHashError(
            f"dataflow.hash could not write frame to Arrow IPC: {exc!r}"
        ) from exc

    digest = hashlib.sha256(buf.getvalue()).hexdigest()
    return f"sha256:{digest}"
