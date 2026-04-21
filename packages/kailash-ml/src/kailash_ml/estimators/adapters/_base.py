# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared base for Lightning adapters (W9 §E3 invariant enforcement).

Per W9 DoD + analyst FP-MED-5, four parallel adapter sub-shards MUST
NOT each own the same invariants (NaN/Inf validation, family_name
presence, to_lightning_module contract). The base file enforces those
invariants in ONE place so drift between siblings is structurally
impossible.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Protocol, runtime_checkable

from kailash_ml.errors import ParamValueError

__all__ = [
    "LightningAdapterBase",
    "validate_hyperparameters",
]


def validate_hyperparameters(
    hyperparameters: Mapping[str, Any] | None,
    *,
    family: str,
) -> Mapping[str, Any]:
    """Reject NaN / Inf / non-numeric coerce-fails in numeric hyperparameters.

    Per W9 invariant 6: NaN/Inf hyperparameters → ``ParamValueError``.
    Non-numeric values pass through untouched (e.g. ``criterion="gini"``
    is a valid sklearn hyperparameter).

    Args:
        hyperparameters: raw hyperparameter dict from the caller. ``None``
            is treated as an empty dict (per ml-engines.md §3.2 default).
        family: the adapter's ``family_name`` for inclusion in error
            messages so the user can tell which adapter rejected the value.

    Returns:
        The validated hyperparameter mapping (unchanged on success).

    Raises:
        ParamValueError: when any numeric hyperparameter is NaN or +/-Inf.
    """
    hp = dict(hyperparameters or {})
    for key, value in hp.items():
        # Only numeric types undergo finiteness check; strings / bools /
        # enums pass through.
        if isinstance(value, bool):
            continue  # bool is a subclass of int; skip it explicitly
        if isinstance(value, (int, float)):
            try:
                fvalue = float(value)
            except (TypeError, ValueError) as exc:
                raise ParamValueError(
                    reason=(
                        f"{family}: hyperparameter {key!r}={value!r} cannot "
                        f"be coerced to float."
                    ),
                    family=family,
                    param=key,
                ) from exc
            if not math.isfinite(fvalue):
                raise ParamValueError(
                    reason=(
                        f"{family}: hyperparameter {key!r}={value!r} is not "
                        f"finite (NaN/Inf rejected at construction time per "
                        f"W9 invariant 6)."
                    ),
                    family=family,
                    param=key,
                )
    return hp


@runtime_checkable
class LightningAdapterBase(Protocol):
    """Runtime-checkable protocol every Lightning adapter satisfies.

    Per ml-engines-v2.md §3.2 MUST 1-5, every non-RL family adapter
    MUST:

    * Expose a string ``family_name`` class attribute (W9 invariant 7).
    * Return a LightningModule from ``to_lightning_module()`` so the
      MLEngine fit path routes through ``L.Trainer`` (W9 invariant 1).
    * Validate its hyperparameters at construction time (enforced by
      sub-classes via :func:`validate_hyperparameters`; the base
      Protocol does not prescribe a constructor signature).
    """

    family_name: str

    def to_lightning_module(self) -> Any: ...

    def get_param_distribution(self) -> Any: ...
