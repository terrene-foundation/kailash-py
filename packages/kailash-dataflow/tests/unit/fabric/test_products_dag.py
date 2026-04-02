# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for product DAG topological ordering (TODO-34)."""

from __future__ import annotations

import pytest

from dataflow.fabric.config import ProductMode, RateLimit, StalenessPolicy
from dataflow.fabric.products import (
    ProductRegistration,
    get_cascade_order,
    topological_order,
)


def _reg(name: str, depends_on: list) -> ProductRegistration:
    async def _fn(ctx):
        return {}

    return ProductRegistration(
        name=name,
        fn=_fn,
        mode=ProductMode.MATERIALIZED,
        depends_on=depends_on,
        staleness=StalenessPolicy(),
        rate_limit=RateLimit(),
    )


class TestTopologicalOrder:
    def test_simple_chain(self):
        products = {
            "a": _reg("a", ["User"]),
            "b": _reg("b", ["a"]),
            "c": _reg("c", ["b"]),
        }
        order = topological_order(products)
        assert order.index("a") < order.index("b")
        assert order.index("b") < order.index("c")

    def test_independent_products(self):
        products = {
            "x": _reg("x", ["User"]),
            "y": _reg("y", ["Task"]),
        }
        order = topological_order(products)
        assert set(order) == {"x", "y"}

    def test_diamond_dependency(self):
        products = {
            "base": _reg("base", ["User"]),
            "left": _reg("left", ["base"]),
            "right": _reg("right", ["base"]),
            "top": _reg("top", ["left", "right"]),
        }
        order = topological_order(products)
        assert order.index("base") < order.index("left")
        assert order.index("base") < order.index("right")
        assert order.index("left") < order.index("top")
        assert order.index("right") < order.index("top")

    def test_circular_dependency_raises(self):
        products = {
            "a": _reg("a", ["b"]),
            "b": _reg("b", ["a"]),
        }
        with pytest.raises(ValueError, match="Circular"):
            topological_order(products)

    def test_empty_products(self):
        assert topological_order({}) == []


class TestCascadeOrder:
    def test_direct_dependency(self):
        products = {
            "dashboard": _reg("dashboard", ["crm"]),
            "report": _reg("report", ["User"]),
        }
        affected = get_cascade_order(products, "crm")
        assert affected == ["dashboard"]

    def test_transitive_cascade(self):
        products = {
            "base": _reg("base", ["crm"]),
            "summary": _reg("summary", ["base"]),
        }
        affected = get_cascade_order(products, "crm")
        assert affected.index("base") < affected.index("summary")

    def test_no_affected_products(self):
        products = {
            "dashboard": _reg("dashboard", ["User"]),
        }
        assert get_cascade_order(products, "crm") == []
