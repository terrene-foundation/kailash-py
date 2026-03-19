from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Aggregation query error hierarchy.

All aggregation errors inherit from AggregationError, which carries a
``details`` dict for structured error context.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

__all__ = ["AggregationError", "AggregationFieldError"]


class AggregationError(Exception):
    """Base error for aggregation query failures.

    Raised when an aggregation query cannot be constructed or executed
    due to invalid parameters, missing tables, or database errors.

    Attributes:
        details: Structured error context for debugging and logging.
    """

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details: Dict[str, Any] = details or {}


class AggregationFieldError(AggregationError):
    """Raised when a requested aggregation field does not exist in the model.

    Attributes:
        field_name: The field that was not found.
        table_name: The table or model that was searched.
    """

    def __init__(
        self,
        field_name: str,
        table_name: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        merged_details: Dict[str, Any] = {
            "field_name": field_name,
            "table_name": table_name,
        }
        if details:
            merged_details.update(details)
        super().__init__(
            f"Aggregation field {field_name!r} not found in table {table_name!r}",
            details=merged_details,
        )
        self.field_name = field_name
        self.table_name = table_name
