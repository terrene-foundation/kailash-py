# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Data classification enums.

All enums are ``str``-backed for JSON-friendly serialization, following
the Kailash SDK convention (see ``.claude/rules/eatp.md``).
"""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)

__all__ = [
    "DataClassification",
    "RetentionPolicy",
    "MaskingStrategy",
]


class DataClassification(str, Enum):
    """Sensitivity level of a data field.

    Ordered from least to most sensitive. Higher sensitivity levels
    require stricter retention, masking, and access controls.
    """

    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    PII = "pii"
    GDPR = "gdpr"
    HIGHLY_CONFIDENTIAL = "highly_confidential"


class RetentionPolicy(str, Enum):
    """How long classified data should be retained.

    Policies map to concrete durations at the infrastructure layer.
    ``UNTIL_CONSENT_REVOKED`` is used for GDPR-subject data where
    the data subject controls the retention window.
    """

    INDEFINITE = "indefinite"
    DAYS_30 = "days_30"
    DAYS_90 = "days_90"
    YEARS_1 = "years_1"
    YEARS_7 = "years_7"
    UNTIL_CONSENT_REVOKED = "until_consent_revoked"


class MaskingStrategy(str, Enum):
    """How a field value should be masked when displayed or exported.

    ``NONE`` means no masking — the value is shown as-is. All other
    strategies obscure the original value to varying degrees.
    """

    NONE = "none"
    HASH = "hash"
    REDACT = "redact"
    LAST_FOUR = "last_four"
    ENCRYPT = "encrypt"
