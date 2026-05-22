# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""kailash.delegate.conformance -- shared conformance vectors with kailash-rs.

Per #1035 F1 invariant: this subpackage MUST have ZERO engine dependencies.
The lint at ``tools/lint-delegate-fences.py`` enforces this; vectors load
from JSON fixtures and validate via dataclass schemas only.

S7 (this shard) ships the behavioural-only conformance schema vendored from
the rs canonical (`crates/kailash-delegate-conformance` per
``rules/cross-sdk-inspection.md`` Rule 4a) PLUS a Fence-B-respecting
dict-shape parity comparator (:func:`receipts_agree_dict`) that engine-callers
feed via the public ``.to_dict()`` method on the runtime engine.
"""

from kailash.delegate.conformance.schema import (
    BehaviouralOutcome,
    ConformanceReceipt,
    ConformanceVector,
    ConformanceVectorIntegrityError,
    ConformanceVectorLoader,
    ReceiptError,
    ReceiptsAgreeReport,
    ReceiptsAgreementError,
    SchemaError,
    SpecAnchor,
    assert_receipts_agree,
    canonical_vector_set_digest,
    receipts_agree,
    receipts_agree_dict,
    validate_vector_set,
)

__all__ = [
    "BehaviouralOutcome",
    "ConformanceReceipt",
    "ConformanceVector",
    "ConformanceVectorIntegrityError",
    "ConformanceVectorLoader",
    "ReceiptError",
    "ReceiptsAgreeReport",
    "ReceiptsAgreementError",
    "SchemaError",
    "SpecAnchor",
    "assert_receipts_agree",
    "canonical_vector_set_digest",
    "receipts_agree",
    "receipts_agree_dict",
    "validate_vector_set",
]
