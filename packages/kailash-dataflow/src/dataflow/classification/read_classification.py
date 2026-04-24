# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Public helper for applying read-time classification masking to records.

This module exposes :func:`apply_read_classification` as the canonical
module-level function for masking classified fields on a record based on
the caller's clearance. The helper is the public form of the private
``ClassificationPolicy.apply_masking_to_record`` and is the single
enforcement point mandated by ``rules/dataflow-classification.md`` for
every mutation return-path (``create``, ``update``, ``upsert``,
``bulk_create``, ``bulk_upsert``).

Cross-SDK parity: the Rust binding at ``bindings/kailash-python/src/dataflow.rs``
(kailash-rs PR #580) exposes the equivalent ``apply_read_classification``
entry via PyO3. Both SDKs produce identical masked output for the same
``(fields, record, caller_clearance)`` triple.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from dataflow.classification.policy import ClassificationPolicy, FieldClassification
from dataflow.classification.types import DataClassification, MaskingStrategy

__all__ = ["apply_read_classification"]


def apply_read_classification(
    fields: Dict[str, FieldClassification],
    record: Any,
    caller_clearance: Optional[DataClassification] = None,
) -> Any:
    """Apply read-time classification masking to a record in-place.

    Walks ``fields`` and, for every field the caller cannot access,
    replaces the value in ``record`` with the result of the field's
    masking strategy. Fields with ``MaskingStrategy.NONE`` are masked
    with ``MaskingStrategy.REDACT`` when the caller is below the
    required clearance.

    Args:
        fields: Mapping of field name to :class:`FieldClassification`.
            Typically obtained from ``ClassificationPolicy.get_model_fields(model_name)``.
        record: The record dict to mask. Non-dict inputs pass through
            unchanged. Mutation is in-place; the same dict is also
            returned so callers may chain or ignore the return value.
        caller_clearance: The caller's clearance. When ``None``, the
            current thread's clearance is read from
            :func:`dataflow.core.agent_context.get_current_clearance`.
            If no ambient clearance is set, the caller is treated as
            ``PUBLIC`` (the most restrictive).

    Returns:
        The same ``record`` dict (mutated), or the original input
        unchanged if ``record`` is not a dict or ``fields`` is empty.

    Example:
        >>> from dataflow.classification import (
        ...     DataClassification, FieldClassification, MaskingStrategy,
        ...     RetentionPolicy, apply_read_classification,
        ... )
        >>> fields = {
        ...     "ssn": FieldClassification(
        ...         DataClassification.PII,
        ...         RetentionPolicy.INDEFINITE,
        ...         MaskingStrategy.REDACT,
        ...     ),
        ... }
        >>> record = {"name": "Alice", "ssn": "123-45-6789"}
        >>> apply_read_classification(fields, record, DataClassification.PUBLIC)
        {'name': 'Alice', 'ssn': '[REDACTED]'}
    """
    if not isinstance(record, dict):
        return record
    if not fields:
        return record

    if caller_clearance is None:
        from dataflow.core.agent_context import get_current_clearance

        caller_clearance = get_current_clearance()

    effective_clearance = caller_clearance or DataClassification.PUBLIC

    for field_name, fc in fields.items():
        if field_name not in record:
            continue
        if ClassificationPolicy.caller_can_access(
            fc.classification, effective_clearance
        ):
            continue
        strategy = (
            fc.masking if fc.masking != MaskingStrategy.NONE else MaskingStrategy.REDACT
        )
        record[field_name] = ClassificationPolicy.apply_masking_strategy(
            record[field_name], strategy
        )
    return record
