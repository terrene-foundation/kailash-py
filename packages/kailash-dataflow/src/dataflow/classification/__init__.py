# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Data classification and retention policies for DataFlow models.

Provides enums for classification levels, retention policies, and
masking strategies. The ``@classify`` decorator attaches classification
metadata to model fields, and ``ClassificationPolicy`` / ``get_field_classification``
provide runtime lookup.

Usage::

    from dataflow.classification import (
        DataClassification,
        MaskingStrategy,
        RetentionPolicy,
        classify,
        ClassificationPolicy,
        get_field_classification,
    )

    @classify("email", DataClassification.PII, RetentionPolicy.UNTIL_CONSENT_REVOKED, MaskingStrategy.REDACT)
    @classify("name", DataClassification.PII, RetentionPolicy.YEARS_1, MaskingStrategy.REDACT)
    @classify("notes", DataClassification.INTERNAL, RetentionPolicy.INDEFINITE, MaskingStrategy.NONE)
    @dataclass
    class User(DataFlowModel):
        name: str = ""
        email: str = ""
        notes: str = ""

    fc = get_field_classification(User, "email")
    assert fc.classification == DataClassification.PII
"""

from dataflow.classification.policy import (
    ClassificationPolicy,
    FieldClassification,
    classify,
    get_field_classification,
)
from dataflow.classification.types import (
    DataClassification,
    MaskingStrategy,
    RetentionPolicy,
)

__all__ = [
    # Types / enums
    "DataClassification",
    "RetentionPolicy",
    "MaskingStrategy",
    # Policy
    "ClassificationPolicy",
    "FieldClassification",
    "classify",
    "get_field_classification",
]

__version__ = "0.1.0"
