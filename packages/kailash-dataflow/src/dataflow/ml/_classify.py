# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``_kml_classify_actions`` — DataFlow classification bridge for kailash-ml.

kailash-ml needs to know, per-column, what action to take during
training and inference:

* ``"allow"``    — the column is unclassified or classified ``PUBLIC``
  and may flow through training / inference unchanged.
* ``"redact"``   — the column is classified with ``MaskingStrategy.REDACT``;
  training MUST exclude the raw column, and inference results MUST NOT
  echo it back.
* ``"hash"``     — classified with ``HASH`` or ``LAST_FOUR``; the ML
  pipeline may use the hashed/tail-truncated form as a feature.
* ``"encrypt"``  — classified with ``ENCRYPT``; the ML pipeline MUST
  call DataFlow's encryption helper before persisting or logging the
  value.

This module is the single consumption point for DataFlow's
``ClassificationPolicy`` from kailash-ml's training path. Placing the
translation here means kailash-ml never imports DataFlow's classification
enums directly — it asks DataFlow "what should I do with this column"
and gets an action string.

The private ``_kml_`` prefix signals this is an internal cross-package
bridge, not a public DataFlow API. Callers outside kailash-ml SHOULD
use :func:`dataflow.classification.policy.get_field_classification`
instead.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional

from dataflow.classification.types import MaskingStrategy

logger = logging.getLogger(__name__)

__all__ = ["_kml_classify_actions"]


def _action_for_masking(masking: MaskingStrategy) -> str:
    """Translate a ``MaskingStrategy`` enum to an action string.

    The mapping is intentionally restrictive — every unknown strategy
    falls through to ``"redact"`` (the safest default) rather than
    ``"allow"``. This way a future new strategy that kailash-ml hasn't
    seen produces a loud behavioral signal (training excludes the
    column) rather than a silent leak (training includes the raw
    classified value).
    """
    if masking is MaskingStrategy.NONE:
        return "allow"
    if masking is MaskingStrategy.REDACT:
        return "redact"
    if masking is MaskingStrategy.HASH:
        return "hash"
    if masking is MaskingStrategy.LAST_FOUR:
        return "hash"
    if masking is MaskingStrategy.ENCRYPT:
        return "encrypt"
    # Unknown strategy — fail safe.
    return "redact"


def _kml_classify_actions(
    policy: "Optional[Any]",
    model_name: str,
    columns: Iterable[str],
) -> Dict[str, str]:
    """Return an ``{column: action}`` map for the given model and columns.

    Args:
        policy: The ``ClassificationPolicy`` from
            ``db.classification_policy`` (spec § 3.3). ``None`` means
            no classifications are registered — every column gets
            ``"allow"``.
        model_name: DataFlow model name (e.g. ``"User"``).
        columns: Iterable of column names the caller intends to use.

    Returns:
        A dict mapping every input column to exactly one of
        ``"allow"`` / ``"redact"`` / ``"hash"`` / ``"encrypt"``.
    """
    actions: Dict[str, str] = {}

    if policy is None:
        for column in columns:
            actions[column] = "allow"
        return actions

    get_field = getattr(policy, "get_field", None)
    if not callable(get_field):
        logger.debug(
            "kml_classify_actions.policy_missing_get_field",
            extra={"policy_type": type(policy).__name__},
        )
        for column in columns:
            actions[column] = "allow"
        return actions

    for column in columns:
        try:
            field_classification = get_field(model_name, column)
        except Exception:
            # A misconfigured policy MUST NOT make the ML bridge silent;
            # fail safe to "redact" so the column is excluded from
            # training rather than passed through raw.
            logger.debug(
                "kml_classify_actions.policy_lookup_failed",
                extra={"model": model_name, "column_count": 1},
            )
            actions[column] = "redact"
            continue

        if field_classification is None:
            actions[column] = "allow"
            continue

        masking = getattr(field_classification, "masking", None)
        if not isinstance(masking, MaskingStrategy):
            actions[column] = "redact"
            continue

        actions[column] = _action_for_masking(masking)

    return actions
