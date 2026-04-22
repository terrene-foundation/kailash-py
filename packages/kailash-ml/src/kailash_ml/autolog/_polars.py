# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""polars schema-fingerprint autolog integration (W23.g).

Implements ``specs/ml-autolog.md §3.1`` row 7 + Phase-B SAFE-DEFAULT
A-04:

- **Passive** integration — does NOT monkey-patch any polars method.
  Per Phase-B A-04, hooking ``DataFrame.to_torch()`` /
  ``DataFrame.to_numpy()`` sites is explicitly BLOCKED (too invasive
  and changes polars call semantics). Instead this integration
  exposes a public helper :func:`log_dataframe_fingerprint` that
  users call inside ``km.autolog()`` to emit the spec's three params:
    * ``polars.schema_fingerprint_sha256`` — stable hash over
      ``(column_name, dtype_str)`` pairs, sorted by column name, so
      the fingerprint is column-order-independent.
    * ``polars.row_count`` — integer row count.
    * ``polars.column_count`` — integer column count.

Sibling integrations (sklearn / lightgbm / xgboost) that observe a
polars DataFrame on their training-data surface MAY opt-in by
calling :func:`log_dataframe_fingerprint` when the
:attr:`AutologConfig.log_datasets` flag is True. This hook surface is
scaffolded by the registration side-effect of this module; real
piping from sibling integrations is a W23.h follow-up.

Per ``rules/orphan-detection.md`` §1, this module's registration
site is ``kailash_ml/autolog/__init__.py`` which eagerly imports
this module. The production call site is the CM's auto-detect +
explicit-name resolver AND :func:`log_dataframe_fingerprint`
invoked by user code OR sibling integrations.

Framework imports (``polars``) are deferred to helper invocation so
importing this module does NOT pull polars into ``sys.modules``.
The auto-detect path is preserved for users who never
``import polars``.
"""
from __future__ import annotations

import hashlib
import logging
import sys
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional

from kailash_ml.autolog._distribution import is_main_process
from kailash_ml.autolog._registry import (
    FrameworkIntegration,
    register_integration,
)

if TYPE_CHECKING:
    from kailash_ml.autolog.config import AutologConfig
    from kailash_ml.tracking import ExperimentRun


__all__ = [
    "PolarsIntegration",
    "compute_dataframe_fingerprint",
    "log_dataframe_fingerprint",
]


logger = logging.getLogger(__name__)


def compute_dataframe_fingerprint(df: Any) -> Dict[str, Any]:
    """Compute the three spec params for a polars DataFrame.

    Returns a dict with keys::

        polars.schema_fingerprint_sha256: str  # sha256:XXXXXXXXXXXXXXXX (16 hex)
        polars.row_count:                int
        polars.column_count:             int

    Column-order-independent: the fingerprint is SHA-256 over the
    sorted ``(column_name, dtype_str)`` pairs, so a rename or
    re-order of columns produces a different fingerprint, but a
    permutation of column ORDER (without rename) does NOT.

    Raises no exceptions — returns an empty dict on probe failure.
    """
    try:
        schema = df.schema
        columns = getattr(df, "columns", None) or list(schema.keys())
    except Exception:
        logger.debug("autolog.polars.schema_probe_failed")
        return {}

    try:
        # Sort by column name for order-independent fingerprint.
        pairs = sorted((str(name), str(schema[name])) for name in columns)
        h = hashlib.sha256()
        for name, dtype in pairs:
            h.update(name.encode("utf-8"))
            h.update(b"\x00")  # delimiter so "ab|c" ≠ "a|bc"
            h.update(dtype.encode("utf-8"))
            h.update(b"\x01")
        fingerprint = f"sha256:{h.hexdigest()[:16]}"
    except Exception:
        logger.debug("autolog.polars.fingerprint_hash_failed")
        return {}

    try:
        row_count = int(df.height)
    except Exception:
        try:
            row_count = int(len(df))
        except Exception:
            row_count = -1

    try:
        column_count = int(df.width)
    except Exception:
        column_count = len(columns) if columns else -1

    return {
        "polars.schema_fingerprint_sha256": fingerprint,
        "polars.row_count": row_count,
        "polars.column_count": column_count,
    }


async def log_dataframe_fingerprint(run: "ExperimentRun", df: Any) -> None:
    """Emit the spec's three polars fingerprint params onto ``run``.

    No-op on non-main-process workers per §3.3 — multi-axis rank gate
    via :func:`kailash_ml.autolog._distribution.is_main_process`.
    """
    if not is_main_process():
        return
    fp = compute_dataframe_fingerprint(df)
    if not fp:
        return
    # Coerce int values to repr for the params table (params are
    # stored as strings; log_params accepts Any and stringifies).
    payload = {
        "polars.schema_fingerprint_sha256": fp["polars.schema_fingerprint_sha256"],
        "polars.row_count": repr(fp["polars.row_count"]),
        "polars.column_count": repr(fp["polars.column_count"]),
    }
    try:
        await run.log_params(payload)
    except Exception:
        logger.exception("autolog.polars.fingerprint_emit_failed")


@register_integration
class PolarsIntegration(FrameworkIntegration):
    """Passive polars fingerprint integration.

    Attach is a no-op — the integration exposes
    :func:`log_dataframe_fingerprint` for user code and sibling
    integrations to call directly. Detach is also a no-op; there's
    nothing to restore.

    Registered so ``km.autolog("polars")`` is a valid explicit-name
    selection (§4.2) and so ``handle.attached_integrations``
    advertises polars presence for user introspection.
    """

    name = "polars"

    def __init__(self) -> None:
        super().__init__()
        self._run: Optional["ExperimentRun"] = None
        self._config: Optional["AutologConfig"] = None

    @classmethod
    def is_available(cls) -> bool:
        return "polars" in sys.modules

    def attach(self, run: "ExperimentRun", config: "AutologConfig") -> None:
        self._guard_double_attach()
        self._run = run
        self._config = config
        logger.info(
            "autolog.polars.attach",
            extra={"run_id": run.run_id},
        )

    def detach(self) -> None:
        self._run = None
        self._config = None
        self._mark_detached()

    async def flush(self, run: "ExperimentRun") -> None:
        # Passive integration — nothing buffered.
        return None
