# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``@feature`` decorator — declarative authoring of a derived feature column.

A ``@feature``-decorated function returns a ``polars.Expr``. The decorator is
DECLARATIVE only (``specs/dataflow-ml-integration.md §3.2`` /
``specs/ml-feature-store.md §11.2``): it captures the function, the declared
output dtype, and a content-SHA version of the function body, and binds them
into a :class:`FeatureDefinition`. It performs NO compute at decoration time.

The captured ``polars.Expr`` is applied at materialisation time by
:meth:`kailash_ml.features.feature_group.FeatureGroup.materialize`, which routes
the expression through the shipped ``dataflow.transform`` binding
(``packages/kailash-dataflow/src/dataflow/ml/_transform.py``) so classification
metadata and lineage tagging are preserved. No raw compute, no raw SQL, lives
here (``rules/framework-first.md``).

Per ``rules/orphan-detection.md §6`` the public symbols are eagerly importable
from ``kailash_ml.features`` and listed in its ``__all__``.
"""
from __future__ import annotations

import hashlib
import inspect
from dataclasses import dataclass
from typing import Any, Callable

from kailash_ml.features.schema import _normalise_dtype, _validate_name

__all__ = ["FeatureDefinition", "feature"]


def _content_sha(fn: Callable[..., Any]) -> str:
    """Stable content-SHA of a feature function's source body.

    Two byte-identical function definitions resolve to the same version hash
    (mirrors :class:`FeatureSchema`'s content-addressing contract,
    ``specs/ml-feature-store.md §3``). When the source is unavailable (e.g. a
    C-extension or a dynamically-constructed lambda), fall back to the
    qualified name + module so the hash stays deterministic per definition.
    """
    try:
        raw = inspect.getsource(fn).encode("utf-8")
    except (OSError, TypeError):
        raw = f"{fn.__module__}.{getattr(fn, '__qualname__', fn.__name__)}".encode(
            "utf-8"
        )
    return hashlib.sha256(raw).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    """A single declaratively-authored derived feature column.

    Captures the producing function (returns a ``polars.Expr``), the declared
    output column name + dtype, and a content-addressed version SHA of the
    function body. Frozen + content-addressed so a re-authored definition with
    the same body resolves to the same ``version``.

    Attributes
    ----------
    name:
        Output column identifier. Validated against the SQL-identifier regex
        so it is safe to materialise into a backing table column.
    dtype:
        Polars-native dtype string (normalised via the schema dtype allowlist).
    fn:
        The producing function. Called with NO positional arguments at
        materialisation time; it MUST return a ``polars.Expr``.
    version:
        Content-SHA of ``fn``'s source body (16 hex chars).
    description:
        Free-form human description.
    """

    name: str
    dtype: str
    fn: Callable[..., Any]
    version: str
    description: str = ""

    def expr(self) -> Any:
        """Evaluate the producing function and return its ``polars.Expr``.

        Raises :class:`TypeError` if the function does not return a
        ``polars.Expr`` — a feature definition that does not produce an
        expression cannot be applied via ``dataflow.transform`` (which rejects
        non-``Expr`` inputs at its boundary).
        """
        import polars as pl

        result = self.fn()
        if not isinstance(result, pl.Expr):
            raise TypeError(
                f"@feature {self.name!r} must return a polars.Expr, got "
                f"{type(result).__name__}. See "
                f"specs/dataflow-ml-integration.md §3.2."
            )
        return result


def feature(
    *,
    name: str,
    dtype: str,
    description: str = "",
) -> Callable[[Callable[..., Any]], FeatureDefinition]:
    """Declaratively author a derived feature column.

    The decorated function MUST return a ``polars.Expr``. The decorator stores
    the function + declared ``dtype`` + a content-SHA ``version`` and returns a
    :class:`FeatureDefinition` (the function is NOT called at decoration time —
    materialisation is :class:`FeatureGroup`'s concern, ``specs/ml-feature-store.md
    §11.2``).

    Parameters
    ----------
    name:
        Output column identifier. Validated against
        ``^[a-zA-Z_][a-zA-Z0-9_]*$``.
    dtype:
        Polars-native dtype string (synonyms like ``int`` / ``float`` / ``str``
        normalise to the canonical form via the schema dtype allowlist).
    description:
        Free-form human description stored on the definition.

    Returns
    -------
    Callable producing a :class:`FeatureDefinition` from the wrapped function.

    Example
    -------
        >>> import polars as pl
        >>> @feature(name="amount_log", dtype="float64")
        ... def amount_log() -> pl.Expr:
        ...     return pl.col("amount").log1p()
        >>> amount_log.name
        'amount_log'
        >>> amount_log.dtype
        'float64'
    """
    _validate_name(name, label="@feature.name")
    canonical_dtype = _normalise_dtype(dtype)

    def _wrap(fn: Callable[..., Any]) -> FeatureDefinition:
        if not callable(fn):
            raise TypeError("@feature must decorate a callable")
        version = _content_sha(fn)
        return FeatureDefinition(
            name=name,
            dtype=canonical_dtype,
            fn=fn,
            version=version,
            description=description or (fn.__doc__ or "").strip().split("\n")[0],
        )

    return _wrap
