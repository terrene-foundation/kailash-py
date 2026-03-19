from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
DataFlow SQL Aggregation Query Module

Provides high-level aggregation functions (count_by, sum_by, aggregate)
that generate parameterized SQL GROUP BY queries with strict identifier
validation to prevent SQL injection.

Usage:
    from dataflow.query import count_by, sum_by, aggregate, AggregateOp, AggregateSpec

    # Count users by status
    result = await count_by(connection, "users", "status")

    # Sum amounts by category with a filter
    result = await sum_by(connection, "orders", "amount", "category", {"status": "paid"})

    # Multi-aggregate query
    specs = [
        AggregateSpec(op=AggregateOp.COUNT, field="*"),
        AggregateSpec(op=AggregateOp.SUM, field="amount"),
        AggregateSpec(op=AggregateOp.AVG, field="amount", alias="avg_amount"),
    ]
    result = await aggregate(connection, "orders", specs, group_by="category")
"""

from dataflow.query.aggregation import aggregate, count_by, sum_by
from dataflow.query.models import AggregateOp, AggregateSpec, AggregationResult

__all__ = [
    "count_by",
    "sum_by",
    "aggregate",
    "AggregateOp",
    "AggregateSpec",
    "AggregationResult",
]
